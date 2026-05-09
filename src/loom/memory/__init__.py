"""Memory system for self-learning across builds.

This module provides vector-based retrieval to improve builds over time.
Past successful builds are stored and retrieved as few-shot context
for the Architect agent.
"""

from loom.memory.models import MemoryConfig, MemoryContext, MemoryRecord

__all__ = [
    "MemoryConfig",
    "MemoryContext",
    "MemoryRecord",
]
