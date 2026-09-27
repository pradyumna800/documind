"""
Embeddings: converts text into a vector of numbers that captures its
*meaning* — texts with similar meaning end up as vectors that are close
together in space. This is what lets us search "by meaning" instead of
by exact keyword match (semantic search).

Works with either OpenAI's real API or a local Ollama server, since both
speak the same OpenAI-style API shape — only base_url/model differ.
"""
from openai import OpenAI
from app.core.config import settings

_client = OpenAI(api_key=settings.embedding_api_key or "ollama", base_url=settings.embedding_base_url)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embeds a batch of texts in one API call (cheaper and faster than
    one call per chunk). Note: Ollama's embeddings endpoint currently only
    embeds one text at a time even via the OpenAI-compatible route, so we
    loop here — harmless for small documents, just slightly slower."""
    if settings.embedding_base_url != "https://api.openai.com/v1":
        return [_client.embeddings.create(model=settings.embedding_model, input=t).data[0].embedding for t in texts]
    response = _client.embeddings.create(model=settings.embedding_model, input=texts)
    return [item.embedding for item in response.data]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
