"""Graph builder for wiring agent nodes.

Creates the LangGraph state machine with all agent nodes and routing.
"""

import logging
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.types import Command

from loom.agents import (
    architect_node,
    backend_dev_node,
    code_reviewer_node,
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
    route_after_architect_chat,
    route_after_devops,
    route_after_pm,
    route_after_pm_chat,
    route_after_qa,
)
from loom.state.models import LoomGraphState

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
    # Create graph with the LoomGraphState TypedDict schema. This gives each
    # field its own channel with the right reducer (e.g. agent_messages uses
    # merge_messages_dict to append per-agent history). Required for the
    # chat-mode loop: aupdate_state(values) only merges correctly when the
    # graph schema declares per-field channels.
    graph = StateGraph(LoomGraphState)

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

    async def reviewer_node(state: dict) -> Command:
        # Returns a Command for a dynamic handoff (approve -> QA, or revise -> devs).
        return await code_reviewer_node(state, config)

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
    graph.add_node("code_reviewer", reviewer_node)
    graph.add_node("qa_engineer", qa_node)
    graph.add_node("devops_engineer", devops_node)
    graph.add_node("memory_persist", mem_persist_node)

    # Set entry point
    graph.set_entry_point("product_manager")

    # ------------------------------------------------------------------
    # Conversational nodes self-loop in chat mode.
    # In legacy mode (interactive=False) the routing is unchanged: PM
    # produces a PRD in one shot, then proceeds to memory_retrieve.
    # In chat mode (interactive=True) PM and Architect can return
    # agent_status in {wait_for_input, ready_to_draft}, which routes
    # back to the same node so the chat loop can supply the next turn.
    # When compiled with interrupt_after=["product_manager", "architect"],
    # the graph pauses after each turn and the chat REPL drives resumes.
    # ------------------------------------------------------------------
    def route_pm_dispatch(state: dict) -> str:
        if state.get("interactive"):
            return route_after_pm_chat(state)
        return route_after_pm(state)

    graph.add_conditional_edges(
        "product_manager",
        route_pm_dispatch,
        {
            "product_manager": "product_manager",  # chat self-loop
            "architect": "memory_retrieve",  # route to memory_retrieve first
            "supervisor": "supervisor",
        },
    )

    # Memory retrieve always goes to architect
    graph.add_edge("memory_retrieve", "architect")

    # Architect routes to parallel developers via Send API or supervisor on error
    def route_architect_to_devs(state: dict) -> Any:
        """Route from architect to developers (or self-loop in chat mode)."""
        if state.get("error"):
            return "supervisor"
        if state.get("interactive"):
            decision = route_after_architect_chat(state)
            if decision == "architect":
                return "architect"  # self-loop for chat
            if decision == "supervisor":
                return "supervisor"
            # decision == "developers" → fan-out via Send
            return route_to_devs(state)
        # Legacy path: always fan out to devs
        return route_to_devs(state)

    graph.add_conditional_edges(
        "architect",
        route_architect_to_devs,
    )

    # Both developers converge at dev_merge
    graph.add_edge("frontend_dev", "dev_merge")
    graph.add_edge("backend_dev", "dev_merge")

    # After merge, check for errors and proceed to the Code Reviewer (the critic
    # in the generator-critic loop). The reviewer then dynamically hands off via a
    # Command — approve → QA, or request revisions → back to the targeted dev(s).
    def route_after_dev_merge(state: dict) -> str:
        if state.get("error"):
            return "supervisor"
        return "code_reviewer"

    graph.add_conditional_edges(
        "dev_merge",
        route_after_dev_merge,
        {
            "code_reviewer": "code_reviewer",
            "supervisor": "supervisor",
        },
    )

    # QA can route to devops, retry devs (via Send), or supervisor
    def route_qa_with_retry(state: dict) -> Any:
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

    # The supervisor is the error-terminal sink: every node's failure path routes
    # here (see route_* functions). It records the failure (phase=FAILED) and ends,
    # so a broken run terminates cleanly with a clear final state rather than
    # half-completing downstream nodes.
    graph.add_edge("supervisor", END)

    logger.info("Built agent graph with parallel developer execution")

    return graph


def compile_graph(
    config: LoomConfig | None = None,
    checkpointer: Any | None = None,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
    interactive: bool = False,
) -> Any:
    """Build and compile the agent graph.

    Args:
        config: Optional Loom configuration
        checkpointer: Optional LangGraph checkpointer (e.g., SqliteSaver)
            for state persistence. Required for interrupt support.
        interrupt_before: Optional list of node names to interrupt before.
            Used for legacy review gates. Requires checkpointer.
        interrupt_after: Optional list of node names to interrupt after.
            Used by the chat REPL to pause on each conversational turn.
        interactive: If True, automatically interrupt after the
            conversational nodes (product_manager, architect) so the
            chat loop can drive turn-by-turn execution.

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

    # In chat mode, default to interrupting after the conversational nodes
    # so the chat REPL can collect user input before each next turn.
    if interactive and interrupt_after is None:
        interrupt_after = ["product_manager", "architect"]

    if interrupt_after is not None:
        if checkpointer is None:
            logger.warning(
                "interrupt_after specified but no checkpointer provided. "
                "Interrupts require a checkpointer for state persistence."
            )
        compile_kwargs["interrupt_after"] = interrupt_after
        logger.info(f"Compiling graph with interrupts after: {interrupt_after}")

    compiled = graph.compile(**compile_kwargs)
    logger.info("Compiled agent graph")
    return compiled
