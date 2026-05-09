"""Pydantic models for Loom state management.

This is the source of truth for inter-agent contracts. Every field defined
here flows between nodes. If an agent's output doesn't match these schemas,
the parser fails and the agent retries.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator

from loom.state.enums import (
    AgentRole,
    ComponentLocation,
    ComponentType,
    EventType,
    HttpMethod,
    Phase,
    Priority,
    ProjectType,
    TargetAgent,
    TechLayer,
)
from loom.state.reducers import append_list, merge_dicts

# Regex patterns for validation
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
USER_STORY_ID_PATTERN = re.compile(r"^US-\d{3}$")
PATH_UNSAFE_PATTERN = re.compile(r"(^/|\.\.)")


# =============================================================================
# PRD Models
# =============================================================================


class UserStory(BaseModel):
    """A user story in the PRD."""

    id: str = Field(..., pattern=r"^US-\d{3}$", description="Format: US-001, US-002, etc.")
    role: str = Field(..., description="The user role (e.g., 'registered user')")
    goal: str = Field(..., description="What the user wants to do")
    benefit: str = Field(..., description="Why they want to do it")
    acceptance_criteria: list[str] = Field(..., min_length=1)
    priority: Priority

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_acceptance_criteria(cls, v: list[str]) -> list[str]:
        """Ensure acceptance criteria are non-empty strings."""
        return [ac.strip() for ac in v if ac.strip()]


class DataEntity(BaseModel):
    """A data entity/model in the system."""

    name: str = Field(..., min_length=1)
    description: str
    fields: dict[str, str] = Field(
        ..., description="Mapping of field_name -> type (e.g., 'string', 'int', 'datetime')"
    )


class PRD(BaseModel):
    """Product Requirements Document."""

    project_name: str = Field(..., min_length=1, max_length=100)
    project_slug: str = Field(
        ..., pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40, description="Kebab-case slug"
    )
    project_type: ProjectType
    one_liner: str = Field(..., max_length=200, description="Brief project description")
    target_users: list[str] = Field(..., min_length=1)
    user_stories: list[UserStory] = Field(..., min_length=1)
    data_entities: list[DataEntity] = Field(default_factory=list)
    must_have_features: list[str] = Field(..., min_length=1)
    nice_to_have_features: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("project_slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Ensure slug is valid kebab-case."""
        if not SLUG_PATTERN.match(v):
            raise ValueError(f"Invalid slug format: {v}. Must be kebab-case (e.g., 'my-project')")
        return v


# =============================================================================
# Architecture Models
# =============================================================================


class TechChoice(BaseModel):
    """A technology choice for a layer of the stack."""

    layer: TechLayer
    technology: str = Field(..., min_length=1)
    version: str = Field(default="latest")
    rationale: str = Field(..., min_length=1)


class APIEndpoint(BaseModel):
    """An API endpoint definition."""

    method: HttpMethod
    path: str = Field(..., min_length=1)
    description: str
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] = Field(default_factory=dict)
    auth_required: bool = False
    user_story_ids: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Ensure path starts with /."""
        if not v.startswith("/"):
            raise ValueError(f"API path must start with '/': {v}")
        return v


class Component(BaseModel):
    """A software component."""

    name: str = Field(..., min_length=1)
    type: ComponentType
    location: ComponentLocation
    responsibility: str
    depends_on: list[str] = Field(default_factory=list)


class ArchitectureDoc(BaseModel):
    """Architecture document produced by the Architect agent."""

    stack: list[TechChoice] = Field(..., min_length=1)
    api_endpoints: list[APIEndpoint] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    data_models: list[DataEntity] = Field(default_factory=list)
    folder_structure: dict[str, str] = Field(
        default_factory=dict, description="Mapping of path -> description"
    )
    component_diagram_mermaid: str = Field(default="")
    deployment_diagram_mermaid: str = Field(default="")
    notes: str = Field(default="")


# =============================================================================
# Code Models
# =============================================================================


class CodeFile(BaseModel):
    """A generated code file."""

    path: str = Field(..., min_length=1, description="Relative path from project root")
    content: str = Field(..., min_length=1, description="File content (non-empty)")
    language: str = Field(..., description="python, javascript, typescript, html, css, json, yaml")

    @field_validator("path")
    @classmethod
    def validate_path_safety(cls, v: str) -> str:
        """Ensure path is safe (no .., no leading /)."""
        if PATH_UNSAFE_PATTERN.search(v):
            raise ValueError(f"Unsafe path: {v}. Cannot contain '..' or start with '/'")
        return v

    @field_validator("content")
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        """Ensure content is not empty or whitespace only."""
        if not v.strip():
            raise ValueError("File content cannot be empty or whitespace only")
        return v


class FileBundle(BaseModel):
    """A bundle of code files from a dev agent."""

    files: list[CodeFile] = Field(..., min_length=1)
    entry_point: str = Field(..., description="Main file to run")
    install_commands: list[str] = Field(default_factory=list)
    run_commands: list[str] = Field(default_factory=list)
    notes: str = Field(default="")


# =============================================================================
# QA Models
# =============================================================================


class TestCase(BaseModel):
    """A single test case result."""

    name: str
    file: str
    passed: bool
    duration_ms: float = Field(ge=0)
    error_message: str | None = None


class TestReport(BaseModel):
    """Test execution report from QA agent."""

    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(default=0, ge=0)
    duration_ms: float = Field(ge=0)
    cases: list[TestCase] = Field(default_factory=list)
    coverage_percent: float | None = Field(default=None, ge=0, le=100)
    raw_output: str = Field(default="", max_length=10000)

    @property
    def all_passed(self) -> bool:
        """Check if all tests passed."""
        return self.failed == 0 and self.total > 0

    @model_validator(mode="after")
    def validate_totals(self) -> TestReport:
        """Ensure total equals passed + failed + skipped."""
        expected = self.passed + self.failed + self.skipped
        if self.total != expected:
            raise ValueError(
                f"Total ({self.total}) must equal passed ({self.passed}) + "
                f"failed ({self.failed}) + skipped ({self.skipped}) = {expected}"
            )
        return self


class QAFeedback(BaseModel):
    """Feedback from QA to dev agents when tests fail."""

    target_agent: TargetAgent
    failed_tests: list[TestCase] = Field(default_factory=list)
    suspected_files: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    raw_error_excerpt: str = Field(..., max_length=4000)


# =============================================================================
# DevOps Models
# =============================================================================


class DevOpsBundle(BaseModel):
    """DevOps configuration files."""

    dockerfile_backend: str | None = None
    dockerfile_frontend: str | None = None
    docker_compose: str = Field(..., min_length=1)
    github_actions_ci: str = Field(default="")
    readme_run_instructions: str = Field(default="")
    env_example: str = Field(default="")
    other_files: dict[str, str] = Field(
        default_factory=dict, description="Additional files: path -> content"
    )


# =============================================================================
# Audit & Cost Models
# =============================================================================


class Event(BaseModel):
    """An event in the build timeline."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    type: EventType
    agent: AgentRole | None = None
    phase: Phase | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class CostEntry(BaseModel):
    """Token/cost tracking for an LLM call."""

    agent: AgentRole
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


# =============================================================================
# Sandbox Execution Models
# =============================================================================


class ExecutionResult(BaseModel):
    """Result of running code in the sandbox."""

    exit_code: int
    stdout: str = Field(default="", max_length=50000)
    stderr: str = Field(default="", max_length=50000)
    duration_ms: float = Field(ge=0)
    timed_out: bool = False
    files_written: list[str] = Field(default_factory=list)


# =============================================================================
# Master AgentState
# =============================================================================


class AgentState(BaseModel):
    """The shared state passed between all LangGraph nodes.

    This is the central data structure for the entire build pipeline.
    Each agent reads from and writes to specific fields.

    Reducers (via Annotated types) define how fields merge when
    multiple nodes update them.
    """

    # Input
    description: str = Field(..., min_length=1, description="User's project description")
    config: dict[str, Any] = Field(default_factory=dict, description="Runtime config overrides")

    # Routing
    phase: Phase = Field(default=Phase.INIT)
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0)
    interactive: bool = Field(default=False)

    # Artifacts (each written by specific agents)
    prd: PRD | None = None
    architecture: ArchitectureDoc | None = None
    code_files: Annotated[dict[str, FileBundle], merge_dicts] = Field(default_factory=dict)
    test_report: TestReport | None = None
    qa_feedback: QAFeedback | None = None
    devops_files: DevOpsBundle | None = None

    # Memory (injected before Architect, used for few-shot context)
    # Uses Any to avoid circular import with loom.memory.models
    memory_context: Any | None = None

    # Plan mode (user feedback for iterating on architecture)
    architecture_feedback: str | None = None

    # Logs (append-only)
    events: Annotated[list[Event], append_list] = Field(default_factory=list)
    costs: Annotated[list[CostEntry], append_list] = Field(default_factory=list)

    # Final output
    output_dir: str | None = None
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @property
    def total_cost_usd(self) -> float:
        """Calculate total cost across all agents."""
        return sum(c.cost_usd for c in self.costs)

    @property
    def total_tokens(self) -> int:
        """Calculate total tokens used."""
        return sum(c.input_tokens + c.output_tokens for c in self.costs)

    def add_event(
        self,
        event_type: EventType,
        agent: AgentRole | None = None,
        phase: Phase | None = None,
        **payload: Any,
    ) -> None:
        """Helper to add an event to the timeline."""
        self.events.append(
            Event(type=event_type, agent=agent, phase=phase or self.phase, payload=payload)
        )

    def add_cost(
        self, agent: AgentRole, model: str, input_tokens: int, output_tokens: int, cost_usd: float
    ) -> None:
        """Helper to add a cost entry."""
        self.costs.append(
            CostEntry(
                agent=agent,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
        )
