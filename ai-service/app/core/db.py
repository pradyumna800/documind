"""
Database setup for the AI service.

We use the SAME Postgres database as Django (same DATABASE_URL), but a
separate table (`document_chunks`) that Django's ORM doesn't manage —
this table is owned by the AI service. Sharing one Postgres instance
(rather than a separate vector DB) is what lets us filter vector search
by user_id/document_id with a plain SQL WHERE clause instead of a second
metadata-filtering system.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .config import settings

# SQLAlchemy dropped support for the short "postgres://" URL prefix (Django
# still accepts it fine via dj-database-url). Normalizing it here means the
# same DATABASE_URL in .env works for both services without needing two
# different values.
_db_url = settings.database_url
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(_db_url, pool_pre_ping=True) if _db_url else None
SessionLocal = sessionmaker(bind=engine) if engine else None


def init_vector_store():
    """Creates the pgvector extension + document_chunks table if they
    don't exist yet. Safe to call every startup (IF NOT EXISTS)."""
    if not engine:
        print("WARNING: DATABASE_URL not set — vector store not initialized.")
        return
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                document_id INTEGER NOT NULL,
                document_name TEXT NOT NULL,
                page_number INTEGER,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding vector({settings.embedding_dimensions}) NOT NULL
            );
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_user_doc "
            "ON document_chunks (user_id, document_id);"
        ))
