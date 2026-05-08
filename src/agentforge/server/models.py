"""Pydantic models for API requests/responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BuildRequest(BaseModel):
    """Request to start a new build."""

    description: str = Field(..., min_length=1, description="Project description")
    interactive: bool = Field(default=False, description="Enable interactive mode")
    model: str | None = Field(default=None, description="LLM model override")


class BuildResponse(BaseModel):
    """Response after starting a build."""

    run_id: str
    thread_id: str
    status: str = "started"
    message: str = "Build started"


class RunStatus(BaseModel):
    """Status of a build run."""

    run_id: str
    thread_id: str
    status: str  # pending, running, completed, failed
    description: str
    started_at: datetime
    completed_at: datetime | None = None
    current_agent: str | None = None
    progress: int = 0  # 0-100
    error: str | None = None


class RunSummary(BaseModel):
    """Summary of a build run."""

    run_id: str
    description: str
    status: str
    started_at: datetime
    duration_seconds: float | None = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0


class ArtifactResponse(BaseModel):
    """Response containing an artifact."""

    type: str  # prd, architecture, code, tests, devops
    content: Any
    format: str = "json"  # json, markdown, text


class WebSocketMessage(BaseModel):
    """Message sent over WebSocket."""

    type: str  # event, token, state_update, error
    data: Any
    timestamp: datetime = Field(default_factory=datetime.utcnow)
