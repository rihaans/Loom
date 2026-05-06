"""Graph builder for wiring agent nodes.

Creates the LangGraph state machine with all agent nodes and routing.
"""

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from agentforge.agents import (
    architect_node,
    backend_dev_node,
    devops_engineer_node,
    frontend_dev_node,
    product_manager_node,
    project_manager_node,
    qa_engineer_node,
)
from agentforge.config import AgentForgeConfig
from agentforge.graph.routing import (
    route_after_architect,
    route_after_devops,
    route_after_devs,
    route_after_pm,
    route_after_qa,
)

logger = logging.getLogger(__name__)


async def _developers_node(state: dict[str, Any], config: AgentForgeConfig | None = None) -> dict[str, Any]:
    """Combined developers node that runs frontend and backend in sequence.

    In Phase 5, this will be replaced with parallel execution using Send API.

    Args:
        state: Current graph state
        config: Optional configuration

    Returns:
        Combined state update from both developers
    """
    # Run frontend dev first
    frontend_result = await frontend_dev_node(state, config)

    # Merge frontend results into state for backend
    merged_state = {**state, **frontend_result}

    # Run backend dev
    backend_result = await backend_dev_node(merged_state, config)

    # Combine results
    combined_code_files = {}
    if "code_files" in frontend_result:
        combined_code_files.update(frontend_result["code_files"])
    if "code_files" in backend_result:
        combined_code_files.update(backend_result["code_files"])

    combined_events = []
    if "events" in frontend_result:
        combined_events.extend(frontend_result["events"])
    if "events" in backend_result:
        combined_events.extend(backend_result["events"])

    combined_costs = []
    if "costs" in frontend_result:
        combined_costs.extend(frontend_result["costs"])
    if "costs" in backend_result:
        combined_costs.extend(backend_result["costs"])

    # Check for errors
    error = frontend_result.get("error") or backend_result.get("error")

    result = {
        "code_files": combined_code_files,
        "events": combined_events,
        "costs": combined_costs,
    }

    if error:
        result["error"] = error

    return result


def build_linear_graph(config: AgentForgeConfig | None = None) -> StateGraph:
    """Build a linear agent graph with all nodes wired in sequence.

    The graph follows this flow:
    1. supervisor -> determines phase
    2. product_manager -> generates PRD
    3. architect -> generates architecture
    4. developers (frontend + backend) -> generates code
    5. qa_engineer -> runs tests
    6. devops_engineer -> generates DevOps configs
    7. END

    Conditional routing handles:
    - Retrying development if tests fail
    - Stopping on errors

    Args:
        config: Optional AgentForge configuration

    Returns:
        Compiled StateGraph ready for execution
    """
    # Create graph with AgentState schema
    # Using dict for state since LangGraph works with dicts
    graph = StateGraph(dict)

    # Wrap nodes to inject config
    async def pm_node(state: dict) -> dict:
        return await product_manager_node(state, config)

    async def arch_node(state: dict) -> dict:
        return await architect_node(state, config)

    async def devs_node(state: dict) -> dict:
        return await _developers_node(state, config)

    async def qa_node(state: dict) -> dict:
        return await qa_engineer_node(state, config)

    async def devops_node(state: dict) -> dict:
        return await devops_engineer_node(state, config)

    def supervisor_node(state: dict) -> dict:
        return project_manager_node(state)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("product_manager", pm_node)
    graph.add_node("architect", arch_node)
    graph.add_node("developers", devs_node)
    graph.add_node("qa_engineer", qa_node)
    graph.add_node("devops_engineer", devops_node)

    # Set entry point
    graph.set_entry_point("product_manager")

    # Add conditional edges
    graph.add_conditional_edges(
        "product_manager",
        route_after_pm,
        {
            "architect": "architect",
            "supervisor": "supervisor",
        },
    )

    graph.add_conditional_edges(
        "architect",
        route_after_architect,
        {
            "developers": "developers",
            "supervisor": "supervisor",
        },
    )

    graph.add_conditional_edges(
        "developers",
        route_after_devs,
        {
            "qa_engineer": "qa_engineer",
            "supervisor": "supervisor",
        },
    )

    graph.add_conditional_edges(
        "qa_engineer",
        route_after_qa,
        {
            "devops_engineer": "devops_engineer",
            "developers": "developers",
            "supervisor": "supervisor",
        },
    )

    graph.add_conditional_edges(
        "devops_engineer",
        route_after_devops,
        {
            "__end__": END,
            "supervisor": "supervisor",
        },
    )

    # Supervisor routes back to the appropriate agent based on phase
    graph.add_edge("supervisor", END)  # For now, supervisor goes to end

    logger.info("Built linear agent graph")

    return graph


def compile_graph(config: AgentForgeConfig | None = None) -> Any:
    """Build and compile the agent graph.

    Args:
        config: Optional AgentForge configuration

    Returns:
        Compiled graph ready for execution
    """
    graph = build_linear_graph(config)
    compiled = graph.compile()
    logger.info("Compiled agent graph")
    return compiled
