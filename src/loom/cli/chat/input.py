"""Input reader for the chat REPL.

Wraps prompt_toolkit to provide:
  - Arrow-key history (per-session)
  - Ctrl-C to cancel current step (raises KeyboardInterrupt)
  - Ctrl-D to exit (raises EOFError)
  - Esc-Enter for multi-line input (paste support)
  - Slash command autocomplete with descriptions
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

logger = logging.getLogger(__name__)


# Visual style for the user prompt — matches the chat renderer's brand color.
_USER_PROMPT_STYLE = Style.from_dict(
    {
        "bar": "#454a53",  # dim gutter
        "prompt": "bold #c9b68c",  # champagne chevron
        "prompt.you": "bold #c9b68c",
        "prompt.arrow": "#c9b68c",
        # Completer popup — a quiet floating menu.
        "completion-menu": "bg:#15171c",
        "completion-menu.completion": "bg:#15171c #a2a7b0",
        "completion-menu.completion.current": "bg:#c9b68c #15171c bold",
        "completion-menu.meta.completion": "bg:#15171c #6a707a italic",
        "completion-menu.meta.completion.current": "bg:#b7a679 #15171c italic",
        "scrollbar.background": "bg:#20232a",
        "scrollbar.button": "bg:#c9b68c",
    }
)


# Single accent — the champagne used across the whole REPL.
_ACCENT = "#c9b68c"

# Canonical slash commands for the autocomplete popup: (display, meta, category).
# The display is inserted (with leading slash); the category tints its ◆ marker.
_SLASH_COMPLETIONS: list[tuple[str, str, str]] = [
    ("/help", "Show command reference", "session"),
    ("/status", "Show current build state", "config"),
    ("/cost", "Running token & dollar cost", "config"),
    ("/model", "Switch or show the active LLM", "config"),
    ("/done", "Tell the current agent to commit", "workflow"),
    ("/skip", "Accept the proposal and proceed", "workflow"),
    ("/back", "Restore the previous checkpoint", "workflow"),
    ("/restart", "Discard build, start over", "workflow"),
    ("/show prd", "Render the PRD artifact", "artifacts"),
    ("/show architecture", "Render the architecture", "artifacts"),
    ("/show code", "Render the code summary", "artifacts"),
    ("/show tests", "Render the test report", "artifacts"),
    ("/save", "Save the chat transcript", "session"),
    ("/clear", "Clear screen (keep transcript)", "session"),
    ("/quit", "Exit the session", "session"),
]


class _SlashCommandCompleter(Completer):
    """Popup completer that fires only when input starts with `/`.

    Mirrors Claude Code's slash-menu behavior: type `/` and a menu of every
    available command appears with a one-line description. We match by prefix
    against the leading word, so `/sh` narrows to the `/show *` family and
    `/c` narrows to `/clear` and `/cost`.
    """

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        # Only show completions for the slash-command form, and only while
        # the user is still on the first token (no space yet).
        if not text.startswith("/"):
            return
        if " " in text and not text.startswith("/show "):
            # Past the first word — let the user type freely (except for /show
            # where we let them pick the artifact type).
            return

        prefix = text.lower()
        for display, meta, _category in _SLASH_COMPLETIONS:
            if display.lower().startswith(prefix):
                yield Completion(
                    text=display,
                    start_position=-len(text),
                    display=[(f"fg:{_ACCENT}", "◇ "), ("", display)],
                    display_meta=meta,
                )


def _build_keybindings() -> KeyBindings:
    """Return the key-binding map.

    Esc-Enter inserts a newline so users can paste multi-line specs.
    Plain Enter submits.
    """
    kb = KeyBindings()

    @kb.add("escape", "enter")
    def _(event: Any) -> None:
        event.current_buffer.insert_text("\n")

    return kb


class ChatInputReader:
    """Async input reader backed by prompt_toolkit.

    Each instance keeps its own history buffer so arrow-up recalls the
    previous user message.
    """

    def __init__(self, prompt_text: str | None = None) -> None:
        self.prompt_text = prompt_text
        self._history = InMemoryHistory()

        # A clean, robust prompt: a coral accent bar + chevron. (A drawn box around
        # a single-line prompt_toolkit prompt doesn't render reliably across
        # terminals, so we keep the prompt itself crisp and let the transcript
        # above carry the visual weight.)
        message: Any
        if prompt_text is not None:
            message = [("class:prompt.you", prompt_text)]
        else:
            message = [("class:bar", "▌ "), ("class:prompt", "❯ ")]

        self._session: PromptSession[str] = PromptSession(
            history=self._history,
            key_bindings=_build_keybindings(),
            multiline=False,
            style=_USER_PROMPT_STYLE,
            message=message,
            completer=_SlashCommandCompleter(),
            complete_while_typing=True,
        )

    async def read(self) -> str:
        """Read a single line of input from the user.

        Returns:
            The user's input string (may be empty).

        Raises:
            KeyboardInterrupt: User pressed Ctrl-C.
            EOFError: User pressed Ctrl-D.
        """
        return await self._session.prompt_async()

    def add_to_history(self, text: str) -> None:
        """Append text to the input history buffer."""
        if text and text.strip():
            self._history.append_string(text)
