"""Unit tests for Product Manager agent."""

import json

import pytest
from langchain_core.messages import AIMessage

from agentforge.agents.product_manager import (
    MAX_PARSE_RETRIES,
    TokenTracker,
    product_manager_node,
)
from agentforge.state.enums import AgentRole, EventType, Phase
from agentforge.state.models import PRD

# Sample valid PRD JSON that matches the schema
VALID_PRD_JSON = json.dumps(
    {
        "project_name": "Todo App",
        "project_slug": "todo-app",
        "project_type": "fullstack_web",
        "one_liner": "A simple todo list application",
        "target_users": ["individual users", "small teams"],
        "user_stories": [
            {
                "id": "US-001",
                "role": "user",
                "goal": "create a todo item",
                "benefit": "track my tasks",
                "acceptance_criteria": ["User can enter task text", "Task appears in list"],
                "priority": "P0",
            },
            {
                "id": "US-002",
                "role": "user",
                "goal": "mark todo as complete",
                "benefit": "track my progress",
                "acceptance_criteria": ["User can click checkbox", "Task shows as completed"],
                "priority": "P0",
            },
        ],
        "data_entities": [
            {
                "name": "Todo",
                "description": "A todo item",
                "fields": {"id": "int", "text": "string", "completed": "boolean"},
            }
        ],
        "must_have_features": ["Create todos", "Complete todos", "List todos"],
        "nice_to_have_features": ["Due dates", "Categories"],
        "out_of_scope": ["User authentication", "Multi-user support"],
        "success_metrics": ["User can manage todos"],
        "assumptions": ["Single user app"],
    }
)

INVALID_JSON = '{"invalid": json without closing'


class FakeListChatModel:
    """Fake LLM that returns predefined responses."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.call_count = 0
        self.callbacks: list | None = None

    async def ainvoke(self, input_data, config=None):
        """Return the next response in the list."""
        if self.call_count >= len(self.responses):
            raise ValueError("No more responses available")
        response = self.responses[self.call_count]
        self.call_count += 1
        return AIMessage(content=response)

    def bind(self, **kwargs):
        """Bind is a no-op for fake model."""
        return self


class TestTokenTracker:
    """Test the TokenTracker callback handler."""

    def test_initial_state(self) -> None:
        """Test that tracker starts with zero tokens."""
        tracker = TokenTracker()
        assert tracker.input_tokens == 0
        assert tracker.output_tokens == 0
        assert tracker.model_name is None


class TestProductManagerNode:
    """Test the product_manager_node function."""

    @pytest.mark.asyncio
    async def test_missing_description_returns_error(self) -> None:
        """Test that missing description returns an error event."""
        state = {"description": ""}
        result = await product_manager_node(state)

        assert "error" in result
        assert result["error"] == "No project description provided"
        assert len(result["events"]) == 1
        assert result["events"][0].type == EventType.ERROR

    @pytest.mark.asyncio
    async def test_happy_path_with_valid_response(self, monkeypatch) -> None:
        """Test successful PRD generation with valid JSON response."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agentforge.config import AgentForgeConfig

        # Create a mock chain that returns a valid PRD
        mock_prd = PRD(
            project_name="Todo App",
            project_slug="todo-app",
            project_type="fullstack_web",
            one_liner="A simple todo list application",
            target_users=["individual users"],
            user_stories=[
                {
                    "id": "US-001",
                    "role": "user",
                    "goal": "create a todo item",
                    "benefit": "track my tasks",
                    "acceptance_criteria": ["User can enter task text"],
                    "priority": "P0",
                }
            ],
            must_have_features=["Create todos"],
        )

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_prd)

        mock_parser = MagicMock()
        mock_parser.get_format_instructions = MagicMock(return_value="Format: JSON")

        with patch(
            "agentforge.agents.product_manager.build_agent_chain",
            return_value=(mock_chain, mock_parser),
        ):
            with patch(
                "agentforge.agents.product_manager.get_llm_for_role",
                return_value=MagicMock(),
            ):
                config = AgentForgeConfig()
                state = {"description": "Build me a todo app"}

                result = await product_manager_node(state, config=config)

        # Check the result
        assert "prd" in result
        assert result["prd"].project_name == "Todo App"
        assert result["prd"].project_slug == "todo-app"
        assert result["phase"] == Phase.DESIGN
        assert len(result["events"]) == 2
        assert result["events"][0].type == EventType.AGENT_START
        assert result["events"][1].type == EventType.AGENT_END

    @pytest.mark.asyncio
    async def test_retry_on_parse_error_then_success(self, monkeypatch) -> None:
        """Test that parse errors trigger retry and eventually succeed."""
        from unittest.mock import MagicMock, patch

        from agentforge.config import AgentForgeConfig

        # Create a mock PRD for successful response
        mock_prd = PRD(
            project_name="Todo App",
            project_slug="todo-app",
            project_type="fullstack_web",
            one_liner="A simple todo list application",
            target_users=["individual users"],
            user_stories=[
                {
                    "id": "US-001",
                    "role": "user",
                    "goal": "create a todo item",
                    "benefit": "track my tasks",
                    "acceptance_criteria": ["User can enter task text"],
                    "priority": "P0",
                }
            ],
            must_have_features=["Create todos"],
        )

        # Mock chain that fails twice then succeeds
        call_count = 0

        async def mock_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Invalid JSON: expected property name")
            return mock_prd

        mock_chain = MagicMock()
        mock_chain.ainvoke = mock_invoke

        mock_parser = MagicMock()
        mock_parser.get_format_instructions = MagicMock(return_value="Format: JSON")

        with patch(
            "agentforge.agents.product_manager.build_agent_chain",
            return_value=(mock_chain, mock_parser),
        ):
            with patch(
                "agentforge.agents.product_manager.get_llm_for_role",
                return_value=MagicMock(),
            ):
                config = AgentForgeConfig()
                state = {"description": "Build me a todo app"}

                result = await product_manager_node(state, config=config)

        # Should eventually succeed after retries
        assert "prd" in result
        assert result["prd"].project_name == "Todo App"
        assert call_count == 3  # Failed twice, succeeded on third

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_returns_error(self, monkeypatch) -> None:
        """Test that exceeding max retries returns an error."""
        from unittest.mock import MagicMock, patch

        from agentforge.config import AgentForgeConfig

        # Mock chain that always fails
        async def mock_invoke(*args, **kwargs):
            raise ValueError("Invalid JSON: expected property name")

        mock_chain = MagicMock()
        mock_chain.ainvoke = mock_invoke

        mock_parser = MagicMock()
        mock_parser.get_format_instructions = MagicMock(return_value="Format: JSON")

        with patch(
            "agentforge.agents.product_manager.build_agent_chain",
            return_value=(mock_chain, mock_parser),
        ):
            with patch(
                "agentforge.agents.product_manager.get_llm_for_role",
                return_value=MagicMock(),
            ):
                config = AgentForgeConfig()
                state = {"description": "Build me a todo app"}

                result = await product_manager_node(state, config=config)

        # Should return error after max retries
        assert "error" in result
        assert f"after {MAX_PARSE_RETRIES} attempts" in result["error"]
        assert len(result["events"]) == 2
        assert result["events"][0].type == EventType.AGENT_START
        assert result["events"][1].type == EventType.ERROR
        assert result["events"][1].payload["attempts"] == MAX_PARSE_RETRIES

    @pytest.mark.asyncio
    async def test_events_include_agent_info(self) -> None:
        """Test that events include correct agent information."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agentforge.config import AgentForgeConfig

        mock_prd = PRD(
            project_name="Test Project",
            project_slug="test-project",
            project_type="fullstack_web",
            one_liner="Test",
            target_users=["testers"],
            user_stories=[
                {
                    "id": "US-001",
                    "role": "user",
                    "goal": "test",
                    "benefit": "testing",
                    "acceptance_criteria": ["Test passes"],
                    "priority": "P0",
                }
            ],
            must_have_features=["Test"],
        )

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_prd)

        mock_parser = MagicMock()
        mock_parser.get_format_instructions = MagicMock(return_value="Format: JSON")

        with patch(
            "agentforge.agents.product_manager.build_agent_chain",
            return_value=(mock_chain, mock_parser),
        ):
            with patch(
                "agentforge.agents.product_manager.get_llm_for_role",
                return_value=MagicMock(),
            ):
                config = AgentForgeConfig()
                state = {"description": "Build me a test project"}

                result = await product_manager_node(state, config=config)

        # Check event agent info
        for event in result["events"]:
            assert event.agent == AgentRole.PRODUCT_MANAGER
            assert event.phase == Phase.REQUIREMENTS


class TestProductManagerPrompt:
    """Test the Product Manager prompt templates."""

    def test_system_prompt_exists(self) -> None:
        """Test that the system prompt is defined."""
        from agentforge.agents.prompts import PRODUCT_MANAGER_SYSTEM_PROMPT

        assert PRODUCT_MANAGER_SYSTEM_PROMPT
        assert "Product Manager" in PRODUCT_MANAGER_SYSTEM_PROMPT
        assert "PRD" in PRODUCT_MANAGER_SYSTEM_PROMPT

    def test_human_template_exists(self) -> None:
        """Test that the human template is defined."""
        from agentforge.agents.prompts import PRODUCT_MANAGER_HUMAN_TEMPLATE

        assert PRODUCT_MANAGER_HUMAN_TEMPLATE
        assert "{description}" in PRODUCT_MANAGER_HUMAN_TEMPLATE
