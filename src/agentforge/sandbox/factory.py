"""Factory for creating sandbox runners."""

import logging
from typing import Protocol

from agentforge.sandbox.models import SandboxConfig, SandboxResult, TestRunConfig

logger = logging.getLogger(__name__)


class SandboxRunnerProtocol(Protocol):
    """Protocol for sandbox runners."""

    async def run(
        self,
        command: str,
        files: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult: ...

    async def run_tests(self, config: TestRunConfig) -> SandboxResult: ...

    def is_available(self) -> bool: ...


def create_sandbox_runner(config: SandboxConfig | None = None) -> SandboxRunnerProtocol:
    """Create a sandbox runner using the best available method.

    Selection order:
    1. Docker (preferred, secure isolation)
    2. Subprocess (fallback, requires AGENTFORGE_UNSAFE_SANDBOX=1)

    Args:
        config: Optional sandbox configuration.

    Returns:
        A sandbox runner instance.

    Raises:
        RuntimeError: If no sandbox runner is available.
    """
    # Try Docker first
    try:
        from agentforge.sandbox.runner import SandboxRunner

        runner = SandboxRunner(config)
        if runner.is_available():
            logger.info("Using Docker sandbox runner")
            return runner
        logger.warning("Docker available but sandbox image not found")
    except Exception as e:
        logger.debug(f"Docker sandbox not available: {e}")

    # Try subprocess fallback
    try:
        from agentforge.sandbox.subprocess_runner import (
            SubprocessRunner,
            is_unsafe_sandbox_enabled,
        )

        if is_unsafe_sandbox_enabled():
            logger.warning("Falling back to UNSAFE subprocess sandbox")
            return SubprocessRunner(config)
    except Exception as e:
        logger.debug(f"Subprocess sandbox not available: {e}")

    raise RuntimeError(
        "No sandbox runner available. Either:\n"
        "1. Install Docker and build the sandbox image:\n"
        "   docker build -f docker/sandbox.Dockerfile -t agentforge-sandbox:latest .\n"
        "2. Enable unsafe subprocess mode (NOT recommended for untrusted code):\n"
        "   export AGENTFORGE_UNSAFE_SANDBOX=1"
    )


def is_sandbox_available() -> bool:
    """Check if any sandbox runner is available.

    Returns:
        True if a sandbox can be created.
    """
    try:
        create_sandbox_runner()
        return True
    except RuntimeError:
        return False


def get_sandbox_info() -> dict[str, bool]:
    """Get information about available sandbox methods.

    Returns:
        Dict with availability status of each method.
    """
    info = {
        "docker_available": False,
        "docker_image_exists": False,
        "subprocess_enabled": False,
    }

    # Check Docker
    try:
        from agentforge.sandbox.runner import SandboxRunner

        runner = SandboxRunner()
        info["docker_available"] = True
        info["docker_image_exists"] = runner._ensure_image()
    except Exception:
        pass

    # Check subprocess
    try:
        from agentforge.sandbox.subprocess_runner import is_unsafe_sandbox_enabled

        info["subprocess_enabled"] = is_unsafe_sandbox_enabled()
    except Exception:
        pass

    return info
