"""Slash command parser for the chat REPL.

A slash command is any user input starting with `/`. The parser splits the
command name from arguments and returns a structured `SlashCommandResult`
that the ChatSession dispatches to handlers.

Supported commands (canonical list — see CHAT_INTERFACE.md § 7):
  /help           Show command reference
  /quit, /q       Exit the session (saves checkpoint)
  /done           Signal the current agent to draft (e.g. PM → write PRD)
  /restart        Discard current build, start over
  /back           Restore the previous checkpoint (one step back)
  /show <type>    Render an artifact (prd, architecture, code, tests)
  /save [name]    Persist the current chat transcript
  /skip           Accept the current proposal as-is and proceed
  /model <id>     Switch the active LLM
  /cost           Print running token / dollar cost
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SlashCommand(StrEnum):
    """Canonical command identifiers."""

    HELP = "help"
    QUIT = "quit"
    DONE = "done"
    RESTART = "restart"
    BACK = "back"
    SHOW = "show"
    SAVE = "save"
    SKIP = "skip"
    MODEL = "model"
    COST = "cost"
    UNKNOWN = "unknown"


# Aliases for usability
_ALIASES: dict[str, SlashCommand] = {
    "h": SlashCommand.HELP,
    "?": SlashCommand.HELP,
    "q": SlashCommand.QUIT,
    "exit": SlashCommand.QUIT,
    "draft": SlashCommand.DONE,
    "yes": SlashCommand.DONE,
    "y": SlashCommand.DONE,
    "reset": SlashCommand.RESTART,
    "undo": SlashCommand.BACK,
    "show": SlashCommand.SHOW,
    "save": SlashCommand.SAVE,
    "skip": SlashCommand.SKIP,
    "model": SlashCommand.MODEL,
    "cost": SlashCommand.COST,
    "tokens": SlashCommand.COST,
}


@dataclass(frozen=True)
class SlashCommandResult:
    """Parsed slash command.

    Attributes:
        command: The canonical SlashCommand
        args: Positional argument tokens after the command name
        raw: The original input string (for error messages)
    """

    command: SlashCommand
    args: list[str] = field(default_factory=list)
    raw: str = ""


class SlashCommandParser:
    """Parses user input into structured slash commands.

    Anything not starting with `/` is NOT a slash command — the chat
    session should treat it as conversational input.
    """

    @staticmethod
    def is_slash_command(text: str) -> bool:
        """Return True if the input is a slash command (starts with /)."""
        return text.strip().startswith("/")

    @staticmethod
    def parse(text: str) -> SlashCommandResult:
        """Parse a user input string into a SlashCommandResult.

        Args:
            text: User input. Must start with '/'; otherwise UNKNOWN is returned.

        Returns:
            SlashCommandResult with command, args, and the original text.
        """
        raw = text
        stripped = text.strip()
        if not stripped.startswith("/"):
            return SlashCommandResult(
                command=SlashCommand.UNKNOWN, args=[], raw=raw
            )

        # Strip the leading '/'
        body = stripped[1:].strip()
        if not body:
            return SlashCommandResult(
                command=SlashCommand.UNKNOWN, args=[], raw=raw
            )

        parts = body.split()
        cmd_token = parts[0].lower()
        args = parts[1:]

        # Check direct match
        try:
            cmd = SlashCommand(cmd_token)
        except ValueError:
            cmd = _ALIASES.get(cmd_token, SlashCommand.UNKNOWN)

        return SlashCommandResult(command=cmd, args=args, raw=raw)


# Help text for /help — kept here so commands.py remains the single source of truth.
HELP_TEXT = """\
Available commands:

  /help, /?           Show this help
  /quit, /q           Exit the session
  /done, /yes, /y     Tell the current agent to commit (e.g. draft the PRD)
  /skip               Accept the current proposal and proceed
  /back, /undo        Restore the previous checkpoint
  /restart, /reset    Start over from the beginning
  /show <type>        Render an artifact: prd | architecture | code | tests
  /save [name]        Save the current chat transcript
  /model <id>         Switch active LLM
  /cost, /tokens      Show running token and dollar cost

Anything else you type is a message to the active agent.
"""
