"""LLM provider wrappers with consistent interface."""

import os
from typing import TYPE_CHECKING

from pydantic import SecretStr

from loom.config.models import LLMConfig

if TYPE_CHECKING:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.language_models import BaseChatModel


def create_anthropic_llm(
    config: LLMConfig, callbacks: list["BaseCallbackHandler"] | None = None
) -> "BaseChatModel":
    """Create an Anthropic Claude LLM instance.

    Args:
        config: LLM configuration
        callbacks: Optional list of callback handlers

    Returns:
        Configured ChatAnthropic instance

    Raises:
        ImportError: If langchain-anthropic not installed
        ValueError: If API key not found
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise ImportError(
            "langchain-anthropic not installed. Run: pip install langchain-anthropic"
        ) from e

    api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
            "or provide api_key in config."
        )

    return ChatAnthropic(  # type: ignore[call-arg]
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        api_key=SecretStr(api_key),
        callbacks=callbacks,
    )


def create_openai_llm(
    config: LLMConfig, callbacks: list["BaseCallbackHandler"] | None = None
) -> "BaseChatModel":
    """Create an OpenAI LLM instance.

    Args:
        config: LLM configuration
        callbacks: Optional list of callback handlers

    Returns:
        Configured ChatOpenAI instance

    Raises:
        ImportError: If langchain-openai not installed
        ValueError: If API key not found
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai not installed. Run: pip install langchain-openai"
        ) from e

    api_key = config.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
            "or provide api_key in config."
        )

    return ChatOpenAI(  # type: ignore[call-arg]
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        api_key=SecretStr(api_key),
        callbacks=callbacks,
    )


def create_ollama_llm(
    config: LLMConfig, callbacks: list["BaseCallbackHandler"] | None = None
) -> "BaseChatModel":
    """Create an Ollama LLM instance.

    Args:
        config: LLM configuration
        callbacks: Optional list of callback handlers

    Returns:
        Configured ChatOllama instance

    Raises:
        ImportError: If langchain-ollama not installed
    """
    try:
        from langchain_ollama import ChatOllama
    except ImportError as e:
        raise ImportError(
            "langchain-ollama not installed. Run: pip install langchain-ollama"
        ) from e

    base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    return ChatOllama(
        model=config.model,
        temperature=config.temperature,
        base_url=base_url,
        format="json",  # Critical for structured output with smaller models
        callbacks=callbacks,
    )


def create_llm(
    config: LLMConfig, callbacks: list["BaseCallbackHandler"] | None = None
) -> "BaseChatModel":
    """Create an LLM instance based on the provider in config.

    Args:
        config: LLM configuration with provider, model, etc.
        callbacks: Optional list of callback handlers

    Returns:
        Configured LangChain chat model

    Raises:
        ValueError: If provider is unknown
    """
    provider = config.provider

    if provider == "anthropic":
        return create_anthropic_llm(config, callbacks)
    elif provider == "openai":
        return create_openai_llm(config, callbacks)
    elif provider == "ollama":
        return create_ollama_llm(config, callbacks)
    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. Supported providers: anthropic, openai, ollama"
        )
