"""Base agent factory and utilities."""

import logging
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel

from loom.config import LoomConfig
from loom.llm import get_llm_for_role
from loom.state.enums import AgentRole

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def build_agent_chain(
    system_prompt: str,
    human_template: str,
    output_model: type[T],
    llm: BaseChatModel,
    include_history: bool = False,
) -> tuple[Any, PydanticOutputParser[T]]:
    """Build a LangChain chain for an agent.

    Args:
        system_prompt: The system prompt for the agent
        human_template: The human message template with placeholders
        output_model: Pydantic model class for structured output
        llm: The language model to use
        include_history: Whether to include message history placeholder

    Returns:
        Tuple of (chain, parser) where chain can be invoked and parser
        can be used to parse outputs or get format instructions
    """
    # Create the output parser
    parser = PydanticOutputParser(pydantic_object=output_model)

    # Build message list
    messages: list[Any] = [("system", system_prompt)]

    if include_history:
        messages.append(MessagesPlaceholder("history", optional=True))

    # Append format instructions to human template
    human_with_format = f"{human_template}\n\n{{format_instructions}}"
    messages.append(("human", human_with_format))

    # Create prompt template
    prompt = ChatPromptTemplate.from_messages(messages)

    # Build the chain
    chain = prompt | llm | parser

    return chain, parser


def get_format_instructions(output_model: type[T]) -> str:
    """Get format instructions for a Pydantic model.

    Args:
        output_model: The Pydantic model class

    Returns:
        Format instructions string
    """
    parser = PydanticOutputParser(pydantic_object=output_model)
    return parser.get_format_instructions()


def create_agent_for_role(
    role: AgentRole,
    system_prompt: str,
    human_template: str,
    output_model: type[T],
    config: LoomConfig,
    include_history: bool = False,
) -> tuple[Any, PydanticOutputParser[T], BaseChatModel]:
    """Create a complete agent chain for a specific role.

    Args:
        role: The agent role (determines which LLM config to use)
        system_prompt: The system prompt for the agent
        human_template: The human message template
        output_model: Pydantic model for structured output
        config: The Loom configuration
        include_history: Whether to include message history

    Returns:
        Tuple of (chain, parser, llm)
    """
    llm = get_llm_for_role(role, config)
    chain, parser = build_agent_chain(
        system_prompt=system_prompt,
        human_template=human_template,
        output_model=output_model,
        llm=llm,
        include_history=include_history,
    )
    return chain, parser, llm
