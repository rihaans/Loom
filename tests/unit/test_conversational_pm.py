"""Unit tests for the conversational Product Manager (Phase 9.1).

All LLM calls are mocked. The legacy interactive=False path is tested to
remain byte-identical to its pre-Phase-9 behaviour.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from loom.agents.product_manager import MAX_PM_TURNS, product_manager_node
from loom.config import LoomConfig
from loom.state.enums import AgentRole, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> LoomConfig:
    return LoomConfig()


def _make_mock_llm(response_text: str = "What kind of users?") -> MagicMock:
    """Return a mock LLM that replies with response_text."""
    llm = MagicMock()
    ai_msg = AIMessage(content=response_text)
    llm.ainvoke = AsyncMock(return_value=ai_msg)
    return llm


SAMPLE_PRD_DICT: dict[str, Any] = {
    "project_name": "Todo App",
    "project_slug": "todo-app",
    "project_type": "fullstack_web",
    "one_liner": "A simple todo app",
    "target_users": ["developers"],
    "user_stories": [
        {
            "id": "US-001",
            "role": "user",
            "goal": "create a todo",
            "benefit": "track tasks",
            "acceptance_criteria": ["Todo is created"],
            "priority": "P0",
        }
    ],
    "must_have_features": ["Create todo"],
}


def _make_prd_mock():
    from loom.state.models import PRD
    return PRD(**SAMPLE_PRD_DICT)


# ---------------------------------------------------------------------------
# Tests: clarifying mode
# ---------------------------------------------------------------------------


class TestClarifyingMode:
    """Tests for the interactive clarifying conversation path."""

    @pytest.mark.asyncio
    async def test_first_turn_does_not_produce_prd(self) -> None:
        """First invocation should produce a chat message, not a PRD."""
        mock_llm = _make_mock_llm("What kind of users — single or multi?")

        state = {
            "description": "todo app",
            "interactive": True,
            "agent_messages": {},
            "pending_user_input": None,
        }

        result = await product_manager_node(state, _make_config(), llm=mock_llm)

        assert result.get("prd") is None
        assert result["agent_status"] == "wait_for_input"
        assert "product_manager" in result["agent_messages"]
        history = result["agent_messages"]["product_manager"]
        # Should have: HumanMessage(description) + AIMessage(response)
        assert len(history) == 2
        assert isinstance(history[0], HumanMessage)
        assert isinstance(history[1], AIMessage)
        assert history[1].content == "What kind of users — single or multi?"

    @pytest.mark.asyncio
    async def test_user_input_appended_to_history(self) -> None:
        """PM returns only NEW messages each turn; reducer appends to existing."""
        existing_history = [
            HumanMessage(content="todo app"),
            AIMessage(content="Who are the users?"),
        ]
        mock_llm = _make_mock_llm("Great! One more question: offline or online?")

        state = {
            "description": "todo app",
            "interactive": True,
            "agent_messages": {"product_manager": existing_history},
            "pending_user_input": "just me, single user",
        }

        result = await product_manager_node(state, _make_config(), llm=mock_llm)

        assert result["agent_status"] == "wait_for_input"
        # PM returns ONLY the new messages (the reducer appends them)
        new_messages = result["agent_messages"]["product_manager"]
        assert len(new_messages) == 2
        assert isinstance(new_messages[0], HumanMessage)
        assert new_messages[0].content == "just me, single user"
        assert isinstance(new_messages[1], AIMessage)
        assert new_messages[1].content == "Great! One more question: offline or online?"

    @pytest.mark.asyncio
    async def test_ready_to_draft_sentinel_detected(self) -> None:
        """<READY_TO_DRAFT> in response triggers ready_to_draft status."""
        mock_llm = _make_mock_llm("I think we have enough. <READY_TO_DRAFT>")

        state = {
            "description": "todo app",
            "interactive": True,
            "agent_messages": {},
            "pending_user_input": None,
        }

        result = await product_manager_node(state, _make_config(), llm=mock_llm)

        assert result["agent_status"] == "ready_to_draft"

    @pytest.mark.asyncio
    async def test_sentinel_stripped_from_message(self) -> None:
        """<READY_TO_DRAFT> token must not appear in the stored message."""
        mock_llm = _make_mock_llm("Looks good to me! <READY_TO_DRAFT>")

        state = {
            "description": "todo app",
            "interactive": True,
            "agent_messages": {},
            "pending_user_input": None,
        }

        result = await product_manager_node(state, _make_config(), llm=mock_llm)

        history = result["agent_messages"]["product_manager"]
        last_ai = history[-1]
        assert "<READY_TO_DRAFT>" not in last_ai.content
        assert "Looks good to me!" in last_ai.content

    @pytest.mark.asyncio
    async def test_no_sentinel_stays_in_wait_state(self) -> None:
        """Response without sentinel keeps status at wait_for_input."""
        mock_llm = _make_mock_llm("Any deadlines or performance requirements?")

        state = {
            "description": "todo app",
            "interactive": True,
            "agent_messages": {},
            "pending_user_input": None,
        }

        result = await product_manager_node(state, _make_config(), llm=mock_llm)

        assert result["agent_status"] == "wait_for_input"

    @pytest.mark.asyncio
    async def test_agent_turn_event_emitted(self) -> None:
        """A clarifying turn should emit an AGENT_TURN event."""
        mock_llm = _make_mock_llm("Any users?")

        state = {
            "description": "todo app",
            "interactive": True,
            "agent_messages": {},
            "pending_user_input": None,
        }

        result = await product_manager_node(state, _make_config(), llm=mock_llm)

        event_types = [e.type for e in result.get("events", [])]
        assert EventType.AGENT_TURN in event_types


# ---------------------------------------------------------------------------
# Tests: turn cap
# ---------------------------------------------------------------------------


class TestTurnCap:
    """Tests for the MAX_PM_TURNS hard cap."""

    @pytest.mark.asyncio
    async def test_turn_cap_forces_ready_to_draft(self) -> None:
        """After MAX_PM_TURNS, agent_status must be ready_to_draft."""
        history = []
        for i in range(MAX_PM_TURNS):
            history.append(HumanMessage(content=f"user turn {i}"))
            history.append(AIMessage(content=f"agent turn {i}"))

        mock_llm = _make_mock_llm("Should not be called")

        state = {
            "description": "todo app",
            "interactive": True,
            "agent_messages": {"product_manager": history},
            "pending_user_input": "keep going",
        }

        result = await product_manager_node(state, _make_config(), llm=mock_llm)

        assert result["agent_status"] == "ready_to_draft"
        # LLM should NOT have been called
        mock_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_turn_cap_emits_turn_limit_event(self) -> None:
        """Turn cap should emit AGENT_TURN_LIMIT event."""
        history = []
        for i in range(MAX_PM_TURNS):
            history.extend([
                HumanMessage(content=f"h{i}"),
                AIMessage(content=f"a{i}"),
            ])

        state = {
            "description": "todo app",
            "interactive": True,
            "agent_messages": {"product_manager": history},
            "pending_user_input": "more",
        }

        result = await product_manager_node(state, _make_config(), llm=MagicMock())

        event_types = [e.type for e in result.get("events", [])]
        assert EventType.AGENT_TURN_LIMIT in event_types

    @pytest.mark.asyncio
    async def test_below_cap_does_not_force_ready(self) -> None:
        """One turn below the cap should still allow normal flow."""
        history = []
        for i in range(MAX_PM_TURNS - 1):  # one below cap
            history.extend([
                HumanMessage(content=f"h{i}"),
                AIMessage(content=f"a{i}"),
            ])

        mock_llm = _make_mock_llm("One more question?")

        state = {
            "description": "todo app",
            "interactive": True,
            "agent_messages": {"product_manager": history},
            "pending_user_input": "still here",
        }

        result = await product_manager_node(state, _make_config(), llm=mock_llm)

        # Should NOT be forced to ready_to_draft
        assert result["agent_status"] in ("wait_for_input", "ready_to_draft")
        mock_llm.ainvoke.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: drafting mode
# ---------------------------------------------------------------------------


class TestDraftingMode:
    """Tests for the __DRAFT__ trigger path."""

    @pytest.mark.asyncio
    async def test_draft_signal_produces_prd(self) -> None:
        """__DRAFT__ pending input should produce a valid PRD."""
        history = [
            HumanMessage(content="todo app"),
            AIMessage(content="Who are the users?"),
            HumanMessage(content="just me"),
        ]

        prd_mock = _make_prd_mock()

        with patch(
            "loom.agents.product_manager._pm_draft_prd",
            new_callable=AsyncMock,
            return_value=prd_mock,
        ):
            state = {
                "description": "todo app",
                "interactive": True,
                "agent_messages": {"product_manager": history},
                "pending_user_input": "__DRAFT__",
            }

            result = await product_manager_node(state, _make_config())

        assert result.get("prd") is not None
        assert result["prd"].project_slug == "todo-app"
        assert result["agent_status"] == "done"
        assert result["pending_user_input"] is None

    @pytest.mark.asyncio
    async def test_draft_clears_pending_input(self) -> None:
        """After drafting, pending_user_input must be None."""
        prd_mock = _make_prd_mock()

        with patch(
            "loom.agents.product_manager._pm_draft_prd",
            new_callable=AsyncMock,
            return_value=prd_mock,
        ):
            state = {
                "description": "todo app",
                "interactive": True,
                "agent_messages": {"product_manager": []},
                "pending_user_input": "__DRAFT__",
            }
            result = await product_manager_node(state, _make_config())

        assert result["pending_user_input"] is None

    @pytest.mark.asyncio
    async def test_draft_emits_agent_end_event(self) -> None:
        """Successful draft should emit AGENT_END event."""
        prd_mock = _make_prd_mock()

        with patch(
            "loom.agents.product_manager._pm_draft_prd",
            new_callable=AsyncMock,
            return_value=prd_mock,
        ):
            state = {
                "description": "todo app",
                "interactive": True,
                "agent_messages": {},
                "pending_user_input": "__DRAFT__",
            }
            result = await product_manager_node(state, _make_config())

        event_types = [e.type for e in result.get("events", [])]
        assert EventType.AGENT_END in event_types

    @pytest.mark.asyncio
    async def test_draft_failure_returns_error_status(self) -> None:
        """If drafting raises, return wait_for_input + error."""
        with patch(
            "loom.agents.product_manager._pm_draft_prd",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM refused"),
        ):
            state = {
                "description": "todo app",
                "interactive": True,
                "agent_messages": {},
                "pending_user_input": "__DRAFT__",
            }
            result = await product_manager_node(state, _make_config())

        assert result.get("prd") is None
        assert result["agent_status"] == "wait_for_input"
        assert "error" in result


# ---------------------------------------------------------------------------
# Tests: legacy path (interactive=False)
# ---------------------------------------------------------------------------


class TestUnwrapJsonResponse:
    """Tests for the defensive JSON unwrapper used on PM clarify responses."""

    def test_plain_text_unchanged(self) -> None:
        from loom.agents.product_manager import _unwrap_json_response
        text = "Hello! What kind of users?"
        assert _unwrap_json_response(text) == text

    def test_unwraps_message_key(self) -> None:
        from loom.agents.product_manager import _unwrap_json_response
        text = '{"message": "Hi! What users?"}'
        assert _unwrap_json_response(text) == "Hi! What users?"

    def test_unwraps_response_key(self) -> None:
        from loom.agents.product_manager import _unwrap_json_response
        text = '{"response": "Got it"}'
        assert _unwrap_json_response(text) == "Got it"

    def test_unwraps_with_code_fence(self) -> None:
        from loom.agents.product_manager import _unwrap_json_response
        text = '```json\n{"message": "Hello"}\n```'
        assert _unwrap_json_response(text) == "Hello"

    def test_unwraps_single_string_value(self) -> None:
        from loom.agents.product_manager import _unwrap_json_response
        text = '{"reply": "Hi there"}'
        assert _unwrap_json_response(text) == "Hi there"

    def test_returns_original_for_non_dict_json(self) -> None:
        from loom.agents.product_manager import _unwrap_json_response
        text = '["not", "a", "wrapper"]'
        assert _unwrap_json_response(text) == text

    def test_returns_original_for_unparseable(self) -> None:
        from loom.agents.product_manager import _unwrap_json_response
        text = '{not valid json at all'
        assert _unwrap_json_response(text) == text

    def test_data_shaped_json_renders_as_bullet_list(self) -> None:
        from loom.agents.product_manager import _unwrap_json_response
        # qwen-coder pathology: answers conversational questions with raw data
        text = '{"single_user": true, "auth_required": false}'
        result = _unwrap_json_response(text)
        # Should be readable, not raw JSON
        assert "{" not in result
        assert "single_user" in result
        assert "auth_required" in result


class TestLegacyPath:
    """Tests proving the interactive=False path is unchanged from Phase 3."""

    @pytest.mark.asyncio
    async def test_legacy_path_produces_prd(self) -> None:
        """interactive=False must still produce a PRD in one shot."""
        prd_mock = _make_prd_mock()

        with patch("loom.agents.product_manager.build_agent_chain") as mock_chain_fn, \
             patch("loom.agents.product_manager.get_llm_for_role"):
            chain = MagicMock()
            chain.ainvoke = AsyncMock(return_value=prd_mock)
            parser = MagicMock()
            parser.get_format_instructions.return_value = "JSON"
            mock_chain_fn.return_value = (chain, parser)

            state = {
                "description": "todo app",
                "interactive": False,
                "agent_messages": {},
                "pending_user_input": None,
            }
            result = await product_manager_node(state, _make_config())

        assert result.get("prd") is not None
        assert result["prd"].project_slug == "todo-app"

    @pytest.mark.asyncio
    async def test_legacy_path_writes_no_agent_messages(self) -> None:
        """interactive=False must not write to agent_messages."""
        prd_mock = _make_prd_mock()

        with patch("loom.agents.product_manager.build_agent_chain") as mock_chain_fn, \
             patch("loom.agents.product_manager.get_llm_for_role"):
            chain = MagicMock()
            chain.ainvoke = AsyncMock(return_value=prd_mock)
            parser = MagicMock()
            parser.get_format_instructions.return_value = "JSON"
            mock_chain_fn.return_value = (chain, parser)

            state = {
                "description": "todo app",
                "interactive": False,
                "agent_messages": {},
                "pending_user_input": None,
            }
            result = await product_manager_node(state, _make_config())

        # No agent_messages key, or it's empty — legacy path doesn't write history
        assert not result.get("agent_messages")

    @pytest.mark.asyncio
    async def test_legacy_path_sets_no_agent_status(self) -> None:
        """interactive=False path must not set agent_status."""
        prd_mock = _make_prd_mock()

        with patch("loom.agents.product_manager.build_agent_chain") as mock_chain_fn, \
             patch("loom.agents.product_manager.get_llm_for_role"):
            chain = MagicMock()
            chain.ainvoke = AsyncMock(return_value=prd_mock)
            parser = MagicMock()
            parser.get_format_instructions.return_value = "JSON"
            mock_chain_fn.return_value = (chain, parser)

            state = {"description": "todo app", "interactive": False}
            result = await product_manager_node(state, _make_config())

        assert "agent_status" not in result or result["agent_status"] is None

    @pytest.mark.asyncio
    async def test_empty_description_non_interactive_returns_error(self) -> None:
        """No description in non-interactive mode must return an error."""
        state = {"description": "", "interactive": False}
        result = await product_manager_node(state, _make_config())

        assert result.get("error") is not None
        assert result.get("prd") is None
