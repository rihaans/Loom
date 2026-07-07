"""Regression tests for the test-output parsers.

These constructions previously crashed (TestCase missing `file`, TestReport
missing `duration_ms` and using a non-existent `test_cases` field), so they had
no working coverage. These tests lock the contract in.
"""

import json

from loom.sandbox.parsers import (
    parse_jest_output,
    parse_pytest_output,
    parse_test_output,
)
from loom.state.models import TestReport


class TestPytestParser:
    def test_verbose_text_output(self) -> None:
        out = (
            "tests/test_api.py::test_create PASSED\n"
            "tests/test_api.py::test_list PASSED\n"
            "tests/test_api.py::test_delete FAILED\n"
        )
        report = parse_pytest_output(out)
        assert isinstance(report, TestReport)
        assert report.total == 3
        assert report.passed == 2
        assert report.failed == 1
        assert len(report.cases) == 3
        # `file` is derived from the nodeid and must be populated.
        assert report.cases[0].file == "tests/test_api.py"

    def test_json_report(self) -> None:
        payload = json.dumps(
            {
                "tests": [
                    {"nodeid": "t.py::a", "outcome": "passed", "duration": 0.01},
                    {"nodeid": "t.py::b", "outcome": "failed", "duration": 0.02},
                ]
            }
        )
        report = parse_pytest_output(payload)
        assert report.passed == 1
        assert report.failed == 1
        assert report.total == 2
        assert report.duration_ms >= 0

    def test_empty_output_is_valid(self) -> None:
        report = parse_pytest_output("")
        assert isinstance(report, TestReport)
        assert report.total == 0


class TestJestParser:
    def test_json_output(self) -> None:
        payload = json.dumps(
            {
                "numPassedTests": 1,
                "numFailedTests": 1,
                "numTotalTests": 2,
                "testResults": [
                    {
                        "name": "src/app.test.js",
                        "assertionResults": [
                            {"status": "passed", "title": "renders", "duration": 5},
                            {"status": "failed", "title": "submits", "duration": 8},
                        ],
                    }
                ],
            }
        )
        report = parse_jest_output(payload)
        assert report.passed == 1
        assert report.failed == 1
        assert report.cases[0].file == "src/app.test.js"


class TestDispatch:
    def test_parse_test_output_routes_by_framework(self) -> None:
        report = parse_test_output("x::y PASSED\n", framework="pytest")
        assert report.passed == 1
        # Unknown framework falls back to pytest without raising.
        report2 = parse_test_output("x::y PASSED\n", framework="unknown")
        assert report2.passed == 1
