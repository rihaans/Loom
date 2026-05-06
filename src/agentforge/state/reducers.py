"""Reducer functions for LangGraph state merging.

Reducers define how state fields are combined when multiple nodes
update the same field. LangGraph uses these via Annotated types.
"""

from typing import Any, TypeVar

T = TypeVar("T")


def merge_dicts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge two dicts, with b taking precedence on key conflicts.

    Used for fields like `code_files` where multiple agents (frontend, backend)
    write to different keys within the same dict.

    Args:
        a: Base dictionary (existing state)
        b: Update dictionary (new values from node)

    Returns:
        Merged dictionary with all keys from both, b's values winning on conflict

    Example:
        >>> merge_dicts({"frontend": f1}, {"backend": b1})
        {"frontend": f1, "backend": b1}
        >>> merge_dicts({"x": 1}, {"x": 2})
        {"x": 2}
    """
    if a is None:
        a = {}
    if b is None:
        b = {}
    return {**a, **b}


def last_value(a: T, b: T) -> T:
    """Return the last (most recent) value.

    Used for fields with a single writer like `prd`, `architecture`, etc.
    This is the default LangGraph behavior, but explicit for documentation.

    Args:
        a: Previous value
        b: New value

    Returns:
        The new value b (last write wins)
    """
    return b


def increment(a: int, b: int) -> int:
    """Add b to a (used for counters like retry_count).

    Args:
        a: Current count
        b: Amount to add (usually 1)

    Returns:
        Sum of a and b
    """
    if a is None:
        a = 0
    return a + b


def append_list(a: list[T] | None, b: list[T] | None) -> list[T]:
    """Concatenate two lists.

    Used for append-only fields like `events` and `costs`.

    Args:
        a: Existing list
        b: New items to append

    Returns:
        Concatenated list with all items from both
    """
    if a is None:
        a = []
    if b is None:
        b = []
    return a + b


def coalesce(a: T | None, b: T | None) -> T | None:
    """Return b if not None, else a.

    Used for optional fields that should only be set once.

    Args:
        a: Previous value
        b: New value (may be None)

    Returns:
        b if b is not None, otherwise a
    """
    return b if b is not None else a
