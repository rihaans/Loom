"""Configuration models for AgentForge."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from agentforge.state.enums import AgentRole


class LLMConfig(BaseModel):
    """Configuration for an LLM provider/model."""

    provider: Literal["anthropic", "openai", "ollama"] = Field(
        default="ollama", description="LLM provider"
    )
    model: str = Field(default="qwen2.5-coder:7b", description="Model name")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=100000)
    api_key: str | None = Field(default=None, description="API key (falls back to env)")

    @field_validator("model")
    @classmethod
    def validate_model_not_empty(cls, v: str) -> str:
        """Ensure model name is not empty."""
        if not v.strip():
            raise ValueError("Model name cannot be empty")
        return v.strip()


class AgentForgeConfig(BaseModel):
    """Main configuration for AgentForge.

    Configuration priority: CLI flags > env vars > config file > defaults
    """

    # LLM Configuration
    llm_default: LLMConfig = Field(default_factory=LLMConfig)
    llm_overrides: dict[AgentRole, LLMConfig] = Field(
        default_factory=dict, description="Per-agent LLM overrides"
    )

    # Output
    output_dir: str = Field(default="./output", description="Directory for generated projects")

    # Build behavior
    max_retries: int = Field(default=2, ge=0, le=10, description="Max QA retry attempts")
    interactive: bool = Field(default=False, description="Pause at phase gates for review")
    use_llm_supervisor: bool = Field(
        default=False, description="Use LLM-based supervisor instead of deterministic"
    )

    # Sandbox
    use_docker_sandbox: bool = Field(default=True, description="Use Docker for code execution")
    sandbox_timeout_seconds: int = Field(default=90, ge=10, le=600)
    sandbox_memory_mb: int = Field(default=512, ge=64, le=4096)

    # Observability
    enable_langsmith: bool = Field(default=False, description="Enable LangSmith tracing")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # Cost controls
    cost_budget_usd: float | None = Field(
        default=None, ge=0, description="Hard cap on total cost (None = unlimited)"
    )
    cost_warn_threshold_usd: float = Field(default=1.0, ge=0)

    def get_llm_config(self, role: AgentRole) -> LLMConfig:
        """Get LLM config for a specific agent role.

        Returns override if configured, otherwise default.
        """
        return self.llm_overrides.get(role, self.llm_default)

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v: str) -> str:
        """Ensure output_dir is not empty."""
        if not v.strip():
            raise ValueError("output_dir cannot be empty")
        return v.strip()


class BuildResult(BaseModel):
    """Result of a completed build."""

    success: bool
    output_dir: str | None = None
    project_slug: str | None = None
    phase: str
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    error: str | None = None
    test_passed: bool | None = None
    retry_count: int = 0
