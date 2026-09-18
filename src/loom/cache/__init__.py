"""Content-addressed cache for generated artifacts."""

from loom.cache.store import (
    ArtifactCache,
    CacheStats,
    cache_key,
    get_cache,
    set_cache,
)

__all__ = [
    "ArtifactCache",
    "CacheStats",
    "cache_key",
    "get_cache",
    "set_cache",
]
