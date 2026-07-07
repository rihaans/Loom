"""Agent implementations for Loom."""

from loom.agents.architect import architect_node
from loom.agents.backend_dev import backend_dev_node
from loom.agents.base import (
    build_agent_chain,
    build_revision_feedback,
    create_agent_for_role,
    get_format_instructions,
)
from loom.agents.devops_engineer import devops_engineer_node
from loom.agents.frontend_dev import frontend_dev_node
from loom.agents.memory_persist import memory_persist_node
from loom.agents.memory_retrieve import memory_retrieve_node
from loom.agents.product_manager import product_manager_node
from loom.agents.project_manager import (
    decide_next_phase,
    project_manager_node,
    route_to_agent,
)
from loom.agents.qa_engineer import qa_engineer_node
from loom.agents.reviewer import code_reviewer_node

__all__ = [
    # Agent nodes
    "architect_node",
    "backend_dev_node",
    # Base utilities
    "build_agent_chain",
    "build_revision_feedback",
    "code_reviewer_node",
    "create_agent_for_role",
    # Routing
    "decide_next_phase",
    "devops_engineer_node",
    "frontend_dev_node",
    "get_format_instructions",
    # Memory nodes
    "memory_persist_node",
    "memory_retrieve_node",
    "product_manager_node",
    "project_manager_node",
    "qa_engineer_node",
    "route_to_agent",
]
