"""Graph routing functions for conditional edges.

These functions determine which node to execute next based on state.
"""

import logging
from typing import Any, Literal

from loom.state.enums import Phase

logger = logging.getLogger(__name__)


def route_after_supervisor(
    state: dict[str, Any],
) -> Literal[
    "product_manager",
    "architect",
    "developers",
    "qa_engineer",
    "devops_engineer",
    "__end__",
]:
    """Route to the appropriate agent after the supervisor determines the phase.

    Args:
        state: Current graph state

    Returns:
        Name of the next node to execute
    """
    phase = state.get("phase", Phase.INIT)

    routing_map = {
        Phase.INIT: "product_manager",
        Phase.REQUIREMENTS: "product_manager",
        Phase.DESIGN: "architect",
        Phase.DEVELOPMENT: "developers",
        Phase.TESTING: "qa_engineer",
        Phase.DEPLOYMENT: "devops_engineer",
        Phase.DONE: "__end__",
    }

    next_node = routing_map.get(phase, "__end__")
    logger.debug(f"Routing phase {phase} -> {next_node}")
    return next_node


def route_after_pm(state: dict[str, Any]) -> Literal["architect", "supervisor"]:
    """Route after Product Manager completes.

    Args:
        state: Current graph state

    Returns:
        Next node - architect if PRD generated, supervisor if error
    """
    if state.get("prd") is not None:
        return "architect"
    return "supervisor"


def route_after_architect(
    state: dict[str, Any],
) -> Literal["developers", "supervisor"]:
    """Route after Architect completes.

    Args:
        state: Current graph state

    Returns:
        Next node - developers if architecture generated, supervisor if error
    """
    if state.get("architecture") is not None:
        return "developers"
    return "supervisor"


def route_after_devs(state: dict[str, Any]) -> Literal["qa_engineer", "supervisor"]:
    """Route after Developers complete.

    Args:
        state: Current graph state

    Returns:
        Next node - qa if code generated, supervisor if error
    """
    code_files = state.get("code_files", {})
    if code_files:
        return "qa_engineer"
    return "supervisor"


def route_after_qa(
    state: dict[str, Any],
) -> Literal["devops_engineer", "developers", "supervisor"]:
    """Route after QA Engineer completes.

    Args:
        state: Current graph state

    Returns:
        Next node based on test results and retry budget
    """
    test_report = state.get("test_report")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    if test_report is None:
        return "supervisor"

    # If tests pass, proceed to devops
    if test_report.failed == 0:
        return "devops_engineer"

    # If tests fail and we have retries left, go back to devs
    if retry_count < max_retries:
        logger.info(f"Tests failed, retry {retry_count + 1}/{max_retries}")
        return "developers"

    # Retry budget exhausted, proceed anyway
    logger.warning("Retry budget exhausted, proceeding to devops despite failures")
    return "devops_engineer"


def route_after_devops(state: dict[str, Any]) -> Literal["__end__", "supervisor"]:
    """Route after DevOps Engineer completes.

    Args:
        state: Current graph state

    Returns:
        End or supervisor based on devops completion
    """
    if state.get("devops_files") is not None:
        return "__end__"
    return "supervisor"


def should_continue(state: dict[str, Any]) -> bool:
    """Check if the graph should continue execution.

    Args:
        state: Current graph state

    Returns:
        True if should continue, False if should stop
    """
    phase = state.get("phase", Phase.INIT)
    error = state.get("error")

    if phase == Phase.DONE:
        return False

    if error:
        logger.warning(f"Error in state, stopping: {error}")
        return False

    return True
