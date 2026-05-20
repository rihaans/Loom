"""Unit tests for the slash command parser (Phase 9.4)."""

from loom.cli.chat.commands import (
    HELP_ENTRIES,
    HELP_TEXT,
    SlashCommand,
    SlashCommandParser,
)


class TestIsSlashCommand:
    def test_starts_with_slash(self) -> None:
        assert SlashCommandParser.is_slash_command("/help") is True

    def test_with_leading_whitespace(self) -> None:
        assert SlashCommandParser.is_slash_command("   /quit") is True

    def test_plain_text(self) -> None:
        assert SlashCommandParser.is_slash_command("hello world") is False

    def test_empty_string(self) -> None:
        assert SlashCommandParser.is_slash_command("") is False


class TestParse:
    def test_help(self) -> None:
        result = SlashCommandParser.parse("/help")
        assert result.command == SlashCommand.HELP
        assert result.args == []

    def test_help_alias_question_mark(self) -> None:
        assert SlashCommandParser.parse("/?").command == SlashCommand.HELP

    def test_help_alias_h(self) -> None:
        assert SlashCommandParser.parse("/h").command == SlashCommand.HELP

    def test_quit(self) -> None:
        assert SlashCommandParser.parse("/quit").command == SlashCommand.QUIT

    def test_quit_alias_q(self) -> None:
        assert SlashCommandParser.parse("/q").command == SlashCommand.QUIT

    def test_quit_alias_exit(self) -> None:
        assert SlashCommandParser.parse("/exit").command == SlashCommand.QUIT

    def test_done(self) -> None:
        assert SlashCommandParser.parse("/done").command == SlashCommand.DONE

    def test_done_alias_yes(self) -> None:
        assert SlashCommandParser.parse("/yes").command == SlashCommand.DONE

    def test_done_alias_y(self) -> None:
        assert SlashCommandParser.parse("/y").command == SlashCommand.DONE

    def test_done_alias_draft(self) -> None:
        assert SlashCommandParser.parse("/draft").command == SlashCommand.DONE

    def test_skip(self) -> None:
        assert SlashCommandParser.parse("/skip").command == SlashCommand.SKIP

    def test_back(self) -> None:
        assert SlashCommandParser.parse("/back").command == SlashCommand.BACK

    def test_back_alias_undo(self) -> None:
        assert SlashCommandParser.parse("/undo").command == SlashCommand.BACK

    def test_restart(self) -> None:
        assert SlashCommandParser.parse("/restart").command == SlashCommand.RESTART

    def test_restart_alias_reset(self) -> None:
        assert SlashCommandParser.parse("/reset").command == SlashCommand.RESTART

    def test_show_with_arg(self) -> None:
        result = SlashCommandParser.parse("/show prd")
        assert result.command == SlashCommand.SHOW
        assert result.args == ["prd"]

    def test_save_with_name(self) -> None:
        result = SlashCommandParser.parse("/save my-build")
        assert result.command == SlashCommand.SAVE
        assert result.args == ["my-build"]

    def test_save_no_args(self) -> None:
        result = SlashCommandParser.parse("/save")
        assert result.command == SlashCommand.SAVE
        assert result.args == []

    def test_model_with_arg(self) -> None:
        result = SlashCommandParser.parse("/model anthropic:sonnet")
        assert result.command == SlashCommand.MODEL
        assert result.args == ["anthropic:sonnet"]

    def test_cost(self) -> None:
        assert SlashCommandParser.parse("/cost").command == SlashCommand.COST

    def test_cost_alias_tokens(self) -> None:
        assert SlashCommandParser.parse("/tokens").command == SlashCommand.COST

    def test_unknown_command(self) -> None:
        result = SlashCommandParser.parse("/foobar")
        assert result.command == SlashCommand.UNKNOWN

    def test_empty_slash(self) -> None:
        result = SlashCommandParser.parse("/")
        assert result.command == SlashCommand.UNKNOWN

    def test_case_insensitive(self) -> None:
        assert SlashCommandParser.parse("/HELP").command == SlashCommand.HELP
        assert SlashCommandParser.parse("/Done").command == SlashCommand.DONE

    def test_leading_whitespace_stripped(self) -> None:
        assert SlashCommandParser.parse("  /quit  ").command == SlashCommand.QUIT

    def test_raw_preserved(self) -> None:
        result = SlashCommandParser.parse("/show prd")
        assert result.raw == "/show prd"

    def test_plain_text_returns_unknown(self) -> None:
        result = SlashCommandParser.parse("hello world")
        assert result.command == SlashCommand.UNKNOWN


class TestHelpText:
    def test_help_text_lists_commands(self) -> None:
        assert "/help" in HELP_TEXT
        assert "/quit" in HELP_TEXT
        assert "/done" in HELP_TEXT
        assert "/show" in HELP_TEXT
        assert "/save" in HELP_TEXT
        assert "/model" in HELP_TEXT
        assert "/cost" in HELP_TEXT
        assert "/status" in HELP_TEXT
        assert "/clear" in HELP_TEXT


class TestStatusCommand:
    def test_status_canonical(self) -> None:
        assert SlashCommandParser.parse("/status").command == SlashCommand.STATUS

    def test_status_alias_info(self) -> None:
        assert SlashCommandParser.parse("/info").command == SlashCommand.STATUS


class TestClearCommand:
    def test_clear_canonical(self) -> None:
        assert SlashCommandParser.parse("/clear").command == SlashCommand.CLEAR

    def test_clear_alias_cls(self) -> None:
        assert SlashCommandParser.parse("/cls").command == SlashCommand.CLEAR


class TestHelpEntries:
    """The structured HELP_ENTRIES is what the renderer consumes."""

    def test_entries_is_tuple_of_four(self) -> None:
        for row in HELP_ENTRIES:
            assert isinstance(row, tuple)
            assert len(row) == 4  # canonical, aliases, description, category

    def test_entries_contain_new_commands(self) -> None:
        canonicals = {row[0] for row in HELP_ENTRIES}
        assert "/status" in canonicals
        assert "/clear" in canonicals
        assert "/help" in canonicals
        assert "/quit" in canonicals

    def test_categories_are_consistent(self) -> None:
        # Each entry belongs to one of a small set of known categories — guard
        # against typos that would create one-row sections.
        allowed = {"Session", "Workflow", "Artifacts", "Config"}
        for row in HELP_ENTRIES:
            assert row[3] in allowed, f"Unknown category: {row[3]}"
