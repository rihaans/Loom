"""Unit tests for ChatSession (Phase 9.4).

These tests mock the graph and input reader so the chat loop can be
exercised deterministically. End-to-end chat flow with a real graph
is covered in tests/integration.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from loom.cli.chat.commands import (
    SlashCommand,
    SlashCommandResult,
)
from loom.cli.chat.session import ChatSession
from loom.config import LoomConfig


def _make_session(initial_values: dict[str, Any] | None = None) -> ChatSession:
    """Build a ChatSession with mocked renderer and input reader."""
    renderer = MagicMock()
    renderer.console = MagicMock()
    input_reader = MagicMock()
    input_reader.read = AsyncMock(return_value="hello")
    session = ChatSession(
        config=LoomConfig(),
        renderer=renderer,
        input_reader=input_reader,
    )
    return session


# ---------------------------------------------------------------------------
# Slash command dispatch
# ---------------------------------------------------------------------------


class TestSlashDispatch:
    @pytest.mark.asyncio
    async def test_help_renders_help_panel(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.HELP, args=[], raw="/help")
        result = await session._handle_slash(cmd, {})
        assert result is None
        # /help now delegates to the renderer's structured table view
        session.renderer.render_help.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_invokes_renderer_clear(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.CLEAR, args=[], raw="/clear")
        result = await session._handle_slash(cmd, {})
        assert result is None
        session.renderer.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_renders_status_panel(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.STATUS, args=[], raw="/status")
        # Pass a state with one cost entry so the panel has real numbers.
        cost = MagicMock(input_tokens=100, output_tokens=200, cost_usd=0.01)
        values = {
            "costs": [cost],
            "retry_count": 1,
            "max_retries": 2,
            "prd": None,
            "architecture": None,
            "code_files": {},
            "test_report": None,
        }
        result = await session._handle_slash(cmd, values)
        assert result is None
        session.renderer.render_status_panel.assert_called_once()
        kwargs = session.renderer.render_status_panel.call_args.kwargs
        assert kwargs["tokens"] == 300
        assert kwargs["retries"] == 1
        assert kwargs["max_retries"] == 2

    @pytest.mark.asyncio
    async def test_cost_renders_per_role_table(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.COST, args=[], raw="/cost")
        # Two cost entries from different agents — should aggregate per role.
        # `agent` is the canonical CostEntry field; the dispatcher prefers it.
        c1 = MagicMock(
            agent="product_manager", input_tokens=100,
            output_tokens=50, cost_usd=0.001,
        )
        c2 = MagicMock(
            agent="architect", input_tokens=200,
            output_tokens=80, cost_usd=0.003,
        )
        await session._handle_slash(cmd, {"costs": [c1, c2]})
        session.renderer.render_cost_table.assert_called_once()
        args, _ = session.renderer.render_cost_table.call_args
        per_role, total_tokens, total_cost = args
        assert set(per_role.keys()) == {"product_manager", "architect"}
        assert per_role["product_manager"] == (100, 50, 0.001)
        assert per_role["architect"] == (200, 80, 0.003)
        assert total_tokens == 430
        assert abs(total_cost - 0.004) < 1e-9

    @pytest.mark.asyncio
    async def test_quit_returns_exit(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.QUIT, args=[], raw="/quit")
        result = await session._handle_slash(cmd, {})
        assert result == "exit"

    @pytest.mark.asyncio
    async def test_done_returns_draft(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.DONE, args=[], raw="/done")
        result = await session._handle_slash(cmd, {})
        assert result == "draft"

    @pytest.mark.asyncio
    async def test_skip_returns_draft(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.SKIP, args=[], raw="/skip")
        result = await session._handle_slash(cmd, {})
        assert result == "draft"

    @pytest.mark.asyncio
    async def test_show_prd_renders_panel(self) -> None:
        session = _make_session()
        from loom.state.models import (
            PRD, Priority, ProjectType, UserStory,
        )
        prd = PRD(
            project_name="X",
            project_slug="x",
            project_type=ProjectType.REST_API,
            one_liner="x",
            target_users=["u"],
            user_stories=[
                UserStory(
                    id="US-001", role="u", goal="g", benefit="b",
                    acceptance_criteria=["a"], priority=Priority.P0,
                )
            ],
            must_have_features=["f"],
        )
        cmd = SlashCommandResult(
            command=SlashCommand.SHOW, args=["prd"], raw="/show prd"
        )
        await session._handle_slash(cmd, {"prd": prd})
        session.renderer.render_prd_panel.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_no_arg_renders_error(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.SHOW, args=[], raw="/show")
        await session._handle_slash(cmd, {})
        session.renderer.render_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_unknown_artifact(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(
            command=SlashCommand.SHOW, args=["bogus"], raw="/show bogus"
        )
        await session._handle_slash(cmd, {})
        session.renderer.render_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_cost_renders_table_with_real_cost_entry(self) -> None:
        """Smoke test the dispatch path with the real CostEntry model."""
        from loom.state.enums import AgentRole
        from loom.state.models import CostEntry
        session = _make_session()
        costs = [
            CostEntry(
                agent=AgentRole.PRODUCT_MANAGER,
                model="claude",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.0123,
            )
        ]
        cmd = SlashCommandResult(command=SlashCommand.COST, args=[], raw="/cost")
        await session._handle_slash(cmd, {"costs": costs})
        session.renderer.render_cost_table.assert_called_once()
        # Per-role dict should be keyed by the CostEntry's `agent` field value.
        per_role, total_tokens, total_cost = session.renderer.render_cost_table.call_args[0]
        # AgentRole values are lowercased role keys (e.g. "product_manager")
        assert AgentRole.PRODUCT_MANAGER.value in per_role
        assert total_tokens == 150
        assert abs(total_cost - 0.0123) < 1e-9

    @pytest.mark.asyncio
    async def test_unknown_command_renders_error(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.UNKNOWN, args=[], raw="/foo")
        await session._handle_slash(cmd, {})
        session.renderer.render_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_model_no_arg_shows_current(self) -> None:
        session = _make_session()
        cmd = SlashCommandResult(command=SlashCommand.MODEL, args=[], raw="/model")
        await session._handle_slash(cmd, {})
        session.renderer.render_status.assert_called_once()


# ---------------------------------------------------------------------------
# Read input behaviour
# ---------------------------------------------------------------------------


class TestReadInput:
    @pytest.mark.asyncio
    async def test_read_returns_text(self) -> None:
        session = _make_session()
        session.input_reader.read = AsyncMock(return_value="hello")
        text = await session._read_input()
        assert text == "hello"

    @pytest.mark.asyncio
    async def test_read_returns_none_on_eof(self) -> None:
        session = _make_session()
        session.input_reader.read = AsyncMock(side_effect=EOFError())
        text = await session._read_input()
        assert text is None

    @pytest.mark.asyncio
    async def test_read_returns_none_on_keyboard_interrupt(self) -> None:
        session = _make_session()
        session.input_reader.read = AsyncMock(side_effect=KeyboardInterrupt())
        text = await session._read_input()
        assert text is None


# ---------------------------------------------------------------------------
# New-message rendering
# ---------------------------------------------------------------------------


class TestRenderNewMessages:
    @pytest.mark.asyncio
    async def test_renders_only_unseen_ai_messages(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        session = _make_session()
        session.renderer.render_agent_message_animated = AsyncMock()
        # Pretend we've already shown 2 PM messages
        session._rendered_count["product_manager"] = 2

        history = [
            HumanMessage(content="user msg 1"),
            AIMessage(content="ai msg 1"),
            AIMessage(content="ai msg 2 NEW"),
        ]
        values = {"agent_messages": {"product_manager": history}}
        await session._render_new_agent_messages(values)

        # Only 1 new AI message should have been rendered
        assert session.renderer.render_agent_speaker.call_count == 1
        assert session.renderer.render_agent_message_animated.call_count == 1
        # Cursor should be updated for that role
        assert session._rendered_count["product_manager"] == 3

    @pytest.mark.asyncio
    async def test_renders_prd_panel_on_done(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage
        from loom.state.models import (
            PRD, Priority, ProjectType, UserStory,
        )

        session = _make_session()
        session.renderer.render_agent_message_animated = AsyncMock()
        prd = PRD(
            project_name="X", project_slug="x",
            project_type=ProjectType.REST_API,
            one_liner="x", target_users=["u"],
            user_stories=[
                UserStory(
                    id="US-001", role="u", goal="g", benefit="b",
                    acceptance_criteria=["a"], priority=Priority.P0,
                )
            ],
            must_have_features=["f"],
        )
        session._current_role = "product_manager"
        history = [
            HumanMessage(content="x"),
            AIMessage(content="here is the PRD"),
        ]
        values = {
            "agent_messages": {"product_manager": history},
            "agent_status": "done",
            "prd": prd,
        }
        await session._render_new_agent_messages(values)
        session.renderer.render_prd_panel.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_messages_no_render(self) -> None:
        session = _make_session()
        session.renderer.render_agent_message_animated = AsyncMock()
        await session._render_new_agent_messages({})
        # Renderer methods on agent messages should not have been called
        session.renderer.render_agent_speaker.assert_not_called()

    @pytest.mark.asyncio
    async def test_renders_new_role_after_previous_role_finished(self) -> None:
        """Bug regression: PM had 4 messages, Architect starts with 2 —
        a single shared counter would skip Architect's messages because
        2 <= 4. Per-role counter must render them."""
        from langchain_core.messages import AIMessage, HumanMessage

        session = _make_session()
        session.renderer.render_agent_message_animated = AsyncMock()
        # Pretend PM already emitted 4 messages (2 turns, all rendered)
        session._rendered_count["product_manager"] = 4

        # Architect just produced its first 2 messages
        values = {
            "agent_messages": {
                "product_manager": [HumanMessage(content="x"),
                                    AIMessage(content="x")] * 2,
                "architect": [
                    HumanMessage(content="please propose"),
                    AIMessage(content="Stack: FastAPI + React. Sound good?"),
                ],
            },
        }
        await session._render_new_agent_messages(values)

        # Architect's AI message must have been rendered, even though its
        # count (2) is less than PM's prior count (4).
        speaker_calls = session.renderer.render_agent_speaker.call_args_list
        roles_rendered = [c.args[0] for c in speaker_calls]
        assert "architect" in roles_rendered
        # PM count untouched (we'd already rendered all of its 4 messages)
        assert session._rendered_count["product_manager"] == 4
        # Architect cursor updated
        assert session._rendered_count["architect"] == 2
