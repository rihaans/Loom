"""Factory functions for memory system components."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from loom.memory.embedder import Embedder, LocalEmbedder, OpenAIEmbedder
from loom.memory.models import MemoryConfig
from loom.memory.store import InMemoryStore, LanceDBStore, MemoryStore

if TYPE_CHECKING:
    from loom.config import LoomConfig

logger = logging.getLogger(__name__)

# Global singletons (lazy initialized)
_embedder: Embedder | None = None
_store: MemoryStore | None = None


def get_memory_config(config: "LoomConfig") -> MemoryConfig:
    """Extract memory config from main config.

    Args:
        config: Main Loom configuration.

    Returns:
        MemoryConfig instance.
    """
    return getattr(config, "memory", MemoryConfig())


def get_embedder(config: MemoryConfig | None = None) -> Embedder:
    """Get or create the embedder singleton.

    Args:
        config: Optional memory configuration.

    Returns:
        An Embedder instance.
    """
    global _embedder

    if _embedder is not None:
        return _embedder

    if config is None:
        config = MemoryConfig()

    if config.embedder == "openai":
        _embedder = OpenAIEmbedder(model_name=config.embedder_model)
    else:
        _embedder = LocalEmbedder(model_name=config.embedder_model)

    return _embedder


def get_memory_store(config: MemoryConfig | None = None) -> MemoryStore:
    """Get or create the memory store singleton.

    Args:
        config: Optional memory configuration.

    Returns:
        A MemoryStore instance.
    """
    global _store

    if _store is not None:
        return _store

    if config is None:
        config = MemoryConfig()

    db_path = Path(config.db_path).expanduser()

    try:
        _store = LanceDBStore(db_path)
        logger.info(f"Initialized LanceDB store at {db_path}")
    except ImportError:
        logger.warning("LanceDB not available, using in-memory store")
        _store = InMemoryStore()

    return _store


def reset_singletons() -> None:
    """Reset the global singletons (for testing)."""
    global _embedder, _store
    _embedder = None
    _store = None


def is_memory_available() -> bool:
    """Check if memory dependencies are available.

    Returns:
        True if lancedb and sentence-transformers are installed.
    """
    try:
        import lancedb  # noqa: F401
        import sentence_transformers  # noqa: F401

        return True
    except ImportError:
        return False
