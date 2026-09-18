"""Content-addressed cache for agent artifacts.

Every Loom build starts from scratch: change one word of the description and
you pay for the PRD, the architecture, both developers, the reviewer and DevOps
all over again. That makes iterating expensive, which is the main reason a
generate-a-project tool gets tried once and abandoned.

This module caches each agent's *output artifact* against a hash of everything
that determined it - the prompts, the resolved inputs, the model, and the
schema. An identical request is then free and instant, and a change that only
affects a later stage reuses every earlier one.

The cache is deliberately conservative: the key includes the full rendered
input, so any change at all misses. It can never return an artifact that a
fresh call would not have produced from the same inputs, on the same model.

Two things legitimately reduce the hit rate, both measured:

* **Memory.** The memory system injects "similar past builds" into the
  architect's prompt, and every build adds to it - so the next build's
  architect prompt genuinely differs and correctly misses, taking everything
  downstream with it. Use ``--no-memory`` for reproducible, cache-friendly runs.
Parse retries used to have the same effect - the artifact was cached under the
retried prompt, so a rerun starting from attempt 1 always missed and cascaded.
Agents now name the *logical* request via ``CACHE_SCOPE_KEY``, so every attempt
shares one entry.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_CACHE_DIR = Path.home() / ".loom" / "artifacts"

# Bump when the cache entry format changes, to invalidate old entries.
CACHE_VERSION = "1"

# Env var to disable caching globally (CLI flag sets this too).
DISABLE_ENV = "LOOM_NO_CACHE"


@dataclass
class CacheStats:
    """Hit/miss accounting for one process."""

    hits: int = 0
    misses: int = 0
    writes: int = 0
    tokens_saved_estimate: int = 0
    agents_hit: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total else 0.0


def cache_key(
    *,
    agent: str,
    system_prompt: str,
    human_template: str,
    prompt_input: dict[str, Any],
    model_id: str,
    output_model: str,
) -> str:
    """Build a stable key from everything that determined the artifact.

    Anything that could change the model's output is part of the key, so a hit
    is only ever returned for a genuinely identical request.
    """
    payload = {
        "v": CACHE_VERSION,
        "agent": agent,
        "system": system_prompt,
        "template": human_template,
        # sort_keys so dict ordering never changes the hash
        "input": json.dumps(prompt_input, sort_keys=True, default=str),
        "model": model_id,
        "schema": output_model,
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class ArtifactCache:
    """Filesystem cache mapping a request hash to a serialized artifact."""

    def __init__(self, cache_dir: Path | None = None, enabled: bool = True):
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.enabled = enabled and os.environ.get(DISABLE_ENV, "").lower() not in (
            "1",
            "true",
            "yes",
        )
        self.stats = CacheStats()

    def _path(self, key: str) -> Path:
        # Shard by first two chars so one directory doesn't collect everything.
        return self.cache_dir / key[:2] / f"{key}.json"

    def get(self, key: str, output_model: type[T], agent: str = "") -> T | None:
        """Return the cached artifact for `key`, or None.

        A corrupt or unreadable entry is treated as a miss and removed - the
        cache is an optimisation and must never be able to fail a build.
        """
        if not self.enabled:
            return None

        path = self._path(key)
        if not path.is_file():
            self.stats.misses += 1
            return None

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            artifact = output_model.model_validate(raw["artifact"])
        except Exception as e:
            logger.debug(f"Discarding unusable cache entry {key[:12]}: {e}")
            try:
                path.unlink()
            except OSError:
                pass
            self.stats.misses += 1
            return None

        self.stats.hits += 1
        self.stats.tokens_saved_estimate += int(raw.get("input_tokens_estimate", 0))
        if agent:
            self.stats.agents_hit.append(agent)
        logger.info(f"Cache hit for {agent or 'agent'} ({key[:12]}) - skipping LLM call")
        return artifact

    def put(
        self,
        key: str,
        artifact: BaseModel,
        *,
        agent: str = "",
        input_tokens_estimate: int = 0,
    ) -> None:
        """Store an artifact. Failures are logged, never raised."""
        if not self.enabled:
            return

        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "version": CACHE_VERSION,
                "agent": agent,
                "created_at": time.time(),
                "artifact_type": type(artifact).__name__,
                "input_tokens_estimate": input_tokens_estimate,
                "artifact": artifact.model_dump(mode="json"),
            }
            # Write via a temp file so a crash can't leave a truncated entry.
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(entry), encoding="utf-8")
            tmp.replace(path)
            self.stats.writes += 1
        except Exception as e:
            logger.debug(f"Could not cache artifact for {agent}: {e}")

    def clear(self) -> int:
        """Delete every entry. Returns how many were removed."""
        if not self.cache_dir.is_dir():
            return 0
        removed = 0
        for p in self.cache_dir.rglob("*.json"):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def entry_count(self) -> int:
        """How many artifacts are currently cached."""
        if not self.cache_dir.is_dir():
            return 0
        return sum(1 for _ in self.cache_dir.rglob("*.json"))

    def size_bytes(self) -> int:
        """Total bytes on disk."""
        if not self.cache_dir.is_dir():
            return 0
        return sum(p.stat().st_size for p in self.cache_dir.rglob("*.json"))


_cache: ArtifactCache | None = None


def get_cache() -> ArtifactCache:
    """Get the process-wide artifact cache."""
    global _cache
    if _cache is None:
        _cache = ArtifactCache()
    return _cache


def set_cache(cache: ArtifactCache | None) -> None:
    """Replace the process-wide cache (used by the CLI and by tests)."""
    global _cache
    _cache = cache
