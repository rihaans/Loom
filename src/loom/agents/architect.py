"""Architect agent node.

Transforms PRD into architecture document with tech stack, API design, and components.
"""

import logging
from datetime import datetime
from typing import Any

from loom.agents.base import build_agent_chain
from loom.agents.product_manager import TokenTracker
from loom.agents.prompts.architect import (
    ARCHITECT_HUMAN_TEMPLATE,
    ARCHITECT_SYSTEM_PROMPT,
)
from loom.config import LoomConfig
from loom.llm import calculate_cost, create_parse_error_feedback, get_llm_for_role
from loom.state.enums import AgentRole, EventType, Phase
from loom.state.models import ArchitectureDoc, CostEntry, Event

logger = logging.getLogger(__name__)

MAX_PARSE_RETRIES = 3


def _create_events(architecture: ArchitectureDoc) -> list[Event]:
    """Create events for a successful architecture generation."""
    return [
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.AGENT_START,
            agent=AgentRole.ARCHITECT,
            phase=Phase.DESIGN,
            payload={"message": "Starting architecture design"},
        ),
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.AGENT_END,
            agent=AgentRole.ARCHITECT,
            phase=Phase.DESIGN,
            payload={
                "stack_count": len(architecture.stack),
                "endpoint_count": len(architecture.api_endpoints),
                "component_count": len(architecture.components),
            },
        ),
    ]


def _create_error_events(error_message: str, attempts: int) -> list[Event]:
    """Create events for a failed architecture generation."""
    return [
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.AGENT_START,
            agent=AgentRole.ARCHITECT,
            phase=Phase.DESIGN,
            payload={"message": "Starting architecture design"},
        ),
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.ERROR,
            agent=AgentRole.ARCHITECT,
            phase=Phase.DESIGN,
            payload={
                "error": error_message,
                "attempts": attempts,
            },
        ),
    ]


def _create_cost_entry(
    tracker: TokenTracker, provider: str, model: str
) -> CostEntry | None:
    """Create a cost entry from token tracking data."""
    if tracker.input_tokens == 0 and tracker.output_tokens == 0:
        return None

    model_name = tracker.model_name or model
    cost = calculate_cost(provider, model_name, tracker.input_tokens, tracker.output_tokens)

    return CostEntry(
        agent=AgentRole.ARCHITECT,
        model=model_name,
        input_tokens=tracker.input_tokens,
        output_tokens=tracker.output_tokens,
        cost_usd=cost,
    )


async def architect_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
) -> dict[str, Any]:
    """Architect agent node function.

    Args:
        state: Current graph state (dict form for LangGraph compatibility)
        config: Optional Loom configuration

    Returns:
        State update dict with architecture, events, and costs
    """
    prd = state.get("prd")
    description = state.get("description", "")
    memory_context = state.get("memory_context")
    architecture_feedback = state.get("architecture_feedback")
    previous_architecture = state.get("architecture")

    if prd is None:
        return {
            "events": [
                Event(
                    timestamp=datetime.utcnow(),
                    type=EventType.ERROR,
                    agent=AgentRole.ARCHITECT,
                    phase=Phase.DESIGN,
                    payload={"error": "No PRD provided"},
                )
            ],
            "error": "No PRD provided for architecture design",
        }

    # Get or create config
    if config is None:
        from loom.config import load_config
        config = load_config()

    # Get LLM configuration
    llm_config = config.get_llm_config(AgentRole.ARCHITECT)
    provider = llm_config.provider
    model = llm_config.model

    # Create token tracker
    tracker = TokenTracker()

    # Get LLM with callback
    llm = get_llm_for_role(AgentRole.ARCHITECT, config, callbacks=[tracker])

    # Build the chain
    chain, parser = build_agent_chain(
        system_prompt=ARCHITECT_SYSTEM_PROMPT,
        human_template=ARCHITECT_HUMAN_TEMPLATE,
        output_model=ArchitectureDoc,
        llm=llm,
    )

    # Get format instructions
    format_instructions = parser.get_format_instructions()

    # Convert PRD to JSON for the prompt
    prd_json = prd.model_dump_json(indent=2)

    # Build memory block from context (if available)
    memory_block = ""
    if memory_context is not None and hasattr(memory_context, "to_prompt_block"):
        memory_block = memory_context.to_prompt_block()
        if memory_block:
            memory_block = f"\n\n{memory_block}\n"

    # Build feedback block for plan iteration (if user provided feedback)
    feedback_block = ""
    if architecture_feedback and previous_architecture:
        # Summarize previous architecture
        prev_stack = ""
        if hasattr(previous_architecture, "stack"):
            tech_names = [t.technology for t in previous_architecture.stack]
            prev_stack = ", ".join(tech_names)

        feedback_block = f"""

# User feedback on previous architecture
You previously proposed a stack with: {prev_stack}

The user requested these changes:
{architecture_feedback}

Produce a revised ArchitectureDoc that addresses the feedback while keeping unchanged decisions stable.
"""

    # Retry loop
    last_error: Exception | None = None
    feedback = ""

    for attempt in range(1, MAX_PARSE_RETRIES + 1):
        try:
            prompt_input = {
                "prd_json": prd_json + feedback,
                "description": description,
                "memory_block": memory_block,
                "feedback_block": feedback_block,
                "format_instructions": format_instructions,
            }

            architecture = await chain.ainvoke(prompt_input)

            # Success
            events = _create_events(architecture)
            costs: list[CostEntry] = []

            cost_entry = _create_cost_entry(tracker, provider, model)
            if cost_entry:
                costs.append(cost_entry)

            logger.info(
                f"Architecture generated: {len(architecture.stack)} tech choices, "
                f"{len(architecture.api_endpoints)} endpoints"
            )

            return {
                "architecture": architecture,
                "phase": Phase.DEVELOPMENT,
                "events": events,
                "costs": costs,
                "architecture_feedback": None,  # Clear feedback after success
            }

        except Exception as e:
            last_error = e
            logger.warning(f"Architecture generation attempt {attempt}/{MAX_PARSE_RETRIES} failed: {e}")

            if attempt < MAX_PARSE_RETRIES:
                raw_output = str(e)
                if hasattr(e, "llm_output"):
                    raw_output = e.llm_output
                feedback = "\n\n" + create_parse_error_feedback(raw_output, str(e))

    # All retries exhausted
    error_message = f"Failed to generate architecture after {MAX_PARSE_RETRIES} attempts: {last_error}"
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
