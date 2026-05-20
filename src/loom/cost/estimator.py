"""Cost and duration estimation for builds.

Provides estimates based on project complexity and LLM pricing.
"""

from typing import Any

from loom.llm import calculate_cost

# Base token estimates per agent (P50, P90) from empirical data
# These should be calibrated from real runs via scripts/calibrate_estimates.py
BASE_TOKENS = {
    "frontend_dev": (8000, 18000),
    "backend_dev": (10000, 22000),
    "qa_engineer": (6000, 14000),
    "devops_engineer": (3000, 6000),
}

# Base duration estimates per agent in seconds (P50, P90)
BASE_DURATION = {
    "frontend_dev": (30, 60),
    "backend_dev": (40, 80),
    "qa_engineer": (20, 45),
    "devops_engineer": (15, 30),
}


def _get_complexity_multiplier(state: dict[str, Any]) -> float:
    """Calculate complexity multiplier based on PRD size.

    Args:
        state: The current agent state.

    Returns:
        Multiplier (1.0 = average complexity).
    """
    prd = state.get("prd")
    if prd is None:
        return 1.0

    # Base multiplier
    mult = 1.0

    # Adjust for number of user stories
    user_stories = getattr(prd, "user_stories", [])
    mult += 0.15 * len(user_stories) / 5

    # Adjust for number of data entities
    data_entities = getattr(prd, "data_entities", [])
    mult += 0.1 * len(data_entities) / 3

    # Adjust for number of features
    features = getattr(prd, "must_have_features", [])
    mult += 0.1 * len(features) / 5

    return min(mult, 2.5)  # Cap at 2.5x


def _has_frontend(state: dict[str, Any]) -> bool:
    """Check if the project has a frontend component.

    Args:
        state: The current agent state.

    Returns:
        True if frontend is needed.
    """
    architecture = state.get("architecture")
    if architecture is None:
        return True  # Assume frontend by default

    # Check stack for frontend layer
    stack = getattr(architecture, "stack", [])
    for tech in stack:
        layer = getattr(tech, "layer", None)
        if layer and str(layer).lower() in ("frontend", "ui"):
            technology = getattr(tech, "technology", "").lower()
            if technology not in ("none", "n/a", ""):
                return True

    return False


def estimate_build_cost(
    state: dict[str, Any],
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
) -> tuple[float, float]:
    """Estimate the cost to complete a build from the current state.

    Args:
        state: The current agent state (with PRD and architecture).
        provider: LLM provider name.
        model: LLM model name.

    Returns:
        Tuple of (low_estimate, high_estimate) in USD.
    """
    # For local models, cost is always zero
    if provider.lower() == "ollama":
        return (0.0, 0.0)

    complexity = _get_complexity_multiplier(state)
    has_frontend = _has_frontend(state)

    # Determine which agents will run
    if has_frontend:
        agents = ["frontend_dev", "backend_dev", "qa_engineer", "devops_engineer"]
    else:
        agents = ["backend_dev", "qa_engineer", "devops_engineer"]

    low = 0.0
    high = 0.0

    for agent in agents:
        tokens_low, tokens_high = BASE_TOKENS.get(agent, (5000, 15000))

        # Assume 40% input, 60% output token split
        input_low = int(tokens_low * 0.4 * complexity)
        output_low = int(tokens_low * 0.6 * complexity)
        input_high = int(tokens_high * 0.4 * complexity)
        output_high = int(tokens_high * 0.6 * complexity)

        low += calculate_cost(provider, model, input_low, output_low)
        high += calculate_cost(provider, model, input_high, output_high)

    # Add retry buffer to high estimate
    high *= 1.4

    return (round(low, 2), round(high, 2))


def estimate_duration(
    state: dict[str, Any],
    provider: str = "anthropic",
) -> tuple[int, int]:
    """Estimate the duration to complete a build.

    Args:
        state: The current agent state.
        provider: LLM provider name.

    Returns:
        Tuple of (low_seconds, high_seconds).
    """
    complexity = _get_complexity_multiplier(state)
    has_frontend = _has_frontend(state)

    # Determine which agents will run
    if has_frontend:
        agents = ["frontend_dev", "backend_dev", "qa_engineer", "devops_engineer"]
    else:
        agents = ["backend_dev", "qa_engineer", "devops_engineer"]

    low = 0
    high = 0

    for agent in agents:
        dur_low, dur_high = BASE_DURATION.get(agent, (20, 50))
        low += int(dur_low * complexity)
        high += int(dur_high * complexity)

    # Ollama is typically slower
    if provider.lower() == "ollama":
        low = int(low * 1.5)
        high = int(high * 2.0)

    # Add retry buffer
    high = int(high * 1.3)

    return (low, high)
