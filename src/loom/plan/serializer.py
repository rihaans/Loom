"""Plan serialization for saving and loading plans."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loom import __version__
from loom.cost.estimator import estimate_build_cost, estimate_duration


def save_plan(
    state: dict[str, Any],
    path: Path,
    thread_id: str,
    description: str,
    config: Any | None = None,
) -> Path:
    """Save a plan to a JSON file.

    Args:
        state: The agent state with PRD and architecture.
        path: Path to save the plan file.
        thread_id: The thread ID for resuming.
        description: The original project description.
        config: Optional Loom configuration.

    Returns:
        The path where the plan was saved.
    """
    prd = state.get("prd")
    architecture = state.get("architecture")
    memory_context = state.get("memory_context")

    # Serialize PRD
    prd_data = None
    if prd is not None:
        prd_data = prd.model_dump() if hasattr(prd, "model_dump") else dict(prd)

    # Serialize architecture
    arch_data = None
    if architecture is not None:
        arch_data = architecture.model_dump() if hasattr(architecture, "model_dump") else dict(architecture)

    # Serialize memory context
    memory_data = None
    if memory_context is not None:
        memory_data = memory_context.model_dump() if hasattr(memory_context, "model_dump") else {}

    # Get config data
    config_data = {}
    if config is not None:
        config_data = {
            "llm_default": {
                "provider": config.llm_default.provider,
                "model": config.llm_default.model,
            },
            "memory": {
                "enabled": config.memory.enabled,
            },
        }

    # Estimate cost and duration
    provider = config.llm_default.provider if config else "anthropic"
    model = config.llm_default.model if config else "claude-sonnet-4-20250514"
    cost_low, cost_high = estimate_build_cost(state, provider, model)
    dur_low, dur_high = estimate_duration(state, provider)

    plan_data = {
        "version": 1,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "loom_version": __version__,
        "thread_id": thread_id,
        "description": description,
        "prd": prd_data,
        "architecture": arch_data,
        "memory_context": memory_data,
        "config": config_data,
        "estimated_cost_usd": [cost_low, cost_high],
        "estimated_duration_sec": [dur_low, dur_high],
    }

    # Ensure directory exists
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write plan
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2, default=str)

    return path


def load_plan(path: Path) -> dict[str, Any]:
    """Load a plan from a JSON file.

    Args:
        path: Path to the plan file.

    Returns:
        Plan data dictionary.

    Raises:
        FileNotFoundError: If the plan file doesn't exist.
        ValueError: If the plan file is invalid.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Plan file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate version
    version = data.get("version", 0)
    if version != 1:
        raise ValueError(f"Unsupported plan version: {version}")

    # Validate required fields
    required = ["thread_id", "description", "prd", "architecture"]
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required field in plan: {field}")

    return data


def default_plan_path(state: dict[str, Any]) -> Path:
    """Generate a default path for a plan file.

    Args:
        state: The agent state.

    Returns:
        Path to save the plan.
    """
    prd = state.get("prd")
    if prd is not None:
        slug = getattr(prd, "project_slug", "plan")
    else:
        slug = "plan"

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"{slug}-{date_str}.json"

    # Find unique filename
    plans_dir = Path("plans")
    path = plans_dir / filename

    counter = 1
    while path.exists():
        path = plans_dir / f"{slug}-{date_str}-{counter}.json"
        counter += 1

    return path
