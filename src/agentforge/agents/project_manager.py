"""Project Manager (Supervisor) node.

Deterministic routing logic - no LLM needed.
Decides the next phase based on current state.
"""

import logging
from datetime import datetime
from typing import Any

from agentforge.state.enums import AgentRole, EventType, Phase
from agentforge.state.models import Event

logger = logging.getLogger(__name__)


def decide_next_phase(state: dict[str, Any]) -> Phase:
    """Determine the next phase based on current state.

    Decision rules:
    1. If no PRD: REQUIREMENTS
    2. If PRD but no architecture: DESIGN
    3. If architecture but no code: DEVELOPMENT
    4. If code but no test report: TESTING
    5. If test report failed AND retry_count < max_retries: DEVELOPMENT (revision)
    6. If tests pass (or retry budget exhausted) and no devops: DEPLOYMENT
    7. If devops done: DONE

    Args:
        state: Current graph state

    Returns:
        Next phase to transition to
    """
    prd = state.get("prd")
    architecture = state.get("architecture")
    code_files = state.get("code_files", {})
    test_report = state.get("test_report")
    devops_files = state.get("devops_files")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)
    error = state.get("error")

    # If there's a critical error, don't proceed
    if error:
        logger.warning(f"Error in state, cannot determine next phase: {error}")
        return Phase.DONE

    # Rule 1: No PRD -> REQUIREMENTS
    if prd is None:
        logger.info("No PRD found, routing to REQUIREMENTS phase")
        return Phase.REQUIREMENTS

    # Rule 2: PRD but no architecture -> DESIGN
    if architecture is None:
        logger.info("PRD exists but no architecture, routing to DESIGN phase")
        return Phase.DESIGN

    # Rule 3: Architecture but no code -> DEVELOPMENT
    if not code_files:
        logger.info("Architecture exists but no code, routing to DEVELOPMENT phase")
        return Phase.DEVELOPMENT

    # Rule 4: Code but no test report -> TESTING
    if test_report is None:
        logger.info("Code exists but no test report, routing to TESTING phase")
        return Phase.TESTING

    # Rule 5: Tests failed and retries remaining -> DEVELOPMENT (revision)
    if test_report.failed > 0 and retry_count < max_retries:
        logger.info(
            f"Tests failed ({test_report.failed} failures), "
            f"retry {retry_count + 1}/{max_retries}, routing back to DEVELOPMENT"
        )
        return Phase.DEVELOPMENT

    # Rule 6: Tests passed (or retries exhausted) but no devops -> DEPLOYMENT
    if devops_files is None:
        if test_report.failed > 0:
            logger.warning(
                f"Tests still failing but retry budget exhausted "
                f"({retry_count}/{max_retries}), proceeding to DEPLOYMENT anyway"
            )
        else:
            logger.info("Tests passed, routing to DEPLOYMENT phase")
        return Phase.DEPLOYMENT

    # Rule 7: Everything done -> DONE
    logger.info("All phases complete, routing to DONE")
    return Phase.DONE


def project_manager_node(state: dict[str, Any]) -> dict[str, Any]:
    """Project Manager (Supervisor) node function.

    This is a deterministic supervisor that routes to the next phase
    based on state. No LLM is used.

    Args:
        state: Current graph state

    Returns:
        State update dict with phase and events
    """
    current_phase = state.get("phase", Phase.INIT)
    next_phase = decide_next_phase(state)

    # Increment retry count if going back to development after testing
    retry_count = state.get("retry_count", 0)
    if current_phase == Phase.TESTING and next_phase == Phase.DEVELOPMENT:
        retry_count += 1

    events = [
        Event(
            timestamp=datetime.utcnow(),
            type=EventType.PHASE_TRANSITION,
            agent=AgentRole.SUPERVISOR,
            phase=next_phase,
            payload={
                "from_phase": current_phase,
                "to_phase": next_phase,
                "retry_count": retry_count,
            },
        ),
    ]

    logger.info(f"Phase transition: {current_phase} -> {next_phase}")

    return {
        "phase": next_phase,
        "retry_count": retry_count,
        "events": events,
    }


def route_to_agent(state: dict[str, Any]) -> str:
    """Route to the appropriate agent based on current phase.

    This is used by LangGraph's conditional edges to determine
    which agent node to execute next.

    Args:
        state: Current graph state

    Returns:
        Name of the next agent node to execute
    """
    phase = state.get("phase", Phase.INIT)

    routing = {
        Phase.INIT: "project_manager",
        Phase.REQUIREMENTS: "product_manager",
        Phase.DESIGN: "architect",
        Phase.DEVELOPMENT: "developers",  # Fan-out to both devs
        Phase.TESTING: "qa_engineer",
        Phase.DEPLOYMENT: "devops_engineer",
        Phase.DONE: "__end__",
    }

    agent = routing.get(phase, "__end__")
    logger.debug(f"Routing phase {phase} to agent: {agent}")
    return agent
