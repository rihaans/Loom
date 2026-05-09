"""Integration tests for parallel developer execution.

Tests the parallel routing and result merging logic.
"""

from unittest.mock import Mock

import pytest

from loom.graph.parallel import (
    get_retry_targets,
    merge_dev_results,
    route_to_devs,
    route_to_retry_devs,
    should_retry_development,
)
from loom.state.enums import TargetAgent


class TestRouteToDevs:
    """Test the parallel fan-out to developers."""

    def test_returns_two_send_objects(self) -> None:
        """Both frontend and backend should be routed."""
        state = {"architecture": Mock(), "error": None}
        result = route_to_devs(state)

        assert isinstance(result, list)
        assert len(result) == 2

    def test_targets_frontend_and_backend(self) -> None:
        """Both frontend_dev and backend_dev should be Send targets."""
        state = {"architecture": Mock(), "error": None}
        result = route_to_devs(state)

        nodes = {send.node for send in result}
        assert nodes == {"frontend_dev", "backend_dev"}

    def test_passes_state_to_both(self) -> None:
        """Both Send objects should carry the state."""
        state = {"architecture": Mock(), "error": None, "description": "test"}
        result = route_to_devs(state)

        for send in result:
            assert send.arg == state


class TestMergeDevResults:
    """Test merging of parallel developer results."""

    def test_merge_empty_results(self) -> None:
        """Empty results should produce empty merged state."""
        merged = merge_dev_results([])

        assert merged["code_files"] == {}
        assert merged["events"] == []
        assert merged["costs"] == []

    def test_merge_code_files(self) -> None:
        """Code files from both devs should be merged."""
        results = [
            {"code_files": {"frontend": Mock()}},
            {"code_files": {"backend": Mock()}},
        ]
        merged = merge_dev_results(results)

        assert "frontend" in merged["code_files"]
        assert "backend" in merged["code_files"]

    def test_merge_events(self) -> None:
        """Events should be appended."""
        results = [
            {"events": ["event1", "event2"]},
            {"events": ["event3"]},
        ]
        merged = merge_dev_results(results)

        assert len(merged["events"]) == 3

    def test_merge_costs(self) -> None:
        """Costs should be appended."""
        results = [
            {"costs": [{"tokens": 100}]},
            {"costs": [{"tokens": 200}]},
        ]
        merged = merge_dev_results(results)

        assert len(merged["costs"]) == 2

    def test_merge_with_error(self) -> None:
        """Errors should be propagated."""
        results = [
            {"code_files": {}, "error": "Frontend failed"},
            {"code_files": {}, "error": None},
        ]
        merged = merge_dev_results(results)

        assert "error" in merged
        assert "Frontend failed" in merged["error"]

    def test_merge_combines_multiple_errors(self) -> None:
        """Multiple errors should be combined."""
        results = [
            {"error": "Frontend failed"},
            {"error": "Backend failed"},
        ]
        merged = merge_dev_results(results)

        assert "error" in merged
        assert "Frontend failed" in merged["error"]
        assert "Backend failed" in merged["error"]


class TestShouldRetryDevelopment:
    """Test retry decision logic."""

    def test_no_test_report_no_retry(self) -> None:
        """No test report means don't retry."""
        state = {"test_report": None}
        assert should_retry_development(state) is False

    def test_passing_tests_no_retry(self) -> None:
        """Passing tests should not retry."""
        test_report = Mock()
        test_report.failed = 0
        state = {"test_report": test_report, "retry_count": 0, "max_retries": 2}

        assert should_retry_development(state) is False

    def test_failing_tests_with_budget_retries(self) -> None:
        """Failing tests with retry budget should retry."""
        test_report = Mock()
        test_report.failed = 3
        qa_feedback = Mock()
        state = {
            "test_report": test_report,
            "qa_feedback": qa_feedback,
            "retry_count": 0,
            "max_retries": 2,
        }

        assert should_retry_development(state) is True

    def test_failing_tests_budget_exhausted(self) -> None:
        """Failing tests with no budget should not retry."""
        test_report = Mock()
        test_report.failed = 3
        state = {
            "test_report": test_report,
            "qa_feedback": Mock(),
            "retry_count": 2,
            "max_retries": 2,
        }

        assert should_retry_development(state) is False

    def test_no_qa_feedback_no_retry(self) -> None:
        """Failing tests without feedback should not retry."""
        test_report = Mock()
        test_report.failed = 3
        state = {
            "test_report": test_report,
            "qa_feedback": None,
            "retry_count": 0,
            "max_retries": 2,
        }

        assert should_retry_development(state) is False


class TestGetRetryTargets:
    """Test retry target selection."""

    def test_no_feedback_retries_both(self) -> None:
        """No feedback should retry both."""
        state = {"qa_feedback": None}
        targets = get_retry_targets(state)
        assert set(targets) == {"frontend_dev", "backend_dev"}

    def test_frontend_target(self) -> None:
        """Frontend feedback targets frontend only."""
        qa_feedback = Mock()
        qa_feedback.target_agent = TargetAgent.FRONTEND_DEV
        state = {"qa_feedback": qa_feedback}

        targets = get_retry_targets(state)
        assert targets == ["frontend_dev"]

    def test_backend_target(self) -> None:
        """Backend feedback targets backend only."""
        qa_feedback = Mock()
        qa_feedback.target_agent = TargetAgent.BACKEND_DEV
        state = {"qa_feedback": qa_feedback}

        targets = get_retry_targets(state)
        assert targets == ["backend_dev"]

    def test_both_target(self) -> None:
        """'Both' feedback targets both."""
        qa_feedback = Mock()
        qa_feedback.target_agent = TargetAgent.BOTH
        state = {"qa_feedback": qa_feedback}

        targets = get_retry_targets(state)
        assert set(targets) == {"frontend_dev", "backend_dev"}


class TestRouteToRetryDevs:
    """Test the retry routing function."""

    def test_returns_send_objects(self) -> None:
        """Should return list of Send objects."""
        qa_feedback = Mock()
        qa_feedback.target_agent = TargetAgent.BOTH
        state = {"qa_feedback": qa_feedback}

        result = route_to_retry_devs(state)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_frontend_only_retry(self) -> None:
        """Frontend-only retry returns single Send."""
        qa_feedback = Mock()
        qa_feedback.target_agent = TargetAgent.FRONTEND_DEV
        state = {"qa_feedback": qa_feedback}

        result = route_to_retry_devs(state)
        assert len(result) == 1
        assert result[0].node == "frontend_dev"

    def test_backend_only_retry(self) -> None:
        """Backend-only retry returns single Send."""
        qa_feedback = Mock()
        qa_feedback.target_agent = TargetAgent.BACKEND_DEV
        state = {"qa_feedback": qa_feedback}

        result = route_to_retry_devs(state)
        assert len(result) == 1
        assert result[0].node == "backend_dev"
