import json
import os
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.security import verify_internal_key
from app.rag.pipeline import (
    process_document, remove_document, answer_question, generate_study_materials, stream_answer,
)

router = APIRouter()

ALLOWED_FILE_TYPES = {"pdf", "txt", "docx"}


class DeleteDocumentRequest(BaseModel):
    document_id: int
    user_id: int


class QueryRequest(BaseModel):
    user_id: int
    conversation_id: int
    question: str
    document_ids: list[int]
    history: list[dict] = []
    mode: str = "chat"  # "chat" (default) or "compare"


class StudyMaterialRequest(BaseModel):
    document_id: int
    user_id: int


@router.post("/internal/process-document", dependencies=[Depends(verify_internal_key)])
def process_document_endpoint(
    document_id: int = Form(...),
    user_id: int = Form(...),
    file_type: str = Form(...),
    document_name: str = Form(""),
    file: UploadFile = File(...),
):
    """
    Receives the document FILE ITSELF (multipart upload) rather than a path
    on Django's disk. Django and this service run as separate servers in
    production, so they don't share a filesystem — a path that exists on
    Django's machine would simply not exist here. The file is written to a
    temporary file just long enough to be processed, then deleted.
    """
    if file_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {file_type}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_type}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        return process_document(
            document_id=document_id,
            user_id=user_id,
            file_path=tmp_path,
            file_type=file_type,
            document_name=document_name or f"document-{document_id}",
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@router.post("/internal/delete-document", dependencies=[Depends(verify_internal_key)])
def delete_document_endpoint(payload: DeleteDocumentRequest):
    remove_document(document_id=payload.document_id, user_id=payload.user_id)
    return {"deleted": True}


@router.post("/internal/query", dependencies=[Depends(verify_internal_key)])
def query_endpoint(payload: QueryRequest):
    return answer_question(
        user_id=payload.user_id,
        question=payload.question,
        document_ids=payload.document_ids,
        history=payload.history,
        mode=payload.mode,
    )


@router.post("/internal/query-stream", dependencies=[Depends(verify_internal_key)])
def query_stream_endpoint(payload: QueryRequest):
    """
    Server-Sent Events version of /internal/query. Each event is a line
    of the form `data: <json>\\n\\n`, with a "type" field the client
    switches on: "sources" (once, first), "chunk" (repeatedly, as text
    generates), "done" (once, last), or "error" instead of the above.
    """
    def event_generator():
        for event in stream_answer(
            user_id=payload.user_id,
            question=payload.question,
            document_ids=payload.document_ids,
            history=payload.history,
            mode=payload.mode,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/internal/study-materials", dependencies=[Depends(verify_internal_key)])
def study_materials_endpoint(payload: StudyMaterialRequest):
    try:
        return generate_study_materials(user_id=payload.user_id, document_id=payload.document_id)
    except ValueError as exc:
        # Genuinely bad input/output (no content, malformed model response) —
        # a 422 tells Django this failed for a real reason, not a server bug.
        raise HTTPException(status_code=422, detail=str(exc))
