"""Memory persistence node.

Persists successful builds to the memory store after DevOps completes.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from loom.config import LoomConfig
from loom.memory.factory import get_embedder, get_memory_store, is_memory_available
from loom.memory.models import MemoryConfig, MemoryRecord
from loom.state.enums import EventType, Phase
from loom.state.models import AgentState, Event

logger = logging.getLogger(__name__)


def _create_persist_event(run_id: str, success: bool) -> Event:
    """Create an event for memory persistence."""
    return Event(
        timestamp=datetime.utcnow(),
        type=EventType.AGENT_END if success else EventType.ERROR,
        phase=Phase.COMPLETE,
        payload={
            "run_id": run_id,
            "persisted": success,
        },
    )


async def memory_persist_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
) -> dict[str, Any]:
    """Memory persistence node function.

    Persists successful builds to the memory store. This runs AFTER the
    DevOps engineer completes, only for successful builds.

    Args:
        state: Current graph state (dict form for LangGraph compatibility)
        config: Optional Loom configuration

    Returns:
        State update dict with events
    """
    # Get or create config
    if config is None:
        from loom.config import load_config
        config = load_config()

    memory_config: MemoryConfig = getattr(config, "memory", MemoryConfig())

    # Skip if memory is disabled
    if not memory_config.enabled:
        logger.debug("Memory system disabled, skipping persistence")
        return {}

    # Check if memory dependencies are available
    if not is_memory_available():
        logger.debug("Memory dependencies not installed, skipping persistence")
        return {}

    # Only persist passing builds (if configured)
    test_report = state.get("test_report")
    if memory_config.only_persist_passing:
        if test_report is None or not getattr(test_report, "all_passed", False):
            logger.debug("Tests did not pass, skipping persistence")
            return {}

    # Check for required state
    prd = state.get("prd")
    architecture = state.get("architecture")

    if prd is None or architecture is None:
        logger.debug("Missing PRD or architecture, skipping persistence")
        return {}

    # Generate run ID
    run_id = str(uuid.uuid4())

    try:
        # Convert state dict to AgentState for the from_state method
        agent_state = AgentState(
            description=state.get("description", ""),
            prd=prd,
            architecture=architecture,
            code_files=state.get("code_files", {}),
            test_report=test_report,
            devops_files=state.get("devops_files"),
            retry_count=state.get("retry_count", 0),
            costs=state.get("costs", []),
        )

        # Create memory record from state
        record = MemoryRecord.from_state(agent_state, run_id)

        # Get embedder and store
        embedder = get_embedder(memory_config)
        store = get_memory_store(memory_config)

        # Generate embedding
        embedding = embedder.embed(record.descriptor)

        # Store the record
        store.upsert(record, embedding)

        logger.info(f"Persisted build to memory: {run_id}")

        return {
            "events": [_create_persist_event(run_id, success=True)],
        }

    except Exception as e:
        logger.warning(f"Memory persistence failed: {e}")
        # Don't fail the build, just log the error
        return {
            "events": [
                Event(
                    timestamp=datetime.utcnow(),
                    type=EventType.ERROR,
                    phase=Phase.COMPLETE,
                    payload={"error": f"Memory persistence failed: {e}"},
                )
            ],
        }
