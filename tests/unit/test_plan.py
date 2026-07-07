"""Tests for the plan and cost estimation modules."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from loom.cost.estimator import (
    _get_complexity_multiplier,
    _has_frontend,
    estimate_build_cost,
    estimate_duration,
)
from loom.plan.serializer import default_plan_path, load_plan, save_plan


class TestCostEstimator:
    """Tests for cost estimation."""

    def test_estimate_build_cost_ollama_is_free(self) -> None:
        """Test that Ollama estimates are always zero."""
        state = {"prd": None, "architecture": None}
        low, high = estimate_build_cost(state, "ollama", "llama3")
        assert low == 0.0
        assert high == 0.0

    def test_estimate_build_cost_anthropic(self) -> None:
        """Test Anthropic cost estimation returns non-zero values."""
        state = {"prd": None, "architecture": None}
        low, high = estimate_build_cost(state, "anthropic", "claude-sonnet-4-20250514")
        assert low >= 0.0
        assert high >= low

    def test_estimate_duration_basic(self) -> None:
        """Test duration estimation returns reasonable values."""
        state = {"prd": None, "architecture": None}
        low, high = estimate_duration(state, "anthropic")
        assert low > 0
        assert high >= low
        assert low < 600  # Less than 10 minutes
        assert high < 1200  # Less than 20 minutes

    def test_estimate_duration_ollama_slower(self) -> None:
        """Test that Ollama estimates are longer."""
        state = {"prd": None, "architecture": None}
        anthropic_low, anthropic_high = estimate_duration(state, "anthropic")
        ollama_low, ollama_high = estimate_duration(state, "ollama")
        assert ollama_low >= anthropic_low
        assert ollama_high >= anthropic_high

    def test_complexity_multiplier_no_prd(self) -> None:
        """Test complexity multiplier with no PRD."""
        state = {"prd": None}
        mult = _get_complexity_multiplier(state)
        assert mult == 1.0

    def test_complexity_multiplier_with_stories(self) -> None:
        """Test complexity multiplier increases with user stories."""
        prd = Mock()
        prd.user_stories = [Mock() for _ in range(10)]
        prd.data_entities = []
        prd.must_have_features = []
        state = {"prd": prd}
        mult = _get_complexity_multiplier(state)
        assert mult > 1.0

    def test_complexity_multiplier_capped(self) -> None:
        """Test complexity multiplier is capped at 2.5."""
        prd = Mock()
        prd.user_stories = [Mock() for _ in range(50)]
        prd.data_entities = [Mock() for _ in range(50)]
        prd.must_have_features = [Mock() for _ in range(50)]
        state = {"prd": prd}
        mult = _get_complexity_multiplier(state)
        assert mult <= 2.5

    def test_has_frontend_no_architecture(self) -> None:
        """Test has_frontend returns True with no architecture."""
        state = {"architecture": None}
        assert _has_frontend(state) is True

    def test_has_frontend_with_frontend_stack(self) -> None:
        """Test has_frontend detects frontend stack."""
        tech = Mock()
        tech.layer = "frontend"
        tech.technology = "React"

        architecture = Mock()
        architecture.stack = [tech]

        state = {"architecture": architecture}
        assert _has_frontend(state) is True

    def test_has_frontend_no_frontend_in_stack(self) -> None:
        """Test has_frontend returns False for backend-only."""
        tech = Mock()
        tech.layer = "backend"
        tech.technology = "FastAPI"

        architecture = Mock()
        architecture.stack = [tech]

        state = {"architecture": architecture}
        assert _has_frontend(state) is False


class TestPlanSerializer:
    """Tests for plan serialization."""

    @pytest.fixture
    def sample_prd(self) -> Mock:
        """Create a sample PRD mock."""
        prd = Mock()
        prd.project_slug = "test-project"
        prd.user_stories = []
        prd.data_entities = []
        prd.must_have_features = []
        prd.model_dump.return_value = {
            "project_name": "Test Project",
            "project_slug": "test-project",
            "one_liner": "A test project",
        }
        return prd

    @pytest.fixture
    def sample_architecture(self) -> Mock:
        """Create a sample architecture mock."""
        tech = Mock()
        tech.layer = "backend"
        tech.technology = "FastAPI"

        arch = Mock()
        arch.stack = [tech]
        arch.api_endpoints = []
        arch.model_dump.return_value = {
            "stack": [{"layer": "backend", "technology": "FastAPI"}],
            "api_endpoints": [],
        }
        return arch

    def test_save_plan_creates_file(
        self, sample_prd: Mock, sample_architecture: Mock, tmp_path: Path
    ) -> None:
        """Test that save_plan creates a file."""
        state = {
            "prd": sample_prd,
            "architecture": sample_architecture,
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

    def test_save_plan_contains_required_fields(
        self, sample_prd: Mock, sample_architecture: Mock, tmp_path: Path
    ) -> None:
        """Test that saved plan contains all required fields."""
        import json

        state = {
            "prd": sample_prd,
            "architecture": sample_architecture,
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

        assert data["version"] == 1
        assert data["thread_id"] == "test-123"
        assert data["description"] == "Test project"
        assert "prd" in data
        assert "architecture" in data
        assert "estimated_cost_usd" in data
        assert "estimated_duration_sec" in data

    def test_load_plan_success(
        self, sample_prd: Mock, sample_architecture: Mock, tmp_path: Path
    ) -> None:
        """Test loading a valid plan file."""
        state = {
            "prd": sample_prd,
            "architecture": sample_architecture,
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
        """Test loading a non-existent plan file."""
        with pytest.raises(FileNotFoundError):
            load_plan(tmp_path / "nonexistent.json")

    def test_load_plan_invalid_version(self, tmp_path: Path) -> None:
        """Test loading a plan with unsupported version."""
        import json

        plan_path = tmp_path / "bad-plan.json"
        with open(plan_path, "w") as f:
            json.dump({"version": 999}, f)

        with pytest.raises(ValueError, match="Unsupported plan version"):
            load_plan(plan_path)

    def test_load_plan_missing_fields(self, tmp_path: Path) -> None:
        """Test loading a plan with missing required fields."""
        import json

        plan_path = tmp_path / "bad-plan.json"
        with open(plan_path, "w") as f:
            json.dump({"version": 1}, f)

        with pytest.raises(ValueError, match="Missing required field"):
            load_plan(plan_path)

    def test_default_plan_path_with_prd(self) -> None:
        """Test default_plan_path uses project slug."""
        prd = Mock()
        prd.project_slug = "my-project"
        state = {"prd": prd}

        path = default_plan_path(state)

        assert "my-project" in str(path)
        assert path.suffix == ".json"

    def test_default_plan_path_without_prd(self) -> None:
        """Test default_plan_path uses 'plan' without PRD."""
        state = {"prd": None}

        path = default_plan_path(state)

        assert "plan" in str(path)
        assert path.suffix == ".json"
