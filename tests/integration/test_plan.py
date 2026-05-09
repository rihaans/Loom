"""Integration tests for the plan workflow.

Tests the plan command flow: plan preview -> save -> build from plan.
"""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from loom.cost.estimator import estimate_build_cost, estimate_duration
from loom.plan.serializer import default_plan_path, load_plan, save_plan
from loom.state.enums import TechLayer


def create_mock_prd() -> Mock:
    """Create a mock PRD."""
    prd = Mock()
    prd.project_name = "Test Project"
    prd.project_slug = "test-project"
    prd.one_liner = "A test project"
    prd.user_stories = [Mock(), Mock(), Mock()]
    prd.data_entities = [Mock()]
    prd.must_have_features = ["Feature 1", "Feature 2"]
    prd.model_dump.return_value = {
        "project_name": "Test Project",
        "project_slug": "test-project",
        "one_liner": "A test project",
    }
    return prd


def create_mock_architecture() -> Mock:
    """Create a mock architecture."""
    arch = Mock()

    backend = Mock()
    backend.layer = TechLayer.BACKEND
    backend.technology = "FastAPI"

    frontend = Mock()
    frontend.layer = TechLayer.FRONTEND
    frontend.technology = "React"

    arch.stack = [backend, frontend]
    arch.api_endpoints = [Mock() for _ in range(5)]
    arch.model_dump.return_value = {
        "overview": "Test architecture",
        "stack": [
            {"layer": "backend", "technology": "FastAPI"},
            {"layer": "frontend", "technology": "React"},
        ],
    }
    return arch


class TestCostEstimation:
    """Test cost estimation functions."""

    def test_anthropic_cost_estimation(self) -> None:
        """Test cost estimation for Anthropic provider."""
        state = {"prd": None, "architecture": None}

        low, high = estimate_build_cost(state, "anthropic", "claude-sonnet-4-20250514")

        assert low >= 0
        assert high >= low
        # Should be non-zero for paid provider
        assert high > 0

    def test_ollama_cost_is_free(self) -> None:
        """Test that Ollama estimates are always zero."""
        state = {"prd": None, "architecture": None}

        low, high = estimate_build_cost(state, "ollama", "llama3")

        assert low == 0
        assert high == 0

    def test_duration_estimation(self) -> None:
        """Test duration estimation."""
        state = {"prd": None, "architecture": None}

        low, high = estimate_duration(state, "anthropic")

        assert low > 0
        assert high >= low
        # Should be reasonable bounds (less than 20 minutes)
        assert high < 1200

    def test_complexity_increases_estimates(self) -> None:
        """Test that more complex projects have higher estimates."""
        simple_state = {"prd": None, "architecture": None}

        complex_prd = Mock()
        complex_prd.user_stories = [Mock() for _ in range(20)]
        complex_prd.data_entities = [Mock() for _ in range(10)]
        complex_prd.must_have_features = [Mock() for _ in range(15)]

        complex_arch = Mock()
        complex_arch.stack = [Mock() for _ in range(5)]

        complex_state = {"prd": complex_prd, "architecture": complex_arch}

        simple_low, simple_high = estimate_build_cost(simple_state, "anthropic", "claude-sonnet-4-20250514")
        complex_low, complex_high = estimate_build_cost(complex_state, "anthropic", "claude-sonnet-4-20250514")

        # Complex project should have higher estimates
        assert complex_high >= simple_high

    def test_frontend_presence_affects_estimates(self) -> None:
        """Test that frontend presence affects duration estimates."""
        # Backend only
        backend_only = Mock()
        backend_only.layer = TechLayer.BACKEND
        backend_only.technology = "FastAPI"

        backend_arch = Mock()
        backend_arch.stack = [backend_only]

        backend_state = {"prd": None, "architecture": backend_arch}

        # With frontend
        frontend = Mock()
        frontend.layer = TechLayer.FRONTEND
        frontend.technology = "React"

        fullstack_arch = Mock()
        fullstack_arch.stack = [backend_only, frontend]

        fullstack_state = {"prd": None, "architecture": fullstack_arch}

        backend_low, backend_high = estimate_duration(backend_state, "anthropic")
        fullstack_low, fullstack_high = estimate_duration(fullstack_state, "anthropic")

        # Fullstack should take longer (or equal)
        assert fullstack_high >= backend_high


class TestPlanSerialization:
    """Test plan save/load functionality."""

    def test_save_plan_creates_file(self, tmp_path: Path) -> None:
        """Test that save_plan creates a valid JSON file."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        state = {
            "prd": prd,
            "architecture": arch,
            "memory_context": None,
        }

        plan_path = tmp_path / "test-plan.json"

        result = save_plan(
            state=state,
            path=plan_path,
            thread_id="test-123",
            description="Test project",
            config=None,
        )

        assert result == plan_path
        assert plan_path.exists()

        # Verify JSON is valid
        with open(plan_path) as f:
            data = json.load(f)

        assert data["version"] == 1
        assert data["thread_id"] == "test-123"

    def test_save_plan_includes_estimates(self, tmp_path: Path) -> None:
        """Test that saved plan includes cost and duration estimates."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        state = {
            "prd": prd,
            "architecture": arch,
            "memory_context": None,
        }

        plan_path = tmp_path / "test-plan.json"

        save_plan(
            state=state,
            path=plan_path,
            thread_id="test-123",
            description="Test project",
            config=None,
        )

        with open(plan_path) as f:
            data = json.load(f)

        assert "estimated_cost_usd" in data
        assert "estimated_duration_sec" in data
        assert len(data["estimated_cost_usd"]) == 2  # [low, high]
        assert len(data["estimated_duration_sec"]) == 2  # [low, high]

    def test_load_plan_success(self, tmp_path: Path) -> None:
        """Test loading a valid plan file."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        state = {
            "prd": prd,
            "architecture": arch,
            "memory_context": None,
        }

        plan_path = tmp_path / "test-plan.json"

        save_plan(
            state=state,
            path=plan_path,
            thread_id="test-123",
            description="Test project",
            config=None,
        )

        loaded = load_plan(plan_path)

        assert loaded["thread_id"] == "test-123"
        assert loaded["description"] == "Test project"
        assert loaded["version"] == 1

    def test_load_plan_file_not_found(self, tmp_path: Path) -> None:
        """Test loading non-existent plan file."""
        with pytest.raises(FileNotFoundError):
            load_plan(tmp_path / "nonexistent.json")

    def test_load_plan_invalid_version(self, tmp_path: Path) -> None:
        """Test loading plan with unsupported version."""
        plan_path = tmp_path / "bad-plan.json"

        with open(plan_path, "w") as f:
            json.dump({"version": 999}, f)

        with pytest.raises(ValueError, match="Unsupported plan version"):
            load_plan(plan_path)

    def test_load_plan_missing_fields(self, tmp_path: Path) -> None:
        """Test loading plan with missing required fields."""
        plan_path = tmp_path / "incomplete-plan.json"

        with open(plan_path, "w") as f:
            json.dump({"version": 1}, f)

        with pytest.raises(ValueError, match="Missing required field"):
            load_plan(plan_path)

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Test that save->load preserves data."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        state = {
            "prd": prd,
            "architecture": arch,
            "memory_context": None,
        }

        plan_path = tmp_path / "roundtrip-plan.json"

        save_plan(
            state=state,
            path=plan_path,
            thread_id="roundtrip-123",
            description="Roundtrip test",
            config=None,
        )

        loaded = load_plan(plan_path)

        assert loaded["thread_id"] == "roundtrip-123"
        assert loaded["description"] == "Roundtrip test"
        assert loaded["prd"]["project_name"] == "Test Project"


class TestDefaultPlanPath:
    """Test default plan path generation."""

    def test_with_prd_uses_slug(self) -> None:
        """Test that default path uses project slug from PRD."""
        prd = Mock()
        prd.project_slug = "my-project"

        state = {"prd": prd}
        path = default_plan_path(state)

        assert "my-project" in str(path)
        assert path.suffix == ".json"

    def test_without_prd_uses_plan(self) -> None:
        """Test that default path uses 'plan' without PRD."""
        state = {"prd": None}
        path = default_plan_path(state)

        assert "plan" in str(path)
        assert path.suffix == ".json"

    def test_path_includes_date(self) -> None:
        """Test that default path includes date."""
        from datetime import datetime

        prd = Mock()
        prd.project_slug = "test"

        state = {"prd": prd}
        path = default_plan_path(state)

        today = datetime.utcnow().strftime("%Y-%m-%d")
        assert today in str(path)


class TestPlanWorkflow:
    """Test the complete plan workflow."""

    def test_plan_then_build_preserves_state(self, tmp_path: Path) -> None:
        """Test that building from plan preserves original state."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        original_state = {
            "prd": prd,
            "architecture": arch,
            "memory_context": None,
        }

        plan_path = tmp_path / "workflow-plan.json"

        # Save plan
        save_plan(
            state=original_state,
            path=plan_path,
            thread_id="workflow-123",
            description="Workflow test",
            config=None,
        )

        # Load plan
        loaded = load_plan(plan_path)

        # Verify key data preserved
        assert loaded["thread_id"] == "workflow-123"
        assert loaded["prd"]["project_name"] == "Test Project"
        assert loaded["architecture"]["overview"] == "Test architecture"

    def test_plan_with_config_saves_llm_settings(self, tmp_path: Path) -> None:
        """Test that plan saves LLM configuration."""
        from loom.config import LoomConfig

        prd = create_mock_prd()
        arch = create_mock_architecture()

        config = LoomConfig()

        state = {
            "prd": prd,
            "architecture": arch,
            "memory_context": None,
        }

        plan_path = tmp_path / "config-plan.json"

        save_plan(
            state=state,
            path=plan_path,
            thread_id="config-123",
            description="Config test",
            config=config,
        )

        with open(plan_path) as f:
            data = json.load(f)

        assert "config" in data
        assert "llm_default" in data["config"]
