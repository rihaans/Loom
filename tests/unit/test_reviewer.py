"""Tests for the Code Reviewer agent (the critic in the generator-critic loop).

Covers:
  - ReviewReport / ReviewIssue model invariants
  - build_revision_feedback() prompt-section composition
  - code_reviewer_node() dynamic Command handoffs:
      approve -> QA, reject -> devs (Send), escalate -> architect,
      budget exhausted -> QA, reviewer failure -> QA (recovered),
      insufficient context -> QA
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.types import Command, Send

from loom.agents.base import build_revision_feedback
from loom.config import LoomConfig
from loom.state.enums import (
    Priority,
    ProjectType,
    ReviewSeverity,
    TargetAgent,
    TechLayer,
)
from loom.state.models import (
    PRD,
    ArchitectureDoc,
    CodeFile,
    FileBundle,
    QAFeedback,
    ReviewIssue,
    ReviewReport,
    TechChoice,
    TestCase,
    UserStory,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _prd() -> PRD:
    return PRD(
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


def _arch() -> ArchitectureDoc:
    return ArchitectureDoc(
        stack=[TechChoice(layer=TechLayer.BACKEND, technology="FastAPI", rationale="r")]
    )


def _code() -> dict[str, FileBundle]:
    return {
        "backend": FileBundle(
            files=[CodeFile(path="backend/main.py", content="print(1)", language="python")],
            entry_point="backend/main.py",
        )
    }


def _state(**overrides) -> dict:
    base = {
        "prd": _prd(),
        "architecture": _arch(),
        "code_files": _code(),
        "review_count": 0,
        "max_review_iterations": 1,
    }
    base.update(overrides)
    return base


def _issue(severity=ReviewSeverity.MAJOR) -> ReviewIssue:
    return ReviewIssue(
        severity=severity, file="backend/main.py", description="bug", suggested_fix="fix it"
    )


def _patch_reviewer_chain(report: ReviewReport | Exception):
    """Patch the reviewer's chain so ainvoke returns `report` (or raises it)."""
    mock_chain = MagicMock()
    if isinstance(report, Exception):
        mock_chain.ainvoke = AsyncMock(side_effect=report)
    else:
        mock_chain.ainvoke = AsyncMock(return_value=report)
    mock_parser = MagicMock()
    mock_parser.get_format_instructions = MagicMock(return_value="Format: JSON")
    return (
        patch("loom.agents.reviewer.build_agent_chain", return_value=(mock_chain, mock_parser)),
        patch("loom.agents.reviewer.get_llm_for_role", return_value=MagicMock()),
    )


async def _run_reviewer(state, report):
    from loom.agents.reviewer import code_reviewer_node

    p1, p2 = _patch_reviewer_chain(report)
    with p1, p2:
        return await code_reviewer_node(state, LoomConfig())


# --------------------------------------------------------------------------- #
# Model invariants
# --------------------------------------------------------------------------- #
class TestReviewReportModel:
    def test_blocking_issues_excludes_minor(self) -> None:
        report = ReviewReport(
            approved=False,
            summary="s",
            issues=[_issue(ReviewSeverity.MINOR), _issue(ReviewSeverity.MAJOR)],
        )
        assert len(report.blocking_issues) == 1
        assert report.blocking_issues[0].severity == ReviewSeverity.MAJOR

    def test_approved_with_only_minor_issues_is_valid(self) -> None:
        report = ReviewReport(approved=True, summary="s", issues=[_issue(ReviewSeverity.MINOR)])
        assert report.approved is True

    def test_approved_with_blocking_issue_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be 'approved'"):
            ReviewReport(approved=True, summary="s", issues=[_issue(ReviewSeverity.CRITICAL)])

    def test_target_agent_defaults_to_both(self) -> None:
        report = ReviewReport(approved=True, summary="s")
        assert report.target_agent == TargetAgent.BOTH
        assert report.escalate_to_architect is False


# --------------------------------------------------------------------------- #
# build_revision_feedback
# --------------------------------------------------------------------------- #
class TestBuildRevisionFeedback:
    def test_empty_when_no_feedback(self) -> None:
        assert build_revision_feedback(None, None) == ""

    def test_includes_qa_feedback(self) -> None:
        qa = QAFeedback(
            target_agent=TargetAgent.BACKEND_DEV,
            failed_tests=[TestCase(name="t1", file="f", passed=False, duration_ms=1.0)],
            raw_error_excerpt="boom",
        )
        out = build_revision_feedback(qa, None)
        assert "QA Feedback" in out
        assert "t1" in out

    def test_includes_review_feedback(self) -> None:
        report = ReviewReport(
            approved=False, summary="needs work", issues=[_issue(ReviewSeverity.MAJOR)]
        )
        out = build_revision_feedback(None, report)
        assert "Code Review feedback" in out
        assert "fix it" in out

    def test_approved_review_contributes_nothing(self) -> None:
        report = ReviewReport(approved=True, summary="great")
        assert build_revision_feedback(None, report) == ""

    def test_merges_both_sources(self) -> None:
        qa = QAFeedback(target_agent=TargetAgent.BOTH, raw_error_excerpt="boom")
        report = ReviewReport(approved=False, summary="s", issues=[_issue(ReviewSeverity.MAJOR)])
        out = build_revision_feedback(qa, report)
        assert "QA Feedback" in out and "Code Review feedback" in out


# --------------------------------------------------------------------------- #
# code_reviewer_node — dynamic handoffs
# --------------------------------------------------------------------------- #
class TestCodeReviewerNode:
    @pytest.mark.asyncio
    async def test_approve_routes_to_qa(self) -> None:
        report = ReviewReport(approved=True, summary="lgtm")
        cmd = await _run_reviewer(_state(), report)
        assert isinstance(cmd, Command)
        assert cmd.goto == "qa_engineer"
        assert cmd.update["review_report"].approved is True

    @pytest.mark.asyncio
    async def test_reject_code_defect_routes_back_to_target_dev(self) -> None:
        report = ReviewReport(
            approved=False,
            summary="bug",
            issues=[_issue(ReviewSeverity.MAJOR)],
            target_agent=TargetAgent.BACKEND_DEV,
        )
        cmd = await _run_reviewer(_state(), report)
        assert isinstance(cmd.goto, list)
        sends = cmd.goto
        assert all(isinstance(s, Send) for s in sends)
        assert {s.node for s in sends} == {"backend_dev"}
        assert cmd.update["review_count"] == 1

    @pytest.mark.asyncio
    async def test_escalation_routes_to_architect(self) -> None:
        report = ReviewReport(
            approved=False,
            summary="wrong stack",
            issues=[_issue(ReviewSeverity.CRITICAL)],
            escalate_to_architect=True,
        )
        cmd = await _run_reviewer(_state(), report)
        assert cmd.goto == "architect"
        assert "architecture_feedback" in cmd.update
        assert "wrong stack" in cmd.update["architecture_feedback"]

    @pytest.mark.asyncio
    async def test_budget_exhausted_proceeds_to_qa(self) -> None:
        report = ReviewReport(
            approved=False, summary="still bad", issues=[_issue(ReviewSeverity.MAJOR)]
        )
        # review_count already at the cap -> proceed despite blocking issues
        cmd = await _run_reviewer(_state(review_count=1, max_review_iterations=1), report)
        assert cmd.goto == "qa_engineer"

    @pytest.mark.asyncio
    async def test_reviewer_failure_recovers_to_qa(self) -> None:
        cmd = await _run_reviewer(_state(), RuntimeError("llm down"))
        assert cmd.goto == "qa_engineer"
        # A recovered-error event should be recorded
        events = cmd.update["events"]
        assert any(e.payload.get("recovered") for e in events)

    @pytest.mark.asyncio
    async def test_insufficient_context_skips_to_qa(self) -> None:
        from loom.agents.reviewer import code_reviewer_node

        # No code_files -> nothing to review
        cmd = await code_reviewer_node({"prd": _prd(), "architecture": _arch()}, LoomConfig())
        assert cmd.goto == "qa_engineer"

    @pytest.mark.asyncio
    async def test_both_target_fans_out_to_both_devs(self) -> None:
        report = ReviewReport(
            approved=False,
            summary="bug",
            issues=[_issue(ReviewSeverity.MAJOR)],
            target_agent=TargetAgent.BOTH,
        )
        cmd = await _run_reviewer(_state(), report)
        assert {s.node for s in cmd.goto} == {"frontend_dev", "backend_dev"}
