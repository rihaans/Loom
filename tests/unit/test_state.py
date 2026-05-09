"""Comprehensive unit tests for state models and reducers."""

import pytest
from pydantic import ValidationError

from loom.state import (
    PRD,
    AgentRole,
    AgentState,
    APIEndpoint,
    ArchitectureDoc,
    CodeFile,
    CostEntry,
    EventType,
    FileBundle,
    HttpMethod,
    # Enums
    Phase,
    Priority,
    ProjectType,
    TechChoice,
    TechLayer,
    TestCase,
    TestReport,
    # Models
    UserStory,
    append_list,
    coalesce,
    increment,
    last_value,
    # Reducers
    merge_dicts,
)

# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    """Test all enum types."""

    def test_phase_values(self) -> None:
        """Test Phase enum has all expected values."""
        assert Phase.INIT == "init"
        assert Phase.REQUIREMENTS == "requirements"
        assert Phase.DESIGN == "design"
        assert Phase.DEVELOPMENT == "development"
        assert Phase.TESTING == "testing"
        assert Phase.DEPLOYMENT == "deployment"
        assert Phase.DONE == "done"
        assert Phase.FAILED == "failed"

    def test_agent_role_values(self) -> None:
        """Test AgentRole enum has all expected values."""
        assert AgentRole.PRODUCT_MANAGER == "product_manager"
        assert AgentRole.ARCHITECT == "architect"
        assert AgentRole.FRONTEND_DEV == "frontend_dev"
        assert AgentRole.BACKEND_DEV == "backend_dev"
        assert AgentRole.QA == "qa_engineer"
        assert AgentRole.DEVOPS == "devops_engineer"
        assert AgentRole.SUPERVISOR == "project_manager"

    def test_priority_values(self) -> None:
        """Test Priority enum values."""
        assert Priority.P0 == "P0"
        assert Priority.P1 == "P1"
        assert Priority.P2 == "P2"

    def test_project_type_values(self) -> None:
        """Test ProjectType enum values."""
        assert ProjectType.REST_API == "rest_api"
        assert ProjectType.FULLSTACK_WEB == "fullstack_web"
        assert ProjectType.CLI_TOOL == "cli_tool"


# =============================================================================
# Reducer Tests
# =============================================================================


class TestReducers:
    """Test reducer functions."""

    def test_merge_dicts_empty(self) -> None:
        """Test merging empty dicts."""
        assert merge_dicts({}, {}) == {}

    def test_merge_dicts_single(self) -> None:
        """Test merging with one empty dict."""
        assert merge_dicts({"a": 1}, {}) == {"a": 1}
        assert merge_dicts({}, {"b": 2}) == {"b": 2}

    def test_merge_dicts_no_conflict(self) -> None:
        """Test merging without key conflicts."""
        result = merge_dicts({"frontend": "f1"}, {"backend": "b1"})
        assert result == {"frontend": "f1", "backend": "b1"}

    def test_merge_dicts_conflict(self) -> None:
        """Test merging with key conflicts (b wins)."""
        result = merge_dicts({"x": 1}, {"x": 2})
        assert result == {"x": 2}

    def test_merge_dicts_none_handling(self) -> None:
        """Test merge_dicts handles None inputs."""
        assert merge_dicts(None, {"a": 1}) == {"a": 1}
        assert merge_dicts({"a": 1}, None) == {"a": 1}
        assert merge_dicts(None, None) == {}

    def test_merge_dicts_idempotent(self) -> None:
        """Test that merging is idempotent."""
        a = {"x": 1}
        b = {"y": 2}
        result1 = merge_dicts(merge_dicts(a, b), b)
        result2 = merge_dicts(a, b)
        assert result1 == result2

    def test_last_value(self) -> None:
        """Test last_value returns the second argument."""
        assert last_value(1, 2) == 2
        assert last_value("old", "new") == "new"
        assert last_value(None, "value") == "value"

    def test_increment(self) -> None:
        """Test increment adds values."""
        assert increment(0, 1) == 1
        assert increment(5, 3) == 8
        assert increment(None, 1) == 1

    def test_append_list_empty(self) -> None:
        """Test appending empty lists."""
        assert append_list([], []) == []

    def test_append_list_single(self) -> None:
        """Test appending to/from empty."""
        assert append_list([1, 2], []) == [1, 2]
        assert append_list([], [3, 4]) == [3, 4]

    def test_append_list_both(self) -> None:
        """Test appending both lists."""
        assert append_list([1, 2], [3, 4]) == [1, 2, 3, 4]

    def test_append_list_none_handling(self) -> None:
        """Test append_list handles None."""
        assert append_list(None, [1]) == [1]
        assert append_list([1], None) == [1]
        assert append_list(None, None) == []

    def test_coalesce(self) -> None:
        """Test coalesce returns non-None value."""
        assert coalesce(None, "new") == "new"
        assert coalesce("old", None) == "old"
        assert coalesce("old", "new") == "new"
        assert coalesce(None, None) is None


# =============================================================================
# PRD Model Tests
# =============================================================================


class TestUserStory:
    """Test UserStory model."""

    def test_valid_user_story(self) -> None:
        """Test creating a valid user story."""
        story = UserStory(
            id="US-001",
            role="registered user",
            goal="log in with email",
            benefit="access my data",
            acceptance_criteria=["Form accepts email", "Password validated"],
            priority=Priority.P0,
        )
        assert story.id == "US-001"
        assert story.priority == Priority.P0

    def test_invalid_id_format(self) -> None:
        """Test that invalid ID format raises error."""
        with pytest.raises(ValidationError) as exc_info:
            UserStory(
                id="US001",  # Missing dash
                role="user",
                goal="goal",
                benefit="benefit",
                acceptance_criteria=["criteria"],
                priority=Priority.P0,
            )
        assert "id" in str(exc_info.value)

    def test_empty_acceptance_criteria(self) -> None:
        """Test that empty acceptance criteria raises error."""
        with pytest.raises(ValidationError):
            UserStory(
                id="US-001",
                role="user",
                goal="goal",
                benefit="benefit",
                acceptance_criteria=[],  # Must have at least one
                priority=Priority.P0,
            )


class TestPRD:
    """Test PRD model."""

    @pytest.fixture
    def valid_prd_data(self) -> dict:
        """Return valid PRD data."""
        return {
            "project_name": "Todo App",
            "project_slug": "todo-app",
            "project_type": ProjectType.FULLSTACK_WEB,
            "one_liner": "A simple todo list application",
            "target_users": ["developers"],
            "user_stories": [
                {
                    "id": "US-001",
                    "role": "user",
                    "goal": "create todos",
                    "benefit": "track tasks",
                    "acceptance_criteria": ["Can add todo"],
                    "priority": Priority.P0,
                }
            ],
            "must_have_features": ["CRUD operations"],
        }

    def test_valid_prd(self, valid_prd_data: dict) -> None:
        """Test creating a valid PRD."""
        prd = PRD(**valid_prd_data)
        assert prd.project_slug == "todo-app"
        assert len(prd.user_stories) == 1

    def test_invalid_slug_uppercase(self, valid_prd_data: dict) -> None:
        """Test that uppercase slug is rejected."""
        valid_prd_data["project_slug"] = "Todo-App"
        with pytest.raises(ValidationError) as exc_info:
            PRD(**valid_prd_data)
        assert "slug" in str(exc_info.value).lower()

    def test_invalid_slug_spaces(self, valid_prd_data: dict) -> None:
        """Test that slug with spaces is rejected."""
        valid_prd_data["project_slug"] = "todo app"
        with pytest.raises(ValidationError):
            PRD(**valid_prd_data)

    def test_slug_too_long(self, valid_prd_data: dict) -> None:
        """Test that slug over 40 chars is rejected."""
        valid_prd_data["project_slug"] = "a" * 41
        with pytest.raises(ValidationError):
            PRD(**valid_prd_data)

    def test_empty_must_have_features(self, valid_prd_data: dict) -> None:
        """Test that empty must_have_features is rejected."""
        valid_prd_data["must_have_features"] = []
        with pytest.raises(ValidationError):
            PRD(**valid_prd_data)


# =============================================================================
# Architecture Model Tests
# =============================================================================


class TestAPIEndpoint:
    """Test APIEndpoint model."""

    def test_valid_endpoint(self) -> None:
        """Test creating a valid API endpoint."""
        endpoint = APIEndpoint(
            method=HttpMethod.GET,
            path="/api/users",
            description="Get all users",
            response_schema={"type": "array"},
        )
        assert endpoint.path == "/api/users"

    def test_path_without_leading_slash(self) -> None:
        """Test that path without leading slash is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            APIEndpoint(
                method=HttpMethod.GET,
                path="api/users",  # Missing /
                description="Get users",
            )
        assert "path" in str(exc_info.value).lower()


class TestArchitectureDoc:
    """Test ArchitectureDoc model."""

    def test_valid_architecture(self) -> None:
        """Test creating a valid architecture doc."""
        arch = ArchitectureDoc(
            stack=[
                TechChoice(
                    layer=TechLayer.BACKEND,
                    technology="FastAPI",
                    version="0.100",
                    rationale="Fast and modern",
                )
            ],
        )
        assert len(arch.stack) == 1
        assert arch.stack[0].technology == "FastAPI"

    def test_empty_stack_rejected(self) -> None:
        """Test that empty stack is rejected."""
        with pytest.raises(ValidationError):
            ArchitectureDoc(stack=[])


# =============================================================================
# Code Model Tests
# =============================================================================


class TestCodeFile:
    """Test CodeFile model."""

    def test_valid_code_file(self) -> None:
        """Test creating a valid code file."""
        file = CodeFile(
            path="backend/main.py",
            content="print('hello')",
            language="python",
        )
        assert file.path == "backend/main.py"

    def test_unsafe_path_dotdot(self) -> None:
        """Test that .. in path is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CodeFile(
                path="../etc/passwd",
                content="content",
                language="text",
            )
        assert "unsafe" in str(exc_info.value).lower()

    def test_unsafe_path_leading_slash(self) -> None:
        """Test that leading / in path is rejected."""
        with pytest.raises(ValidationError):
            CodeFile(
                path="/etc/passwd",
                content="content",
                language="text",
            )

    def test_empty_content_rejected(self) -> None:
        """Test that empty content is rejected."""
        with pytest.raises(ValidationError):
            CodeFile(
                path="file.py",
                content="",
                language="python",
            )

    def test_whitespace_only_content_rejected(self) -> None:
        """Test that whitespace-only content is rejected."""
        with pytest.raises(ValidationError):
            CodeFile(
                path="file.py",
                content="   \n\t  ",
                language="python",
            )


class TestFileBundle:
    """Test FileBundle model."""

    def test_valid_file_bundle(self) -> None:
        """Test creating a valid file bundle."""
        bundle = FileBundle(
            files=[CodeFile(path="main.py", content="print('hi')", language="python")],
            entry_point="main.py",
            install_commands=["pip install -r requirements.txt"],
            run_commands=["python main.py"],
        )
        assert len(bundle.files) == 1

    def test_empty_files_rejected(self) -> None:
        """Test that empty files list is rejected."""
        with pytest.raises(ValidationError):
            FileBundle(files=[], entry_point="main.py")


# =============================================================================
# QA Model Tests
# =============================================================================


class TestTestReport:
    """Test TestReport model."""

    def test_valid_test_report(self) -> None:
        """Test creating a valid test report."""
        report = TestReport(
            total=5,
            passed=4,
            failed=1,
            skipped=0,
            duration_ms=1234.5,
            cases=[
                TestCase(name="test_one", file="test.py", passed=True, duration_ms=100),
            ],
        )
        assert report.total == 5
        assert not report.all_passed

    def test_all_passed_property(self) -> None:
        """Test all_passed property."""
        report = TestReport(
            total=3,
            passed=3,
            failed=0,
            skipped=0,
            duration_ms=500,
        )
        assert report.all_passed

    def test_invalid_totals(self) -> None:
        """Test that mismatched totals are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TestReport(
                total=10,  # Should be 5
                passed=3,
                failed=2,
                skipped=0,
                duration_ms=100,
            )
        assert "total" in str(exc_info.value).lower()

    def test_negative_values_rejected(self) -> None:
        """Test that negative values are rejected."""
        with pytest.raises(ValidationError):
            TestReport(
                total=-1,
                passed=0,
                failed=0,
                duration_ms=100,
            )


# =============================================================================
# AgentState Tests
# =============================================================================


class TestAgentState:
    """Test AgentState model."""

    def test_minimal_state(self) -> None:
        """Test creating a minimal valid state."""
        state = AgentState(description="Build a todo app")
        assert state.description == "Build a todo app"
        assert state.phase == Phase.INIT
        assert state.retry_count == 0
        assert state.prd is None

    def test_state_with_prd(self) -> None:
        """Test state with a PRD attached."""
        prd = PRD(
            project_name="Test",
            project_slug="test",
            project_type=ProjectType.REST_API,
            one_liner="A test project",
            target_users=["devs"],
            user_stories=[
                UserStory(
                    id="US-001",
                    role="user",
                    goal="do thing",
                    benefit="value",
                    acceptance_criteria=["works"],
                    priority=Priority.P0,
                )
            ],
            must_have_features=["feature"],
        )
        state = AgentState(description="test", prd=prd)
        assert state.prd is not None
        assert state.prd.project_slug == "test"

    def test_total_cost_property(self) -> None:
        """Test total_cost_usd calculation."""
        state = AgentState(
            description="test",
            costs=[
                CostEntry(
                    agent=AgentRole.PRODUCT_MANAGER,
                    model="gpt-4",
                    input_tokens=100,
                    output_tokens=50,
                    cost_usd=0.05,
                ),
                CostEntry(
                    agent=AgentRole.ARCHITECT,
                    model="gpt-4",
                    input_tokens=200,
                    output_tokens=100,
                    cost_usd=0.10,
                ),
            ],
        )
        assert abs(state.total_cost_usd - 0.15) < 0.0001

    def test_total_tokens_property(self) -> None:
        """Test total_tokens calculation."""
        state = AgentState(
            description="test",
            costs=[
                CostEntry(
                    agent=AgentRole.PRODUCT_MANAGER,
                    model="gpt-4",
                    input_tokens=100,
                    output_tokens=50,
                    cost_usd=0.05,
                ),
            ],
        )
        assert state.total_tokens == 150

    def test_add_event_helper(self) -> None:
        """Test add_event helper method."""
        state = AgentState(description="test")
        state.add_event(
            EventType.AGENT_START,
            agent=AgentRole.PRODUCT_MANAGER,
            message="Starting PM",
        )
        assert len(state.events) == 1
        assert state.events[0].type == EventType.AGENT_START

    def test_add_cost_helper(self) -> None:
        """Test add_cost helper method."""
        state = AgentState(description="test")
        state.add_cost(
            agent=AgentRole.ARCHITECT,
            model="claude-3",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.02,
        )
        assert len(state.costs) == 1
        assert state.costs[0].cost_usd == 0.02

    def test_state_round_trip(self) -> None:
        """Test serialization round-trip."""
        state = AgentState(
            description="test project",
            phase=Phase.DESIGN,
            retry_count=1,
        )
        data = state.model_dump()
        restored = AgentState.model_validate(data)
        assert restored.description == state.description
        assert restored.phase == state.phase
        assert restored.retry_count == state.retry_count

    def test_empty_description_rejected(self) -> None:
        """Test that empty description is rejected."""
        with pytest.raises(ValidationError):
            AgentState(description="")


# =============================================================================
# Config Model Tests
# =============================================================================


class TestLLMConfig:
    """Test LLMConfig model."""

    def test_default_config(self) -> None:
        """Test default LLM config."""
        from loom.config import LLMConfig

        config = LLMConfig()
        assert config.provider == "ollama"
        assert config.model == "qwen2.5-coder:7b"
        assert config.temperature == 0.2

    def test_custom_config(self) -> None:
        """Test custom LLM config."""
        from loom.config import LLMConfig

        config = LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.3,
        )
        assert config.provider == "anthropic"

    def test_invalid_temperature(self) -> None:
        """Test that invalid temperature is rejected."""
        from loom.config import LLMConfig

        with pytest.raises(ValidationError):
            LLMConfig(temperature=3.0)  # Max is 2.0


class TestLoomConfig:
    """Test LoomConfig model."""

    def test_default_config(self) -> None:
        """Test default Loom config."""
        from loom.config import LoomConfig

        config = LoomConfig()
        assert config.output_dir == "./output"
        assert config.max_retries == 2
        assert not config.interactive

    def test_get_llm_config_default(self) -> None:
        """Test getting default LLM config for a role."""
        from loom.config import LoomConfig

        config = LoomConfig()
        llm_config = config.get_llm_config(AgentRole.PRODUCT_MANAGER)
        assert llm_config.model == "qwen2.5-coder:7b"

    def test_get_llm_config_override(self) -> None:
        """Test getting overridden LLM config for a role."""
        from loom.config import LoomConfig, LLMConfig

        config = LoomConfig(
            llm_overrides={
                AgentRole.DEVOPS: LLMConfig(provider="anthropic", model="claude-haiku-3-5")
            }
        )
        devops_config = config.get_llm_config(AgentRole.DEVOPS)
        assert devops_config.model == "claude-haiku-3-5"

        # Other roles still use default
        pm_config = config.get_llm_config(AgentRole.PRODUCT_MANAGER)
        assert pm_config.model == "qwen2.5-coder:7b"
