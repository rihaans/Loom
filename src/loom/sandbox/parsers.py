"""Test output parsers for converting stdout to TestCase/TestReport."""

import json
import logging
import re

from loom.state.models import TestCase, TestReport

logger = logging.getLogger(__name__)


def parse_pytest_output(stdout: str, stderr: str = "") -> TestReport:
    """Parse pytest output into TestReport.

    Handles both verbose (-v) and JSON (--json-report) output formats.

    Args:
        stdout: Pytest stdout.
        stderr: Pytest stderr.

    Returns:
        TestReport with parsed results.
    """
    test_cases: list[TestCase] = []
    passed = 0
    failed = 0
    skipped = 0

    # Try JSON format first (if pytest-json-report was used)
    try:
        # Look for JSON report in output
        json_match = re.search(r'\{.*"tests".*\}', stdout, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            for test in data.get("tests", []):
                outcome = test.get("outcome", "unknown")
                nodeid = test.get("nodeid", "unknown")
                test_cases.append(
                    TestCase(
                        name=nodeid,
                        file=nodeid.split("::")[0],
                        passed=outcome == "passed",
                        error_message=test.get("call", {}).get("longrepr")
                        if outcome == "failed"
                        else None,
                        duration_ms=int(test.get("duration", 0) * 1000),
                    )
                )
                if outcome == "passed":
                    passed += 1
                elif outcome == "failed":
                    failed += 1
                elif outcome == "skipped":
                    skipped += 1

            return TestReport(
                passed=passed,
                failed=failed,
                skipped=skipped,
                total=passed + failed + skipped,
                duration_ms=sum(tc.duration_ms for tc in test_cases),
                cases=test_cases,
                raw_output=stdout[:5000],
            )
    except (json.JSONDecodeError, KeyError):
        pass

    # Parse verbose text output
    # Match patterns like: test_foo.py::test_bar PASSED
    test_pattern = re.compile(r"([\w/\._-]+::\w+)\s+(PASSED|FAILED|SKIPPED|ERROR)")
    for match in test_pattern.finditer(stdout):
        name, outcome = match.groups()
        test_cases.append(
            TestCase(
                name=name,
                file=name.split("::")[0],
                passed=outcome == "PASSED",
                error_message=None,  # Would need more parsing for error details
                duration_ms=0,
            )
        )
        if outcome == "PASSED":
            passed += 1
        elif outcome in ("FAILED", "ERROR"):
            failed += 1
        elif outcome == "SKIPPED":
            skipped += 1

    # Try to extract summary line: "5 passed, 2 failed, 1 skipped"
    summary_pattern = re.compile(
        r"(?:=+\s*)?"
        r"(?:(\d+)\s+passed)?\s*,?\s*"
        r"(?:(\d+)\s+failed)?\s*,?\s*"
        r"(?:(\d+)\s+skipped)?"
    )
    summary_match = summary_pattern.search(stdout)
    if summary_match and not test_cases:
        p, f, s = summary_match.groups()
        passed = int(p) if p else 0
        failed = int(f) if f else 0
        skipped = int(s) if s else 0

    total = passed + failed + skipped
    if total == 0 and test_cases:
        total = len(test_cases)

    return TestReport(
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=total or len(test_cases),
        duration_ms=sum(tc.duration_ms for tc in test_cases),
        cases=test_cases,
        raw_output=stdout[:5000] + ("\n---STDERR---\n" + stderr[:2000] if stderr else ""),
    )


def parse_jest_output(stdout: str, stderr: str = "") -> TestReport:
    """Parse Jest/Vitest output into TestReport.

    Args:
        stdout: Jest stdout.
        stderr: Jest stderr.

    Returns:
        TestReport with parsed results.
    """
    test_cases: list[TestCase] = []
    passed = 0
    failed = 0
    skipped = 0

    # Try JSON format first (jest --json)
    try:
        # Jest outputs JSON to stdout with --json flag
        data = json.loads(stdout)
        for result in data.get("testResults", []):
            for assertion in result.get("assertionResults", []):
                status = assertion.get("status", "unknown")
                test_cases.append(
                    TestCase(
                        name=f"{result.get('name', 'unknown')}::{assertion.get('title', 'unknown')}",
                        file=result.get("name", ""),
                        passed=status == "passed",
                        error_message="\n".join(assertion.get("failureMessages", [])) or None,
                        duration_ms=int(assertion.get("duration", 0)),
                    )
                )
                if status == "passed":
                    passed += 1
                elif status == "failed":
                    failed += 1
                elif status in ("skipped", "pending"):
                    skipped += 1

        return TestReport(
            passed=data.get("numPassedTests", passed),
            failed=data.get("numFailedTests", failed),
            skipped=data.get("numPendingTests", skipped),
            total=data.get("numTotalTests", passed + failed + skipped),
            duration_ms=sum(tc.duration_ms for tc in test_cases),
            cases=test_cases,
            raw_output=stdout[:5000],
        )
    except (json.JSONDecodeError, KeyError):
        pass

    # Parse text output
    # Match: ✓ test name (Xms) or ✕ test name
    pass_pattern = re.compile(r"[✓✔]\s+(.+?)(?:\s+\((\d+)\s*m?s\))?$", re.MULTILINE)
    # The multiplication-sign char in the class is intentional: Vitest emits it for failures.
    fail_pattern = re.compile(r"[✕✗×]\s+(.+?)(?:\s+\((\d+)\s*m?s\))?$", re.MULTILINE)  # noqa: RUF001
    skip_pattern = re.compile(r"[○◌]\s+skipped\s+(.+)", re.MULTILINE)

    for match in pass_pattern.finditer(stdout):
        name = match.group(1).strip()
        duration = int(match.group(2)) if match.group(2) else 0
        test_cases.append(TestCase(name=name, file="", passed=True, duration_ms=duration))
        passed += 1

    for match in fail_pattern.finditer(stdout):
        name = match.group(1).strip()
        duration = int(match.group(2)) if match.group(2) else 0
        test_cases.append(TestCase(name=name, file="", passed=False, duration_ms=duration))
        failed += 1

    for match in skip_pattern.finditer(stdout):
        name = match.group(1).strip()
        test_cases.append(TestCase(name=name, file="", passed=True, duration_ms=0))
        skipped += 1

    # Try summary: Tests: X passed, Y failed, Z total
    summary_match = re.search(
        r"Tests:\s*(?:(\d+)\s+passed)?\s*,?\s*(?:(\d+)\s+failed)?\s*,?\s*(\d+)\s+total",
        stdout,
    )
    if summary_match:
        p, f, _total = summary_match.groups()
        passed = int(p) if p else passed
        failed = int(f) if f else failed

    total = passed + failed + skipped

    return TestReport(
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=total or len(test_cases),
        duration_ms=sum(tc.duration_ms for tc in test_cases),
        cases=test_cases,
        raw_output=stdout[:5000] + ("\n---STDERR---\n" + stderr[:2000] if stderr else ""),
    )


def parse_vitest_output(stdout: str, stderr: str = "") -> TestReport:
    """Parse Vitest output. Vitest format is similar to Jest."""
    return parse_jest_output(stdout, stderr)


def parse_test_output(
    stdout: str,
    stderr: str = "",
    framework: str = "pytest",
) -> TestReport:
    """Parse test output based on framework.

    Args:
        stdout: Test runner stdout.
        stderr: Test runner stderr.
        framework: Test framework name (pytest, jest, vitest).

    Returns:
        TestReport with parsed results.
    """
    parsers = {
        "pytest": parse_pytest_output,
        "jest": parse_jest_output,
        "vitest": parse_vitest_output,
    }

    parser = parsers.get(framework.lower(), parse_pytest_output)
    return parser(stdout, stderr)
