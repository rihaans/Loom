"""DevOps Engineer agent node.

Produces Docker, CI/CD, and deployment configurations.
"""

import logging
from typing import Any

from loom._time import now_utc
from loom.agents.base import build_agent_chain
from loom.agents.product_manager import TokenTracker
from loom.agents.prompts.devops_engineer import (
    DEVOPS_ENGINEER_HUMAN_TEMPLATE,
    DEVOPS_ENGINEER_SYSTEM_PROMPT,
)
from loom.config import LoomConfig
from loom.llm import calculate_cost, create_parse_error_feedback, get_llm_for_role
from loom.state.enums import AgentRole, EventType, Phase
from loom.state.models import CostEntry, DevOpsBundle, Event

logger = logging.getLogger(__name__)

MAX_PARSE_RETRIES = 3


def _summarize_files(bundle: Any) -> str:
    """Create a summary of files for the DevOps prompt."""
    if bundle is None:
        return "No files"

    if hasattr(bundle, "files"):
        file_list = [f.path for f in bundle.files]
        return f"Files: {file_list}\nEntry point: {bundle.entry_point}\nInstall: {bundle.install_commands}\nRun: {bundle.run_commands}"

    return str(bundle)


def _create_events(devops: DevOpsBundle) -> list[Event]:
    """Create events for successful DevOps config generation."""
    return [
        Event(
            timestamp=now_utc(),
            type=EventType.AGENT_START,
            agent=AgentRole.DEVOPS,
            phase=Phase.DEPLOYMENT,
            payload={"message": "Starting DevOps configuration"},
        ),
        Event(
            timestamp=now_utc(),
            type=EventType.AGENT_END,
            agent=AgentRole.DEVOPS,
            phase=Phase.DEPLOYMENT,
            payload={
                "has_backend_dockerfile": devops.dockerfile_backend is not None,
                "has_frontend_dockerfile": devops.dockerfile_frontend is not None,
                "has_ci": bool(devops.github_actions_ci),
            },
        ),
    ]


def _create_error_events(error_message: str, attempts: int) -> list[Event]:
    """Create events for failed DevOps config generation."""
    return [
        Event(
            timestamp=now_utc(),
            type=EventType.AGENT_START,
            agent=AgentRole.DEVOPS,
            phase=Phase.DEPLOYMENT,
            payload={"message": "Starting DevOps configuration"},
        ),
        Event(
            timestamp=now_utc(),
            type=EventType.ERROR,
            agent=AgentRole.DEVOPS,
            phase=Phase.DEPLOYMENT,
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
        agent=AgentRole.DEVOPS,
        model=model_name,
        input_tokens=tracker.input_tokens,
        output_tokens=tracker.output_tokens,
        cost_usd=cost,
    )


async def devops_engineer_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
) -> dict[str, Any]:
    """DevOps Engineer agent node function.

    Args:
        state: Current graph state
        config: Optional Loom configuration

    Returns:
        State update dict with devops_files, events, and costs
    """
    architecture = state.get("architecture")
    code_files = state.get("code_files", {})

    if architecture is None:
        return {
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.ERROR,
                    agent=AgentRole.DEVOPS,
                    phase=Phase.DEPLOYMENT,
                    payload={"error": "No architecture provided"},
                )
            ],
            "error": "No architecture provided for DevOps configuration",
        }

    # Get or create config
    if config is None:
        from loom.config import load_config

        config = load_config()

    # Get LLM configuration
    llm_config = config.get_llm_config(AgentRole.DEVOPS)
    provider = llm_config.provider
    model = llm_config.model

    # Create token tracker
    tracker = TokenTracker()

    # Get LLM with callback
    llm = get_llm_for_role(AgentRole.DEVOPS, config, callbacks=[tracker])

    # Build the chain
    chain, parser = build_agent_chain(
        system_prompt=DEVOPS_ENGINEER_SYSTEM_PROMPT,
        human_template=DEVOPS_ENGINEER_HUMAN_TEMPLATE,
        output_model=DevOpsBundle,
        llm=llm,
    )

    # Get format instructions
    format_instructions = parser.get_format_instructions()

    # Prepare summaries
    architecture_json = architecture.model_dump_json(indent=2)
    frontend_summary = _summarize_files(code_files.get("frontend"))
    backend_summary = _summarize_files(code_files.get("backend"))

    # Retry loop
    last_error: Exception | None = None
    feedback = ""

    for attempt in range(1, MAX_PARSE_RETRIES + 1):
        try:
            prompt_input = {
                "architecture_json": architecture_json + feedback,
                "frontend_summary": frontend_summary,
                "backend_summary": backend_summary,
                "format_instructions": format_instructions,
            }

            devops = await chain.ainvoke(prompt_input)

            # Success
            events = _create_events(devops)
            costs: list[CostEntry] = []

            cost_entry = _create_cost_entry(tracker, provider, model)
            if cost_entry:
                costs.append(cost_entry)

            logger.info("DevOps configuration generated successfully")

            return {
                "devops_files": devops,
                "phase": Phase.DONE,
                "events": events,
                "costs": costs,
            }

        except Exception as e:
            last_error = e
            logger.warning(f"DevOps config attempt {attempt}/{MAX_PARSE_RETRIES} failed: {e}")

            if attempt < MAX_PARSE_RETRIES:
                raw_output = str(e)
                if hasattr(e, "llm_output"):
                    raw_output = e.llm_output
                feedback = "\n\n" + create_parse_error_feedback(raw_output, str(e))

    # All retries exhausted
    error_message = (
        f"Failed to generate DevOps config after {MAX_PARSE_RETRIES} attempts: {last_error}"
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
