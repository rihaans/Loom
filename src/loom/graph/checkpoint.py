"""Checkpoint support for graph state persistence.

Uses LangGraph's MemorySaver for in-process checkpoints and SqliteSaver for durable persistence.
"""

import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

logger = logging.getLogger(__name__)

# Global connection registry to prevent connections from being garbage collected
_connections: list[sqlite3.Connection] = []

# Global memory savers for persistence across runs
_memory_savers: dict[str, MemorySaver] = {}

# Default checkpoint database location
DEFAULT_CHECKPOINT_DIR = Path.home() / ".loom" / "checkpoints"
DEFAULT_DB_NAME = "checkpoints.db"


def get_checkpoint_path(db_dir: Path | str | None = None) -> Path:
    """Get the path to the checkpoint database.

    Args:
        db_dir: Optional directory for the database. If not provided,
            uses ~/.loom/checkpoints/

    Returns:
        Path to the checkpoint database file
    """
    if db_dir is None:
        db_dir = DEFAULT_CHECKPOINT_DIR
    else:
        db_dir = Path(db_dir)

    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / DEFAULT_DB_NAME


def create_checkpointer(db_path: Path | str | None = None) -> SqliteSaver:
    """Create a SqliteSaver checkpointer for graph persistence.

    The checkpointer enables:
    - Pause/resume of graph execution
    - Recovery from failures
    - Interactive mode with review gates

    Args:
        db_path: Optional path to the SQLite database. If not provided,
            uses the default location (~/.loom/checkpoints/checkpoints.db)

    Returns:
        Configured SqliteSaver instance
    """
    if db_path is None:
        db_path = get_checkpoint_path()
    else:
        db_path = Path(db_path)

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Creating checkpointer at: {db_path}")

    # Create a direct sqlite3 connection
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    _connections.append(conn)  # Keep reference to prevent GC

    # Create and setup the checkpointer
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    return checkpointer


def create_memory_checkpointer() -> SqliteSaver:
    """Create an in-memory checkpointer for testing.

    Uses SQLite's :memory: database for ephemeral checkpoints
    that don't persist between runs.

    Returns:
        SqliteSaver using in-memory database
    """
    logger.debug("Creating in-memory checkpointer")

    # Create an in-memory sqlite3 connection
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    _connections.append(conn)  # Keep reference to prevent GC

    # Create and setup the checkpointer
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    return checkpointer


@asynccontextmanager
async def get_async_checkpointer_context(db_path: Path | str | None = None) -> AsyncIterator[MemorySaver]:
    """Get an async context manager for the checkpointer.

    Note: Currently uses MemorySaver for async compatibility. For true persistence
    across process restarts, use the sync SqliteSaver with sync graph execution.

    Args:
        db_path: Optional path to the SQLite database (currently unused for MemorySaver).

    Yields:
        MemorySaver instance for checkpointing
    """
    if db_path is None:
        db_path = get_checkpoint_path()
    else:
        db_path = Path(db_path)

    # Use a global MemorySaver keyed by path for in-process persistence
    key = str(db_path)
    if key not in _memory_savers:
        logger.info(f"Creating checkpointer (MemorySaver) for: {db_path}")
        _memory_savers[key] = MemorySaver()

    yield _memory_savers[key]


@asynccontextmanager
async def get_async_memory_checkpointer_context() -> AsyncIterator[MemorySaver]:
    """Get an async context manager for an in-memory checkpointer.

    Yields:
        MemorySaver instance for ephemeral checkpointing
    """
    logger.debug("Creating in-memory checkpointer (MemorySaver)")
    yield MemorySaver()


def generate_thread_id(description: str, timestamp: str | None = None) -> str:
    """Generate a unique thread ID for a build session.

    Thread IDs identify a specific execution of the graph,
    allowing multiple builds to be tracked independently.

    Args:
        description: Project description (used for human-readable prefix)
        timestamp: Optional timestamp string. If not provided,
            uses current UTC time.

    Returns:
        Unique thread ID string
    """
    from datetime import datetime

    from loom.output.slugify import slugify

    if timestamp is None:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    # Create a slug from the first few words of the description
    desc_slug = slugify(description[:50])

    return f"{desc_slug}-{timestamp}"


def get_checkpoint_config(thread_id: str) -> dict[str, Any]:
    """Create the configuration dict for checkpointed execution.

    Args:
        thread_id: Unique identifier for this execution thread

    Returns:
        Configuration dict for graph.invoke() or graph.ainvoke()
    """
    return {
        "configurable": {
            "thread_id": thread_id,
        }
    }


def list_checkpoints(checkpointer: SqliteSaver, thread_id: str) -> list[dict[str, Any]]:
    """List all checkpoints for a given thread.

    Args:
        checkpointer: The SqliteSaver instance
        thread_id: Thread ID to list checkpoints for

    Returns:
        List of checkpoint metadata dicts
    """
    config = get_checkpoint_config(thread_id)
    checkpoints = []

    try:
        for checkpoint in checkpointer.list(config):
            checkpoints.append({
                "thread_id": thread_id,
                "checkpoint_id": checkpoint.config.get("configurable", {}).get(
                    "checkpoint_id"
                ),
                "parent_id": checkpoint.parent_config.get("configurable", {}).get(
                    "checkpoint_id"
                )
                if checkpoint.parent_config
                else None,
                "metadata": checkpoint.metadata,
            })
    except Exception as e:
        logger.warning(f"Failed to list checkpoints for {thread_id}: {e}")

    return checkpoints


def get_latest_checkpoint(
    checkpointer: SqliteSaver, thread_id: str
) -> dict[str, Any] | None:
    """Get the most recent checkpoint for a thread.

    Args:
        checkpointer: The SqliteSaver instance
        thread_id: Thread ID to get checkpoint for

    Returns:
        Checkpoint data dict or None if no checkpoint exists
    """
    config = get_checkpoint_config(thread_id)

    try:
        checkpoint = checkpointer.get(config)
        if checkpoint:
            return {
                "thread_id": thread_id,
                "state": checkpoint.get("channel_values", {}),
                "metadata": checkpoint.get("metadata", {}),
            }
    except Exception as e:
        logger.warning(f"Failed to get checkpoint for {thread_id}: {e}")

    return None


def delete_thread_checkpoints(checkpointer: SqliteSaver, thread_id: str) -> bool:
    """Delete all checkpoints for a given thread.

    Args:
        checkpointer: The SqliteSaver instance
        thread_id: Thread ID to delete checkpoints for

    Returns:
        True if deletion was successful, False otherwise
    """
    # Note: SqliteSaver doesn't have a direct delete method,
    # but we can track thread IDs and clean up manually if needed
    logger.info(f"Checkpoint deletion requested for thread: {thread_id}")
    logger.warning("Checkpoint deletion not yet implemented in SqliteSaver")
    return False
