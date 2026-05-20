"""Unit tests for the chat input completer."""

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from loom.cli.chat.input import _SLASH_COMPLETIONS, _SlashCommandCompleter


def _complete(text: str) -> list[str]:
    """Return the list of completion display strings for a given input."""
    completer = _SlashCommandCompleter()
    doc = Document(text=text, cursor_position=len(text))
    return [c.text for c in completer.get_completions(doc, CompleteEvent())]


class TestSlashCompleter:
    def test_no_completions_for_plain_text(self) -> None:
        # Not a slash command — completer stays out of the way.
        assert _complete("hello") == []

    def test_single_slash_offers_every_command(self) -> None:
        results = _complete("/")
        # Every registered command should appear.
        assert len(results) == len(_SLASH_COMPLETIONS)
        assert "/help" in results
        assert "/status" in results
        assert "/clear" in results

    def test_prefix_filter(self) -> None:
        # Typing `/c` narrows to commands starting with /c.
        results = _complete("/c")
        assert "/clear" in results
        assert "/cost" in results
        assert "/help" not in results

    def test_status_prefix(self) -> None:
        results = _complete("/sta")
        assert results == ["/status"]

    def test_show_subcommands(self) -> None:
        # `/show ` past the first word still offers artifact-type completions.
        results = _complete("/show ")
        # All four /show variants should be present.
        assert "/show prd" in results
        assert "/show architecture" in results
        assert "/show code" in results
        assert "/show tests" in results

    def test_non_show_past_first_word_quiet(self) -> None:
        # A normal command followed by a space — the user is typing args;
        # don't keep popping completions over their text.
        assert _complete("/model claude-3") == []
