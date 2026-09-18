"""Preflight checks for LLM provider reachability.

A build that starts without a usable provider fails deep inside the graph with
a generic transport error ("All connection attempts failed"), which tells the
user nothing about what to fix. These checks run *before* the graph is
compiled so the failure is reported once, in terms of the thing to change.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

from loom.config.defaults import ENV_KEYS
from loom.config.models import LLMConfig

OLLAMA_DEFAULT_HOST = "http://localhost:11434"


class ProviderUnavailableError(RuntimeError):
    """Raised when the configured LLM provider cannot be used.

    The message is written for a human about to run a build, not for a log.
    """


def ollama_host() -> str:
    """Resolve the Ollama host the same way the provider factory does."""
    return os.getenv("OLLAMA_HOST", OLLAMA_DEFAULT_HOST)


def is_ollama_running(timeout: float = 1.5) -> bool:
    """Check whether an Ollama server answers on the configured host."""
    try:
        with urllib.request.urlopen(f"{ollama_host()}/api/tags", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def check_provider(llm: LLMConfig) -> None:
    """Verify the configured provider is usable, or raise with how to fix it.

    Args:
        llm: The resolved default LLM configuration for this run.

    Raises:
        ProviderUnavailableError: With actionable guidance when unusable.
    """
    provider = llm.provider

    if provider in ENV_KEYS:
        if not os.getenv(ENV_KEYS[provider]):
            raise ProviderUnavailableError(
                f"No API key for provider '{provider}'.\n"
                f"  Set {ENV_KEYS[provider]} in your environment, or pick another\n"
                f"  provider with --model (e.g. --model ollama:llama3.1:8b).\n"
                f"  Run `loom doctor` to see everything Loom can find."
            )
        return

    if provider == "ollama":
        if not is_ollama_running():
            raise ProviderUnavailableError(
                f"No LLM provider is reachable.\n"
                f"  Loom fell back to Ollama, but nothing is listening at {ollama_host()}.\n"
                f"  Either start Ollama (`ollama serve`, then `ollama pull {llm.model}`),\n"
                f"  or set ANTHROPIC_API_KEY / OPENAI_API_KEY to use a hosted model.\n"
                f"  Run `loom doctor` to see everything Loom can find."
            )
        return

    # Unknown providers are left to the factory, which raises its own error.
