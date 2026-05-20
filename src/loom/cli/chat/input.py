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
        "prompt.you": "bold #00d9ff",
        "prompt.arrow": "#ff5fd2 bold",
        # Completer popup colors
        "completion-menu.completion": "bg:#1a1a2e #ffffff",
        "completion-menu.completion.current": "bg:#00d9ff #000000 bold",
        "completion-menu.meta.completion": "bg:#1a1a2e #88c0d0",
        "completion-menu.meta.completion.current": "bg:#00d9ff #000000",
    }
)


# Canonical slash commands surfaced in the autocomplete popup. Each entry is
# (display, meta) — the display is what gets inserted (including the leading
# slash), the meta is the right-column description.
_SLASH_COMPLETIONS: list[tuple[str, str]] = [
    ("/help", "Show command reference"),
    ("/status", "Show current build state"),
    ("/clear", "Clear screen (keep transcript)"),
    ("/cost", "Show running token and dollar cost"),
    ("/done", "Tell the current agent to commit"),
    ("/skip", "Accept current proposal and proceed"),
    ("/show prd", "Render the PRD artifact"),
    ("/show architecture", "Render the architecture artifact"),
    ("/show code", "Render the code summary"),
    ("/show tests", "Render the test report"),
    ("/back", "Restore the previous checkpoint"),
    ("/restart", "Discard current build, start over"),
    ("/save", "Save the current chat transcript"),
    ("/model", "Switch active LLM (with arg) or show current"),
    ("/quit", "Exit the session"),
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
        for display, meta in _SLASH_COMPLETIONS:
            if display.lower().startswith(prefix):
                yield Completion(
                    text=display,
                    start_position=-len(text),
                    display=display,
                    display_meta=meta,
                )


def _build_keybindings() -> KeyBindings:
    """Return the key-binding map.

    Esc-Enter inserts a newline so users can paste multi-line specs.
    Plain Enter submits.
    """
    kb = KeyBindings()

    @kb.add("escape", "enter")
    def _(event) -> None:
        event.current_buffer.insert_text("\n")

    return kb


class ChatInputReader:
    """Async input reader backed by prompt_toolkit.

    Each instance keeps its own history buffer so arrow-up recalls the
    previous user message.
    """

    def __init__(self, prompt_text: str | None = None) -> None:
        # Default prompt: "You ▸ " — colored bicolor (You in cyan, ▸ in magenta)
        self.prompt_text = prompt_text
        self._history = InMemoryHistory()

        if prompt_text is not None:
            # Caller-supplied custom prompt — render in single style for backward compat
            message = [("class:prompt.you", prompt_text)]
        else:
            message = [
                ("class:prompt.you", "You "),
                ("class:prompt.arrow", "▸ "),
            ]

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
        try:
            text = await self._session.prompt_async()
        except KeyboardInterrupt:
            raise
        except EOFError:
            raise
        return text

    def add_to_history(self, text: str) -> None:
        """Append text to the input history buffer."""
        if text and text.strip():
            self._history.append_string(text)
