"""QA Engineer agent node.

Writes and runs tests against the generated code using the sandbox.
Falls back to stub mode if sandbox is unavailable.
"""

import logging
from typing import Any

from loom._time import now_utc
from loom.config import LoomConfig
from loom.sandbox import (
    ExecutionStatus,
    SandboxConfig,
    TestRunConfig,
    create_sandbox_runner,
    is_sandbox_available,
    parse_test_output,
)
from loom.state.enums import AgentRole, EventType, Phase, TargetAgent
from loom.state.models import Event, QAFeedback, TestCase, TestReport

logger = logging.getLogger(__name__)

SANDBOX_REQUIRED_MESSAGE = (
    "No sandbox available, so tests cannot actually be run. Install Docker and "
    "run `loom sandbox build`, or drop --require-sandbox to continue with "
    "results explicitly marked as unverified."
)


def _create_stub_test_report(prd: Any) -> TestReport:
    """Create a stub test report with fake passing tests.

    Used when sandbox is not available.
    """
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
        # No coverage is reported: nothing was executed, so nothing was measured.
        coverage_percent=None,
        raw_output=(
            "NOT VERIFIED - no sandbox was available, so no tests were executed. "
            "These cases are placeholders derived from the PRD, not results."
        ),
        is_stub=True,
    )


def _extract_files_from_bundles(code_files: dict[str, Any]) -> dict[str, str]:
    """Extract file contents from FileBundle objects.

    Args:
        code_files: Dict of bundle_name -> FileBundle

    Returns:
        Dict of file_path -> content
    """
    files: dict[str, str] = {}
    for bundle in code_files.values():
        if hasattr(bundle, "files"):
            for code_file in bundle.files:
                files[code_file.path] = code_file.content
    return files


def _detect_test_framework(files: dict[str, str]) -> tuple[str, str]:
    """Detect test framework and return (framework, test_command).

    Args:
        files: Dict of file paths to contents.

    Returns:
        Tuple of (framework_name, test_command)
    """
    # Check for Python tests
    has_pytest = any("pytest" in content for content in files.values())
    has_python_tests = any(path.startswith("tests/") and path.endswith(".py") for path in files)

    # Check for JS/TS tests
    has_jest = any("jest" in content.lower() for content in files.values())
    has_vitest = any("vitest" in content.lower() for content in files.values())
    has_js_tests = any(
        path.endswith((".test.js", ".test.ts", ".spec.js", ".spec.ts")) for path in files
    )

    # Prefer Python pytest
    if has_python_tests or has_pytest:
        return "pytest", "pytest tests/ -v --tb=short"

    # JavaScript tests
    if has_vitest:
        return "vitest", "npx vitest run --reporter=json"
    if has_jest or has_js_tests:
        return "jest", "npx jest --json"

    # Default to pytest
    return "pytest", "pytest tests/ -v --tb=short"


def _create_qa_feedback(test_report: TestReport, files: dict[str, str]) -> QAFeedback | None:
    """Create QA feedback for failed tests.

    Args:
        test_report: The test report with failures.
        files: Dict of file paths to determine target agent.

    Returns:
        QAFeedback if tests failed, None otherwise.
    """
    if test_report.failed == 0:
        return None

    # Determine which agent to target based on failed tests
    failed_cases = [tc for tc in test_report.cases if not tc.passed]

    # Analyze failed test files to determine target
    frontend_failures = 0
    backend_failures = 0

    for tc in failed_cases:
        file_path = tc.file or tc.name
        if any(kw in file_path.lower() for kw in ["frontend", "react", "component", "ui"]):
            frontend_failures += 1
        elif any(kw in file_path.lower() for kw in ["backend", "api", "server", "endpoint"]):
            backend_failures += 1

    # Determine target
    if frontend_failures > 0 and backend_failures == 0:
        target = TargetAgent.FRONTEND_DEV
    elif backend_failures > 0 and frontend_failures == 0:
        target = TargetAgent.BACKEND_DEV
    else:
        target = TargetAgent.BOTH

    # Build feedback message
    error_messages = []
    for tc in failed_cases[:5]:  # Limit to 5 failures
        if tc.error_message:
            error_messages.append(f"- {tc.name}: {tc.error_message[:200]}")
        else:
            error_messages.append(f"- {tc.name}: FAILED")

    summary = f"{test_report.failed} of {test_report.total} tests failed.\n\nFailed tests:\n"
    summary += "\n".join(error_messages)

    suspected_files = sorted({tc.file for tc in failed_cases if tc.file})

    return QAFeedback(
        target_agent=target,
        failed_tests=failed_cases,
        suspected_files=suspected_files,
        suggested_fixes=["Fix the failing tests based on the error messages above"],
        raw_error_excerpt=summary[:4000],
    )


async def qa_engineer_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
) -> dict[str, Any]:
    """QA Engineer agent node function.

    Runs tests in the sandbox and reports results.
    Falls back to stub mode if sandbox is unavailable.

    Args:
        state: Current graph state
        config: Optional Loom configuration

    Returns:
        State update dict with test_report, events, qa_feedback, and costs
    """
    prd = state.get("prd")
    code_files = state.get("code_files", {})
    retry_count = state.get("retry_count", 0)

    # Check required inputs
    if not code_files:
        return {
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.ERROR,
                    agent=AgentRole.QA,
                    phase=Phase.TESTING,
                    payload={"error": "No code files provided"},
                )
            ],
            "error": "No code files provided for testing",
        }

    events = [
        Event(
            timestamp=now_utc(),
            type=EventType.AGENT_START,
            agent=AgentRole.QA,
            phase=Phase.TESTING,
            payload={"message": "Starting QA testing", "retry_count": retry_count},
        ),
    ]

    # Extract files from bundles
    files = _extract_files_from_bundles(code_files)

    # Check if sandbox is available
    if not is_sandbox_available():
        # Without a sandbox nothing can actually be executed. Depending on
        # configuration we either fail loudly or continue with a report that is
        # explicitly marked unverified - we never pretend the tests passed.
        if config is not None and config.require_sandbox:
            logger.error("Sandbox required but unavailable - failing the build")
            events.append(
                Event(
                    timestamp=now_utc(),
                    type=EventType.ERROR,
                    agent=AgentRole.QA,
                    phase=Phase.TESTING,
                    payload={"error": SANDBOX_REQUIRED_MESSAGE},
                )
            )
            return {
                "events": events,
                "error": SANDBOX_REQUIRED_MESSAGE,
                "costs": [],
            }

        logger.warning(
            "Sandbox not available - tests were NOT executed. Emitting an "
            "unverified stub report; results carry no evidence about the code."
        )
        test_report = _create_stub_test_report(prd)
        events.append(
            Event(
                timestamp=now_utc(),
                type=EventType.AGENT_END,
                agent=AgentRole.QA,
                phase=Phase.TESTING,
                payload={
                    "total_tests": test_report.total,
                    "passed": test_report.passed,
                    "failed": test_report.failed,
                    "stub": True,
                    "verified": False,
                },
            )
        )
        return {
            "test_report": test_report,
            "phase": Phase.DEPLOYMENT,
            "qa_feedback": None,
            "events": events,
            "costs": [],
        }

    # Run tests in sandbox
    try:
        framework, test_command = _detect_test_framework(files)
        logger.info(f"Running {framework} tests: {test_command}")

        runner = create_sandbox_runner(
            SandboxConfig(
                timeout_seconds=120,  # 2 minutes for tests
                memory_limit="1g",
            )
        )

        test_config = TestRunConfig(
            files=files,
            command=test_command,
            framework=framework,
        )

        result = await runner.run_tests(test_config)

        # Parse test output
        if result.status == ExecutionStatus.SUCCESS or result.status == ExecutionStatus.FAILED:
            test_report = parse_test_output(
                result.stdout,
                result.stderr,
                framework=framework,
            )
        elif result.status == ExecutionStatus.TIMEOUT:
            test_report = TestReport(
                total=0,
                passed=0,
                failed=1,
                skipped=0,
                duration_ms=result.duration_seconds * 1000,
                cases=[
                    TestCase(
                        name="test_execution",
                        file="tests/",
                        passed=False,
                        duration_ms=result.duration_seconds * 1000,
                        error_message=f"Test execution timed out after {result.duration_seconds}s",
                    )
                ],
                raw_output=result.error or "Timeout",
            )
        else:
            test_report = TestReport(
                total=0,
                passed=0,
                failed=1,
                skipped=0,
                duration_ms=result.duration_seconds * 1000,
                cases=[
                    TestCase(
                        name="test_execution",
                        file="tests/",
                        passed=False,
                        duration_ms=result.duration_seconds * 1000,
                        error_message=result.error or "Unknown error",
                    )
                ],
                raw_output=result.stderr or result.stdout or "Execution failed",
            )

        # Create QA feedback if tests failed
        qa_feedback = _create_qa_feedback(test_report, files)

        # Determine next phase
        if test_report.failed == 0:
            next_phase = Phase.DEPLOYMENT
        else:
            next_phase = Phase.TESTING  # Stay in testing for retry

        events.append(
            Event(
                timestamp=now_utc(),
                type=EventType.AGENT_END,
                agent=AgentRole.QA,
                phase=Phase.TESTING,
                payload={
                    "total_tests": test_report.total,
                    "passed": test_report.passed,
                    "failed": test_report.failed,
                    "duration_seconds": result.duration_seconds,
                    "framework": framework,
                },
            )
        )

        logger.info(
            f"QA tests: {test_report.passed}/{test_report.total} passed "
            f"({test_report.failed} failed) in {result.duration_seconds:.1f}s"
        )

        return {
            "test_report": test_report,
            "phase": next_phase,
            "qa_feedback": qa_feedback,
            "retry_count": retry_count + 1 if test_report.failed > 0 else retry_count,
            "events": events,
            "costs": [],  # No LLM costs for test execution
        }

    except Exception as e:
        logger.exception(f"QA execution failed: {e}")
        events.append(
            Event(
                timestamp=now_utc(),
                type=EventType.ERROR,
                agent=AgentRole.QA,
                phase=Phase.TESTING,
                payload={"error": str(e)},
            )
        )
        return {
            "events": events,
            "error": f"QA execution failed: {e}",
        }
