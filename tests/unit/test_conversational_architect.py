"""Unit tests for the conversational Architect (Phase 9.2).

Mirrors the test patterns of test_conversational_pm.py. All LLM calls are
mocked. The legacy interactive=False path is verified to remain unchanged.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from loom.agents.architect import (
    MAX_ARCHITECT_REVISIONS,
    architect_node,
)
from loom.config import LoomConfig
from loom.state.enums import AgentRole, EventType
from loom.state.models import (
    PRD,
    APIEndpoint,
    ArchitectureDoc,
    Component,
    HttpMethod,
    Priority,
    ProjectType,
    TechChoice,
    TechLayer,
    UserStory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> LoomConfig:
    return LoomConfig()


def _make_mock_llm(response_text: str = "Stack: FastAPI + React. Sound good?") -> MagicMock:
    """Return a mock LLM that replies with response_text."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content=response_text))
    return llm


def _make_prd() -> PRD:
    return PRD(
        project_name="Todo App",
        project_slug="todo-app",
        project_type=ProjectType.FULLSTACK_WEB,
        one_liner="A simple todo app",
        target_users=["developers"],
        user_stories=[
            UserStory(
                id="US-001",
                role="user",
                goal="create a todo",
                benefit="track tasks",
                acceptance_criteria=["Todo is created"],
                priority=Priority.P0,
            )
        ],
        must_have_features=["Create todo"],
    )


def _make_arch_mock() -> ArchitectureDoc:
    return ArchitectureDoc(
        stack=[
            TechChoice(
                layer=TechLayer.BACKEND,
                technology="FastAPI",
                version="0.115",
                rationale="Modern async Python framework",
            ),
            TechChoice(
                layer=TechLayer.FRONTEND,
                technology="React",
                version="18",
                rationale="Popular UI library",
            ),
        ],
        api_endpoints=[],
        components=[],
        folder_structure={},
    )


# ---------------------------------------------------------------------------
# Tests: propose mode (first turn)
# ---------------------------------------------------------------------------


class TestProposeMode:
    """Tests for the first-turn proposal in the chat path."""

    @pytest.mark.asyncio
    async def test_first_turn_does_not_produce_arch(self) -> None:
        """First invocation produces a chat proposal, not an ArchitectureDoc."""
        mock_llm = _make_mock_llm(
            "Stack: FastAPI + React + SQLite + JWT.\nWhy: lightweight defaults.\nSound good?"
        )

        state = {
            "interactive": True,
            "prd": _make_prd(),
            "agent_messages": {},
            "pending_user_input": None,
        }

        result = await architect_node(state, _make_config(), llm=mock_llm)

        assert result.get("architecture") is None
        assert result["agent_status"] == "wait_for_input"
        assert "architect" in result["agent_messages"]
        history = result["agent_messages"]["architect"]
        # Bootstrap human msg + AI proposal = 2
        assert len(history) == 2
        assert isinstance(history[0], HumanMessage)
        assert isinstance(history[1], AIMessage)
        assert "Stack:" in history[1].content

    @pytest.mark.asyncio
    async def test_propose_emits_agent_turn_event(self) -> None:
        """Propose turn should emit AGENT_TURN."""
        mock_llm = _make_mock_llm()

        state = {
            "interactive": True,
            "prd": _make_prd(),
            "agent_messages": {},
            "pending_user_input": None,
        }
        result = await architect_node(state, _make_config(), llm=mock_llm)

        event_types = [e.type for e in result.get("events", [])]
        assert EventType.AGENT_TURN in event_types

    @pytest.mark.asyncio
    async def test_no_prd_returns_error_in_chat_mode(self) -> None:
        """Architect without PRD in chat mode returns an error."""
        state = {
            "interactive": True,
            "prd": None,
            "agent_messages": {},
            "pending_user_input": None,
        }
        result = await architect_node(state, _make_config(), llm=MagicMock())

        assert "error" in result
        assert result.get("architecture") is None


# ---------------------------------------------------------------------------
# Tests: revise mode
# ---------------------------------------------------------------------------


class TestReviseMode:
    """Tests for the revise turn after user feedback."""

    @pytest.mark.asyncio
    async def test_user_feedback_produces_revised_proposal(self) -> None:
        """Architect returns only NEW messages; reducer appends to existing."""
        existing_history = [
            HumanMessage(content="Please propose a stack."),
            AIMessage(content="Stack: FastAPI + React + SQLite. Sound good?"),
        ]
        mock_llm = _make_mock_llm(
            "Stack: FastAPI + React + Postgres + JWT. Sound good?"
        )

        state = {
            "interactive": True,
            "prd": _make_prd(),
            "agent_messages": {"architect": existing_history},
            "pending_user_input": "use Postgres instead of SQLite",
        }

        result = await architect_node(state, _make_config(), llm=mock_llm)

        assert result["agent_status"] == "wait_for_input"
        new_messages = result["agent_messages"]["architect"]
        # Only the new messages (user feedback + revised proposal)
        assert len(new_messages) == 2
        assert new_messages[0].content == "use Postgres instead of SQLite"
        assert "Postgres" in new_messages[1].content

    @pytest.mark.asyncio
    async def test_revise_does_not_produce_arch(self) -> None:
        """A revise turn must not commit an ArchitectureDoc."""
        existing_history = [
            HumanMessage(content="Please propose a stack."),
            AIMessage(content="Stack: A + B + C. Sound good?"),
        ]
        mock_llm = _make_mock_llm("Stack: D + E + F. Sound good?")

        state = {
            "interactive": True,
            "prd": _make_prd(),
            "agent_messages": {"architect": existing_history},
            "pending_user_input": "swap everything",
        }
        result = await architect_node(state, _make_config(), llm=mock_llm)

        assert result.get("architecture") is None


# ---------------------------------------------------------------------------
# Tests: revision cap
# ---------------------------------------------------------------------------


class TestRevisionCap:
    """Tests for the MAX_ARCHITECT_REVISIONS hard cap."""

    @pytest.mark.asyncio
    async def test_cap_forces_ready_to_draft(self) -> None:
        """At MAX_ARCHITECT_REVISIONS, status flips to ready_to_draft."""
        history: list[Any] = []
        for i in range(MAX_ARCHITECT_REVISIONS):
            history.append(HumanMessage(content=f"feedback {i}"))
            history.append(AIMessage(content=f"proposal {i}"))

        mock_llm = _make_mock_llm("Should not be called")

        state = {
            "interactive": True,
            "prd": _make_prd(),
            "agent_messages": {"architect": history},
            "pending_user_input": "more feedback",
        }
        result = await architect_node(state, _make_config(), llm=mock_llm)

        assert result["agent_status"] == "ready_to_draft"
        mock_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_cap_emits_turn_limit_event(self) -> None:
        """Revision cap should emit AGENT_TURN_LIMIT."""
        history: list[Any] = []
        for i in range(MAX_ARCHITECT_REVISIONS):
            history.extend([
                HumanMessage(content=f"f{i}"),
                AIMessage(content=f"p{i}"),
            ])

        state = {
            "interactive": True,
            "prd": _make_prd(),
            "agent_messages": {"architect": history},
            "pending_user_input": "another change",
        }
        result = await architect_node(state, _make_config(), llm=MagicMock())

        event_types = [e.type for e in result.get("events", [])]
        assert EventType.AGENT_TURN_LIMIT in event_types

    @pytest.mark.asyncio
    async def test_below_cap_processes_normally(self) -> None:
        """One revision below the cap should still call the LLM."""
        history: list[Any] = []
        for i in range(MAX_ARCHITECT_REVISIONS - 1):
            history.extend([
                HumanMessage(content=f"f{i}"),
                AIMessage(content=f"p{i}"),
            ])
        mock_llm = _make_mock_llm("Stack: revised. Sound good?")

        state = {
            "interactive": True,
            "prd": _make_prd(),
            "agent_messages": {"architect": history},
            "pending_user_input": "one more change",
        }
        result = await architect_node(state, _make_config(), llm=mock_llm)

        # LLM should have been invoked
        mock_llm.ainvoke.assert_called_once()
        assert result["agent_status"] == "wait_for_input"


# ---------------------------------------------------------------------------
# Tests: drafting mode
# ---------------------------------------------------------------------------


class TestDraftingMode:
    """Tests for the __DRAFT__ trigger that produces the full doc."""

    @pytest.mark.asyncio
    async def test_draft_signal_produces_arch(self) -> None:
        """__DRAFT__ pending input should produce an ArchitectureDoc."""
        history = [
            HumanMessage(content="Please propose a stack."),
            AIMessage(content="Stack: FastAPI + React + SQLite. Sound good?"),
        ]
        arch_mock = _make_arch_mock()

        with patch(
            "loom.agents.architect._architect_draft_doc",
            new_callable=AsyncMock,
            return_value=arch_mock,
        ):
            state = {
                "interactive": True,
                "prd": _make_prd(),
                "agent_messages": {"architect": history},
                "pending_user_input": "__DRAFT__",
            }
            result = await architect_node(state, _make_config())

        assert result.get("architecture") is not None
        assert result["agent_status"] == "done"
        assert result["pending_user_input"] is None

    @pytest.mark.asyncio
    async def test_draft_emits_agent_end_event(self) -> None:
        """Successful draft emits AGENT_END."""
        arch_mock = _make_arch_mock()

        with patch(
            "loom.agents.architect._architect_draft_doc",
            new_callable=AsyncMock,
            return_value=arch_mock,
        ):
            state = {
                "interactive": True,
                "prd": _make_prd(),
                "agent_messages": {"architect": []},
                "pending_user_input": "__DRAFT__",
            }
            result = await architect_node(state, _make_config())

        event_types = [e.type for e in result.get("events", [])]
        assert EventType.AGENT_END in event_types

    @pytest.mark.asyncio
    async def test_draft_advances_phase(self) -> None:
        """Draft should advance phase to DEVELOPMENT."""
        from loom.state.enums import Phase

        arch_mock = _make_arch_mock()

        with patch(
            "loom.agents.architect._architect_draft_doc",
            new_callable=AsyncMock,
            return_value=arch_mock,
        ):
            state = {
                "interactive": True,
                "prd": _make_prd(),
                "agent_messages": {},
                "pending_user_input": "__DRAFT__",
            }
            result = await architect_node(state, _make_config())

        assert result.get("phase") == Phase.DEVELOPMENT

    @pytest.mark.asyncio
    async def test_draft_failure_returns_error_status(self) -> None:
        """If drafting raises, return wait_for_input + error."""
        with patch(
            "loom.agents.architect._architect_draft_doc",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM refused"),
        ):
            state = {
                "interactive": True,
                "prd": _make_prd(),
                "agent_messages": {},
                "pending_user_input": "__DRAFT__",
            }
            result = await architect_node(state, _make_config())

        assert result.get("architecture") is None
        assert result["agent_status"] == "wait_for_input"
        assert "error" in result


# ---------------------------------------------------------------------------
# Tests: legacy path (interactive=False)
# ---------------------------------------------------------------------------


class TestLegacyPath:
    """Tests proving the interactive=False path is unchanged from Phase 4."""

    @pytest.mark.asyncio
    async def test_legacy_path_produces_arch(self) -> None:
        """interactive=False must produce an ArchitectureDoc in one shot."""
        arch_mock = _make_arch_mock()

        with patch("loom.agents.architect.build_agent_chain") as mock_chain_fn, \
             patch("loom.agents.architect.get_llm_for_role"):
            chain = MagicMock()
            chain.ainvoke = AsyncMock(return_value=arch_mock)
            parser = MagicMock()
            parser.get_format_instructions.return_value = "JSON"
            mock_chain_fn.return_value = (chain, parser)

            state = {
                "interactive": False,
                "prd": _make_prd(),
                "description": "todo app",
                "agent_messages": {},
                "pending_user_input": None,
            }
            result = await architect_node(state, _make_config())

        assert result.get("architecture") is not None
        assert len(result["architecture"].stack) == 2

    @pytest.mark.asyncio
    async def test_legacy_path_writes_no_agent_messages(self) -> None:
        """interactive=False must not write to agent_messages."""
        arch_mock = _make_arch_mock()

        with patch("loom.agents.architect.build_agent_chain") as mock_chain_fn, \
             patch("loom.agents.architect.get_llm_for_role"):
            chain = MagicMock()
            chain.ainvoke = AsyncMock(return_value=arch_mock)
            parser = MagicMock()
            parser.get_format_instructions.return_value = "JSON"
            mock_chain_fn.return_value = (chain, parser)

            state = {
                "interactive": False,
                "prd": _make_prd(),
                "description": "todo app",
            }
            result = await architect_node(state, _make_config())

        assert not result.get("agent_messages")

    @pytest.mark.asyncio
    async def test_legacy_path_sets_no_agent_status(self) -> None:
        """interactive=False must not set agent_status."""
        arch_mock = _make_arch_mock()

        with patch("loom.agents.architect.build_agent_chain") as mock_chain_fn, \
             patch("loom.agents.architect.get_llm_for_role"):
            chain = MagicMock()
            chain.ainvoke = AsyncMock(return_value=arch_mock)
            parser = MagicMock()
            parser.get_format_instructions.return_value = "JSON"
            mock_chain_fn.return_value = (chain, parser)

            state = {
                "interactive": False,
                "prd": _make_prd(),
                "description": "todo app",
            }
            result = await architect_node(state, _make_config())

        assert "agent_status" not in result or result["agent_status"] is None

    @pytest.mark.asyncio
    async def test_legacy_path_no_prd_returns_error(self) -> None:
        """interactive=False without PRD returns an error."""
        state = {"interactive": False, "prd": None, "description": "todo app"}
        result = await architect_node(state, _make_config())

        assert result.get("error") is not None
        assert result.get("architecture") is None
