"""Integration tests for the generator-critic review loop through the compiled graph.

Drives the real LangGraph state machine with mocked agent nodes to verify the
Code Reviewer's Command-based handoffs actually loop: reject -> dev re-runs ->
approve -> QA, and escalate -> architect re-runs -> approve -> QA. The loop must
always terminate (bounded by max_review_iterations).
"""

import pytest
from langgraph.types import Command, Send

import loom.graph.builder as gb
from loom.config import LoomConfig
from loom.graph.builder import compile_graph
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
    DevOpsBundle,
    FileBundle,
    ReviewIssue,
    ReviewReport,
    TechChoice,
    TestReport,
    UserStory,
)


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


def _bundle() -> FileBundle:
    return FileBundle(
        files=[CodeFile(path="backend/main.py", content="print(1)", language="python")],
        entry_point="backend/main.py",
    )


def _mock_pipeline(monkeypatch, reviewer_fn, counters):
    """Patch all agent nodes; reviewer behaviour is supplied by the caller."""

    async def pm(state, config=None):
        return {"prd": _prd()}

    async def mem(state, config=None):
        return {}

    async def architect(state, config=None):
        counters["architect"] += 1
        return {"architecture": _arch(), "architecture_feedback": None}

    async def fe(state, config=None):
        counters["frontend_dev"] += 1
        return {"code_files": {"frontend": _bundle()}}

    async def be(state, config=None):
        counters["backend_dev"] += 1
        return {"code_files": {"backend": _bundle()}}

    async def qa(state, config=None):
        counters["qa"] += 1
        return {"test_report": TestReport(total=1, passed=1, failed=0, duration_ms=1.0)}

    async def devops(state, config=None):
        return {"devops_files": DevOpsBundle(docker_compose="x")}

    async def persist(state, config=None):
        return {}

    async def reviewer(state, config=None):
        counters["reviewer"] += 1
        return await reviewer_fn(state)

    monkeypatch.setattr(gb, "product_manager_node", pm)
    monkeypatch.setattr(gb, "memory_retrieve_node", mem)
    monkeypatch.setattr(gb, "architect_node", architect)
    monkeypatch.setattr(gb, "frontend_dev_node", fe)
    monkeypatch.setattr(gb, "backend_dev_node", be)
    monkeypatch.setattr(gb, "qa_engineer_node", qa)
    monkeypatch.setattr(gb, "devops_engineer_node", devops)
    monkeypatch.setattr(gb, "memory_persist_node", persist)
    monkeypatch.setattr(gb, "code_reviewer_node", reviewer)


@pytest.mark.asyncio
async def test_reject_then_approve_reruns_dev(monkeypatch) -> None:
    counters = dict.fromkeys(["architect", "frontend_dev", "backend_dev", "qa", "reviewer"], 0)

    async def reviewer_fn(state):
        if state.get("review_count", 0) == 0:
            rep = ReviewReport(
                approved=False,
                summary="bug",
                issues=[
                    ReviewIssue(
                        severity=ReviewSeverity.MAJOR,
                        file="backend/main.py",
                        description="bug",
                        suggested_fix="fix",
                    )
                ],
                target_agent=TargetAgent.BACKEND_DEV,
            )
            return Command(
                goto=[Send("backend_dev", {**state, "review_report": rep, "review_count": 1})],
                update={"review_report": rep, "review_count": 1},
            )
        return Command(
            goto="qa_engineer", update={"review_report": ReviewReport(approved=True, summary="ok")}
        )

    _mock_pipeline(monkeypatch, reviewer_fn, counters)
    app = compile_graph(LoomConfig())
    out = await app.ainvoke({"description": "x", "max_review_iterations": 1, "interactive": False})

    assert counters["reviewer"] == 2
    assert counters["backend_dev"] == 2  # initial + one revision
    assert counters["qa"] == 1  # only after approval
    assert out["review_report"].approved is True
    assert out["devops_files"] is not None


@pytest.mark.asyncio
async def test_escalation_reruns_architect(monkeypatch) -> None:
    counters = dict.fromkeys(["architect", "frontend_dev", "backend_dev", "qa", "reviewer"], 0)

    async def reviewer_fn(state):
        if state.get("review_count", 0) == 0:
            rep = ReviewReport(
                approved=False,
                summary="stack wrong",
                issues=[
                    ReviewIssue(
                        severity=ReviewSeverity.CRITICAL,
                        file="",
                        description="db cannot do X",
                        suggested_fix="use postgres",
                    )
                ],
                escalate_to_architect=True,
            )
            return Command(
                goto="architect",
                update={
                    "review_report": rep,
                    "review_count": 1,
                    "architecture_feedback": rep.summary,
                },
            )
        return Command(
            goto="qa_engineer", update={"review_report": ReviewReport(approved=True, summary="ok")}
        )

    _mock_pipeline(monkeypatch, reviewer_fn, counters)
    app = compile_graph(LoomConfig())
    out = await app.ainvoke({"description": "x", "max_review_iterations": 1, "interactive": False})

    assert counters["architect"] == 2  # initial design + escalation revision
    assert counters["reviewer"] == 2
    assert out["review_report"].approved is True
    assert out["devops_files"] is not None
