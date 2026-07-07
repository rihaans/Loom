"""Code Reviewer agent node — the critic in the generator-critic loop.

Sits between the developers and QA. It reviews the generated code as a whole and
either approves it (→ QA) or sends targeted revision instructions back to the
developer(s) that need to act, using a LangGraph ``Command`` for a dynamic handoff.
The loop is bounded by ``max_review_iterations`` so it always terminates.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from langgraph.types import Command, Send

from loom.agents.base import build_agent_chain
from loom.agents.product_manager import TokenTracker
from loom.agents.prompts.reviewer import (
    REVIEWER_HUMAN_TEMPLATE,
    REVIEWER_SYSTEM_PROMPT,
)
from loom.config import LoomConfig
from loom.llm import calculate_cost, get_llm_for_role
from loom.state.enums import AgentRole, EventType, Phase, TargetAgent
from loom.state.models import CostEntry, Event, ReviewReport

logger = logging.getLogger(__name__)

# How many files/characters to show the reviewer before truncating, to stay within
# context limits on large builds. The reviewer still sees every file path.
_MAX_FILE_CHARS = 6000


def _dump_code(code_files: dict[str, Any]) -> tuple[str, int]:
    """Render all generated files into a single annotated string for the prompt.

    Returns (dump, file_count).
    """
    blocks: list[str] = []
    count = 0
    for bundle_name, bundle in code_files.items():
        files = getattr(bundle, "files", [])
        for f in files:
            count += 1
            content = f.content
            if len(content) > _MAX_FILE_CHARS:
                content = content[:_MAX_FILE_CHARS] + "\n... [truncated for review] ..."
            blocks.append(f"=== [{bundle_name}] {f.path} ({f.language}) ===\n{content}")
    return "\n\n".join(blocks), count


def _review_targets(target: TargetAgent) -> list[str]:
    """Map a review target onto the developer node names to re-run."""
    if target == TargetAgent.FRONTEND_DEV:
        return ["frontend_dev"]
    if target == TargetAgent.BACKEND_DEV:
        return ["backend_dev"]
    return ["frontend_dev", "backend_dev"]


def _start_event() -> Event:
    return Event(
        timestamp=datetime.now(UTC),
        type=EventType.AGENT_START,
        agent=AgentRole.CODE_REVIEWER,
        phase=Phase.REVIEW,
        payload={"message": "Reviewing generated code"},
    )


def _proceed(update: dict[str, Any]) -> Command:
    """Approve (or give up) and hand off to QA."""
    return Command(goto="qa_engineer", update=update)


async def code_reviewer_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
) -> Command:
    """Code Reviewer node: critique the build, then dynamically hand off.

    Returns a ``Command`` that either advances to QA or fans back out to the
    developer(s) needing revision via the Send API.
    """
    code_files = state.get("code_files") or {}
    prd = state.get("prd")
    architecture = state.get("architecture")
    review_count = state.get("review_count", 0)
    max_iterations = state.get("max_review_iterations", 1)

    # Nothing to review, or missing context: don't block the pipeline — go to QA.
    if not code_files or prd is None or architecture is None:
        logger.info("Code reviewer: insufficient context to review, skipping to QA")
        return _proceed({"events": [_start_event()]})

    if config is None:
        from loom.config import load_config

        config = load_config()

    llm_config = config.get_llm_config(AgentRole.CODE_REVIEWER)
    provider = llm_config.provider
    model = llm_config.model

    tracker = TokenTracker()
    llm = get_llm_for_role(AgentRole.CODE_REVIEWER, config, callbacks=[tracker])

    chain, parser = build_agent_chain(
        system_prompt=REVIEWER_SYSTEM_PROMPT,
        human_template=REVIEWER_HUMAN_TEMPLATE,
        output_model=ReviewReport,
        llm=llm,
    )

    code_dump, file_count = _dump_code(code_files)
    prompt_input = {
        "prd_json": prd.model_dump_json(indent=2),
        "architecture_json": architecture.model_dump_json(indent=2),
        "code_dump": code_dump,
        "file_count": file_count,
        "format_instructions": parser.get_format_instructions(),
    }

    costs: list[CostEntry] = []
    try:
        report: ReviewReport = await chain.ainvoke(prompt_input)
    except Exception as e:
        # A reviewer failure must never sink an otherwise-good build. Log and proceed.
        logger.warning("Code review failed (%s); proceeding to QA without a verdict", e)
        return _proceed(
            {
                "events": [
                    _start_event(),
                    Event(
                        timestamp=datetime.now(UTC),
                        type=EventType.ERROR,
                        agent=AgentRole.CODE_REVIEWER,
                        phase=Phase.REVIEW,
                        payload={"error": str(e), "recovered": True},
                    ),
                ]
            }
        )

    cost_entry = _build_cost(tracker, provider, model)
    if cost_entry:
        costs.append(cost_entry)

    blocking = report.blocking_issues
    end_event = Event(
        timestamp=datetime.now(UTC),
        type=EventType.AGENT_END,
        agent=AgentRole.CODE_REVIEWER,
        phase=Phase.REVIEW,
        payload={
            "approved": report.approved,
            "issues": len(report.issues),
            "blocking": len(blocking),
            "iteration": review_count,
        },
    )
    base_update = {
        "review_report": report,
        "events": [_start_event(), end_event],
        "costs": costs,
    }

    # Approve, or exhausted the revision budget → proceed to QA.
    if report.approved or not blocking or review_count >= max_iterations:
        if blocking and review_count >= max_iterations:
            logger.info(
                "Code reviewer: %d blocking issue(s) but review budget exhausted "
                "(%d/%d); proceeding to QA",
                len(blocking),
                review_count,
                max_iterations,
            )
        else:
            logger.info("Code reviewer: approved (%d minor note(s))", len(report.issues))
        return _proceed(base_update)

    # Changes requested and budget remains. Two kinds of handoff:
    base_update["review_count"] = review_count + 1

    # (a) Architectural root cause → escalate UPSTREAM to the Architect, which revises
    # the design (its legacy path consumes `architecture_feedback`) and re-fans to devs.
    if report.escalate_to_architect:
        logger.info(
            "Code reviewer: escalating to Architect (architectural issue) [iteration %d/%d]",
            review_count + 1,
            max_iterations,
        )
        issue_text = "; ".join(
            f"[{i.severity}] {i.file or '(cross-cutting)'}: {i.description}" for i in blocking
        )
        base_update["architecture_feedback"] = f"{report.summary}\n\nBlocking issues: {issue_text}"
        return Command(goto="architect", update=base_update)

    # (b) Code defect → hand back to the targeted developer(s).
    targets = _review_targets(report.target_agent)
    logger.info(
        "Code reviewer: requesting revision (%d blocking issue(s)) from %s [iteration %d/%d]",
        len(blocking),
        targets,
        review_count + 1,
        max_iterations,
    )

    # The developers read `review_report` from their input state to make fixes, so
    # carry the fresh report (and bumped count) in each Send payload.
    dev_input = {**state, "review_report": report, "review_count": review_count + 1}
    return Command(
        goto=[Send(target, dev_input) for target in targets],
        update=base_update,
    )


def _build_cost(tracker: TokenTracker, provider: str, model: str) -> CostEntry | None:
    """Create a cost entry from token tracking data, or None if no usage."""
    if tracker.input_tokens == 0 and tracker.output_tokens == 0:
        return None
    model_name = tracker.model_name or model
    cost = calculate_cost(provider, model_name, tracker.input_tokens, tracker.output_tokens)
    return CostEntry(
        agent=AgentRole.CODE_REVIEWER,
        model=model_name,
        input_tokens=tracker.input_tokens,
        output_tokens=tracker.output_tokens,
        cost_usd=cost,
    )
