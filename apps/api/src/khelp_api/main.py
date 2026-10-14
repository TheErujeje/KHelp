"""Klaudesk API.

    uv run khelp-api        # http://localhost:8000/api/...
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import APIRouter, FastAPI  # noqa: E402
from sqlalchemy import text  # noqa: E402

from khelp_db import get_engine  # noqa: E402
from khelp_scoring import load_rules  # noqa: E402

from .agent.runner import Settings  # noqa: E402
from .routes import runs, triage  # noqa: E402
from .worker import mark_interrupted_runs  # noqa: E402

log = logging.getLogger("khelp")


@asynccontextmanager
async def lifespan(_: FastAPI):
    interrupted = mark_interrupted_runs()
    if interrupted:
        log.warning("marked %d interrupted agent runs as FAILED", interrupted)
    yield


app = FastAPI(title="Klaudesk", version="0.1.0", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json")
meta = APIRouter()


@meta.get("/health")
def health() -> dict[str, Any]:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    settings = Settings()
    return {"ok": True, "model": settings.model_label}


@meta.get("/rules/status")
def rules_status() -> dict[str, Any]:
    rules = load_rules()
    unverified = rules.unverified_entries()
    return {
        "total": len(rules.all_entries()),
        "unverified_count": len(unverified),
        "all_verified": not unverified,
        "unverified_ids": [e["id"] for e in unverified],
        "scale": rules.tews["scale"],
        "min_age_years": rules.min_age_years,
    }


app.include_router(meta, prefix="/api")
app.include_router(triage.router, prefix="/api")
app.include_router(runs.router, prefix="/api")


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run("khelp_api.main:app", host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8000")), workers=1)
