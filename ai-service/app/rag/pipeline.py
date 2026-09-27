"""
Orchestrates the two main flows: processing an uploaded document, and
answering a question. This is the module the API routes call — it
doesn't know about HTTP, just the actual RAG logic.
"""
import json
import re
from app.loaders.document_loader import load_document
from app.loaders.chunker import chunk_pages
from app.embeddings.embedder import embed_texts, embed_query
from app.retrieval.vector_store import (
    store_chunks, delete_document_chunks, search_similar_chunks, get_all_chunks_for_document,
)
from app.llm.client import (
    generate_answer, generate_answer_stream, generate_study_material, rewrite_query,
    answer_from_history, answer_from_history_stream,
    SYSTEM_PROMPT, build_comparison_system_prompt,
)
from app.core.config import settings

# Hard ceiling on how many source citations are ever shown for a single
# chat answer, independent of top_k/distance tuning above. Comparison mode
# is exempt (see _dedupe_sources) since it deliberately needs one from
# each document.
MAX_DISPLAYED_SOURCES = 5

# Deliberately deterministic, NOT LLM-judged. Only skip document search
# when EVERY word in the message is a known filler/acknowledgment word AND
# the message is short — see stream_answer's docstring for why an LLM was
# not trusted to make this specific call. Broadened after a real miss:
# "thanks for your help" wasn't caught because "for"/"your"/"help" weren't
# in the list, so it fell through to document search. Also raised the
# word-count ceiling from 6 to 10 so slightly longer polite phrases
# ("thank you so much for your help") still qualify — still bounded and
# safe, since every single word must still be a filler word regardless of
# how high the ceiling is.
_ACK_WORDS = {
    "ok", "okay", "okey", "alright", "fine", "sure", "cool", "great", "nice",
    "its", "it's", "is", "no", "worry", "worries", "problem", "problems",
    "thanks", "thank", "you", "your", "for", "got", "understood", "noted",
    "all", "good", "np", "yep", "yes", "help", "helping", "helpful",
    "much", "so", "very", "really", "appreciate", "appreciated",
    "appreciation", "awesome", "perfect", "job", "assist", "assistance",
    "it's", "a", "lot",
}

# Also deterministic and deliberately narrow: specific phrasings for
# "meta" questions about the conversation itself (what did I ask, what did
# you say, repeat that, etc.) rather than about the documents. Without
# this, a question like "what was my previous question?" fell through to
# normal document search and the model fabricated a document-flavored
# answer to something that was never about the documents at all.
_META_CONVERSATION_PATTERNS = [
    # "pr\w*vious" instead of a literal "previous" tolerates the common typo
    # "privious" (and similar single-vowel slips) without needing a full
    # spell-checker — a narrow, targeted fix for a demonstrated real case,
    # not a general typo-correction system.
    r"\bwhat (was|is) my (pr\w*vious|last|first|earlier) (question|message)\b",
    r"\bwhat did i (just |previously |earlier )?(ask|say|type|write)\b",
    r"\bwhat did you (just |previously |earlier )?(say|answer|respond|reply)\b",
    r"\bcan you (repeat|remind me)\b",
    r"\bwhat (have|did) we (talk|discuss)(ed)? about\b",
    r"\b(summarize|recap) (this|our) conversation\b",
]
_META_CONVERSATION_RE = [re.compile(p) for p in _META_CONVERSATION_PATTERNS]


def process_document(document_id: int, user_id: int, file_path: str, file_type: str, document_name: str) -> dict:
    """
    Document -> text extraction -> chunking -> embeddings -> vector DB.
    Returns metadata (page/chunk counts) for Django to store.
    """
    pages = load_document(file_path, file_type)
    chunks = chunk_pages(pages)

    if not chunks:
        return {"page_count": len(pages), "chunk_count": 0}

    embeddings = embed_texts([c["content"] for c in chunks])
    store_chunks(user_id, document_id, document_name, chunks, embeddings)

    return {"page_count": len(pages), "chunk_count": len(chunks)}


def remove_document(document_id: int, user_id: int):
    delete_document_chunks(user_id, document_id)


def _extract_json(raw_text: str) -> dict:
    """
    Local models frequently ignore "respond with ONLY JSON" and wrap the
    answer in markdown code fences or add a stray sentence before/after.
    This pulls out the first {...} block and parses that, rather than
    failing outright on a technically-correct-but-decorated response.
    """
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in the model's response.")
    return json.loads(match.group(0))


def _is_pure_acknowledgment(message: str) -> bool:
    text = re.sub(r"[^\w\s']", "", message.strip().lower())
    words = text.split()
    if not words or len(words) > 10:
        return False
    return all(w in _ACK_WORDS for w in words)


def _is_meta_conversation_question(message: str) -> bool:
    text = message.strip().lower()
    return any(pattern.search(text) for pattern in _META_CONVERSATION_RE)


def _dedupe_sources(chunks: list[dict], limit: int | None = None) -> list[dict]:
    """
    De-duplicates chunks down to one entry per (document, page) — multiple
    chunks can come from the same page. `limit`, when given, caps the
    result to the N most-relevant entries (chunks arrive pre-sorted by
    distance ascending from search_similar_chunks, so keeping the first N
    after dedup keeps the closest matches).
    """
    sources = [
        {"document_id": c["document_id"], "document_name": c["document_name"], "page_number": c["page_number"]}
        for c in chunks
    ]
    seen = set()
    unique = []
    for s in sources:
        key = (s["document_id"], s["page_number"])
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique[:limit] if limit else unique


def _retrieve_for_chat(user_id: int, search_question: str, document_ids: list[int]) -> list[dict]:
    """Normal Q&A retrieval: top_k chunks ranked across ALL selected documents together."""
    query_embedding = embed_query(search_question)
    chunks = search_similar_chunks(user_id, document_ids, query_embedding, top_k=settings.top_k)
    return [c for c in chunks if c["distance"] <= settings.max_chunk_distance]


def _retrieve_for_comparison(user_id: int, search_question: str, document_ids: list[int]) -> list[dict]:
    """
    Comparison retrieval: a fixed number of chunks PER document, fetched
    separately for each one. Without this, a single overall top_k search
    could easily return several chunks all from the same document (if it
    happens to be more semantically similar), leaving nothing to compare
    the other document against — which would defeat the entire point of
    "compare these documents." Fetching per-document guarantees every
    selected document is represented in the context the model sees.
    """
    query_embedding = embed_query(search_question)
    per_doc_k = max(2, settings.top_k // max(len(document_ids), 1))
    all_chunks = []
    for doc_id in document_ids:
        chunks = search_similar_chunks(user_id, [doc_id], query_embedding, top_k=per_doc_k)
        all_chunks.extend(c for c in chunks if c["distance"] <= settings.max_chunk_distance)
    return all_chunks


def _comparison_prompt_for(relevant_chunks: list[dict]) -> str:
    """
    Builds a comparison prompt that names the EXACT documents actually
    retrieved for this question. Naming them explicitly is what lets the
    model be held to a concrete checklist instead of a vague "cover every
    document" instruction it can quietly ignore.
    """
    document_names = list(dict.fromkeys(c["document_name"] for c in relevant_chunks))
    return build_comparison_system_prompt(document_names)


def stream_answer(user_id: int, question: str, document_ids: list[int], history: list[dict], mode: str = "chat"):
    """
    Generator yielding dict events for Server-Sent Events framing:
      {"type": "sources", "sources": [...]}   sent once, before any text
      {"type": "chunk", "content": "..."}      sent repeatedly as text streams in
      {"type": "done"}                         sent once, at the very end
      {"type": "error", "detail": "..."}       sent instead of the above, on failure

    Two short-circuits happen BEFORE any document search, regardless of
    mode (chat or compare) — a message that's just an acknowledgment or a
    question about the conversation itself was never a document question
    in the first place.
    """
    try:
        if _is_pure_acknowledgment(question):
            yield {"type": "sources", "sources": []}
            yield {"type": "chunk", "content": "You're welcome! Let me know if you have any other questions about your documents."}
            yield {"type": "done"}
            return

        if _is_meta_conversation_question(question):
            yield {"type": "sources", "sources": []}
            for piece in answer_from_history_stream(question, history):
                yield {"type": "chunk", "content": piece}
            yield {"type": "done"}
            return

        try:
            search_question = rewrite_query(question, history) or question
        except Exception:
            search_question = question

        if mode == "compare":
            relevant_chunks = _retrieve_for_comparison(user_id, search_question, document_ids)
            system_prompt = _comparison_prompt_for(relevant_chunks)
            sources = _dedupe_sources(relevant_chunks)  # no cap — every document must stay represented
        else:
            relevant_chunks = _retrieve_for_chat(user_id, search_question, document_ids)
            system_prompt = SYSTEM_PROMPT
            sources = _dedupe_sources(relevant_chunks, limit=MAX_DISPLAYED_SOURCES)

        yield {"type": "sources", "sources": sources}

        for piece in generate_answer_stream(search_question, relevant_chunks, history, system_prompt=system_prompt):
            yield {"type": "chunk", "content": piece}

        yield {"type": "done"}
    except Exception as exc:
        yield {"type": "error", "detail": str(exc)}


def answer_question(user_id: int, question: str, document_ids: list[int], history: list[dict], mode: str = "chat") -> dict:
    """
    Non-streaming version of the same flow, kept for any caller that wants
    the whole answer at once (e.g. tests, or a future non-streaming client).
    """
    if _is_pure_acknowledgment(question):
        return {
            "answer": "You're welcome! Let me know if you have any other questions about your documents.",
            "sources": [],
        }

    if _is_meta_conversation_question(question):
        return {"answer": answer_from_history(question, history), "sources": []}

    try:
        search_question = rewrite_query(question, history) or question
    except Exception:
        search_question = question

    if mode == "compare":
        relevant_chunks = _retrieve_for_comparison(user_id, search_question, document_ids)
        system_prompt = _comparison_prompt_for(relevant_chunks)
        sources = _dedupe_sources(relevant_chunks)
    else:
        relevant_chunks = _retrieve_for_chat(user_id, search_question, document_ids)
        system_prompt = SYSTEM_PROMPT
        sources = _dedupe_sources(relevant_chunks, limit=MAX_DISPLAYED_SOURCES)

    answer = generate_answer(search_question, relevant_chunks, history, system_prompt=system_prompt)
    return {"answer": answer, "sources": sources}


def generate_study_materials(user_id: int, document_id: int) -> dict:
    """
    Document -> full text (all chunks, in order) -> ask the LLM for a
    summary + glossary + quiz -> validated, structured result.
    """
    chunks = get_all_chunks_for_document(user_id, document_id)
    if not chunks:
        raise ValueError("This document has no processed content to generate study material from.")

    full_text = "\n\n".join(c["content"] for c in chunks)
    raw_response = generate_study_material(full_text)
    data = _extract_json(raw_response)

    summary = str(data.get("summary", "")).strip()
    key_terms = data.get("key_terms", [])
    quiz = data.get("quiz", [])

    if not isinstance(key_terms, list) or not isinstance(quiz, list):
        raise ValueError("Model response had an unexpected shape for key_terms/quiz.")

    return {"summary": summary, "key_terms": key_terms, "quiz": quiz}
