"""Centralised UTC clock.

``datetime.utcnow()`` is deprecated as of Python 3.12 (and was always a footgun:
it returned a *naive* datetime that merely happened to hold UTC). This module is
the one place Loom reads the wall clock, so timestamps are consistent and we have
a single seam to freeze in tests.
"""

from datetime import UTC, datetime


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)
