"""Transcript persistence for chat sessions.

Each chat session writes a JSONL file under ~/.loom/chats/<thread_id>.jsonl
with one JSON object per event:
  - user_input      {role: "user", content: str}
  - agent_message   {role: "assistant", agent: str, content: str}
  - slash_command   {role: "system", command: str, args: list}
  - state_snapshot  {role: "system", snapshot: dict, timestamp: ISO-8601}

The format is intentionally append-only and tail-readable so it doubles as
a debug log.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from loom._time import now_utc

logger = logging.getLogger(__name__)

DEFAULT_CHAT_DIR = Path.home() / ".loom" / "chats"


def get_chat_path(thread_id: str, base_dir: Path | None = None) -> Path:
    """Return the JSONL path for a given chat thread."""
    base = base_dir if base_dir is not None else DEFAULT_CHAT_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{thread_id}.jsonl"


def append_event(path: Path, event: dict[str, Any]) -> None:
    """Append one event as a JSON line to the transcript file."""
    enriched = {"timestamp": now_utc().isoformat(), **event}
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(enriched, default=_json_default) + "\n")
    except OSError as e:
        logger.warning(f"Failed to write transcript event to {path}: {e}")


def _json_default(obj: Any) -> Any:
    """Best-effort JSON serializer for non-JSON-native values."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def list_transcripts(base_dir: Path | None = None) -> list[dict[str, Any]]:
    """List recent chat transcripts.

    Returns:
        A list of {thread_id, path, modified_at, size_bytes} dicts,
        sorted most-recent-first.
    """
    base = base_dir if base_dir is not None else DEFAULT_CHAT_DIR
    if not base.exists():
        return []
    entries = []
    for p in base.glob("*.jsonl"):
        try:
            stat = p.stat()
            entries.append(
                {
                    "thread_id": p.stem,
                    "path": str(p),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "size_bytes": stat.st_size,
                }
            )
        except OSError:
            continue
    entries.sort(key=lambda e: str(e["modified_at"]), reverse=True)
    return entries


def read_transcript(thread_id: str, base_dir: Path | None = None) -> list[dict[str, Any]]:
    """Read all events for a thread."""
    path = get_chat_path(thread_id, base_dir=base_dir)
    if not path.exists():
        return []
    events = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping malformed transcript line: {e}")
    return events
