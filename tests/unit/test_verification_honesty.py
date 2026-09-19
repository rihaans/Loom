"""Tests for the guarantees that stop Loom from overstating its results.

Two things must never happen:
  1. A stubbed QA report reading like a passing test run.
  2. A model with no published price reporting a confident $0.00.
"""

from loom.config.models import LoomConfig
from loom.llm.cost import calculate_cost, get_pricing, pricing_status
from loom.state.enums import Priority, ProjectType
from loom.state.models import PRD, TestCase, TestReport, UserStory


def _report(**kwargs: object) -> TestReport:
    defaults: dict[str, object] = {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "duration_ms": 10.0,
        "cases": [TestCase(name="t", file="tests/t.py", passed=True, duration_ms=10.0)],
    }
    defaults.update(kwargs)
    return TestReport(**defaults)  # type: ignore[arg-type]


class TestStubReportsNeverPass:
    """A report nothing produced must not claim everything passed."""

    def test_real_report_can_pass(self) -> None:
        assert _report().all_passed is True
        assert _report().verified is True

    def test_stub_report_never_passes(self) -> None:
        stub = _report(is_stub=True)
        assert stub.all_passed is False, "a stubbed report must never read as passing"
        assert stub.verified is False

    def test_stub_reports_no_coverage(self) -> None:
        """Coverage is a measurement; an unexecuted run has none to report."""
        from loom.agents.qa_engineer import _create_stub_test_report

        prd = PRD(
            project_name="X",
            project_slug="x",
            project_type=ProjectType.REST_API,
            one_liner="x",
            target_users=["u"],
            user_stories=[
                UserStory(
                    id="US-001",
                    role="u",
                    goal="g",
                    benefit="b",
                    acceptance_criteria=["a"],
                    priority=Priority.P0,
                )
            ],
            must_have_features=["f"],
        )
        stub = _create_stub_test_report(prd)
        assert stub.is_stub is True
        assert stub.coverage_percent is None
        assert stub.all_passed is False
        assert "NOT VERIFIED" in stub.raw_output


class TestRequireSandboxConfig:
    def test_defaults_to_permissive(self) -> None:
        assert LoomConfig().require_sandbox is False

    def test_can_be_required(self) -> None:
        assert LoomConfig(require_sandbox=True).require_sandbox is True


class TestPricingIsHonest:
    """Unknown prices must be reported as unknown, not as free."""

    def test_current_models_are_priced(self) -> None:
        for model in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"):
            pricing = get_pricing("anthropic", model)
            assert pricing is not None, f"{model} must have a price"
            assert pricing.input_per_million > 0

    def test_opus_48_is_not_billed_at_opus_45_rates(self) -> None:
        """Regression: prefix matching used to bill Opus 4.8 at Opus 4.5 rates."""
        pricing = get_pricing("anthropic", "claude-opus-4-8")
        assert pricing is not None
        assert pricing.input_per_million == 5.00
        assert pricing.output_per_million == 25.00

    def test_dated_snapshot_resolves_to_base_model(self) -> None:
        dated = get_pricing("anthropic", "claude-opus-5-20260401")
        base = get_pricing("anthropic", "claude-opus-5")
        assert dated is not None and base is not None
        assert dated.input_per_million == base.input_per_million

    def test_unknown_model_is_unknown_not_free(self) -> None:
        assert get_pricing("anthropic", "claude-not-a-real-model") is None
        assert pricing_status("anthropic", "claude-not-a-real-model") == "unknown"

    def test_local_models_are_free(self) -> None:
        assert pricing_status("ollama", "llama3.1:8b") == "free"
        assert calculate_cost("ollama", "llama3.1:8b", 1_000_000, 1_000_000) == 0.0

    def test_known_model_costs_real_money(self) -> None:
        cost = calculate_cost("anthropic", "claude-sonnet-5", 1_000_000, 1_000_000)
        assert cost == 12.00  # $2 in + $10 out


class TestRequireSandboxBranch:
    """`--require-sandbox` must fail the run rather than emit a stub report."""

    async def _run_qa(self, config: LoomConfig) -> dict:
        from unittest.mock import patch

        from loom.agents import qa_engineer
        from loom.state.models import CodeFile, FileBundle

        state = {
            "prd": None,
            "code_files": {
                "backend": FileBundle(
                    files=[CodeFile(path="backend/main.py", content="print(1)", language="python")],
                    entry_point="backend/main.py",
                )
            },
            "retry_count": 0,
        }
        with patch.object(qa_engineer, "is_sandbox_available", return_value=False):
            return await qa_engineer.qa_engineer_node(state, config=config)

    async def test_fails_when_sandbox_required(self) -> None:
        result = await self._run_qa(LoomConfig(require_sandbox=True))
        assert result.get("error"), "require_sandbox must surface an error"
        assert "sandbox" in result["error"].lower()
        assert "test_report" not in result, "no report should be invented"

    async def test_continues_unverified_by_default(self) -> None:
        result = await self._run_qa(LoomConfig(require_sandbox=False))
        assert not result.get("error")
        report = result["test_report"]
        assert report.is_stub is True
        assert report.all_passed is False


class TestFailingTestsAreNotSuccess:
    """A build whose own tests failed must not read, or exit, as success."""

    def _result(self, **kw: object):
        from loom.config.models import BuildResult

        base: dict[str, object] = {
            "success": True,
            "output_dir": "out/x",
            "phase": "done",
            "tests_verified": True,
            "test_passed": True,
        }
        base.update(kw)
        return BuildResult(**base)  # type: ignore[arg-type]

    def test_passing_tests_are_not_a_failure(self) -> None:
        from loom.cli.app import _tests_failed

        assert _tests_failed(self._result()) is False

    def test_failed_tests_are_a_failure(self) -> None:
        from loom.cli.app import _tests_failed

        assert _tests_failed(self._result(test_passed=False)) is True

    def test_unverified_is_not_reported_as_failure(self) -> None:
        """Unverified means unknown, not broken - the warning covers that case."""
        from loom.cli.app import _tests_failed

        unverified = self._result(tests_verified=False, test_passed=None)
        assert _tests_failed(unverified) is False
