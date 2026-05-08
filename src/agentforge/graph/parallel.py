"""Parallel execution utilities using LangGraph Send API.

Enables fan-out to multiple agents executing in parallel.
"""

import logging
from typing import Any

from langgraph.constants import Send

logger = logging.getLogger(__name__)


def route_to_devs(state: dict[str, Any]) -> list[Send]:
    """Route to frontend and backend developers in parallel.

    Uses LangGraph's Send API to fan-out to both developers,
    allowing them to execute concurrently.

    Args:
        state: Current graph state

    Returns:
        List of Send objects targeting frontend_dev and backend_dev nodes
    """
    logger.info("Fanning out to frontend and backend developers in parallel")

    # Both developers receive the same state
    return [
        Send("frontend_dev", state),
        Send("backend_dev", state),
    ]


def merge_dev_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge results from parallel developer executions.

    Combines code_files, events, and costs from both developers.

    Args:
        results: List of state updates from each developer

    Returns:
        Merged state update
    """
    merged_code_files: dict[str, Any] = {}
    merged_events: list[Any] = []
    merged_costs: list[Any] = []
    error = None

    for result in results:
        # Merge code files
        if "code_files" in result:
            merged_code_files.update(result["code_files"])

        # Append events
        if "events" in result:
            merged_events.extend(result["events"])

        # Append costs
        if "costs" in result:
            merged_costs.extend(result["costs"])

        # Capture any error
        if "error" in result and result["error"]:
            if error:
                error = f"{error}; {result['error']}"
            else:
                error = result["error"]

    merged = {
        "code_files": merged_code_files,
        "events": merged_events,
        "costs": merged_costs,
    }

    if error:
        merged["error"] = error

    logger.info(
        f"Merged dev results: {len(merged_code_files)} bundles, "
        f"{len(merged_events)} events, {len(merged_costs)} cost entries"
    )

    return merged


def should_retry_development(state: dict[str, Any]) -> bool:
    """Check if development should be retried based on QA feedback.

    Args:
        state: Current graph state

    Returns:
        True if should retry development, False otherwise
    """
    test_report = state.get("test_report")
    qa_feedback = state.get("qa_feedback")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    # No test report means we haven't tested yet
    if test_report is None:
        return False

    # Tests passed, no retry needed
    if test_report.failed == 0:
        return False

    # Tests failed but no retries left
    if retry_count >= max_retries:
        logger.warning(f"Tests failed but retry budget exhausted ({retry_count}/{max_retries})")
        return False

    # Tests failed and we have retries, check if we have feedback
    if qa_feedback is None:
        logger.warning("Tests failed but no QA feedback provided")
        return False

    logger.info(f"Tests failed, will retry development (attempt {retry_count + 1}/{max_retries})")
    return True


def get_retry_targets(state: dict[str, Any]) -> list[str]:
    """Determine which developers should be retried based on QA feedback.

    Args:
        state: Current graph state with qa_feedback

    Returns:
        List of developer node names to retry ("frontend_dev", "backend_dev", or both)
    """
    qa_feedback = state.get("qa_feedback")

    if qa_feedback is None:
        # No specific feedback, retry both
        return ["frontend_dev", "backend_dev"]

    target = qa_feedback.target_agent

    if target == "frontend_dev":
        return ["frontend_dev"]
    elif target == "backend_dev":
        return ["backend_dev"]
    else:  # "both"
        return ["frontend_dev", "backend_dev"]


def route_to_retry_devs(state: dict[str, Any]) -> list[Send]:
    """Route to specific developers for retry based on QA feedback.

    Only retries the developers that QA identified as needing fixes.

    Args:
        state: Current graph state

    Returns:
        List of Send objects for targeted developers
    """
    targets = get_retry_targets(state)
    logger.info(f"Retrying development for: {targets}")

    return [Send(target, state) for target in targets]
