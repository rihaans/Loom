"""Docker-based sandbox runner for isolated code execution.

Uses the Docker SDK to run code in isolated containers with resource limits.
"""

import logging
import tarfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from loom.sandbox.models import (
    ExecutionStatus,
    SandboxConfig,
    SandboxResult,
    TestRunConfig,
)

logger = logging.getLogger(__name__)

# Default image name
DEFAULT_IMAGE = "loom-sandbox:latest"


class DockerNotAvailableError(Exception):
    """Raised when Docker is not available."""

    pass


class SandboxRunner:
    """Run code in an isolated Docker container.

    Features:
    - Resource limits (memory, CPU, PIDs)
    - Network isolation
    - Timeout enforcement
    - Output capture with truncation
    - Non-root execution

    Example:
        >>> runner = SandboxRunner()
        >>> result = await runner.run("python -c 'print(1+1)'")
        >>> print(result.stdout)  # "2"
    """

    def __init__(self, config: SandboxConfig | None = None):
        """Initialize the sandbox runner.

        Args:
            config: Optional sandbox configuration. Uses defaults if not provided.

        Raises:
            DockerNotAvailableError: If Docker is not available.
        """
        self.config = config or SandboxConfig()
        # Docker SDK client, created lazily; typed Any since the SDK ships no stubs.
        self._client: Any = None
        self._initialize_docker()

    def _initialize_docker(self) -> None:
        """Initialize Docker client."""
        try:
            import docker

            self._client = docker.from_env()  # type: ignore[attr-defined]
            # Test connection
            self._client.ping()
            logger.debug("Docker client initialized successfully")
        except ImportError as e:
            raise DockerNotAvailableError(
                "Docker SDK not installed. Install with: pip install docker"
            ) from e
        except Exception as e:
            raise DockerNotAvailableError(f"Docker not available: {e}") from e

    def _ensure_image(self) -> bool:
        """Ensure the sandbox image exists.

        Returns:
            True if image exists, False otherwise.
        """
        try:
            self._client.images.get(self.config.image)
            return True
        except Exception:
            logger.warning(
                f"Sandbox image '{self.config.image}' not found. "
                f"Build it with: docker build -f docker/sandbox.Dockerfile -t {self.config.image} ."
            )
            return False

    def _create_tar_archive(self, files: dict[str, str]) -> bytes:
        """Create a tar archive from file contents.

        Args:
            files: Map of file paths to contents.

        Returns:
            Tar archive as bytes.
        """
        tar_buffer = BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            for path, content in files.items():
                # Create file info
                data = content.encode("utf-8")
                info = tarfile.TarInfo(name=path)
                info.size = len(data)
                info.mode = 0o644

                # Add to archive
                tar.addfile(info, BytesIO(data))

        tar_buffer.seek(0)
        return tar_buffer.read()

    def _truncate_output(self, output: str) -> tuple[str, bool]:
        """Truncate output if it exceeds the limit.

        Args:
            output: Output string.

        Returns:
            Tuple of (possibly truncated output, was_truncated).
        """
        max_bytes = self.config.max_output_bytes
        if len(output.encode("utf-8")) > max_bytes:
            # Truncate with message
            truncated = output.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
            truncated += "\n\n... (output truncated)"
            return truncated, True
        return output, False

    async def run(
        self,
        command: str,
        files: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run a command in the sandbox.

        Args:
            command: Command to execute.
            files: Optional files to copy into the container.
            env: Optional environment variables.

        Returns:
            SandboxResult with execution details.
        """
        import asyncio

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._run_sync(command, files, env))

    def _run_sync(
        self,
        command: str,
        files: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Synchronous implementation of run.

        Args:
            command: Command to execute.
            files: Optional files to copy into the container.
            env: Optional environment variables.

        Returns:
            SandboxResult with execution details.
        """
        if not self._ensure_image():
            return SandboxResult(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=f"Sandbox image '{self.config.image}' not found",
            )

        container = None
        start_time = time.time()

        try:
            # Create container with security constraints
            container = self._client.containers.create(
                image=self.config.image,
                command=["bash", "-c", command],
                working_dir=self.config.workdir,
                environment=env or {},
                # Resource limits
                mem_limit=self.config.memory_limit,
                nano_cpus=int(self.config.cpu_limit * 1e9),
                pids_limit=self.config.pids_limit,
                # Security
                network_disabled=self.config.network_disabled,
                cap_drop=["ALL"],  # Drop all capabilities
                security_opt=["no-new-privileges"],  # Prevent privilege escalation
                read_only=False,  # Need write for test output
                # User
                user="sandbox",
            )

            # Copy files into container if provided
            if files:
                tar_data = self._create_tar_archive(files)
                container.put_archive(self.config.workdir, tar_data)

            # Start container
            container.start()

            # Wait for completion with timeout
            try:
                result = container.wait(timeout=self.config.timeout_seconds)
                exit_code = result.get("StatusCode", -1)

                # Check if OOM killed
                container.reload()
                oom_killed = container.attrs.get("State", {}).get("OOMKilled", False)

                if oom_killed:
                    status = ExecutionStatus.OOM_KILLED
                elif exit_code == 0:
                    status = ExecutionStatus.SUCCESS
                else:
                    status = ExecutionStatus.FAILED

            except Exception as timeout_error:
                # Timeout or other error
                logger.warning(f"Container execution timeout or error: {timeout_error}")
                container.kill()
                return SandboxResult(
                    status=ExecutionStatus.TIMEOUT,
                    exit_code=-1,
                    error=f"Execution timed out after {self.config.timeout_seconds}s",
                    duration_seconds=time.time() - start_time,
                )

            # Get logs
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            # Truncate if needed
            stdout, stdout_truncated = self._truncate_output(stdout)
            stderr, stderr_truncated = self._truncate_output(stderr)

            duration = time.time() - start_time

            return SandboxResult(
                status=status,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                truncated=stdout_truncated or stderr_truncated,
                error=None
                if status == ExecutionStatus.SUCCESS
                else stderr[:500]
                if stderr
                else None,
            )

        except Exception as e:
            logger.exception(f"Sandbox execution failed: {e}")
            return SandboxResult(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

        finally:
            # Always clean up container
            if container:
                try:
                    container.remove(force=True)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to remove container: {cleanup_error}")

    async def run_tests(self, config: TestRunConfig) -> SandboxResult:
        """Run tests in the sandbox.

        Convenience method that sets up files and runs the test command.

        Args:
            config: Test run configuration.

        Returns:
            SandboxResult with test execution details.
        """
        # Override sandbox config if provided
        if config.sandbox_config:
            self.config = config.sandbox_config

        return await self.run(
            command=config.command,
            files=config.files,
            env=config.env,
        )

    def is_available(self) -> bool:
        """Check if Docker is available and the sandbox image exists.

        Returns:
            True if sandbox is ready to use.
        """
        try:
            self._client.ping()
            return self._ensure_image()
        except Exception:
            return False

    def build_image(self, dockerfile_path: str | Path = "docker/sandbox.Dockerfile") -> bool:
        """Build the sandbox Docker image.

        Args:
            dockerfile_path: Path to the Dockerfile.

        Returns:
            True if build succeeded.
        """
        dockerfile_path = Path(dockerfile_path)
        if not dockerfile_path.exists():
            logger.error(f"Dockerfile not found: {dockerfile_path}")
            return False

        # The daemon resolves `dockerfile` relative to the build context and
        # expects POSIX separators. Passing a Windows path here fails with
        # "Cannot locate specified Dockerfile: docker\sandbox.Dockerfile".
        context = dockerfile_path.parent.parent  # project root
        try:
            relative_dockerfile = dockerfile_path.resolve().relative_to(context.resolve())
        except ValueError:
            logger.error(f"Dockerfile {dockerfile_path} is outside build context {context}")
            return False

        try:
            logger.info(f"Building sandbox image from {dockerfile_path}...")
            _image, logs = self._client.images.build(
                path=str(context),
                dockerfile=relative_dockerfile.as_posix(),
                tag=self.config.image,
                rm=True,
            )
            for log in logs:
                if "stream" in log:
                    logger.debug(log["stream"].strip())
            logger.info(f"Successfully built image: {self.config.image}")
            return True
        except Exception as e:
            logger.error(f"Failed to build image: {e}")
            return False
