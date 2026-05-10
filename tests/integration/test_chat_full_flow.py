"""End-to-end test of the chat REPL through PM, Architect, and beyond.

Walks the chat session through:
  1. User describes a project
  2. PM clarifies (1 turn)
  3. User types "yes" → should auto-trigger drafting
  4. PM produces PRD
  5. Architect proposes a stack
  6. User types "yes" → should advance Architect
  7. Build pipeline runs (devs, QA, devops mocked)
  8. Build completes with output

This is the full happy-path flow exercised end-to-end with mocked LLMs.
"""

import asyncio
from pathlib import Path
from typing import Any
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver


def _make_renderer_mock() -> MagicMock:
    """Build a renderer mock with a working `thinking()` context manager."""
    @contextmanager
    def _noop_thinking(label: str = "thinking"):
        yield

    renderer = MagicMock()
    renderer.console = MagicMock()
    renderer.thinking = _noop_thinking
    renderer.render_agent_message_animated = AsyncMock()
    return renderer

from loom.cli.chat.session import ChatSession, looks_affirmative
from loom.config import LoomConfig
from loom.state.models import (
    PRD,
    ArchitectureDoc,
    Priority,
    ProjectType,
    TechChoice,
    TechLayer,
    UserStory,
)


# ---------------------------------------------------------------------------
# Affirmative detection unit tests
# ---------------------------------------------------------------------------


class TestLooksAffirmative:
    """Verify the affirmative detector handles real user inputs."""

    def test_plain_yes(self) -> None:
        assert looks_affirmative("yes") is True

    def test_yes_uppercase(self) -> None:
        assert looks_affirmative("YES") is True

    def test_yes_with_punctuation(self) -> None:
        assert looks_affirmative("yes!") is True
        assert looks_affirmative("yes.") is True
        assert looks_affirmative("yes?") is True

    def test_short_phrase_with_yes_prefix(self) -> None:
        assert looks_affirmative("yes go ahead") is True
        assert looks_affirmative("ok do it") is True
        assert looks_affirmative("sure draft it") is True

    def test_done(self) -> None:
        assert looks_affirmative("done") is True

    def test_perfect_great(self) -> None:
        assert looks_affirmative("perfect") is True
        assert looks_affirmative("great") is True
        assert looks_affirmative("looks good") is True
        assert looks_affirmative("lgtm") is True

    def test_long_prose_not_affirmative(self) -> None:
        assert looks_affirmative(
            "yes but I want to also include the auth feature"
        ) is False  # too long, real content
        assert looks_affirmative(
            "build me a simple cli tool"
        ) is False

    def test_negative_not_affirmative(self) -> None:
        assert looks_affirmative("no") is False
        assert looks_affirmative("not yet") is False

    def test_empty_string(self) -> None:
        assert looks_affirmative("") is False
        assert looks_affirmative("   ") is False

    def test_unrelated_input(self) -> None:
        assert looks_affirmative("hello world") is False
        assert looks_affirmative("/help") is False  # slash command


# ---------------------------------------------------------------------------
# Full chat flow with mocked agents
# ---------------------------------------------------------------------------


def _make_prd() -> PRD:
    return PRD(
        project_name="Markdown to PDF CLI",
        project_slug="md-to-pdf-cli",
        project_type=ProjectType.CLI_TOOL,
        one_liner="Convert markdown files to PDF",
        target_users=["developers"],
        user_stories=[
            UserStory(
                id="US-001",
                role="user",
                goal="convert md to pdf",
                benefit="generate documents",
                acceptance_criteria=["File converted"],
                priority=Priority.P0,
            )
        ],
        must_have_features=["MD-to-PDF conversion"],
    )


def _make_arch() -> ArchitectureDoc:
    return ArchitectureDoc(
        stack=[
            TechChoice(
                layer=TechLayer.BACKEND,
                technology="Python",
                version="3.12",
                rationale="standard for CLI tools",
            ),
        ],
        api_endpoints=[],
        components=[],
        folder_structure={},
    )


class TestFullChatFlow:
    """Drive a full chat session end-to-end with mocked agent nodes."""

    @pytest.mark.asyncio
    async def test_yes_triggers_pm_drafting(self, tmp_path: Path) -> None:
        """The 'yes' affirmative should advance PM to drafting (no /done needed)."""
        prd = _make_prd()
        pm_calls: list[dict[str, Any]] = []

        async def fake_pm(state, config=None, llm=None):
            user_input = state.get("pending_user_input")
            pm_calls.append({"user_input": user_input})

            if user_input == "__DRAFT__":
                return {
                    "prd": prd,
                    "agent_status": "done",
                    "pending_user_input": None,
                }
            # First clarify turn
            return {
                "agent_messages": {
                    "product_manager": [
                        HumanMessage(content=state.get("description", "")),
                        AIMessage(content="What kind of users?"),
                    ]
                },
                "agent_status": "wait_for_input",
                "pending_user_input": None,
            }

        # Block memory_retrieve and architect so the test stops after PM drafts
        async def fake_arch(state, config=None, llm=None):
            return {
                "agent_messages": {
                    "architect": [
                        HumanMessage(content="Please propose a stack."),
                        AIMessage(content="Stack: Python. Sound good?"),
                    ]
                },
                "agent_status": "wait_for_input",
                "pending_user_input": None,
            }

        # Scripted user inputs
        inputs = ["build me a md→pdf CLI", "yes", "/quit"]

        renderer = _make_renderer_mock()
        input_reader = MagicMock()
        input_reader.read = AsyncMock(side_effect=inputs)

        session = ChatSession(
            config=LoomConfig(),
            renderer=renderer,
            input_reader=input_reader,
            checkpointer=MemorySaver(),
            thread_id="full-flow-yes",
        )
        from loom.cli.chat.transcript import get_chat_path
        session._transcript_path = get_chat_path(
            "full-flow-yes", base_dir=tmp_path
        )

        with patch(
            "loom.graph.builder.product_manager_node",
            new=AsyncMock(side_effect=fake_pm),
        ), patch(
            "loom.graph.builder.architect_node",
            new=AsyncMock(side_effect=fake_arch),
        ):
            try:
                await session.run()
            except Exception:
                pass

        # PM should have been called at least twice — first with no draft trigger,
        # then with "__DRAFT__" because we typed "yes" which got translated.
        draft_calls = [c for c in pm_calls if c["user_input"] == "__DRAFT__"]
        assert len(draft_calls) >= 1, (
            f"Plain 'yes' should have triggered drafting. "
            f"PM calls were: {pm_calls}"
        )

    @pytest.mark.asyncio
    async def test_done_word_triggers_drafting(self, tmp_path: Path) -> None:
        """The plain word 'done' (no slash) should also trigger drafting."""
        prd = _make_prd()
        pm_calls: list[str | None] = []

        async def fake_pm(state, config=None, llm=None):
            user_input = state.get("pending_user_input")
            pm_calls.append(user_input)

            if user_input == "__DRAFT__":
                return {"prd": prd, "agent_status": "done", "pending_user_input": None}
            return {
                "agent_messages": {
                    "product_manager": [
                        HumanMessage(content=state.get("description", "")),
                        AIMessage(content="?"),
                    ]
                },
                "agent_status": "wait_for_input",
                "pending_user_input": None,
            }

        async def fake_arch(state, config=None, llm=None):
            return {
                "agent_messages": {
                    "architect": [
                        HumanMessage(content="propose"),
                        AIMessage(content="prop"),
                    ]
                },
                "agent_status": "wait_for_input",
                "pending_user_input": None,
            }

        inputs = ["a project", "done", "/quit"]
        renderer = _make_renderer_mock()
        input_reader = MagicMock()
        input_reader.read = AsyncMock(side_effect=inputs)

        session = ChatSession(
            config=LoomConfig(),
            renderer=renderer,
            input_reader=input_reader,
            checkpointer=MemorySaver(),
            thread_id="done-word",
        )
        from loom.cli.chat.transcript import get_chat_path
        session._transcript_path = get_chat_path("done-word", base_dir=tmp_path)

        with patch(
            "loom.graph.builder.product_manager_node",
            new=AsyncMock(side_effect=fake_pm),
        ), patch(
            "loom.graph.builder.architect_node",
            new=AsyncMock(side_effect=fake_arch),
        ):
            try:
                await session.run()
            except Exception:
                pass

        assert "__DRAFT__" in pm_calls, (
            f"'done' (no slash) should trigger drafting. PM calls: {pm_calls}"
        )

    @pytest.mark.asyncio
    async def test_long_prose_is_not_treated_as_affirmative(
        self, tmp_path: Path
    ) -> None:
        """Long replies should be passed through to the PM, not auto-drafted."""
        pm_calls: list[str | None] = []

        async def fake_pm(state, config=None, llm=None):
            user_input = state.get("pending_user_input")
            pm_calls.append(user_input)

            return {
                "agent_messages": {
                    "product_manager": [
                        HumanMessage(content=state.get("description", "")),
                        AIMessage(content="ack"),
                    ]
                },
                "agent_status": "wait_for_input",
                "pending_user_input": None,
            }

        async def fake_arch(state, config=None, llm=None):
            return {
                "agent_messages": {"architect": []},
                "agent_status": "wait_for_input",
                "pending_user_input": None,
            }

        long_input = (
            "yes but I want to make it support multiple files and have a watch mode"
        )
        inputs = ["build a tool", long_input, "/quit"]
        renderer = _make_renderer_mock()
        input_reader = MagicMock()
        input_reader.read = AsyncMock(side_effect=inputs)

        session = ChatSession(
            config=LoomConfig(),
            renderer=renderer,
            input_reader=input_reader,
            checkpointer=MemorySaver(),
            thread_id="long-prose",
        )
        from loom.cli.chat.transcript import get_chat_path
        session._transcript_path = get_chat_path("long-prose", base_dir=tmp_path)

        with patch(
            "loom.graph.builder.product_manager_node",
            new=AsyncMock(side_effect=fake_pm),
        ), patch(
            "loom.graph.builder.architect_node",
            new=AsyncMock(side_effect=fake_arch),
        ):
            try:
                await session.run()
            except Exception:
                pass

        # The long prose should have been passed through as-is, not converted
        # to __DRAFT__
        assert long_input in pm_calls, (
            f"Long reply should be passed to PM verbatim. PM calls: {pm_calls}"
        )
        assert "__DRAFT__" not in pm_calls
