"""Graph builder for wiring agent nodes.

Creates the LangGraph state machine with all agent nodes and routing.
"""

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from loom.agents import (
    architect_node,
    backend_dev_node,
    devops_engineer_node,
    frontend_dev_node,
    memory_persist_node,
    memory_retrieve_node,
    product_manager_node,
    project_manager_node,
    qa_engineer_node,
)
from loom.config import LoomConfig
from loom.graph.parallel import route_to_devs, route_to_retry_devs
from loom.graph.routing import (
    route_after_devops,
    route_after_pm,
    route_after_qa,
)

logger = logging.getLogger(__name__)


async def _dev_merge_node(state: dict[str, Any]) -> dict[str, Any]:
    """Merge node that combines results from parallel developer executions.

    This node is called after the fan-in from frontend_dev and backend_dev.
    LangGraph automatically collects results from parallel Send operations.

    Args:
        state: Current graph state (includes results from both devs)

    Returns:
        State with merged developer results
    """
    # In LangGraph's Send API, parallel results are collected automatically
    # The state already contains merged results from the reducer
    # This node serves as a synchronization point after fan-in
    logger.info("Developer merge node: synchronizing parallel results")
    return {}


def build_linear_graph(config: LoomConfig | None = None) -> StateGraph:
    """Build agent graph with parallel developer execution.

    The graph follows this flow:
    1. product_manager -> generates PRD
    2. memory_retrieve -> retrieves similar past builds (injects memory_context)
    3. architect -> generates architecture (uses memory_context)
    4. frontend_dev + backend_dev (PARALLEL via Send API) -> generates code
    5. dev_merge -> synchronization point after parallel execution
    6. qa_engineer -> runs tests
    7. devops_engineer -> generates DevOps configs
    8. memory_persist -> persists successful build
    9. END

    Conditional routing handles:
    - Parallel fan-out to developers using Send API
    - Targeted retry of specific developers based on QA feedback
    - Stopping on errors

    Args:
        config: Optional Loom configuration

    Returns:
        Compiled StateGraph ready for execution
    """
    # Create graph with AgentState schema
    # Using dict for state since LangGraph works with dicts
    graph = StateGraph(dict)

    # Wrap nodes to inject config
    async def pm_node(state: dict) -> dict:
        return await product_manager_node(state, config)

    async def mem_retrieve_node(state: dict) -> dict:
        return await memory_retrieve_node(state, config)

    async def arch_node(state: dict) -> dict:
        return await architect_node(state, config)

    async def fe_dev_node(state: dict) -> dict:
        return await frontend_dev_node(state, config)

    async def be_dev_node(state: dict) -> dict:
        return await backend_dev_node(state, config)

    async def dev_merge(state: dict) -> dict:
        return await _dev_merge_node(state)

    async def qa_node(state: dict) -> dict:
        return await qa_engineer_node(state, config)

    async def devops_node(state: dict) -> dict:
        return await devops_engineer_node(state, config)

    async def mem_persist_node(state: dict) -> dict:
        return await memory_persist_node(state, config)

    def supervisor_node(state: dict) -> dict:
        return project_manager_node(state)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("product_manager", pm_node)
    graph.add_node("memory_retrieve", mem_retrieve_node)
    graph.add_node("architect", arch_node)
    graph.add_node("frontend_dev", fe_dev_node)
    graph.add_node("backend_dev", be_dev_node)
    graph.add_node("dev_merge", dev_merge)
    graph.add_node("qa_engineer", qa_node)
    graph.add_node("devops_engineer", devops_node)
    graph.add_node("memory_persist", mem_persist_node)

    # Set entry point
    graph.set_entry_point("product_manager")

    # Add conditional edges
    # Product manager routes to memory_retrieve (to fetch similar builds)
    graph.add_conditional_edges(
        "product_manager",
        route_after_pm,
        {
            "architect": "memory_retrieve",  # Route to memory_retrieve first
            "supervisor": "supervisor",
        },
    )

    # Memory retrieve always goes to architect
    graph.add_edge("memory_retrieve", "architect")

    # Architect routes to parallel developers via Send API or supervisor on error
    def route_architect_to_devs(state: dict):
        """Route from architect to developers using Send for parallel execution."""
        if state.get("error"):
            return "supervisor"
        # Return list of Send objects for parallel fan-out
        return route_to_devs(state)

    graph.add_conditional_edges(
        "architect",
        route_architect_to_devs,
    )

    # Both developers converge at dev_merge
    graph.add_edge("frontend_dev", "dev_merge")
    graph.add_edge("backend_dev", "dev_merge")

    # After merge, check for errors and proceed to QA
    def route_after_dev_merge(state: dict) -> str:
        if state.get("error"):
            return "supervisor"
        return "qa_engineer"

    graph.add_conditional_edges(
        "dev_merge",
        route_after_dev_merge,
        {
            "qa_engineer": "qa_engineer",
            "supervisor": "supervisor",
        },
    )

    # QA can route to devops, retry devs (via Send), or supervisor
    def route_qa_with_retry(state: dict):
        """Route after QA with support for targeted developer retry."""
        result = route_after_qa(state)
        if result == "developers":
            # Use Send API to retry specific developers
            return route_to_retry_devs(state)
        return result

    graph.add_conditional_edges(
        "qa_engineer",
        route_qa_with_retry,
        {
            "devops_engineer": "devops_engineer",
            "supervisor": "supervisor",
        },
    )

    # DevOps routes to memory_persist for successful builds, or supervisor on error
    def route_devops_to_persist(state: dict) -> str:
        result = route_after_devops(state)
        if result == "__end__":
            return "memory_persist"
        return result

    graph.add_conditional_edges(
        "devops_engineer",
        route_devops_to_persist,
        {
            "memory_persist": "memory_persist",
            "supervisor": "supervisor",
        },
    )

    # Memory persist always goes to END
    graph.add_edge("memory_persist", END)

    # Supervisor routes back to the appropriate agent based on phase
    graph.add_edge("supervisor", END)  # For now, supervisor goes to end

    logger.info("Built agent graph with parallel developer execution")

    return graph


def compile_graph(
    config: LoomConfig | None = None,
    checkpointer: Any | None = None,
    interrupt_before: list[str] | None = None,
) -> Any:
    """Build and compile the agent graph.

    Args:
        config: Optional Loom configuration
        checkpointer: Optional LangGraph checkpointer (e.g., SqliteSaver)
            for state persistence. Required for interrupt support.
        interrupt_before: Optional list of node names to interrupt before.
            Used for interactive mode review gates. Requires checkpointer.

    Returns:
        Compiled graph ready for execution
    """
    graph = build_linear_graph(config)

    compile_kwargs: dict[str, Any] = {}

    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
        logger.info("Compiling graph with checkpointer enabled")

    if interrupt_before is not None:
        if checkpointer is None:
            logger.warning(
                "interrupt_before specified but no checkpointer provided. "
                "Interrupts require a checkpointer for state persistence."
            )
        compile_kwargs["interrupt_before"] = interrupt_before
        logger.info(f"Compiling graph with interrupts before: {interrupt_before}")

    compiled = graph.compile(**compile_kwargs)
    logger.info("Compiled agent graph")
    return compiled
