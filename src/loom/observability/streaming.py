"""Streaming support for real-time build observation.

Converts LangGraph astream_events to typed Loom events.
"""

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from langchain_core.runnables import RunnableConfig

from loom._time import now_utc
from loom.state.enums import AgentRole, Phase

logger = logging.getLogger(__name__)


class StreamEventType(StrEnum):
    """Types of streaming events."""

    # Graph events
    GRAPH_START = "graph_start"
    GRAPH_END = "graph_end"

    # Node events
    NODE_START = "node_start"
    NODE_END = "node_end"

    # LLM events
    LLM_START = "llm_start"
    LLM_TOKEN = "llm_token"
    LLM_END = "llm_end"

    # State events
    STATE_UPDATE = "state_update"

    # Error events
    ERROR = "error"


@dataclass
class StreamEvent:
    """A streaming event from the build pipeline."""

    type: StreamEventType
    timestamp: datetime
    node: str | None = None
    agent: AgentRole | None = None
    phase: Phase | None = None
    data: dict[str, Any] | None = None
    token: str | None = None  # For LLM_TOKEN events
    error: str | None = None


# Map node names to agent roles
NODE_TO_AGENT: dict[str, AgentRole] = {
    "product_manager": AgentRole.PRODUCT_MANAGER,
    "architect": AgentRole.ARCHITECT,
    "frontend_dev": AgentRole.FRONTEND_DEV,
    "backend_dev": AgentRole.BACKEND_DEV,
    "code_reviewer": AgentRole.CODE_REVIEWER,
    "qa_engineer": AgentRole.QA,
    "devops_engineer": AgentRole.DEVOPS,
    "supervisor": AgentRole.SUPERVISOR,
    "dev_merge": AgentRole.SUPERVISOR,
}


def _parse_langgraph_event(event: dict[str, Any]) -> StreamEvent | None:
    """Parse a LangGraph event into a StreamEvent.

    Args:
        event: Raw event from astream_events.

    Returns:
        StreamEvent or None if event should be skipped.
    """
    event_type = event.get("event", "")
    timestamp = now_utc()

    # Graph start/end
    if event_type == "on_chain_start":
        name = event.get("name", "")
        if name == "LangGraph":
            return StreamEvent(
                type=StreamEventType.GRAPH_START,
                timestamp=timestamp,
                data={"run_id": event.get("run_id")},
            )

    elif event_type == "on_chain_end":
        name = event.get("name", "")
        if name == "LangGraph":
            return StreamEvent(
                type=StreamEventType.GRAPH_END,
                timestamp=timestamp,
                data=event.get("data", {}),
            )

    # Node events
    elif event_type == "on_chain_start" and "tags" in event:
        tags = event.get("tags", [])
        for tag in tags:
            if tag.startswith("graph:node:"):
                node_name = tag.split(":")[-1]
                agent = NODE_TO_AGENT.get(node_name)
                return StreamEvent(
                    type=StreamEventType.NODE_START,
                    timestamp=timestamp,
                    node=node_name,
                    agent=agent,
                )

    elif event_type == "on_chain_end" and "tags" in event:
        tags = event.get("tags", [])
        for tag in tags:
            if tag.startswith("graph:node:"):
                node_name = tag.split(":")[-1]
                agent = NODE_TO_AGENT.get(node_name)
                return StreamEvent(
                    type=StreamEventType.NODE_END,
                    timestamp=timestamp,
                    node=node_name,
                    agent=agent,
                    data=event.get("data", {}),
                )

    # LLM events
    elif event_type == "on_llm_start":
        return StreamEvent(
            type=StreamEventType.LLM_START,
            timestamp=timestamp,
            data={
                "model": event.get("data", {}).get("invocation_params", {}).get("model"),
            },
        )

    elif event_type == "on_llm_stream":
        chunk = event.get("data", {}).get("chunk", {})
        content = chunk.get("content", "")
        if content:
            return StreamEvent(
                type=StreamEventType.LLM_TOKEN,
                timestamp=timestamp,
                token=content,
            )

    elif event_type == "on_llm_end":
        output = event.get("data", {}).get("output", {})
        return StreamEvent(
            type=StreamEventType.LLM_END,
            timestamp=timestamp,
            data={
                "usage": output.get("usage_metadata", {}),
            },
        )

    # Error events
    elif event_type == "on_chain_error":
        return StreamEvent(
            type=StreamEventType.ERROR,
            timestamp=timestamp,
            error=str(event.get("data", {}).get("error", "Unknown error")),
        )

    return None


async def stream_build_events(
    graph: Any,
    initial_state: dict[str, Any],
    config: RunnableConfig | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream events from a build execution.

    Args:
        graph: Compiled LangGraph.
        initial_state: Initial state dict.
        config: Optional execution config.

    Yields:
        StreamEvent objects as they occur.
    """
    try:
        async for event in graph.astream_events(
            initial_state,
            config=config,
            version="v2",
        ):
            parsed = _parse_langgraph_event(event)
            if parsed:
                yield parsed
    except Exception as e:
        yield StreamEvent(
            type=StreamEventType.ERROR,
            timestamp=now_utc(),
            error=str(e),
        )


class BuildObserver:
    """Observer for build events with callback support."""

    def __init__(self) -> None:
        self.callbacks: dict[StreamEventType, list[Callable[[StreamEvent], None]]] = {}
        self._current_node: str | None = None
        self._current_agent: AgentRole | None = None
        self._tokens_buffer: list[str] = []

    def on(
        self,
        event_type: StreamEventType,
        callback: Callable[[StreamEvent], None],
    ) -> "BuildObserver":
        """Register a callback for an event type.

        Args:
            event_type: Event type to listen for.
            callback: Function to call when event occurs.

        Returns:
            Self for chaining.
        """
        if event_type not in self.callbacks:
            self.callbacks[event_type] = []
        self.callbacks[event_type].append(callback)
        return self

    def handle(self, event: StreamEvent) -> None:
        """Handle an incoming event.

        Args:
            event: The event to handle.
        """
        # Track current node/agent
        if event.type == StreamEventType.NODE_START:
            self._current_node = event.node
            self._current_agent = event.agent
            self._tokens_buffer = []
        elif event.type == StreamEventType.NODE_END:
            self._current_node = None
            self._current_agent = None

        # Accumulate tokens
        if event.type == StreamEventType.LLM_TOKEN and event.token:
            self._tokens_buffer.append(event.token)

        # Call registered callbacks
        callbacks = self.callbacks.get(event.type, [])
        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    @property
    def current_node(self) -> str | None:
        """Get the currently executing node."""
        return self._current_node

    @property
    def current_agent(self) -> AgentRole | None:
        """Get the currently executing agent."""
        return self._current_agent

    @property
    def current_output(self) -> str:
        """Get the accumulated LLM output for the current node."""
        return "".join(self._tokens_buffer)

    async def observe(
        self,
        graph: Any,
        initial_state: dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        """Observe a build execution.

        Args:
            graph: Compiled LangGraph.
            initial_state: Initial state dict.
            config: Optional execution config.

        Returns:
            Final state dict.
        """
        final_state = initial_state

        async for event in stream_build_events(graph, initial_state, config):
            self.handle(event)

            # Capture final state from graph end
            if event.type == StreamEventType.GRAPH_END and event.data:
                final_state = event.data.get("output", final_state)

        return final_state
