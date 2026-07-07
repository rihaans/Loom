"""Architect agent node.

Transforms PRD into architecture document with tech stack, API design, and components.

Supports two modes controlled by state.interactive:
  - interactive=False (default): one-shot legacy path — unchanged from Phase 4
  - interactive=True (Phase 9): multi-turn conversational path with propose/revise/draft
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from loom._time import now_utc
from loom.agents.base import build_agent_chain
from loom.agents.product_manager import TokenTracker
from loom.agents.prompts.architect import (
    ARCHITECT_DRAFT_PROMPT,
    ARCHITECT_HUMAN_TEMPLATE,
    ARCHITECT_PROPOSE_PROMPT,
    ARCHITECT_REVISE_PROMPT,
    ARCHITECT_SYSTEM_PROMPT,
)
from loom.config import LoomConfig
from loom.llm import calculate_cost, create_parse_error_feedback, get_llm_for_role
from loom.state.enums import AgentRole, EventType, Phase
from loom.state.models import PRD, ArchitectureDoc, CostEntry, Event

logger = logging.getLogger(__name__)

MAX_PARSE_RETRIES = 3
MAX_ARCHITECT_REVISIONS = 5  # Hard cap on revision rounds before forcing a draft


def _create_events(architecture: ArchitectureDoc) -> list[Event]:
    """Create events for a successful architecture generation."""
    return [
        Event(
            timestamp=now_utc(),
            type=EventType.AGENT_START,
            agent=AgentRole.ARCHITECT,
            phase=Phase.DESIGN,
            payload={"message": "Starting architecture design"},
        ),
        Event(
            timestamp=now_utc(),
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
            timestamp=now_utc(),
            type=EventType.AGENT_START,
            agent=AgentRole.ARCHITECT,
            phase=Phase.DESIGN,
            payload={"message": "Starting architecture design"},
        ),
        Event(
            timestamp=now_utc(),
            type=EventType.ERROR,
            agent=AgentRole.ARCHITECT,
            phase=Phase.DESIGN,
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
        agent=AgentRole.ARCHITECT,
        model=model_name,
        input_tokens=tracker.input_tokens,
        output_tokens=tracker.output_tokens,
        cost_usd=cost,
    )


# =============================================================================
# Legacy one-shot path (interactive=False)
# =============================================================================


async def _legacy_one_shot_architect(
    state: dict[str, Any],
    config: LoomConfig,
) -> dict[str, Any]:
    """Original one-shot Architect logic — preserved byte-identical from Phase 4."""
    prd: PRD = state["prd"]  # guaranteed set by architect_node before this path
    description = state.get("description", "")
    memory_context = state.get("memory_context")
    architecture_feedback = state.get("architecture_feedback")
    previous_architecture = state.get("architecture")

    llm_config = config.get_llm_config(AgentRole.ARCHITECT)
    provider = llm_config.provider
    model = llm_config.model

    tracker = TokenTracker()
    llm = get_llm_for_role(AgentRole.ARCHITECT, config, callbacks=[tracker])

    chain, parser = build_agent_chain(
        system_prompt=ARCHITECT_SYSTEM_PROMPT,
        human_template=ARCHITECT_HUMAN_TEMPLATE,
        output_model=ArchitectureDoc,
        llm=llm,
    )

    format_instructions = parser.get_format_instructions()
    prd_json = prd.model_dump_json(indent=2)

    memory_block = ""
    if memory_context is not None and hasattr(memory_context, "to_prompt_block"):
        memory_block = memory_context.to_prompt_block()
        if memory_block:
            memory_block = f"\n\n{memory_block}\n"

    feedback_block = ""
    if architecture_feedback and previous_architecture:
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
                "architecture_feedback": None,
            }

        except Exception as e:
            last_error = e
            logger.warning(
                f"Architecture generation attempt {attempt}/{MAX_PARSE_RETRIES} failed: {e}"
            )
            if attempt < MAX_PARSE_RETRIES:
                raw_output = str(e)
                if hasattr(e, "llm_output"):
                    raw_output = e.llm_output
                feedback = "\n\n" + create_parse_error_feedback(raw_output, str(e))

    error_message = (
        f"Failed to generate architecture after {MAX_PARSE_RETRIES} attempts: {last_error}"
    )
    logger.error(error_message)
    events = _create_error_events(str(last_error), MAX_PARSE_RETRIES)
    costs = []
    cost_entry = _create_cost_entry(tracker, provider, model)
    if cost_entry:
        costs.append(cost_entry)

    return {"events": events, "costs": costs, "error": error_message}


# =============================================================================
# Conversational path helpers (interactive=True)
# =============================================================================


async def _architect_propose_turn(
    prd_json: str,
    history: list[BaseMessage],
    llm: BaseChatModel,
) -> str:
    """Run propose or revise turn. Returns raw AI response text.

    First turn (empty history): use propose prompt with the PRD.
    Subsequent turns: use revise prompt with the conversation.

    Builds plain BaseMessage lists rather than going through ChatPromptTemplate
    so JSON braces in the PRD aren't parsed as template placeholders.
    """
    messages: list[BaseMessage]
    if not history:
        # First turn — propose
        system_text = ARCHITECT_PROPOSE_PROMPT.replace("{prd_json}", prd_json)
        messages = [
            SystemMessage(content=system_text),
            HumanMessage(content="Propose a stack and short design."),
        ]
    else:
        # Subsequent turn — revise. Pass conversation as-is.
        messages = [SystemMessage(content=ARCHITECT_REVISE_PROMPT), *history]

    response = await llm.ainvoke(messages)
    return str(response.content)


async def _architect_draft_doc(
    prd_json: str,
    history: list[BaseMessage],
    config: LoomConfig,
    llm: BaseChatModel | None,
) -> ArchitectureDoc:
    """Draft the full ArchitectureDoc from the accumulated conversation.

    Builds plain BaseMessage lists then invokes llm + parser directly,
    avoiding ChatPromptTemplate placeholder collisions with JSON braces.
    """
    from langchain_core.output_parsers import PydanticOutputParser

    if llm is None:
        llm = get_llm_for_role(AgentRole.ARCHITECT, config)

    parser = PydanticOutputParser(pydantic_object=ArchitectureDoc)
    format_instructions = parser.get_format_instructions()

    system_text = ARCHITECT_DRAFT_PROMPT.replace("{format_instructions}", format_instructions)

    messages: list[BaseMessage] = [
        SystemMessage(content=system_text),
        HumanMessage(content=f"PRD:\n{prd_json}"),
        *history,
        HumanMessage(content="Now produce the complete ArchitectureDoc as JSON."),
    ]

    last_error: Exception | None = None
    for attempt in range(1, MAX_PARSE_RETRIES + 1):
        try:
            response = await llm.ainvoke(messages)
            arch = parser.parse(str(response.content))
            return arch
        except Exception as e:
            last_error = e
            logger.warning(f"Architect draft attempt {attempt}/{MAX_PARSE_RETRIES} failed: {e}")

    raise RuntimeError(
        f"Architect drafting failed after {MAX_PARSE_RETRIES} attempts: {last_error}"
    )


async def _interactive_architect(
    state: dict[str, Any],
    config: LoomConfig,
    llm: BaseChatModel | None,
) -> dict[str, Any]:
    """Conversational Architect path (interactive=True).

    Called once per chat turn. Reads agent_messages and pending_user_input,
    runs one LLM call (propose/revise) or drafts the full doc on __DRAFT__.
    """
    role_key = AgentRole.ARCHITECT.value
    history: list[BaseMessage] = list(state.get("agent_messages", {}).get(role_key, []))
    user_input: str | None = state.get("pending_user_input")
    prd = state.get("prd")

    if prd is None:
        return {
            "agent_status": "wait_for_input",
            "pending_user_input": None,
            "error": "No PRD available for architecture design",
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.ERROR,
                    agent=AgentRole.ARCHITECT,
                    phase=Phase.DESIGN,
                    payload={"error": "No PRD provided"},
                )
            ],
        }

    prd_json = prd.model_dump_json(indent=2)

    if llm is None:
        llm = get_llm_for_role(AgentRole.ARCHITECT, config)

    # --- Drafting trigger ---
    if user_input == "__DRAFT__":
        try:
            arch = await _architect_draft_doc(prd_json, history, config, llm)
            logger.info(
                f"Architect drafted doc: {len(arch.stack)} stack items, "
                f"{len(arch.api_endpoints)} endpoints"
            )
            return {
                "architecture": arch,
                "agent_status": "done",
                "pending_user_input": None,
                "phase": Phase.DEVELOPMENT,
                "events": [
                    Event(
                        timestamp=now_utc(),
                        type=EventType.AGENT_END,
                        agent=AgentRole.ARCHITECT,
                        phase=Phase.DESIGN,
                        payload={
                            "stack_count": len(arch.stack),
                            "endpoint_count": len(arch.api_endpoints),
                        },
                    )
                ],
            }
        except Exception as e:
            return {
                "agent_status": "wait_for_input",
                "pending_user_input": None,
                "error": f"Architect drafting failed: {e}",
                "events": [
                    Event(
                        timestamp=now_utc(),
                        type=EventType.ERROR,
                        agent=AgentRole.ARCHITECT,
                        phase=Phase.DESIGN,
                        payload={"error": str(e)},
                    )
                ],
            }

    # --- Revision cap: force ready_to_draft after MAX_ARCHITECT_REVISIONS ---
    # Each revision is 2 messages (Human user feedback + AI revised proposal).
    # The first turn is also 2 messages (Human bootstrap + AI proposal).
    # So total messages == 2 * (revisions + 1). Cap at 2 * MAX_ARCHITECT_REVISIONS.
    if len(history) >= 2 * MAX_ARCHITECT_REVISIONS:
        logger.info(
            f"Architect hit revision cap ({MAX_ARCHITECT_REVISIONS}), forcing ready_to_draft"
        )
        return {
            "agent_status": "ready_to_draft",
            "pending_user_input": None,
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.AGENT_TURN_LIMIT,
                    agent=AgentRole.ARCHITECT,
                    phase=Phase.DESIGN,
                    payload={
                        "reason": "max_revisions_reached",
                        "revisions": MAX_ARCHITECT_REVISIONS,
                    },
                )
            ],
        }

    # --- Build the new messages for this turn ---
    new_messages: list[BaseMessage] = []
    if user_input:
        new_messages.append(HumanMessage(content=user_input))
    elif not history:
        # Bootstrap: trigger the initial proposal
        new_messages.append(HumanMessage(content="Please propose a stack for this project."))

    full_context = history + new_messages

    # --- Run propose/revise LLM call ---
    try:
        # First-turn propose has the PRD embedded in the system prompt; pass an
        # empty history so the LLM doesn't see the bootstrap message twice.
        propose_history = full_context if len(full_context) > 1 else []
        response_text = await _architect_propose_turn(prd_json, propose_history, llm)
    except Exception as e:
        logger.error(f"Architect propose call failed: {e}")
        return {
            "agent_status": "wait_for_input",
            "pending_user_input": None,
            "error": f"Architect propose failed: {e}",
        }

    # Architect doesn't use a sentinel; it always asks "Sound good?" — the user
    # types "yes" / "/skip" / "/done" to advance, which becomes __DRAFT__.
    new_messages.append(AIMessage(content=response_text.strip()))

    logger.info(f"Architect proposal turn complete (added {len(new_messages)} msgs)")

    # Return ONLY the new messages — reducer appends them to existing history
    return {
        "agent_messages": {role_key: new_messages},
        "agent_status": "wait_for_input",
        "pending_user_input": None,
        "events": [
            Event(
                timestamp=now_utc(),
                type=EventType.AGENT_TURN,
                agent=AgentRole.ARCHITECT,
                phase=Phase.DESIGN,
                payload={"history_length": len(history) + len(new_messages)},
            )
        ],
    }


# =============================================================================
# Public node entry point
# =============================================================================


async def architect_node(
    state: dict[str, Any],
    config: LoomConfig | None = None,
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    """Architect agent node function.

    Routes to legacy one-shot path or conversational path based on
    state['interactive']. The legacy path is byte-identical to Phase 4.

    Args:
        state: Current graph state (dict form for LangGraph compatibility)
        config: Optional Loom configuration
        llm: Optional LLM (only used by conversational path)

    Returns:
        State update dict
    """
    prd = state.get("prd")

    if prd is None and not state.get("interactive"):
        return {
            "events": [
                Event(
                    timestamp=now_utc(),
                    type=EventType.ERROR,
                    agent=AgentRole.ARCHITECT,
                    phase=Phase.DESIGN,
                    payload={"error": "No PRD provided"},
                )
            ],
            "error": "No PRD provided for architecture design",
        }

    if config is None:
        from loom.config import load_config

        config = load_config()

    if state.get("interactive"):
        return await _interactive_architect(state, config, llm)
    else:
        return await _legacy_one_shot_architect(state, config)
