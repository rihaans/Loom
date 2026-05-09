"""Product Manager agent node.

Transforms user description into a structured PRD.
"""

import logging
from datetime import datetime
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import LLMResult

from loom.agents.base import build_agent_chain
from loom.agents.prompts import (
    PRODUCT_MANAGER_HUMAN_TEMPLATE,
    PRODUCT_MANAGER_SYSTEM_PROMPT,
)
from loom.config import LoomConfig
from loom.llm import (
    calculate_cost,
    create_parse_error_feedback,
    get_llm_for_role,
)
from loom.state.enums import AgentRole, EventType, Phase
from loom.state.models import PRD, CostEntry, Event

logger = logging.getLogger(__name__)

# Constants
MAX_PARSE_RETRIES = 3
DEFAULT_MODEL = "qwen2.5-coder:7b"


class TokenTracker(BaseCallbackHandler):
    """Callback handler to track token usage."""

    def __init__(self) -> None:
        super().__init__()
        self.input_tokens = 0
        self.output_tokens = 0
        self.model_name: str | None = None

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract token counts from LLM response."""
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            if usage:
                self.input_tokens = usage.get("prompt_tokens", 0)
                self.output_tokens = usage.get("completion_tokens", 0)
            # Try to get model name
            self.model_name = response.llm_output.get("model_name")


def _create_events(prd: PRD) -> list[Event]:
    """Create events for a successful PRD generation."""
    return [
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.AGENT_START,
            agent=AgentRole.PRODUCT_MANAGER,
            phase=Phase.REQUIREMENTS,
            payload={"message": "Starting PRD generation"},
        ),
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.AGENT_END,
            agent=AgentRole.PRODUCT_MANAGER,
            phase=Phase.REQUIREMENTS,
            payload={
                "project_name": prd.project_name,
                "project_slug": prd.project_slug,
                "user_story_count": len(prd.user_stories),
            },
        ),
    ]


def _create_error_events(error_message: str, attempts: int) -> list[Event]:
    """Create events for a failed PRD generation."""
    return [
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.AGENT_START,
            agent=AgentRole.PRODUCT_MANAGER,
            phase=Phase.REQUIREMENTS,
            payload={"message": "Starting PRD generation"},
        ),
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.ERROR,
            agent=AgentRole.PRODUCT_MANAGER,
            phase=Phase.REQUIREMENTS,
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

    # Use tracked model name if available, otherwise use provided
    model_name = tracker.model_name or model
    cost = calculate_cost(provider, model_name, tracker.input_tokens, tracker.output_tokens)

    return CostEntry(
        agent=AgentRole.PRODUCT_MANAGER,
        model=model_name,
        input_tokens=tracker.input_tokens,
        output_tokens=tracker.output_tokens,
        cost_usd=cost,
    )


async def product_manager_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    """Product Manager agent node function.

    Args:
        state: Current graph state (dict form for LangGraph compatibility)
        config: Optional Loom configuration (uses default if not provided)
        llm: Optional LLM instance (creates one from config if not provided)

    Returns:
        State update dict with prd, events, and costs
    """
    description = state.get("description", "")

    if not description:
        return {
            "events": [
                Event(
                    timestamp=datetime.utcnow(),
                    type=EventType.ERROR,
                    agent=AgentRole.PRODUCT_MANAGER,
                    phase=Phase.REQUIREMENTS,
                    payload={"error": "No description provided"},
                )
            ],
            "error": "No project description provided",
        }

    # Get or create config
    if config is None:
        from loom.config import load_config
        config = load_config()

    # Get LLM configuration
    llm_config = config.get_llm_config(AgentRole.PRODUCT_MANAGER)
    provider = llm_config.provider
    model = llm_config.model

    # Create token tracker
    tracker = TokenTracker()

    # Get or create LLM with callback
    if llm is None:
        llm = get_llm_for_role(AgentRole.PRODUCT_MANAGER, config, callbacks=[tracker])
    else:
        # Add tracker to existing LLM
        if hasattr(llm, "callbacks"):
            if llm.callbacks is None:
                llm.callbacks = [tracker]
            else:
                llm.callbacks.append(tracker)

    # Build the chain
    chain, parser = build_agent_chain(
        system_prompt=PRODUCT_MANAGER_SYSTEM_PROMPT,
        human_template=PRODUCT_MANAGER_HUMAN_TEMPLATE,
        output_model=PRD,
        llm=llm,
    )

    # Get format instructions
    format_instructions = parser.get_format_instructions()

    # Retry loop
    last_error: Exception | None = None
    feedback = ""

    for attempt in range(1, MAX_PARSE_RETRIES + 1):
        try:
            # Build input with optional feedback from previous attempts
            prompt_input = {
                "description": description + feedback,
                "format_instructions": format_instructions,
            }

            # Invoke the chain
            prd = await chain.ainvoke(prompt_input)

            # Success - create response
            events = _create_events(prd)
            costs: list[CostEntry] = []

            cost_entry = _create_cost_entry(tracker, provider, model)
            if cost_entry:
                costs.append(cost_entry)

            logger.info(
                f"PRD generated successfully: {prd.project_name} ({prd.project_slug})"
            )

            return {
                "prd": prd,
                "phase": Phase.DESIGN,
                "events": events,
                "costs": costs,
            }

        except Exception as e:
            last_error = e
            logger.warning(f"PRD generation attempt {attempt}/{MAX_PARSE_RETRIES} failed: {e}")

            if attempt < MAX_PARSE_RETRIES:
                # Create feedback for next attempt
                raw_output = str(e)
                if hasattr(e, "llm_output"):
                    raw_output = e.llm_output
                feedback = "\n\n" + create_parse_error_feedback(raw_output, str(e))

    # All retries exhausted
    error_message = f"Failed to generate PRD after {MAX_PARSE_RETRIES} attempts: {last_error}"
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
