"""Product Manager agent node.

Transforms user description into a structured PRD.

Supports two modes controlled by state.interactive:
  - interactive=False (default): one-shot legacy path — unchanged from Phase 3
  - interactive=True (Phase 9): multi-turn conversational path
"""

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import LLMResult

from loom._time import now_utc
from loom.agents.base import CACHE_SCOPE_KEY, build_agent_chain
from loom.agents.prompts import (
    PRODUCT_MANAGER_HUMAN_TEMPLATE,
    PRODUCT_MANAGER_SYSTEM_PROMPT,
)
from loom.agents.prompts.product_manager import (
    PRODUCT_MANAGER_CLARIFY_PROMPT,
    PRODUCT_MANAGER_DRAFT_PROMPT,
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
MAX_PM_TURNS = 8  # Hard cap on conversational turns before forcing a draft
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
            self.model_name = response.llm_output.get("model_name")


def _create_events(prd: PRD) -> list[Event]:
    """Create events for a successful PRD generation."""
    return [
        Event(
            timestamp=now_utc(),
            type=EventType.AGENT_START,
            agent=AgentRole.PRODUCT_MANAGER,
            phase=Phase.REQUIREMENTS,
            payload={"message": "Starting PRD generation"},
        ),
        Event(
            timestamp=now_utc(),
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
            timestamp=now_utc(),
            type=EventType.AGENT_START,
            agent=AgentRole.PRODUCT_MANAGER,
            phase=Phase.REQUIREMENTS,
            payload={"message": "Starting PRD generation"},
        ),
        Event(
            timestamp=now_utc(),
            type=EventType.ERROR,
            agent=AgentRole.PRODUCT_MANAGER,
            phase=Phase.REQUIREMENTS,
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
        agent=AgentRole.PRODUCT_MANAGER,
        model=model_name,
        input_tokens=tracker.input_tokens,
        output_tokens=tracker.output_tokens,
        cost_usd=cost,
    )


# =============================================================================
# Legacy one-shot path (interactive=False)
# =============================================================================


async def _legacy_one_shot_pm(
    state: dict[str, Any],
    config: LoomConfig,
    llm: BaseChatModel | None,
) -> dict[str, Any]:
    """Original one-shot PM logic — preserved byte-identical from Phase 3."""
    description = state.get("description", "")

    llm_config = config.get_llm_config(AgentRole.PRODUCT_MANAGER)
    provider = llm_config.provider
    model = llm_config.model

    tracker = TokenTracker()

    if llm is None:
        llm = get_llm_for_role(AgentRole.PRODUCT_MANAGER, config, callbacks=[tracker])
    else:
        if hasattr(llm, "callbacks"):
            if llm.callbacks is None:
                llm.callbacks = [tracker]
            elif isinstance(llm.callbacks, list):
                llm.callbacks.append(tracker)

    chain, parser = build_agent_chain(
        system_prompt=PRODUCT_MANAGER_SYSTEM_PROMPT,
        human_template=PRODUCT_MANAGER_HUMAN_TEMPLATE,
        output_model=PRD,
        llm=llm,
        agent_name="product_manager",
    )

    format_instructions = parser.get_format_instructions()
    last_error: Exception | None = None
    feedback = ""

    for attempt in range(1, MAX_PARSE_RETRIES + 1):
        try:
            prompt_input = {
                "description": description + feedback,
                "format_instructions": format_instructions,
            }
            # All attempts for this request share one cache entry: the
            # retry feedback is an implementation detail, not a new request.
            prompt_input[CACHE_SCOPE_KEY] = {**prompt_input, "description": description}
            prd = await chain.ainvoke(prompt_input)

            events = _create_events(prd)
            costs: list[CostEntry] = []
            cost_entry = _create_cost_entry(tracker, provider, model)
            if cost_entry:
                costs.append(cost_entry)

            logger.info(f"PRD generated successfully: {prd.project_name} ({prd.project_slug})")

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
                raw_output = str(e)
                if hasattr(e, "llm_output"):
                    raw_output = e.llm_output
                feedback = "\n\n" + create_parse_error_feedback(raw_output, str(e))

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


# =============================================================================
# Conversational path helpers (interactive=True)
# =============================================================================


def _unwrap_json_response(text: str) -> str:
    """Strip JSON wrapping that small code models add despite prompt instructions.

    qwen2.5-coder and similar code-tuned models often wrap conversational
    replies in {"message": "..."} or {"response": "..."} regardless of how
    explicitly the system prompt forbids it. We unwrap here so the rendered
    output is plain prose.

    For "data-shaped" JSON (e.g. {"single_user": true, "auth": false}), we
    render the keys/values as a bullet list — it's at least readable.

    Returns the original text unchanged if it doesn't look like JSON at all.
    """
    import json
    import re

    stripped = text.strip()

    # Strip optional ```json ... ``` code fence
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```\s*$", "", stripped)
    stripped = stripped.strip()

    if not stripped.startswith("{"):
        return text

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return text

    if not isinstance(parsed, dict):
        return text

    # Look for a single string field with a known wrapper key
    for key in ("message", "response", "content", "text", "reply", "answer"):
        value = parsed.get(key)
        if isinstance(value, str):
            return value

    # Single string value — use it directly
    if len(parsed) == 1:
        only_value = next(iter(parsed.values()))
        if isinstance(only_value, str):
            return only_value

    # Data-shaped JSON: render as a bullet list for readability.
    # This is the qwen-coder pathology where it answers conversational
    # questions with raw data structures.
    lines = ["Got it — I read that as:"]
    for k, v in parsed.items():
        lines.append(f"  • {k}: {v}")
    lines.append("")
    lines.append("(If that's wrong, just type your answer in plain English.)")
    return "\n".join(lines)


async def _pm_clarify_turn(
    history: list[BaseMessage],
    llm: BaseChatModel,
) -> str:
    """Run one clarifying turn. Returns the raw AI response text.

    Builds a plain message list (system + conversation) so user-typed text
    isn't parsed as template placeholders. Unwraps any JSON wrapping that
    code-tuned models add reflexively.
    """
    messages: list[BaseMessage] = [
        SystemMessage(content=PRODUCT_MANAGER_CLARIFY_PROMPT),
        *history,
    ]
    response = await llm.ainvoke(messages)
    return _unwrap_json_response(str(response.content))


async def _pm_draft_prd(
    history: list[BaseMessage],
    config: LoomConfig,
    llm: BaseChatModel | None,
) -> PRD:
    """Draft a PRD from the accumulated conversation history.

    Uses raw message lists + parser directly so JSON schema braces in
    `format_instructions` don't collide with template parsing.
    """
    from langchain_core.output_parsers import PydanticOutputParser

    if llm is None:
        llm = get_llm_for_role(AgentRole.PRODUCT_MANAGER, config)

    parser = PydanticOutputParser(pydantic_object=PRD)
    format_instructions = parser.get_format_instructions()

    system_text = PRODUCT_MANAGER_DRAFT_PROMPT.replace("{format_instructions}", format_instructions)

    messages: list[BaseMessage] = [
        SystemMessage(content=system_text),
        *history,
        HumanMessage(content="Now produce the complete PRD as JSON."),
    ]

    last_error: Exception | None = None
    for attempt in range(1, MAX_PARSE_RETRIES + 1):
        try:
            response = await llm.ainvoke(messages)
            prd = parser.parse(str(response.content))
            return prd
        except Exception as e:
            last_error = e
            logger.warning(f"PM draft attempt {attempt}/{MAX_PARSE_RETRIES} failed: {e}")

    raise RuntimeError(f"PM drafting failed after {MAX_PARSE_RETRIES} attempts: {last_error}")


async def _interactive_pm(
    state: dict[str, Any],
    config: LoomConfig,
    llm: BaseChatModel | None,
) -> dict[str, Any]:
    """Conversational PM path (interactive=True).

    Called once per chat turn. Reads agent_messages and pending_user_input
    from state, runs one LLM call, then returns ONLY the new messages from
    this turn. The merge_messages_dict reducer appends them to the existing
    history — so returning the full history would cause duplication.
    """
    role_key = AgentRole.PRODUCT_MANAGER.value
    existing_history: list[BaseMessage] = list(state.get("agent_messages", {}).get(role_key, []))
    user_input: str | None = state.get("pending_user_input")

    if llm is None:
        llm = get_llm_for_role(AgentRole.PRODUCT_MANAGER, config)

    # --- Drafting trigger ---
    if user_input == "__DRAFT__":
        try:
            prd = await _pm_draft_prd(existing_history, config, llm)
            logger.info(f"PM drafted PRD: {prd.project_name}")
            return {
                "prd": prd,
                "agent_status": "done",
                "pending_user_input": None,
                "events": [
                    Event(
                        timestamp=now_utc(),
                        type=EventType.AGENT_END,
                        agent=AgentRole.PRODUCT_MANAGER,
                        phase=Phase.REQUIREMENTS,
                        payload={"project_name": prd.project_name},
                    )
                ],
            }
        except Exception as e:
            return {
                "agent_status": "wait_for_input",
                "pending_user_input": None,
                "error": f"PM drafting failed: {e}",
                "events": [
                    Event(
                        timestamp=now_utc(),
                        type=EventType.ERROR,
                        agent=AgentRole.PRODUCT_MANAGER,
                        phase=Phase.REQUIREMENTS,
                        payload={"error": str(e)},
                    )
                ],
            }

    # --- Turn cap: force ready_to_draft after MAX_PM_TURNS ---
    # history has 2 messages per turn (HumanMessage + AIMessage)
    if len(existing_history) >= 2 * MAX_PM_TURNS:
        logger.info(f"PM hit turn cap ({MAX_PM_TURNS}), forcing ready_to_draft")
        return {
            "agent_status": "ready_to_draft",
            "pending_user_input": None,
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.AGENT_TURN_LIMIT,
                    agent=AgentRole.PRODUCT_MANAGER,
                    phase=Phase.REQUIREMENTS,
                    payload={"reason": "max_turns_reached", "turns": MAX_PM_TURNS},
                )
            ],
        }

    # --- Build the new messages for this turn ---
    new_messages: list[BaseMessage] = []
    if user_input:
        new_messages.append(HumanMessage(content=user_input))
    elif not existing_history:
        # Bootstrap: first invocation, no input yet — use description
        description = state.get("description", "")
        new_messages.append(HumanMessage(content=description))

    # Full context for the LLM = existing + new (LLM needs full conversation)
    full_context = existing_history + new_messages

    # --- Run clarifying LLM call ---
    try:
        response_text = await _pm_clarify_turn(full_context, llm)
    except Exception as e:
        logger.error(f"PM clarify call failed: {e}")
        return {
            "agent_status": "wait_for_input",
            "pending_user_input": None,
            "error": f"PM clarify failed: {e}",
        }

    # --- Detect <READY_TO_DRAFT> sentinel ---
    suggests_drafting = "<READY_TO_DRAFT>" in response_text
    cleaned = response_text.replace("<READY_TO_DRAFT>", "").strip()

    # Defensive: small models sometimes return empty content (e.g. they emitted
    # only a tool-call-shaped wrapper that unwrapped to nothing, or produced
    # only the sentinel and nothing else). Don't render an empty bubble — surface
    # an error and let the user retry. We still keep the user's input in history
    # so it isn't lost.
    if not cleaned:
        logger.warning(
            f"PM clarify returned empty content (raw={response_text!r}). "
            "Likely a small-model output-format issue."
        )
        return {
            "agent_messages": {role_key: new_messages} if new_messages else {},
            "agent_status": "wait_for_input",
            "pending_user_input": None,
            "error": (
                "The model returned an empty response. This sometimes happens "
                "with small code-tuned models — try rephrasing, or switch to a "
                "non-coder model: loom --model ollama:llama3.1:8b"
            ),
        }

    new_messages.append(AIMessage(content=cleaned))

    logger.info(f"PM clarifying turn complete. suggests_drafting={suggests_drafting}")

    # Return ONLY the new messages — reducer appends them to existing history
    return {
        "agent_messages": {role_key: new_messages},
        "agent_status": "ready_to_draft" if suggests_drafting else "wait_for_input",
        "pending_user_input": None,
        "events": [
            Event(
                timestamp=now_utc(),
                type=EventType.AGENT_TURN,
                agent=AgentRole.PRODUCT_MANAGER,
                phase=Phase.REQUIREMENTS,
                payload={"suggests_drafting": suggests_drafting},
            )
        ],
    }


# =============================================================================
# Public node entry point
# =============================================================================


async def product_manager_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    """Product Manager agent node function.

    Routes to legacy one-shot path or conversational path based on
    state['interactive']. The legacy path is byte-identical to Phase 3.

    Args:
        state: Current graph state (dict form for LangGraph compatibility)
        config: Optional Loom configuration (uses default if not provided)
        llm: Optional LLM instance (creates one from config if not provided)

    Returns:
        State update dict
    """
    description = state.get("description", "")

    if not description and not state.get("interactive"):
        return {
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.ERROR,
                    agent=AgentRole.PRODUCT_MANAGER,
                    phase=Phase.REQUIREMENTS,
                    payload={"error": "No description provided"},
                )
            ],
            "error": "No project description provided",
        }

    if config is None:
        from loom.config import load_config

        config = load_config()

    if state.get("interactive"):
        return await _interactive_pm(state, config, llm)
    else:
        return await _legacy_one_shot_pm(state, config, llm)
