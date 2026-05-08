"""Subprocess-based sandbox runner (unsafe fallback).

WARNING: This runner provides NO isolation. Only use for local development
when Docker is unavailable. Gated by AGENTFORGE_UNSAFE_SANDBOX=1.
"""

import asyncio
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from agentforge.sandbox.models import (
    ExecutionStatus,
    SandboxConfig,
    SandboxResult,
    TestRunConfig,
)

logger = logging.getLogger(__name__)

# Environment variable to enable unsafe subprocess runner
UNSAFE_SANDBOX_ENV = "AGENTFORGE_UNSAFE_SANDBOX"


class UnsafeSandboxError(Exception):
    """Raised when trying to use subprocess runner without explicit opt-in."""

    pass


def is_unsafe_sandbox_enabled() -> bool:
    """Check if unsafe subprocess sandbox is enabled."""
    return os.environ.get(UNSAFE_SANDBOX_ENV, "").lower() in ("1", "true", "yes")


class SubprocessRunner:
    """Run code using subprocess (NO ISOLATION).

    WARNING: This provides no security isolation. Code runs with the same
    privileges as the parent process. Only use for trusted code in
    development environments.

    Must set AGENTFORGE_UNSAFE_SANDBOX=1 to use.
    """

    def __init__(self, config: SandboxConfig | None = None):
        """Initialize subprocess runner.

        Args:
            config: Optional configuration (timeout honored, resource limits ignored).

        Raises:
            UnsafeSandboxError: If AGENTFORGE_UNSAFE_SANDBOX is not set.
        """
        if not is_unsafe_sandbox_enabled():
            raise UnsafeSandboxError(
                "Subprocess sandbox requires AGENTFORGE_UNSAFE_SANDBOX=1. "
                "WARNING: This provides NO isolation. Use Docker for production."
            )

        self.config = config or SandboxConfig()
        logger.warning(
            "Using UNSAFE subprocess sandbox. No isolation provided. "
            "For production, use Docker-based sandbox."
        )

    async def run(
        self,
        command: str,
        files: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run a command using subprocess.

        Args:
            command: Command to execute.
            files: Optional files to write to temp directory.
            env: Optional environment variables.

        Returns:
            SandboxResult with execution details.
        """
        start_time = time.time()
        temp_dir = None

        try:
            # Create temp directory for files
            temp_dir = tempfile.mkdtemp(prefix="agentforge_sandbox_")

            # Write files if provided
            if files:
                for path, content in files.items():
                    file_path = Path(temp_dir) / path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(content, encoding="utf-8")

            # Prepare environment
            run_env = os.environ.copy()
            if env:
                run_env.update(env)

            # Run command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=temp_dir,
                env=run_env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.timeout_seconds,
                )
                exit_code = process.returncode or 0

                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")

                # Truncate if needed
                truncated = False
                max_bytes = self.config.max_output_bytes
                if len(stdout) > max_bytes:
                    stdout = stdout[:max_bytes] + "\n... (truncated)"
                    truncated = True
                if len(stderr) > max_bytes:
                    stderr = stderr[:max_bytes] + "\n... (truncated)"
                    truncated = True

                status = ExecutionStatus.SUCCESS if exit_code == 0 else ExecutionStatus.FAILED

                return SandboxResult(
                    status=status,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=time.time() - start_time,
                    truncated=truncated,
                )

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return SandboxResult(
                    status=ExecutionStatus.TIMEOUT,
                    exit_code=-1,
                    error=f"Execution timed out after {self.config.timeout_seconds}s",
                    duration_seconds=time.time() - start_time,
                )

        except Exception as e:
            logger.exception(f"Subprocess execution failed: {e}")
            return SandboxResult(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

        finally:
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp dir: {e}")

    async def run_tests(self, config: TestRunConfig) -> SandboxResult:
        """Run tests using subprocess."""
        if config.sandbox_config:
            self.config = config.sandbox_config

        return await self.run(
            command=config.command,
            files=config.files,
            env=config.env,
        )

    def is_available(self) -> bool:
        """Subprocess is always available if enabled."""
        return is_unsafe_sandbox_enabled()
