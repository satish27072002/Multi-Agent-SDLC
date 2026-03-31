"""FastAPI server — connects the CLI client to backend agents (hosted mode).

In hosted mode, the CLI sends tasks over HTTP and the server runs agents
on the K8s cluster, streaming progress back via SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agents.coding import CodingResult
from src.agents.docs import DocsResult
from src.agents.gitops import GitPlan
from src.agents.orchestrator import (
    PipelineCallback,
    PipelineState,
    Stage,
    run_pipeline,
)
from src.agents.review import ReviewResult
from src.agents.testing import TestGenResult, TestRunResult
from src.core.config import load_settings
from src.core.state import TaskRecord, TaskStatus, TaskStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SDLC Agent Server",
    description="Multi-agent SDLC automation API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

task_store = TaskStore()


def _auth_guard(authorization: str | None = Header(default=None)) -> None:
    settings = load_settings()
    if not settings.api_token:
        return

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.api_token:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class TaskRequest(BaseModel):
    task: str = Field(description="The coding task to execute")
    workspace: str = Field(default="/tmp/sdlc-workspace", description="Server-side workspace path")
    skip_tests: bool = False
    skip_docs: bool = False
    skip_git: bool = False
    auto_approve: bool = True


class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    current_stage: str
    errors: list[str]
    result: dict | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    agents: int
    uptime: float


# ---------------------------------------------------------------------------
# SSE callback — streams pipeline events to the client
# ---------------------------------------------------------------------------

class SSEPipelineCallback(PipelineCallback):
    """Sends pipeline events as SSE messages."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict] = asyncio.Queue()
        self._done = False

    async def _emit(self, event: str, data: dict) -> None:
        await self._queue.put({"event": event, **data})

    async def on_stage_change(self, state: PipelineState) -> None:
        await self._emit("stage", {"stage": state.stage.value})

    async def on_coding_done(self, result: CodingResult) -> None:
        await self._emit("coding_done", {
            "files": [{"path": f.path, "explanation": f.explanation} for f in result.files],
            "summary": result.summary,
        })

    async def on_tests_generated(self, result: TestGenResult) -> None:
        await self._emit("tests_generated", {
            "count": len(result.test_files),
            "summary": result.summary,
        })

    async def on_tests_run(self, result: TestRunResult) -> None:
        await self._emit("tests_run", {
            "passed": result.passed,
            "tests_run": result.tests_run,
            "tests_passed": result.tests_passed,
        })

    async def on_review_done(self, result: ReviewResult) -> None:
        await self._emit("review_done", {
            "approved": result.approved,
            "issues_count": len(result.issues),
            "summary": result.summary,
        })

    async def on_docs_done(self, result: DocsResult) -> None:
        await self._emit("docs_done", {"count": len(result.files)})

    async def on_git_plan(self, plan: GitPlan) -> None:
        await self._emit("git_plan", {
            "branch": plan.branch_name,
            "commit": plan.commit_message,
        })

    async def on_error(self, stage: Stage, error: str) -> None:
        await self._emit("error", {"stage": stage.value, "error": error})

    async def request_approval(self, state: PipelineState) -> bool:
        return True  # Auto-approve in server mode

    def mark_done(self) -> None:
        self._done = True

    async def events(self) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted events."""
        while not self._done or not self._queue.empty():
            try:
                data = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield f"data: {json.dumps(data)}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"
        yield f"data: {json.dumps({'event': 'done'})}\n\n"


# ---------------------------------------------------------------------------
# Start time for uptime tracking
# ---------------------------------------------------------------------------

_start_time = time.time()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        version="0.1.0",
        agents=6,
        uptime=time.time() - _start_time,
    )


@app.post("/tasks", response_model=TaskResponse)
async def create_task(req: TaskRequest, _: None = Depends(_auth_guard)):
    """Submit a new task for the agent pipeline."""
    record = task_store.create(req.task)
    workspace = Path(req.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    # Run pipeline in the background
    asyncio.create_task(_run_task(record, req, workspace))

    return TaskResponse(
        task_id=record.id,
        status="running",
        message=(
            "Task submitted. Use GET /tasks/{id} to check status "
            "or POST /tasks/stream for SSE."
        ),
    )


@app.post("/tasks/stream")
async def stream_task(req: TaskRequest, _: None = Depends(_auth_guard)):
    """Submit a task and stream progress via Server-Sent Events."""
    workspace = Path(req.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    callback = SSEPipelineCallback()

    async def run_and_stream():
        settings = load_settings()
        try:
            await run_pipeline(
                task=req.task,
                workspace=workspace,
                settings=settings,
                callback=callback,
                skip_tests=req.skip_tests,
                skip_docs=req.skip_docs,
                skip_git=req.skip_git,
            )
        except Exception as e:
            await callback._emit("error", {"stage": "pipeline", "error": str(e)})
        finally:
            callback.mark_done()

    asyncio.create_task(run_and_stream())
    return StreamingResponse(callback.events(), media_type="text/event-stream")


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str, _: None = Depends(_auth_guard)):
    """Get the status of a task."""
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(
        task_id=record.id,
        status=record.status.value,
        current_stage=record.current_stage,
        errors=record.errors,
        result=record.result,
    )


@app.get("/tasks")
async def list_tasks(limit: int = 50, _: None = Depends(_auth_guard)):
    """List recent tasks."""
    tasks = task_store.list_tasks(limit=limit)
    return [t.to_dict() for t in tasks]


@app.get("/agents")
async def list_agents(_: None = Depends(_auth_guard)):
    """List available agents and their models."""
    settings = load_settings()
    return {
        "agents": [
            {
                "name": "orchestrator",
                "model": settings.orchestrator_model,
                "role": "Coordinates pipeline",
            },
            {"name": "coding", "model": settings.coding_model, "role": "Generates code"},
            {"name": "testing", "model": settings.testing_model, "role": "Writes and runs tests"},
            {"name": "review", "model": settings.review_model, "role": "Reviews code quality"},
            {"name": "docs", "model": settings.docs_model, "role": "Generates documentation"},
            {"name": "gitops", "model": settings.gitops_model, "role": "Manages git operations"},
        ]
    }


# ---------------------------------------------------------------------------
# Background task runner
# ---------------------------------------------------------------------------

async def _run_task(record: TaskRecord, req: TaskRequest, workspace: Path) -> None:
    """Execute the pipeline for a task record."""
    settings = load_settings()
    task_store.update(record.id, status=TaskStatus.RUNNING)

    try:
        state = await run_pipeline(
            task=req.task,
            workspace=workspace,
            settings=settings,
            skip_tests=req.skip_tests,
            skip_docs=req.skip_docs,
            skip_git=req.skip_git,
        )
        result: dict[str, object] = {}
        if state.coding_result:
            result["files"] = [f.path for f in state.coding_result.files]
        if state.test_run_result:
            result["tests"] = {
                "passed": state.test_run_result.passed,
                "run": state.test_run_result.tests_run,
            }
        if state.review_result:
            result["review"] = {"approved": state.review_result.approved}

        task_store.update(
            record.id,
            status=TaskStatus.COMPLETED if state.stage == Stage.DONE else TaskStatus.FAILED,
            current_stage=state.stage.value,
            result=result,
            errors=state.errors,
        )
    except Exception as e:
        task_store.update(
            record.id,
            status=TaskStatus.FAILED,
            errors=[str(e)],
        )
