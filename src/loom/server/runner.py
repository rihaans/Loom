"""Background task runner for builds."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from loom._time import now_utc
from loom.config import LoomConfig, load_config
from loom.graph.builder import compile_graph
from loom.graph.checkpoint import (
    create_memory_checkpointer,
    generate_thread_id,
    get_checkpoint_config,
)
from loom.observability import BuildObserver, StreamEventType
from loom.state.enums import Phase

logger = logging.getLogger(__name__)


class BuildRun:
    """Represents a single build run."""

    def __init__(
        self,
        run_id: str,
        description: str,
        config: LoomConfig,
        interactive: bool = False,
    ):
        self.run_id = run_id
        self.thread_id = generate_thread_id(description)
        self.description = description
        self.config = config
        self.interactive = interactive

        self.status = "pending"
        self.started_at = now_utc()
        self.completed_at: datetime | None = None
        self.current_agent: str | None = None
        self.progress = 0
        self.error: str | None = None

        self.state: dict[str, Any] = {}
        self.observers: list[asyncio.Queue] = []

    def add_observer(self) -> asyncio.Queue:
        """Add an observer queue for this run."""
        queue: asyncio.Queue = asyncio.Queue()
        self.observers.append(queue)
        return queue

    def remove_observer(self, queue: asyncio.Queue) -> None:
        """Remove an observer queue."""
        if queue in self.observers:
            self.observers.remove(queue)

    async def notify(self, message: dict[str, Any]) -> None:
        """Notify all observers."""
        for queue in self.observers:
            try:
                await queue.put(message)
            except Exception as e:
                logger.warning(f"Failed to notify observer: {e}")


class BuildRunner:
    """Manages background build tasks."""

    def __init__(self) -> None:
        self.runs: dict[str, BuildRun] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def create_run(
        self,
        description: str,
        config: LoomConfig | None = None,
        interactive: bool = False,
    ) -> BuildRun:
        """Create a new build run."""
        run_id = str(uuid.uuid4())[:8]
        if config is None:
            config = load_config()

        run = BuildRun(run_id, description, config, interactive)
        self.runs[run_id] = run
        return run

    def get_run(self, run_id: str) -> BuildRun | None:
        """Get a run by ID."""
        return self.runs.get(run_id)

    def list_runs(self) -> list[BuildRun]:
        """List all runs."""
        return list(self.runs.values())

    async def start_run(self, run: BuildRun) -> None:
        """Start a build run in the background."""
        task = asyncio.create_task(self._execute_run(run))
        self._tasks[run.run_id] = task

    async def _execute_run(self, run: BuildRun) -> None:
        """Execute a build run."""
        run.status = "running"
        observer = BuildObserver()

        # Progress tracking
        agent_order = [
            "product_manager",
            "architect",
            "frontend_dev",
            "backend_dev",
            "dev_merge",
            "qa_engineer",
            "devops_engineer",
        ]

        def update_progress(event: Any) -> None:
            if event.node in agent_order:
                idx = agent_order.index(event.node)
                run.progress = int((idx + 1) / len(agent_order) * 100)
                run.current_agent = event.node

        observer.on(StreamEventType.NODE_START, update_progress)

        # Forward events to observers
        async def forward_event(event: Any) -> None:
            await run.notify(
                {
                    "type": "event",
                    "data": {
                        "event_type": event.type.value,
                        "node": event.node,
                        "agent": event.agent.value if event.agent else None,
                        "token": event.token,
                        "error": event.error,
                    },
                    "timestamp": event.timestamp.isoformat(),
                }
            )

        for event_type in StreamEventType:
            # Fire-and-forget async forwarding; the callback's return is ignored.
            observer.on(
                event_type,
                lambda e: asyncio.create_task(forward_event(e)),  # type: ignore[arg-type]
            )

        # Create initial state
        initial_state = {
            "description": run.description,
            "phase": Phase.INIT,
            "interactive": run.interactive,
            "retry_count": 0,
            "max_retries": run.config.max_retries,
            "events": [],
            "costs": [],
            "code_files": {},
        }

        try:
            # Compile and run graph
            checkpointer = create_memory_checkpointer()
            graph = compile_graph(run.config, checkpointer=checkpointer)
            run_config = get_checkpoint_config(run.thread_id)

            final_state = await observer.observe(graph, initial_state, run_config)

            run.state = final_state
            run.status = "completed" if not final_state.get("error") else "failed"
            run.error = final_state.get("error")
            run.progress = 100

        except Exception as e:
            logger.exception(f"Build run failed: {e}")
            run.status = "failed"
            run.error = str(e)

        finally:
            run.completed_at = now_utc()
            run.current_agent = None

            # Notify completion
            await run.notify(
                {
                    "type": "complete",
                    "data": {
                        "status": run.status,
                        "error": run.error,
                    },
                    "timestamp": now_utc().isoformat(),
                }
            )


# Global runner instance
_runner: BuildRunner | None = None


def get_runner() -> BuildRunner:
    """Get the global build runner."""
    global _runner
    if _runner is None:
        _runner = BuildRunner()
    return _runner
