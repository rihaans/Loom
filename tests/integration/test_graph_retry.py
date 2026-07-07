"""Integration tests for QA retry flow.

Tests the retry budget enforcement and routing decisions.
"""

from unittest.mock import Mock

from loom.graph.parallel import should_retry_development
from loom.graph.routing import route_after_qa


class TestQARetryBudget:
    """Test QA retry budget enforcement."""

    def test_first_failure_routes_to_developers(self) -> None:
        """First test failure should route back to developers."""
        test_report = Mock()
        test_report.failed = 2

        state = {
            "test_report": test_report,
            "retry_count": 0,
            "max_retries": 2,
        }

        result = route_after_qa(state)
        assert result == "developers"

    def test_second_failure_routes_to_developers(self) -> None:
        """Second test failure should still route back if budget remains."""
        test_report = Mock()
        test_report.failed = 1

        state = {
            "test_report": test_report,
            "retry_count": 1,
            "max_retries": 2,
        }

        result = route_after_qa(state)
        assert result == "developers"

    def test_budget_exhausted_proceeds_to_devops(self) -> None:
        """When retry budget is exhausted, proceed to devops anyway."""
        test_report = Mock()
        test_report.failed = 1

        state = {
            "test_report": test_report,
            "retry_count": 2,
            "max_retries": 2,
        }

        result = route_after_qa(state)
        assert result == "devops_engineer"

    def test_passing_tests_skip_retry(self) -> None:
        """Passing tests should skip retry and go to devops."""
        test_report = Mock()
        test_report.failed = 0

        state = {
            "test_report": test_report,
            "retry_count": 0,
            "max_retries": 2,
        }

        result = route_after_qa(state)
        assert result == "devops_engineer"

    def test_no_test_report_routes_to_supervisor(self) -> None:
        """No test report indicates an error — route to supervisor."""
        state = {
            "test_report": None,
            "retry_count": 0,
            "max_retries": 2,
        }

        result = route_after_qa(state)
        assert result == "supervisor"


class TestRetryDecision:
    """Test the should_retry_development decision logic."""

    def test_retry_when_failures_and_budget(self) -> None:
        """Should retry when there are failures and budget."""
        test_report = Mock()
        test_report.failed = 2
        qa_feedback = Mock()

        state = {
            "test_report": test_report,
            "qa_feedback": qa_feedback,
            "retry_count": 0,
            "max_retries": 2,
        }

        assert should_retry_development(state) is True

    def test_no_retry_when_passing(self) -> None:
        """Should not retry when tests pass."""
        test_report = Mock()
        test_report.failed = 0

        state = {
            "test_report": test_report,
            "qa_feedback": None,
            "retry_count": 0,
            "max_retries": 2,
        }

        assert should_retry_development(state) is False

    def test_no_retry_when_no_feedback(self) -> None:
        """Should not retry without QA feedback."""
        test_report = Mock()
        test_report.failed = 1

        state = {
            "test_report": test_report,
            "qa_feedback": None,
            "retry_count": 0,
            "max_retries": 2,
        }

        assert should_retry_development(state) is False


class TestRetryCountIncrement:
    """Test that retry behavior depends on retry count."""

    def test_retry_count_zero_with_failures(self) -> None:
        """At retry_count=0, failures should retry."""
        test_report = Mock()
        test_report.failed = 1

        state = {
            "test_report": test_report,
            "retry_count": 0,
            "max_retries": 3,
        }

        # Should retry: 0 < 3
        assert route_after_qa(state) == "developers"

    def test_retry_count_at_max_no_retry(self) -> None:
        """At retry_count=max, should not retry further."""
        test_report = Mock()
        test_report.failed = 1

        state = {
            "test_report": test_report,
            "retry_count": 3,
            "max_retries": 3,
        }

        # Should not retry: 3 not < 3
        assert route_after_qa(state) == "devops_engineer"

    def test_max_retries_zero_never_retries(self) -> None:
        """With max_retries=0, never retries."""
        test_report = Mock()
        test_report.failed = 1

        state = {
            "test_report": test_report,
            "retry_count": 0,
            "max_retries": 0,
        }

        assert route_after_qa(state) == "devops_engineer"
