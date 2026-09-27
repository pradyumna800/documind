"""
Central settings for the AI service, read from environment variables.
Keeping this in one place means every module imports `settings` instead
of calling os.environ.get() scattered everywhere.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env lives at the project root (chat_bot/.env), one level above ai-service/
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(ROOT_DIR / ".env")


class Settings:
    internal_key: str = os.environ.get("FASTAPI_INTERNAL_KEY", "changeme-shared-secret")
    database_url: str = os.environ.get("DATABASE_URL", "")

    llm_api_key: str = os.environ.get("LLM_API_KEY", "")
    embedding_api_key: str = os.environ.get("EMBEDDING_API_KEY", os.environ.get("LLM_API_KEY", ""))

    # Base URL for the LLM/embedding provider's API. Defaults to OpenAI's
    # real endpoint. Point this at http://localhost:11434/v1 to use a local
    # Ollama installation instead — Ollama exposes an OpenAI-compatible API,
    # so no other code needs to change, just this URL and the model names.
    llm_base_url: str = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    embedding_base_url: str = os.environ.get("EMBEDDING_BASE_URL", os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"))

    embedding_model: str = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    # IMPORTANT: this must match the actual output size of your embedding model.
    # OpenAI text-embedding-3-small = 1536. Ollama's nomic-embed-text = 768.
    # Getting this wrong causes a database error when storing embeddings.
    embedding_dimensions: int = int(os.environ.get("EMBEDDING_DIMENSIONS", 1536))
    llm_model: str = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    chunk_size: int = int(os.environ.get("CHUNK_SIZE", 1000))       # characters per chunk
    chunk_overlap: int = int(os.environ.get("CHUNK_OVERLAP", 150))  # overlap between consecutive chunks

    # How many chunks to retrieve per question. Lowered from an earlier 8 —
    # that many, combined with a loose distance cutoff, was pulling in
    # weakly-related chunks from scattered, unrelated pages of dense
    # documents (lecture notes, textbooks), producing citation lists that
    # looked unfocused even for a single narrow question.
    top_k: int = int(os.environ.get("RETRIEVAL_TOP_K", 5))

    # Cosine distance cutoff for "is this chunk actually relevant?" (0 = identical
    # meaning, 2 = opposite). Lower = stricter. Tightened from 0.75 to 0.55 for
    # the same reason as top_k above — 0.75 let in a lot of only-superficially-
    # related chunks. If genuine answers start coming back as "not found" too
    # often after this change, raise it a bit (e.g. 0.65) rather than reverting
    # all the way — it's a real precision/recall trade-off, tune to taste.
    max_chunk_distance: float = float(os.environ.get("MAX_CHUNK_DISTANCE", 0.55))


settings = Settings()
