"""
Embeddings: converts text into a vector of numbers that captures its
*meaning* — texts with similar meaning end up as vectors that are close
together in space. This is what lets us search "by meaning" instead of
by exact keyword match (semantic search).

Works with OpenAI's real API, a local Ollama server, or Google Gemini's
OpenAI-compatible endpoint, since all speak the same OpenAI-style API
shape — only base_url/model differ.
"""
import time
from openai import OpenAI, RateLimitError
from app.core.config import settings

_OPENAI_URL = "https://api.openai.com/v1"
_MAX_RETRIES = 6

_client = OpenAI(api_key=settings.embedding_api_key or "ollama", base_url=settings.embedding_base_url)


def _create_with_retry(input_):
    """
    Calls the embeddings API, retrying with exponential backoff if the
    provider says we're going too fast (HTTP 429). Free API tiers
    (Gemini's included) have per-minute request limits, and embedding a
    long document one chunk at a time can hit them — without retry, one
    429 halfway through would fail the whole upload.
    """
    delay = 2.0
    for attempt in range(_MAX_RETRIES):
        try:
            return _client.embeddings.create(model=settings.embedding_model, input=input_)
        except RateLimitError:
            if attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 30)


def _check_dimensions(vectors: list[list[float]]) -> None:
    """
    Fails loudly, with an actionable message, if the model's actual output
    size doesn't match EMBEDDING_DIMENSIONS. Without this, a mismatch only
    surfaces later as a confusing database error when storing the vectors.
    """
    if vectors and len(vectors[0]) != settings.embedding_dimensions:
        raise RuntimeError(
            f"The embedding model returned {len(vectors[0])}-dimensional vectors, but "
            f"EMBEDDING_DIMENSIONS is set to {settings.embedding_dimensions}. Set "
            f"EMBEDDING_DIMENSIONS={len(vectors[0])} (and recreate the document_chunks "
            f"table if it already exists with a different size)."
        )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embeds a list of texts. OpenAI accepts a whole batch in one call;
    other providers (Ollama, Gemini's compatibility endpoint) are called
    one text at a time, which is slower but works reliably everywhere."""
    if settings.embedding_base_url != _OPENAI_URL:
        vectors = [_create_with_retry(t).data[0].embedding for t in texts]
    else:
        vectors = [item.embedding for item in _create_with_retry(texts).data]
    _check_dimensions(vectors)
    return vectors


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
