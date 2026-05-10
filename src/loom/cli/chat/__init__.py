"""Chat REPL for Loom — the interactive entry point (Phase 9).

The chat REPL is the new primary user interface. It opens a styled terminal
session where users collaborate with each agent (PM, Architect) via
multi-turn conversation, then watch the parallel build pipeline run.

Public exports:
- ChatSession: the loop driver that owns the chat state machine
- ChatRenderer: rich-based renderer for messages, panels, banners
- SlashCommandParser: parses /help, /quit, /done, etc.
"""

from loom.cli.chat.commands import (
    SlashCommand,
    SlashCommandParser,
    SlashCommandResult,
)
from loom.cli.chat.renderer import ChatRenderer
from loom.cli.chat.session import ChatSession

__all__ = [
    "ChatRenderer",
    "ChatSession",
    "SlashCommand",
    "SlashCommandParser",
    "SlashCommandResult",
]
