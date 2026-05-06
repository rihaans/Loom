"""Agent implementations for AgentForge."""

from agentforge.agents.architect import architect_node
from agentforge.agents.backend_dev import backend_dev_node
from agentforge.agents.base import (
    build_agent_chain,
    create_agent_for_role,
    get_format_instructions,
)
from agentforge.agents.devops_engineer import devops_engineer_node
from agentforge.agents.frontend_dev import frontend_dev_node
from agentforge.agents.product_manager import product_manager_node
from agentforge.agents.project_manager import (
    decide_next_phase,
    project_manager_node,
    route_to_agent,
)
from agentforge.agents.qa_engineer import qa_engineer_node

__all__ = [
    # Agent nodes
    "architect_node",
    "backend_dev_node",
    # Base utilities
    "build_agent_chain",
    "create_agent_for_role",
    # Routing
    "decide_next_phase",
    "devops_engineer_node",
    "frontend_dev_node",
    "get_format_instructions",
    "product_manager_node",
    "project_manager_node",
    "qa_engineer_node",
    "route_to_agent",
]
