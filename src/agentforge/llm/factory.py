"""LLM factory for creating configured LLMs per agent role."""

from typing import TYPE_CHECKING

from agentforge.config.models import AgentForgeConfig
from agentforge.llm.providers import create_llm
from agentforge.state.enums import AgentRole

if TYPE_CHECKING:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.language_models import BaseChatModel


def get_llm_for_role(
    role: AgentRole,
    config: AgentForgeConfig,
    callbacks: list["BaseCallbackHandler"] | None = None,
) -> "BaseChatModel":
    """Get a configured LLM for a specific agent role.

    Uses per-role overrides if configured, otherwise falls back to default.

    Args:
        role: The agent role requesting an LLM
        config: AgentForge configuration
        callbacks: Optional list of callback handlers

    Returns:
        Configured LangChain chat model for the role

    Example:
        >>> config = AgentForgeConfig()
        >>> llm = get_llm_for_role(AgentRole.ARCHITECT, config)
        >>> response = llm.invoke("Design a system...")
    """
    llm_config = config.get_llm_config(role)
    return create_llm(llm_config, callbacks)


def get_llm(
    config: AgentForgeConfig, callbacks: list["BaseCallbackHandler"] | None = None
) -> "BaseChatModel":
    """Get the default configured LLM.

    Args:
        config: AgentForge configuration
        callbacks: Optional list of callback handlers

    Returns:
        Configured LangChain chat model using default settings
    """
    return create_llm(config.llm_default, callbacks)


# Role-specific temperature recommendations
RECOMMENDED_TEMPERATURES = {
    AgentRole.PRODUCT_MANAGER: 0.3,  # Slight creativity for PRD writing
    AgentRole.ARCHITECT: 0.2,  # More deterministic
    AgentRole.FRONTEND_DEV: 0.2,
    AgentRole.BACKEND_DEV: 0.2,
    AgentRole.QA: 0.0,  # Fully deterministic
    AgentRole.DEVOPS: 0.0,  # Fully deterministic
    AgentRole.SUPERVISOR: 0.0,  # Deterministic routing
}
