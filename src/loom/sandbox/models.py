"""Data models for sandbox execution."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ExecutionStatus(StrEnum):
    """Status of sandbox execution."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    OOM_KILLED = "oom_killed"
    ERROR = "error"


class SandboxResult(BaseModel):
    """Result of running code in the sandbox."""

    status: ExecutionStatus
    exit_code: int = Field(default=0, description="Process exit code")
    stdout: str = Field(default="", description="Standard output (may be truncated)")
    stderr: str = Field(default="", description="Standard error (may be truncated)")
    duration_seconds: float = Field(default=0.0, description="Execution time in seconds")
    truncated: bool = Field(default=False, description="Whether output was truncated")
    error: str | None = Field(default=None, description="Error message if execution failed")

    @property
    def succeeded(self) -> bool:
        """Check if execution succeeded."""
        return self.status == ExecutionStatus.SUCCESS and self.exit_code == 0


class SandboxConfig(BaseModel):
    """Configuration for sandbox execution."""

    # Resource limits
    memory_limit: str = Field(default="512m", description="Memory limit (e.g., '512m', '1g')")
    cpu_limit: float = Field(default=1.0, description="CPU limit (number of cores)")
    pids_limit: int = Field(default=100, description="Max number of processes")

    # Timeouts
    timeout_seconds: int = Field(default=60, description="Execution timeout in seconds")

    # Network
    network_disabled: bool = Field(default=True, description="Disable network access")

    # Output limits
    max_output_bytes: int = Field(
        default=1_000_000, description="Max stdout/stderr bytes (1MB default)"
    )

    # Image
    image: str = Field(default="loom-sandbox:latest", description="Docker image to use")

    # Working directory inside container
    workdir: str = Field(default="/workspace", description="Working directory in container")


class TestRunConfig(BaseModel):
    """Configuration for running tests."""

    # Project files to copy into sandbox
    files: dict[str, str] = Field(default_factory=dict, description="Map of file paths to contents")

    # Test command to run
    command: str = Field(description="Test command (e.g., 'pytest tests/')")

    # Test framework (for output parsing)
    framework: str = Field(default="pytest", description="Test framework: pytest, jest, vitest")

    # Additional environment variables
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")

    # Sandbox configuration overrides
    sandbox_config: SandboxConfig = Field(default_factory=SandboxConfig)
