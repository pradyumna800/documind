"""
Conversation memory helpers.

For MVP, Django already sends only the last N messages (see
chat/views.py HISTORY_LIMIT in the backend) — that IS our memory
strategy for now: simple recency-based trimming, no summarization.

This module exists as the seam where smarter memory (e.g. summarizing
older messages once conversations get long) will plug in later, without
having to change the API contract between Django and FastAPI.
"""


def format_history_for_prompt(history: list[dict]) -> list[dict]:
    """Currently a passthrough. Placeholder for future summarization logic."""
    return history
