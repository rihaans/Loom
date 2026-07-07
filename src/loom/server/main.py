"""FastAPI application for Loom web dashboard."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from loom._time import now_utc
from loom.config import load_config, parse_llm_string
from loom.server.models import (
    ArtifactResponse,
    BuildRequest,
    BuildResponse,
    RunStatus,
    RunSummary,
)
from loom.server.runner import get_runner

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    logger.info("Starting Loom server")
    yield
    logger.info("Shutting down Loom server")


app = FastAPI(
    title="Loom",
    description="Autonomous software development team API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Build Routes
# =============================================================================


@app.post("/api/build", response_model=BuildResponse)
async def start_build(request: BuildRequest) -> BuildResponse:
    """Start a new build."""
    runner = get_runner()

    # Load config with optional model override
    config = load_config()
    if request.model:
        config.llm_default = parse_llm_string(request.model)

    # Create and start run
    run = runner.create_run(
        description=request.description,
        config=config,
        interactive=request.interactive,
    )
    await runner.start_run(run)

    return BuildResponse(
        run_id=run.run_id,
        thread_id=run.thread_id,
        status="started",
        message=f"Build started for: {request.description[:50]}...",
    )


@app.get("/api/runs", response_model=list[RunSummary])
async def list_runs() -> list[RunSummary]:
    """List all build runs."""
    runner = get_runner()
    runs = runner.list_runs()

    return [
        RunSummary(
            run_id=run.run_id,
            description=run.description,
            status=run.status,
            started_at=run.started_at,
            duration_seconds=(
                (run.completed_at - run.started_at).total_seconds() if run.completed_at else None
            ),
            total_tokens=sum(c.input_tokens + c.output_tokens for c in run.state.get("costs", [])),
            total_cost_usd=sum(c.cost_usd for c in run.state.get("costs", [])),
        )
        for run in runs
    ]


@app.get("/api/runs/{run_id}", response_model=RunStatus)
async def get_run(run_id: str) -> RunStatus:
    """Get status of a specific run."""
    runner = get_runner()
    run = runner.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunStatus(
        run_id=run.run_id,
        thread_id=run.thread_id,
        status=run.status,
        description=run.description,
        started_at=run.started_at,
        completed_at=run.completed_at,
        current_agent=run.current_agent,
        progress=run.progress,
        error=run.error,
    )


@app.get("/api/runs/{run_id}/artifacts/{artifact_type}", response_model=ArtifactResponse)
async def get_artifact(run_id: str, artifact_type: str) -> ArtifactResponse:
    """Get a specific artifact from a run."""
    runner = get_runner()
    run = runner.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    state = run.state
    artifact_map = {
        "prd": ("prd", "json"),
        "architecture": ("architecture", "json"),
        "code": ("code_files", "json"),
        "tests": ("test_report", "json"),
        "devops": ("devops_files", "json"),
    }

    if artifact_type not in artifact_map:
        raise HTTPException(status_code=400, detail=f"Unknown artifact type: {artifact_type}")

    state_key, format_type = artifact_map[artifact_type]
    content = state.get(state_key)

    if content is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_type}")

    # Convert Pydantic models to dict
    if hasattr(content, "model_dump"):
        content = content.model_dump()
    elif isinstance(content, dict):
        # Handle nested Pydantic models
        content = {k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in content.items()}

    return ArtifactResponse(
        type=artifact_type,
        content=content,
        format=format_type,
    )


# =============================================================================
# WebSocket for Real-time Updates
# =============================================================================


@app.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint for real-time build updates."""
    runner = get_runner()
    run = runner.get_run(run_id)

    if not run:
        await websocket.close(code=4004, reason="Run not found")
        return

    await websocket.accept()
    queue = run.add_observer()

    try:
        # Send current status
        await websocket.send_json(
            {
                "type": "status",
                "data": {
                    "status": run.status,
                    "progress": run.progress,
                    "current_agent": run.current_agent,
                },
                "timestamp": now_utc().isoformat(),
            }
        )

        # Stream events
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(message)

                # Close if build is complete
                if message.get("type") == "complete":
                    break

            except TimeoutError:
                # Send heartbeat
                await websocket.send_json(
                    {
                        "type": "heartbeat",
                        "timestamp": now_utc().isoformat(),
                    }
                )

    except WebSocketDisconnect:
        logger.debug(f"WebSocket disconnected for run {run_id}")
    finally:
        run.remove_observer(queue)


# =============================================================================
# Health Check
# =============================================================================


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {"status": "ok", "timestamp": now_utc().isoformat()}


# =============================================================================
# Static Files (for production)
# =============================================================================


def mount_static_files(static_dir: Path) -> None:
    """Mount static files for the frontend."""
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
        logger.info(f"Mounted static files from {static_dir}")


def create_app(static_dir: Path | None = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        static_dir: Optional path to static files directory.

    Returns:
        Configured FastAPI application.
    """
    if static_dir:
        mount_static_files(static_dir)
    return app
