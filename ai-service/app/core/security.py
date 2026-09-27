"""
Guards every internal endpoint so only Django (which knows the shared
secret) can call this service. The AI service is never exposed publicly
in production — this header check is a second layer of defense in case
it ever is reachable directly.
"""
from fastapi import Header, HTTPException, status
from .config import settings


async def verify_internal_key(x_internal_key: str = Header(...)):
    if x_internal_key != settings.internal_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal key")
