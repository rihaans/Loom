"""Backend Developer agent node.

Produces backend code files based on PRD and architecture.
"""

import logging
from typing import Any

from loom._time import now_utc
from loom.agents.base import CACHE_SCOPE_KEY, build_agent_chain, build_revision_feedback
from loom.agents.product_manager import TokenTracker
from loom.agents.prompts.backend_dev import (
    BACKEND_DEV_HUMAN_TEMPLATE,
    BACKEND_DEV_SYSTEM_PROMPT,
)
from loom.config import LoomConfig
from loom.cost import check_budget
from loom.llm import calculate_cost, create_parse_error_feedback, get_llm_for_role
from loom.state.enums import AgentRole, EventType, Phase
from loom.state.models import CostEntry, Event, FileBundle

logger = logging.getLogger(__name__)

MAX_PARSE_RETRIES = 3


def _create_events(bundle: FileBundle) -> list[Event]:
    """Create events for successful backend code generation."""
    return [
        Event(
            timestamp=now_utc(),
            type=EventType.AGENT_START,
            agent=AgentRole.BACKEND_DEV,
            phase=Phase.DEVELOPMENT,
            payload={"message": "Starting backend development"},
        ),
        Event(
            timestamp=now_utc(),
            type=EventType.AGENT_END,
            agent=AgentRole.BACKEND_DEV,
            phase=Phase.DEVELOPMENT,
            payload={
                "file_count": len(bundle.files),
                "entry_point": bundle.entry_point,
            },
        ),
    ]


def _create_error_events(error_message: str, attempts: int) -> list[Event]:
    """Create events for failed backend code generation."""
    return [
        Event(
            timestamp=now_utc(),
            type=EventType.AGENT_START,
            agent=AgentRole.BACKEND_DEV,
            phase=Phase.DEVELOPMENT,
            payload={"message": "Starting backend development"},
        ),
        Event(
            timestamp=now_utc(),
            type=EventType.ERROR,
            agent=AgentRole.BACKEND_DEV,
            phase=Phase.DEVELOPMENT,
            payload={
                "error": error_message,
                "attempts": attempts,
            },
        ),
    ]


def _create_cost_entry(tracker: TokenTracker, provider: str, model: str) -> CostEntry | None:
    """Create a cost entry from token tracking data."""
    if tracker.input_tokens == 0 and tracker.output_tokens == 0:
        return None

    model_name = tracker.model_name or model
    cost = calculate_cost(provider, model_name, tracker.input_tokens, tracker.output_tokens)

    return CostEntry(
        agent=AgentRole.BACKEND_DEV,
        model=model_name,
        input_tokens=tracker.input_tokens,
        output_tokens=tracker.output_tokens,
        cost_usd=cost,
    )


async def backend_dev_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
) -> dict[str, Any]:
    """Backend Developer agent node function.

    Args:
        state: Current graph state
        config: Optional Loom configuration

    Returns:
        State update dict with code_files["backend"], events, and costs
    """
    prd = state.get("prd")
    architecture = state.get("architecture")
    qa_feedback = state.get("qa_feedback")
    review_report = state.get("review_report")

    if prd is None:
        return {
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.ERROR,
                    agent=AgentRole.BACKEND_DEV,
                    phase=Phase.DEVELOPMENT,
                    payload={"error": "No PRD provided"},
                )
            ],
            "error": "No PRD provided for backend development",
        }

    if architecture is None:
        return {
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.ERROR,
                    agent=AgentRole.BACKEND_DEV,
                    phase=Phase.DEVELOPMENT,
                    payload={"error": "No architecture provided"},
                )
            ],
            "error": "No architecture provided for backend development",
        }

    # Get or create config
    if config is None:
        from loom.config import load_config

        config = load_config()

    # Get LLM configuration
    llm_config = config.get_llm_config(AgentRole.BACKEND_DEV)
    provider = llm_config.provider
    model = llm_config.model

    # Create token tracker
    tracker = TokenTracker()

    # Get LLM with callback
    llm = get_llm_for_role(AgentRole.BACKEND_DEV, config, callbacks=[tracker])

    # Build the chain
    chain, parser = build_agent_chain(
        system_prompt=BACKEND_DEV_SYSTEM_PROMPT,
        human_template=BACKEND_DEV_HUMAN_TEMPLATE,
        output_model=FileBundle,
        llm=llm,
        agent_name="backend_dev",
    )

    # Stop before spending if this build has already hit its budget.
    budget_error = check_budget(state, config, "backend developer")
    if budget_error:
        return {"error": budget_error, "events": [], "costs": []}

    # Get format instructions
    format_instructions = parser.get_format_instructions()

    # Convert models to JSON
    prd_json = prd.model_dump_json(indent=2)
    architecture_json = architecture.model_dump_json(indent=2)

    # Build the revision-feedback section (QA failures and/or code-review issues).
    qa_feedback_section = build_revision_feedback(qa_feedback, review_report)

    # Retry loop
    last_error: Exception | None = None
    feedback = ""

    for attempt in range(1, MAX_PARSE_RETRIES + 1):
        try:
            prompt_input = {
                "prd_json": prd_json,
                "architecture_json": architecture_json + feedback,
                "qa_feedback_section": qa_feedback_section,
                "format_instructions": format_instructions,
            }
            # All attempts for this request share one cache entry: the
            # retry feedback is an implementation detail, not a new request.
            prompt_input[CACHE_SCOPE_KEY] = {**prompt_input, "architecture_json": architecture_json}

            bundle = await chain.ainvoke(prompt_input)

            # Success
            events = _create_events(bundle)
            costs: list[CostEntry] = []

            cost_entry = _create_cost_entry(tracker, provider, model)
            if cost_entry:
                costs.append(cost_entry)

            logger.info(f"Backend code generated: {len(bundle.files)} files")

            return {
                "code_files": {"backend": bundle},
                "events": events,
                "costs": costs,
            }

        except Exception as e:
            last_error = e
            logger.warning(f"Backend dev attempt {attempt}/{MAX_PARSE_RETRIES} failed: {e}")

            if attempt < MAX_PARSE_RETRIES:
                raw_output = str(e)
                if hasattr(e, "llm_output"):
                    raw_output = e.llm_output
                feedback = "\n\n" + create_parse_error_feedback(raw_output, str(e))

    # All retries exhausted
    error_message = (
        f"Failed to generate backend code after {MAX_PARSE_RETRIES} attempts: {last_error}"
    )
    logger.error(error_message)

    events = _create_error_events(str(last_error), MAX_PARSE_RETRIES)
    costs = []

    cost_entry = _create_cost_entry(tracker, provider, model)
    if cost_entry:
        costs.append(cost_entry)

    return {
        "events": events,
        "costs": costs,
        "error": error_message,
    }
