# SANDBOX — Docker-Based Code Execution

The QA agent must actually run the generated tests to verify they pass. Doing so on the host is dangerous (the LLM could produce `rm -rf /`). We use Docker.

---

## 1. Goals

| Requirement | How we meet it |
|---|---|
| Isolation | Container with no host filesystem access except mount |
| Resource caps | `--memory`, `--cpus`, `--pids-limit` |
| Network restriction | `--network=none` for tests; `--network=bridge` only when explicitly needed |
| Time-bounded | `--stop-timeout` + signal-based kill |
| Reproducible | Pre-built image with all common test runners |
| Cross-platform | Works on macOS (Docker Desktop), Linux, WSL2 |
| Fast | < 5 sec startup overhead with image cache |

## 2. Sandbox Image

```dockerfile
# docker/sandbox.Dockerfile
FROM python:3.11-slim AS base

# Install Node.js 20
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Common Python test deps (cached, fast install for generated code)
RUN pip install --no-cache-dir \
    pytest pytest-asyncio pytest-cov httpx \
    fastapi uvicorn flask sqlalchemy pydantic \
    python-jose passlib bcrypt python-multipart

# Common Node test deps in a global location
RUN npm install -g vitest jest supertest
RUN mkdir -p /opt/node_modules && cd /opt && \
    npm install --prefix /opt express cors better-sqlite3 jsonwebtoken bcryptjs zod \
                       react react-dom @vitejs/plugin-react vite

# Non-root user for safety
RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /workspace

CMD ["bash"]
```

Build once:
```bash
docker build -f docker/sandbox.Dockerfile -t loom-sandbox:latest .
```

The image is ~800 MB but provides instant startup for most generated projects.

## 3. SandboxRunner

```python
# loom/sandbox/runner.py
import docker
import tempfile
import time
from pathlib import Path
from loom.state.models import ExecutionResult

class SandboxRunner:
    IMAGE = "loom-sandbox:latest"

    def __init__(
        self,
        timeout_seconds: int = 90,
        memory_mb: int = 512,
        cpus: float = 1.0,
        network_enabled: bool = False,
    ):
        self.client = docker.from_env()
        self.timeout = timeout_seconds
        self.memory = f"{memory_mb}m"
        self.cpus = cpus
        self.network = "bridge" if network_enabled else "none"

    def run(self, files: dict[str, str], command: str) -> ExecutionResult:
        """Materialize files, run command, return result."""
        with tempfile.TemporaryDirectory(prefix="loom-sb-") as tmpdir:
            tmp = Path(tmpdir)
            for path, content in files.items():
                full = tmp / path
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content)

            return self._run_in_container(tmp, command)

    def _run_in_container(self, host_path: Path, command: str) -> ExecutionResult:
        start = time.monotonic()
        try:
            container = self.client.containers.run(
                self.IMAGE,
                command=["bash", "-c", command],
                volumes={str(host_path): {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                network_mode=self.network,
                mem_limit=self.memory,
                nano_cpus=int(self.cpus * 1e9),
                pids_limit=256,
                read_only=False,             # tests may write files
                tmpfs={"/tmp": "size=64M"},
                detach=True,
                stdout=True,
                stderr=True,
                user="sandbox",
                environment={"PYTHONUNBUFFERED": "1", "NODE_ENV": "test"},
                # Security
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
            )

            timed_out = False
            try:
                exit_status = container.wait(timeout=self.timeout)
                exit_code = exit_status["StatusCode"]
            except Exception:
                container.kill()
                exit_code = 124  # convention for timeout
                timed_out = True

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            container.remove(force=True)

            return ExecutionResult(
                exit_code=exit_code,
                stdout=stdout[:50_000],
                stderr=stderr[:50_000],
                duration_ms=(time.monotonic() - start) * 1000,
                timed_out=timed_out,
            )

        except docker.errors.ImageNotFound:
            raise RuntimeError(
                f"Sandbox image {self.IMAGE} not found. "
                f"Run: loom sandbox build"
            )
        except docker.errors.APIError as e:
            raise RuntimeError(f"Docker error: {e}")
```

## 4. The `sandbox_exec` Tool (LangChain)

```python
# loom/tools/sandbox_exec.py
from langchain_core.tools import tool
from loom.sandbox.runner import SandboxRunner
from loom.state.models import ExecutionResult

_runner: SandboxRunner | None = None

def get_runner() -> SandboxRunner:
    global _runner
    if _runner is None:
        _runner = SandboxRunner()
    return _runner

@tool
def sandbox_exec(
    files: dict[str, str],
    command: str,
) -> ExecutionResult:
    """Execute shell command in an isolated Docker sandbox with the given files materialized.
    
    Args:
        files: dict mapping relative file paths to file contents
        command: shell command to run (e.g. "pip install -r requirements.txt && pytest")
    
    Returns:
        ExecutionResult with exit_code, stdout, stderr, duration, timed_out
    """
    return get_runner().run(files, command)
```

## 5. Subprocess Fallback (Dev Mode)

For dev iteration when Docker startup overhead is annoying, Loom supports a subprocess-based runner gated behind `LOOM_UNSAFE_SANDBOX=1`:

```python
class SubprocessRunner:
    """UNSAFE — only for local dev. Runs in a tmp dir on the host."""
    def __init__(self, timeout_seconds: int = 60):
        self.timeout = timeout_seconds

    def run(self, files: dict[str, str], command: str) -> ExecutionResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            for path, content in files.items():
                full = Path(tmpdir) / path
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(content)
            
            start = time.monotonic()
            try:
                result = subprocess.run(
                    command, shell=True, cwd=tmpdir,
                    capture_output=True, text=True,
                    timeout=self.timeout,
                )
                return ExecutionResult(
                    exit_code=result.returncode,
                    stdout=result.stdout[:50_000],
                    stderr=result.stderr[:50_000],
                    duration_ms=(time.monotonic() - start) * 1000,
                    timed_out=False,
                )
            except subprocess.TimeoutExpired as e:
                return ExecutionResult(
                    exit_code=124, stdout=e.stdout or "", stderr=e.stderr or "",
                    duration_ms=self.timeout * 1000, timed_out=True,
                )
```

Selected via factory:

```python
def get_sandbox(config: LoomConfig) -> SandboxRunner | SubprocessRunner:
    if config.use_docker_sandbox:
        return SandboxRunner(
            timeout_seconds=config.sandbox_timeout_seconds,
            memory_mb=config.sandbox_memory_mb,
        )
    if not os.getenv("LOOM_UNSAFE_SANDBOX"):
        raise RuntimeError(
            "Subprocess sandbox requires LOOM_UNSAFE_SANDBOX=1. "
            "Use Docker for safety, or accept the risk explicitly."
        )
    return SubprocessRunner(timeout_seconds=config.sandbox_timeout_seconds)
```

## 6. CLI Helper

```bash
# Build the sandbox image
loom sandbox build

# Test it
loom sandbox test
# → runs `python -c "print('hello')"` in the sandbox

# Inspect it
loom sandbox shell
# → drops you into a shell in a fresh sandbox container
```

## 7. Failure Modes & Handling

| Failure | Handling |
|---|---|
| Image not found | Clear error → tell user to run `loom sandbox build` |
| Docker daemon not running | Clear error → suggest starting Docker Desktop |
| Permission denied on Linux (no docker group) | Clear error → suggest `sudo usermod -aG docker $USER` |
| Image build fails (no internet) | Cache pre-built image as a release artifact in GitHub |
| Container OOM | exit_code=137 → QA agent sees and reports "memory exceeded" |
| Container timeout | exit_code=124 + timed_out=True → QA agent reports "tests timed out" |
| Tests need network | Set `network_enabled=True` per call (rare) |

## 8. Observability

Every sandbox execution emits an event:

```python
state.events.append(Event(
    type="tool_call",
    agent=AgentRole.QA,
    payload={
        "tool": "sandbox_exec",
        "command": command,
        "duration_ms": result.duration_ms,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "files_count": len(files),
    },
))
```

These show up live in the dashboard.

## 9. Testing the Sandbox Itself

```python
# tests/test_sandbox.py
def test_sandbox_runs_python():
    runner = SandboxRunner(timeout_seconds=10)
    result = runner.run(
        files={"hello.py": "print('hi')"},
        command="python hello.py",
    )
    assert result.exit_code == 0
    assert "hi" in result.stdout

def test_sandbox_blocks_network_by_default():
    runner = SandboxRunner(timeout_seconds=10)
    result = runner.run(
        files={"net.py": "import urllib.request; urllib.request.urlopen('https://example.com')"},
        command="python net.py",
    )
    assert result.exit_code != 0  # network blocked

def test_sandbox_oom_killed():
    runner = SandboxRunner(timeout_seconds=10, memory_mb=64)
    result = runner.run(
        files={"oom.py": "x = 'a' * (256 * 1024 * 1024)"},  # 256MB string
        command="python oom.py",
    )
    assert result.exit_code in (137, 1)  # OOM kill or memory error
```
