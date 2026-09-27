"""
All reads/writes to the document_chunks table live here, so the rest of
the app never writes raw SQL directly.
"""
from sqlalchemy import text
from app.core.db import SessionLocal


def store_chunks(user_id: int, document_id: int, document_name: str, chunks: list[dict], embeddings: list[list[float]]):
    with SessionLocal() as session:
        for chunk, embedding in zip(chunks, embeddings):
            session.execute(
                text("""
                    INSERT INTO document_chunks
                        (user_id, document_id, document_name, page_number, chunk_index, content, embedding)
                    VALUES
                        (:user_id, :document_id, :document_name, :page_number, :chunk_index, :content, :embedding)
                """),
                {
                    "user_id": user_id,
                    "document_id": document_id,
                    "document_name": document_name,
                    "page_number": chunk["page_number"],
                    "chunk_index": chunk["chunk_index"],
                    "content": chunk["content"],
                    "embedding": str(embedding),  # pgvector accepts '[0.1,0.2,...]' text format
                },
            )
        session.commit()


def delete_document_chunks(user_id: int, document_id: int):
    with SessionLocal() as session:
        session.execute(
            text("DELETE FROM document_chunks WHERE user_id = :user_id AND document_id = :document_id"),
            {"user_id": user_id, "document_id": document_id},
        )
        session.commit()


def search_similar_chunks(user_id: int, document_ids: list[int], query_embedding: list[float], top_k: int) -> list[dict]:
    """
    Finds the top_k most similar chunks using cosine distance (<=> operator,
    provided by pgvector). Distance ranges 0 (identical) to 2 (opposite) —
    lower is more similar.

    CRITICAL: user_id is always part of the WHERE clause. This is the line
    that guarantees User A can never retrieve User B's chunks, no matter
    what document_ids are requested.
    """
    if not document_ids:
        return []

    with SessionLocal() as session:
        result = session.execute(
            text("""
                SELECT document_id, document_name, page_number, content,
                       embedding <=> CAST(:query_embedding AS vector) AS distance
                FROM document_chunks
                WHERE user_id = :user_id AND document_id = ANY(:document_ids)
                ORDER BY distance ASC
                LIMIT :top_k
            """),
            {
                "user_id": user_id,
                "document_ids": document_ids,
                "query_embedding": str(query_embedding),
                "top_k": top_k,
            },
        )
        return [dict(row._mapping) for row in result]


def get_all_chunks_for_document(user_id: int, document_id: int) -> list[dict]:
    """
    Returns every chunk for one document, in original reading order
    (by chunk_index) — not similarity-ranked. Used for whole-document
    tasks like generating a summary/quiz, where we want the full content
    rather than only the chunks most similar to a specific question.

    Still scoped by user_id for the same ownership-isolation reason as
    search_similar_chunks.
    """
    with SessionLocal() as session:
        result = session.execute(
            text("""
                SELECT page_number, chunk_index, content
                FROM document_chunks
                WHERE user_id = :user_id AND document_id = :document_id
                ORDER BY chunk_index ASC
            """),
            {"user_id": user_id, "document_id": document_id},
        )
        return [dict(row._mapping) for row in result]
