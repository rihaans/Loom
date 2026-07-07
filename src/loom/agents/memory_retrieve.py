"""Memory retrieval node.

Retrieves similar past builds before the Architect runs, injecting MemoryContext
into the state for few-shot guidance.
"""

import logging
from typing import Any

from loom._time import now_utc
from loom.config import LoomConfig
from loom.memory.factory import get_embedder, get_memory_store, is_memory_available
from loom.memory.models import MemoryConfig, MemoryContext, build_descriptor
from loom.state.enums import EventType, Phase
from loom.state.models import Event

logger = logging.getLogger(__name__)


def _create_retrieve_event(num_retrieved: int, top_similarity: float | None = None) -> Event:
    """Create an event for memory retrieval."""
    payload: dict[str, Any] = {"num_retrieved": num_retrieved}
    if top_similarity is not None:
        payload["top_similarity"] = round(top_similarity, 3)

    return Event(
        timestamp=now_utc(),
        type=EventType.AGENT_END,
        phase=Phase.INIT,
        payload=payload,
    )


async def memory_retrieve_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
) -> dict[str, Any]:
    """Memory retrieval node function.

    Retrieves similar past builds based on the PRD and injects MemoryContext
    into the state. This runs BEFORE the Architect agent.

    Args:
        state: Current graph state (dict form for LangGraph compatibility)
        config: Optional Loom configuration

    Returns:
        State update dict with memory_context and events
    """
    prd = state.get("prd")

    # Skip if no PRD yet
    if prd is None:
        logger.debug("No PRD available, skipping memory retrieval")
        return {}

    # Get or create config
    if config is None:
        from loom.config import load_config

        config = load_config()

    memory_config: MemoryConfig = getattr(config, "memory", MemoryConfig())

    # Skip if memory is disabled
    if not memory_config.enabled:
        logger.debug("Memory system disabled, skipping retrieval")
        return {}

    # Check if memory dependencies are available
    if not is_memory_available():
        logger.debug("Memory dependencies not installed, skipping retrieval")
        return {}

    try:
        # Build descriptor from PRD for embedding
        descriptor = build_descriptor(prd)
        if not descriptor.strip():
            logger.debug("Empty descriptor, skipping memory retrieval")
            return {}

        # Get embedder and store
        embedder = get_embedder(memory_config)
        store = get_memory_store(memory_config)

        # Embed the query
        query_embedding = embedder.embed(descriptor)

        # Search for similar builds
        filters: dict[str, Any] = {}
        if hasattr(prd, "project_type") and prd.project_type:
            # Optionally filter by project type for better relevance
            pass  # Don't filter for now, let similarity handle it

        results = store.search(
            query_embedding=query_embedding,
            k=memory_config.top_k,
            filters=filters,
        )

        # Filter by minimum similarity threshold
        filtered_results = [
            (record, score) for record, score in results if score >= memory_config.min_similarity
        ]

        if not filtered_results:
            logger.info("No similar past builds found above threshold")
            return {
                "events": [_create_retrieve_event(0)],
            }

        # Build MemoryContext
        examples = [record for record, _ in filtered_results]
        scores = [score for _, score in filtered_results]

        memory_context = MemoryContext(
            examples=examples,
            similarity_scores=scores,
        )

        top_score = scores[0] if scores else None
        logger.info(
            f"Retrieved {len(examples)} similar past builds (top similarity: {top_score:.3f})"
        )

        return {
            "memory_context": memory_context,
            "events": [_create_retrieve_event(len(examples), top_score)],
        }

    except Exception as e:
        logger.warning(f"Memory retrieval failed: {e}")
        # Don't fail the build, just skip memory
        return {
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.ERROR,
                    phase=Phase.INIT,
                    payload={"error": f"Memory retrieval failed: {e}"},
                )
            ],
        }
