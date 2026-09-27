import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.security import verify_internal_key
from app.rag.pipeline import (
    process_document, remove_document, answer_question, generate_study_materials, stream_answer,
)

router = APIRouter()


class ProcessDocumentRequest(BaseModel):
    document_id: int
    user_id: int
    file_path: str
    file_type: str
    document_name: str = ""


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
def process_document_endpoint(payload: ProcessDocumentRequest):
    result = process_document(
        document_id=payload.document_id,
        user_id=payload.user_id,
        file_path=payload.file_path,
        file_type=payload.file_type,
        document_name=payload.document_name or f"document-{payload.document_id}",
    )
    return result


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
