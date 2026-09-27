"""
Thin client for calling the FastAPI AI service from Django.

Centralizing this here means every call automatically includes the
internal shared-secret header, and nowhere else in the codebase has to
remember to add it.
"""
import requests
from django.conf import settings


def _headers():
    return {"X-Internal-Key": settings.FASTAPI_INTERNAL_KEY}


def _raise_with_body(response):
    """requests' default raise_for_status() message doesn't include the
    response body, which is exactly where FastAPI puts the useful error
    detail. This re-raises with that body included so it actually shows up
    in Django's logs instead of a bare 'HTTPError: 500 Server Error'."""
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(f"{exc} — response body: {response.text}") from exc


def trigger_document_processing(document_id: int, user_id: int, file_path: str, file_type: str, document_name: str):
    """Tell the AI service to extract text, chunk it, embed it, and store it.

    We pass user_id explicitly because Django is the source of truth for
    identity — FastAPI trusts this value ONLY because it arrives over this
    internal, key-protected channel, never from a public request.
    """
    response = requests.post(
        f"{settings.FASTAPI_BASE_URL}/internal/process-document",
        json={
            "document_id": document_id,
            "user_id": user_id,
            "file_path": file_path,
            "file_type": file_type,
            "document_name": document_name,
        },
        headers=_headers(),
        timeout=300,  # local embedding models can be slow — see stream_answer() note below
    )
    _raise_with_body(response)
    return response.json()


def trigger_document_deletion(document_id: int, user_id: int):
    """Tells the AI service to delete this document's chunks/embeddings.
    Called before/alongside deleting the Document row in Django."""
    response = requests.post(
        f"{settings.FASTAPI_BASE_URL}/internal/delete-document",
        json={"document_id": document_id, "user_id": user_id},
        headers=_headers(),
        timeout=30,
    )
    _raise_with_body(response)
    return response.json()


def ask_question(user_id: int, conversation_id: int, question: str, document_ids: list[int], history: list[dict], mode: str = "chat"):
    """Ask the AI service to run RAG + generate an answer for this question
    all at once (non-streaming). Kept for any caller that doesn't need
    streaming; the chat UI itself uses stream_answer() below instead."""
    response = requests.post(
        f"{settings.FASTAPI_BASE_URL}/internal/query",
        json={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "question": question,
            "document_ids": document_ids,
            "history": history,
            "mode": mode,
        },
        headers=_headers(),
        timeout=300,
    )
    _raise_with_body(response)
    return response.json()


def stream_answer(user_id: int, conversation_id: int, question: str, document_ids: list[int], history: list[dict], mode: str = "chat"):
    """
    Opens a streaming connection to the AI service and yields each SSE
    line ("data: {...}") exactly as FastAPI sent it, so Django can proxy
    them straight through to the browser without re-parsing the content.

    Timeout is generous because local models via Ollama run on your CPU
    rather than a fast cloud GPU — the FIRST question after starting
    Ollama is especially slow since it has to load the model into memory
    before it can generate anything at all. A hosted API like OpenAI
    would typically respond in a few seconds.
    """
    response = requests.post(
        f"{settings.FASTAPI_BASE_URL}/internal/query-stream",
        json={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "question": question,
            "document_ids": document_ids,
            "history": history,
            "mode": mode,
        },
        headers=_headers(),
        stream=True,
        timeout=300,
    )
    response.raise_for_status()
    for line in response.iter_lines(decode_unicode=True):
        if line:  # iter_lines already strips the blank SSE separator lines
            yield line


def trigger_study_materials(document_id: int, user_id: int):
    """Ask the AI service to generate a summary/glossary/quiz for a whole
    document.

    This is the single heaviest local-model call in the whole app — it
    reads much more text at once than a normal question, and has to
    generate a much longer, more structured response (summary + terms +
    quiz). On a CPU-only local Ollama setup this can genuinely take
    several minutes, so the timeout here is intentionally much higher
    (15 minutes) than the other calls.
    """
    response = requests.post(
        f"{settings.FASTAPI_BASE_URL}/internal/study-materials",
        json={"document_id": document_id, "user_id": user_id},
        headers=_headers(),
        timeout=900,
    )
    _raise_with_body(response)
    return response.json()
