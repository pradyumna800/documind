"""
Chunking: splits page text into overlapping windows.

Why overlap? If a sentence is cut exactly at a chunk boundary, the answer
to a question might be split across two chunks and neither one alone has
enough context. Overlap (default 150 chars) means the end of one chunk
reappears at the start of the next, so boundary-straddling facts still
get captured whole in at least one chunk.
"""
from app.core.config import settings


def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> list[str]:
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap

    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap  # step back by `overlap` so chunks overlap
    return chunks


def chunk_pages(pages: list[tuple[int, str]]) -> list[dict]:
    """Turns [(page_number, text), ...] into a flat list of chunk dicts,
    each tagged with which page and chunk-index it came from."""
    result = []
    chunk_index = 0
    for page_number, text in pages:
        for piece in chunk_text(text):
            result.append({
                "page_number": page_number,
                "chunk_index": chunk_index,
                "content": piece,
            })
            chunk_index += 1
    return result
