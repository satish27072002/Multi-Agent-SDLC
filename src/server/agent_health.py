from __future__ import annotations

import os

from fastapi import FastAPI

app = FastAPI(title="SDLC Agent Health")


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "agent": os.getenv("AGENT_NAME", "unknown"),
    }
