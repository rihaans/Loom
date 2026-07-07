"""Data models for the memory system."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from loom._time import now_utc

if TYPE_CHECKING:
    from loom.state.models import AgentState


class MemoryConfig(BaseModel):
    """Configuration for the memory system."""

    enabled: bool = Field(default=True, description="Enable memory system")
    db_path: str = Field(
        default=".loom/memory/lancedb",
        description="Path to LanceDB storage",
    )
    embedder: Literal["local", "openai"] = Field(
        default="local",
        description="Embedding provider",
    )
    embedder_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Embedding model name",
    )
    top_k: int = Field(default=3, ge=1, le=10, description="Number of examples to retrieve")
    min_similarity: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold",
    )
    only_persist_passing: bool = Field(
        default=True,
        description="Only store builds where all tests pass",
    )


class MemoryRecord(BaseModel):
    """A single past-build record stored in the vector DB."""

    run_id: str = Field(description="UUID, primary key")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Embedded text
    descriptor: str = Field(description="Text used for embedding")

    # Filterable metadata
    project_type: str = Field(description="Project type enum value")
    stack_summary: str = Field(description="Summary like 'FastAPI+React+SQLite'")
    test_passed: bool = Field(default=True)
    retry_count: int = Field(default=0, ge=0)
    file_count: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)

    # Payload (returned with hits, used in few-shot context)
    one_liner: str = Field(description="Project one-liner description")
    must_have_features: list[str] = Field(default_factory=list)
    data_entity_names: list[str] = Field(default_factory=list)
    chosen_stack: list[dict[str, Any]] = Field(
        default_factory=list,
        description="TechChoice dicts",
    )
    api_endpoint_summary: list[str] = Field(
        default_factory=list,
        description="List like ['GET /todos', 'POST /todos']",
    )
    folder_structure_keys: list[str] = Field(
        default_factory=list,
        description="Top-level directories",
    )

    @classmethod
    def from_state(cls, state: AgentState, run_id: str) -> MemoryRecord:
        """Create a MemoryRecord from final build state.

        Args:
            state: The final AgentState after a successful build.
            run_id: The unique run identifier.

        Returns:
            A MemoryRecord ready for storage.
        """
        prd = state.prd
        architecture = state.architecture
        test_report = state.test_report
        code_files = state.code_files or {}

        # Build descriptor for embedding
        descriptor = build_descriptor(prd) if prd else ""

        # Build stack summary
        stack_summary = ""
        if architecture and architecture.stack:
            tech_names = [t.technology for t in architecture.stack]
            stack_summary = "+".join(tech_names[:4])

        # Count total files
        file_count = 0
        folder_keys = set()
        for bundle in code_files.values():
            if hasattr(bundle, "files"):
                for f in bundle.files:
                    file_count += 1
                    parts = f.path.split("/")
                    if len(parts) > 1:
                        folder_keys.add(parts[0])

        # Build API endpoint summary
        api_summary = []
        if architecture and architecture.api_endpoints:
            for ep in architecture.api_endpoints[:10]:
                api_summary.append(f"{ep.method.value} {ep.path}")

        # Build chosen stack as dicts
        chosen_stack = []
        if architecture and architecture.stack:
            for tech in architecture.stack:
                chosen_stack.append(tech.model_dump())

        return cls(
            run_id=run_id,
            timestamp=now_utc(),
            descriptor=descriptor,
            project_type=prd.project_type.value if prd else "unknown",
            stack_summary=stack_summary,
            test_passed=test_report.all_passed if test_report else False,
            retry_count=state.retry_count,
            file_count=file_count,
            total_cost_usd=state.total_cost_usd,
            one_liner=prd.one_liner if prd else "",
            must_have_features=list(prd.must_have_features[:6]) if prd else [],
            data_entity_names=[e.name for e in prd.data_entities[:6]] if prd else [],
            chosen_stack=chosen_stack,
            api_endpoint_summary=api_summary,
            folder_structure_keys=list(folder_keys),
        )


class MemoryContext(BaseModel):
    """What the Architect receives in its prompt."""

    examples: list[MemoryRecord] = Field(
        default_factory=list,
        description="Top-K examples ordered by similarity",
    )
    similarity_scores: list[float] = Field(
        default_factory=list,
        description="Parallel array of similarity scores",
    )

    def to_prompt_block(self) -> str:
        """Render as a few-shot block for the Architect prompt.

        Returns:
            Formatted string with past build examples, or empty string if none.
        """
        if not self.examples:
            return ""

        lines = ["# Similar past builds (use as guidance, not constraints)"]

        for i, (rec, score) in enumerate(zip(self.examples, self.similarity_scores, strict=True)):
            lines.append(f"\n## Example {i + 1} (similarity {score:.2f})")
            lines.append(f"Project: {rec.one_liner}")
            lines.append(f"Stack chosen: {rec.stack_summary}")
            if rec.api_endpoint_summary:
                endpoints = ", ".join(rec.api_endpoint_summary[:8])
                lines.append(f"Endpoints: {endpoints}")
            outcome = "tests passed" if rec.test_passed else "tests failed"
            retry_info = "first try" if rec.retry_count == 0 else f"retry #{rec.retry_count}"
            lines.append(f"Outcome: {outcome} on {retry_info}")

        return "\n".join(lines)


def build_descriptor(prd: Any) -> str:
    """Build the embedding descriptor text from a PRD.

    Args:
        prd: The PRD model.

    Returns:
        A concise text representation for embedding.
    """
    if prd is None:
        return ""

    parts = []

    # Project type and one-liner
    project_type = (
        prd.project_type.value if hasattr(prd.project_type, "value") else str(prd.project_type)
    )
    parts.append(f"{project_type} | {prd.one_liner}")

    # Must-have features
    if prd.must_have_features:
        features = ", ".join(prd.must_have_features[:6])
        parts.append(f"must_have: {features}")

    # Data entities
    if prd.data_entities:
        entity_names = ", ".join(e.name for e in prd.data_entities[:6])
        parts.append(f"data_entities: {entity_names}")

    return "\n".join(parts)
