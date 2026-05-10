"""Input reader for the chat REPL.

Wraps prompt_toolkit to provide:
  - Arrow-key history (per-session)
  - Ctrl-C to cancel current step (raises KeyboardInterrupt)
  - Ctrl-D to exit (raises EOFError)
  - Esc-Enter for multi-line input (paste support)
"""

from __future__ import annotations

import logging

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

logger = logging.getLogger(__name__)


# Visual style for the user prompt — matches the chat renderer's brand color.
_USER_PROMPT_STYLE = Style.from_dict(
    {
        "prompt.you": "bold #00d9ff",
        "prompt.arrow": "#ff5fd2 bold",
    }
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
