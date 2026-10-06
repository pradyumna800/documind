"""
Main FastAPI application entrypoint.
"""
from fastapi import FastAPI
from app.api.routes import router
from app.core.db import init_vector_store

app = FastAPI(title="DocuMind AI Service")

app.include_router(router)


@app.on_event("startup")
def on_startup():
    init_vector_store()


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}
