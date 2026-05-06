"""QA Engineer agent node.

Writes and runs tests against the generated code.
NOTE: This is a STUB that produces fake passing tests until the sandbox is implemented.
"""

import logging
from datetime import datetime
from typing import Any

from agentforge.config import AgentForgeConfig
from agentforge.state.enums import AgentRole, EventType, Phase
from agentforge.state.models import Event, TestCase, TestReport

logger = logging.getLogger(__name__)


def _create_stub_test_report(prd: Any) -> TestReport:
    """Create a stub test report with fake passing tests.

    In the real implementation, this will use the sandbox to run actual tests.
    """
    # Create fake test cases based on user stories
    test_cases = []
    if prd and hasattr(prd, "user_stories"):
        for i, story in enumerate(prd.user_stories):
            test_cases.append(
                TestCase(
                    name=f"test_{story.id.lower().replace('-', '_')}_happy_path",
                    file=f"tests/test_user_story_{i + 1}.py",
                    passed=True,
                    duration_ms=50.0 + (i * 10),
                    error_message=None,
                )
            )

    # Add a basic health check test
    test_cases.append(
        TestCase(
            name="test_health_endpoint",
            file="tests/test_health.py",
            passed=True,
            duration_ms=25.0,
            error_message=None,
        )
    )

    total = len(test_cases)
    return TestReport(
        total=total,
        passed=total,
        failed=0,
        skipped=0,
        duration_ms=sum(tc.duration_ms for tc in test_cases),
        cases=test_cases,
        coverage_percent=85.0,  # Fake coverage
        raw_output="All tests passed (STUB - sandbox not implemented)",
    )


async def qa_engineer_node(
    state: dict[str, Any],
    config: AgentForgeConfig | None = None,
) -> dict[str, Any]:
    """QA Engineer agent node function.

    NOTE: This is a STUB implementation that produces fake passing tests.
    Real implementation will use the sandbox to run actual tests.

    Args:
        state: Current graph state
        config: Optional AgentForge configuration

    Returns:
        State update dict with test_report, events, and costs
    """
    prd = state.get("prd")
    code_files = state.get("code_files", {})

    # Check required inputs
    if not code_files:
        return {
            "events": [
                Event(
                    timestamp=datetime.utcnow(),
                    type=EventType.ERROR,
                    agent=AgentRole.QA,
                    phase=Phase.TESTING,
                    payload={"error": "No code files provided"},
                )
            ],
            "error": "No code files provided for testing",
        }

    logger.warning("QA Engineer is using STUB implementation - returning fake passing tests")

    # Create stub test report
    test_report = _create_stub_test_report(prd)

    events = [
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.AGENT_START,
            agent=AgentRole.QA,
            phase=Phase.TESTING,
            payload={"message": "Starting QA testing (STUB)"},
        ),
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.AGENT_END,
            agent=AgentRole.QA,
            phase=Phase.TESTING,
            payload={
                "total_tests": test_report.total,
                "passed": test_report.passed,
                "failed": test_report.failed,
                "stub": True,
            },
        ),
    ]

    logger.info(
        f"QA tests (STUB): {test_report.passed}/{test_report.total} passed"
    )

    return {
        "test_report": test_report,
        "phase": Phase.DEPLOYMENT,  # Move to deployment since tests "pass"
        "qa_feedback": None,  # No feedback needed since tests pass
        "events": events,
        "costs": [],  # No LLM costs for stub
    }
