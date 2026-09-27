"""
Thin wrapper around the LLM provider. Keeping this isolated means
swapping providers later (e.g. OpenAI -> Ollama -> Anthropic) only
touches this one file, not the RAG pipeline logic.
"""
from openai import OpenAI
from app.core.config import settings

_client = OpenAI(api_key=settings.llm_api_key or "ollama", base_url=settings.llm_base_url)

SYSTEM_PROMPT = """You are DocuMind, an AI assistant that answers questions strictly using the provided document excerpts.

Rules:
- Answer ONLY the current question being asked. Do not repeat or reuse a previous answer just because it appears earlier in the conversation — each question is different and deserves its own answer, even if the topic is related.
- Only use information found in the "Document context" section below to answer. Conversation history is there ONLY to help you understand references like "it" or "that" — never treat it as a source of facts to answer from.
- If the document context does not contain information relevant to the CURRENT question, say exactly: "I couldn't find enough information about this in your uploaded documents." Do not guess, and do not fall back on a previous answer.
- Be concise and direct.
- Do not mention that you were given "context" or "chunks" — just answer naturally, as if you'd read the documents yourself.
"""

COMPARISON_SYSTEM_PROMPT = """You are DocuMind, an AI assistant comparing information ACROSS MULTIPLE documents for the user.

Rules:
- The document context below is grouped by document name. Read all of it before answering.
- Structure your answer clearly: briefly cover what each relevant document says, then end with a short "Key differences" (or "Key similarities," whichever fits) section that directly compares them.
- Only use information found in the document context — never guess or fill gaps with general knowledge.
- If a document doesn't contain anything relevant to the question, say so plainly for that document rather than omitting it silently.
- Be concise. Do not mention "context" or "chunks" — refer to documents by name naturally.
"""

HISTORY_ONLY_SYSTEM_PROMPT = """You are DocuMind. The user's latest message is asking about THIS CONVERSATION itself — for example, what they asked earlier, what you said before, or a request to repeat/summarize something already said. It is NOT a question about their uploaded documents.

Answer using ONLY the conversation history below. Do not search for or mention documents, and do not fabricate anything that isn't actually in the history. If the history genuinely doesn't contain what they're asking about (e.g. they're asking about a first message but this is the first message), say so plainly and honestly.

Be concise and natural."""


def build_comparison_system_prompt(document_names: list[str]) -> str:
    """
    Extends COMPARISON_SYSTEM_PROMPT with the EXACT filenames being
    compared, and a hard requirement to address every single one of them
    by name. This exists because the generic instruction above ("cover
    each relevant document... say so if one has nothing relevant") proved
    unreliable on its own with a local model — it would sometimes cite a
    document as a source while never actually discussing it in the
    answer. Naming the files explicitly and demanding a labeled section
    per name gives the model a concrete checklist instead of a vague
    guideline, which is a meaningfully stronger constraint even for a
    weaker model to follow.
    """
    if not document_names:
        return COMPARISON_SYSTEM_PROMPT
    names_list = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(document_names))
    return (
        f"{COMPARISON_SYSTEM_PROMPT}\n\n"
        f"You are comparing EXACTLY these {len(document_names)} documents:\n{names_list}\n\n"
        f"REQUIRED: your answer MUST include one clearly labeled section for EACH document listed "
        f"above, by its exact name, even if that section is just one sentence saying it has nothing "
        f"relevant. Do not skip any of the {len(document_names)} documents listed above."
    )


def _build_messages(question: str, context_chunks: list[dict], history: list[dict], system_prompt: str) -> list[dict]:
    if context_chunks:
        context_text = "\n\n".join(
            f"[Source: {c['document_name']}, page {c.get('page_number') or 'N/A'}]\n{c['content']}"
            for c in context_chunks
        )
    else:
        context_text = "(No relevant document content was found for this specific question.)"

    messages = [{"role": "system", "content": system_prompt}]
    for turn in history[:-1]:  # exclude the current question, added explicitly below
        messages.append({"role": turn["role"] if turn["role"] == "user" else "assistant", "content": turn["content"]})

    messages.append({
        "role": "user",
        "content": (
            f"Document context for THIS question only:\n{context_text}\n\n"
            f"Current question (answer only this): {question}"
        ),
    })
    return messages


def generate_answer(question: str, context_chunks: list[dict], history: list[dict], system_prompt: str = SYSTEM_PROMPT) -> str:
    messages = _build_messages(question, context_chunks, history, system_prompt)
    response = _client.chat.completions.create(model=settings.llm_model, messages=messages, temperature=0.1)
    return response.choices[0].message.content


def generate_answer_stream(question: str, context_chunks: list[dict], history: list[dict], system_prompt: str = SYSTEM_PROMPT):
    """
    Same as generate_answer, but yields the answer piece by piece as the
    model generates it (stream=True), instead of waiting for the whole
    response and returning it all at once. This is what powers the
    word-by-word "typing" effect in the chat UI.
    """
    messages = _build_messages(question, context_chunks, history, system_prompt)
    stream = _client.chat.completions.create(model=settings.llm_model, messages=messages, temperature=0.1, stream=True)
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def _build_history_only_messages(question: str, history: list[dict]) -> list[dict]:
    messages = [{"role": "system", "content": HISTORY_ONLY_SYSTEM_PROMPT}]
    for turn in history[:-1]:  # exclude the current message, sent explicitly below
        messages.append({"role": turn["role"] if turn["role"] == "user" else "assistant", "content": turn["content"]})
    messages.append({"role": "user", "content": question})
    return messages


def answer_from_history(question: str, history: list[dict]) -> str:
    """
    For meta-questions about the conversation itself (e.g. "what was my
    previous question?") — answers using ONLY the conversation history,
    with no document retrieval at all. Without this, such a question would
    fall through to the normal document-search path and the model would
    end up fabricating a document-flavored answer to a question that was
    never about the documents in the first place.
    """
    messages = _build_history_only_messages(question, history)
    response = _client.chat.completions.create(model=settings.llm_model, messages=messages, temperature=0.1)
    return response.choices[0].message.content


def answer_from_history_stream(question: str, history: list[dict]):
    messages = _build_history_only_messages(question, history)
    stream = _client.chat.completions.create(model=settings.llm_model, messages=messages, temperature=0.1, stream=True)
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


QUERY_REWRITE_SYSTEM_PROMPT = """Rewrite the user's latest message into a fully self-contained question, using the conversation history to resolve pronouns or vague references (e.g. "what about its downsides?" -> "What are the downsides of supervised learning?").

If the message is already clear and self-contained, return it completely unchanged.

Respond with ONLY the rewritten question text — no quotes, no explanation, no labels, nothing else."""


def rewrite_query(question: str, history: list[dict]) -> str:
    """
    Turns a possibly-vague follow-up into a clear, standalone question
    before it's embedded and searched. Deliberately does NOT decide
    whether document search should happen at all — that decision is made
    deterministically in the pipeline layer instead, because letting a
    local model make that call proved unreliable: it occasionally
    misclassified genuine document questions as "conversational" and
    skipped search entirely, which is a much worse failure than an
    unnecessary rewrite ever is.
    """
    messages = [{"role": "system", "content": QUERY_REWRITE_SYSTEM_PROMPT}]
    for turn in history[:-1]:  # exclude the current message, sent explicitly below
        messages.append({"role": turn["role"] if turn["role"] == "user" else "assistant", "content": turn["content"]})
    messages.append({"role": "user", "content": f"Latest message: {question}"})

    response = _client.chat.completions.create(model=settings.llm_model, messages=messages, temperature=0.0)
    return response.choices[0].message.content.strip()


STUDY_MATERIAL_SYSTEM_PROMPT = """You are DocuMind's study-material generator. Given the full text of a document, produce study material to help someone learn and review it.

You MUST respond with ONLY valid JSON — no markdown code fences, no explanation before or after, just the raw JSON object. Use exactly this shape:

{
  "summary": "A clear 3-4 sentence summary of the document's main content and purpose.",
  "key_terms": [
    {"term": "Term name", "definition": "One sentence definition based on how it's used in this document."}
  ],
  "quiz": [
    {
      "question": "A question testing understanding of the document.",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_index": 0,
      "explanation": "One short sentence on why this answer is correct."
    }
  ]
}

Rules:
- Generate exactly 5 key_terms and exactly 3 quiz questions. Keep every piece of text as short as the format above shows — this is a fast reference tool, not an essay.
- Base everything strictly on the provided document content — do not invent facts, terms, or quiz answers not supported by the text.
- Quiz options must be plausible (no obviously-wrong joke answers) and exactly one must be correct.
- correct_index is 0-based (0 = first option).
- If the document is too short or unclear to generate real study material, still return the JSON shape, but with as much as you can genuinely support — do not pad with filler.
"""


def generate_study_material(document_text: str) -> str:
    """
    Returns the raw JSON string from the LLM — parsing/validation happens
    in the pipeline layer, since that's where we decide what to do if the
    model returns something malformed (retry, fail, etc).
    """
    max_chars = 6000
    truncated = document_text[:max_chars]

    messages = [
        {"role": "system", "content": STUDY_MATERIAL_SYSTEM_PROMPT},
        {"role": "user", "content": f"Document content:\n\n{truncated}"},
    ]

    response = _client.chat.completions.create(model=settings.llm_model, messages=messages, temperature=0.3)
    return response.choices[0].message.content
