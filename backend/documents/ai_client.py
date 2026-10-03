"""
Thin client for calling the FastAPI AI service from Django.

Centralizing this here means every call automatically includes the
internal shared-secret header, and nowhere else in the codebase has to
remember to add it.
"""
import os
import time

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


# On a free hosting tier, the AI service's own server can be fully asleep
# after inactivity. The FIRST request to wake it can get an immediate 502
# from the host's own proxy (returned before the app has even started
# listening), rather than being queued until it's ready. Retrying a couple
# of times with a short wait is what papers over this — by the second or
# third attempt, the service is reliably awake. This has nothing to do
# with request correctness; it's purely about giving a cold host time to
# finish booting.
_WAKE_UP_RETRIES = 3
_WAKE_UP_DELAY_SECONDS = 8


def _post_with_wakeup_retry(url: str, **kwargs) -> requests.Response:
    last_exc = None
    for attempt in range(_WAKE_UP_RETRIES):
        try:
            response = requests.post(url, **kwargs)
            if response.status_code == 502 and attempt < _WAKE_UP_RETRIES - 1:
                time.sleep(_WAKE_UP_DELAY_SECONDS)
                continue
            return response
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < _WAKE_UP_RETRIES - 1:
                time.sleep(_WAKE_UP_DELAY_SECONDS)
                continue
    raise last_exc


def trigger_document_processing(document_id: int, user_id: int, file_path: str, file_type: str, document_name: str):
    """Send the document to the AI service to extract text, chunk it,
    embed it, and store it.

    The file's BYTES are uploaded, not just its path: in production Django
    and the AI service run on separate servers with separate disks, so a
    path that exists here would not exist there. (Locally they share a
    machine, which is why passing a path used to work and hid this.)

    We pass user_id explicitly because Django is the source of truth for
    identity — FastAPI trusts this value ONLY because it arrives over this
    internal, key-protected channel, never from a public request.
    """
    with open(file_path, "rb") as fh:
        response = _post_with_wakeup_retry(
            f"{settings.FASTAPI_BASE_URL}/internal/process-document",
            data={
                "document_id": document_id,
                "user_id": user_id,
                "file_type": file_type,
                "document_name": document_name,
            },
            files={"file": (os.path.basename(file_path), fh, "application/octet-stream")},
            headers=_headers(),
            timeout=600,  # embedding a long document one chunk at a time can be slow
        )
    _raise_with_body(response)
    return response.json()


def trigger_document_deletion(document_id: int, user_id: int):
    """Tells the AI service to delete this document's chunks/embeddings.
    Called before/alongside deleting the Document row in Django."""
    response = _post_with_wakeup_retry(
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
    response = _post_with_wakeup_retry(
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

    Uses the same wake-up retry as the other calls, but only for the
    INITIAL connection attempt — once the stream actually starts, there's
    real content to lose, so no retry happens mid-stream.
    """
    response = _post_with_wakeup_retry(
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
    document. Generous timeout, since this is the heaviest LLM call in the app."""
    response = _post_with_wakeup_retry(
        f"{settings.FASTAPI_BASE_URL}/internal/study-materials",
        json={"document_id": document_id, "user_id": user_id},
        headers=_headers(),
        timeout=900,
    )
    _raise_with_body(response)
    return response.json()
