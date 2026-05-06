"""Default configuration and auto-detection logic."""

import os

from agentforge.config.models import LLMConfig

# Default LLM settings for each provider
PROVIDER_DEFAULTS = {
    "anthropic": LLMConfig(
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.2,
        max_tokens=8192,
    ),
    "openai": LLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=4096,
    ),
    "ollama": LLMConfig(
        provider="ollama",
        model="qwen2.5-coder:7b",
        temperature=0.0,  # Lower for local models
        max_tokens=2048,
    ),
}

# Environment variable names for API keys
ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def detect_available_provider() -> str:
    """Detect the best available LLM provider from environment.

    Priority order:
    1. Anthropic (best quality for code generation)
    2. OpenAI (widely available)
    3. Ollama (always available if installed)

    Returns:
        Provider name: "anthropic", "openai", or "ollama"
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "ollama"


def auto_detect_default() -> LLMConfig:
    """Automatically detect and return the best available LLM config.

    If user provides no config, pick best available based on environment.

    Returns:
        LLMConfig for the best available provider
    """
    provider = detect_available_provider()
    return PROVIDER_DEFAULTS[provider]


def get_default_config() -> LLMConfig:
    """Get the hardcoded default config (Ollama with qwen2.5-coder:7b).

    This is used when no auto-detection is desired.

    Returns:
        Default Ollama LLMConfig
    """
    return LLMConfig(
        provider="ollama",
        model="qwen2.5-coder:7b",
        temperature=0.0,
        max_tokens=2048,
    )
