"""Cost budget enforcement.

`cost_budget_usd` has been configurable since the beginning but nothing ever
read it, so a user could set a $1 cap and watch a build spend $50. A budget you
cannot rely on is worse than no budget, because people set one and stop
watching.

The check runs before each expensive node, using the costs accumulated in graph
state. It stops the build cleanly - artifacts produced so far are kept, and the
error says what was spent and what the cap was.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BudgetExceededError(RuntimeError):
    """Raised when a build would exceed its configured cost budget."""

    def __init__(self, spent: float, budget: float, next_agent: str):
        self.spent = spent
        self.budget = budget
        self.next_agent = next_agent
        super().__init__(
            f"Cost budget exceeded: spent ${spent:.4f} of ${budget:.2f} budget "
            f"before running {next_agent}. Raise cost.budget_usd in loom.toml "
            f"(or set LOOM_COST_BUDGET), or use a cheaper model."
        )


def spent_so_far(state: dict[str, Any]) -> float:
    """Total USD recorded in graph state so far."""
    return float(sum(c.cost_usd for c in state.get("costs", [])))


def check_budget(state: dict[str, Any], config: Any, next_agent: str) -> str | None:
    """Return an error message if continuing would exceed the budget.

    Returns None when there is no budget, or when spending is still under it.
    A string is returned rather than raising so graph nodes can put it into
    state and let the normal error path stop the build.
    """
    budget = getattr(config, "cost_budget_usd", None)
    if budget is None:
        return None

    spent = spent_so_far(state)
    if spent < budget:
        return None

    logger.error(f"Budget exceeded before {next_agent}: ${spent:.4f} >= ${budget:.2f}")
    return str(BudgetExceededError(spent, budget, next_agent).args[0])


def warn_threshold_crossed(state: dict[str, Any], config: Any) -> float | None:
    """Return the amount spent if it has crossed the warning threshold.

    Returns None when there is nothing to warn about.
    """
    threshold = getattr(config, "cost_warn_threshold_usd", None)
    if not threshold:
        return None
    spent = spent_so_far(state)
    return spent if spent >= threshold else None
