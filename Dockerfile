# Multi-stage Dockerfile for SDLC Agent System
# Supports both CLI (local) and server (hosted) modes

# ── Stage 1: Base with dependencies ──────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir ".[server]"

# ── Stage 2: Application code ────────────────────────────────────────────
FROM base AS app

COPY src/ ./src/
COPY tests/ ./tests/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# ── Stage 3: Server mode (default for K8s deployment) ────────────────────
FROM app AS server

EXPOSE 8080

CMD ["uvicorn", "src.server.api:app", "--host", "0.0.0.0", "--port", "8080"]

# ── Stage 4: Individual agent (for per-agent K8s pods) ───────────────────
FROM app AS agent

# Set AGENT_NAME env var at runtime to select which agent to run
# e.g., docker run -e AGENT_NAME=coding -e AGENT_PORT=9001 ...
ENV AGENT_NAME=coding
ENV AGENT_PORT=9000

CMD python -c "\
from protocols.a2a_server import create_a2a_app; \
from agents.${AGENT_NAME} import build_${AGENT_NAME}_agent; \
from core.config import load_settings; \
import uvicorn; \
settings = load_settings(); \
agent = build_${AGENT_NAME}_agent(settings); \
app = create_a2a_app(agent, '${AGENT_NAME}', '${AGENT_NAME} agent', int('${AGENT_PORT}')); \
uvicorn.run(app, host='0.0.0.0', port=int('${AGENT_PORT}'))"

# ── Default target: server ───────────────────────────────────────────────
FROM server
