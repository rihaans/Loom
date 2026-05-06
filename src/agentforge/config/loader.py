"""Configuration loader with priority chain: CLI > env > toml > defaults."""

import os
from pathlib import Path
from typing import Any

import tomli_w

from agentforge.config.defaults import auto_detect_default
from agentforge.config.models import AgentForgeConfig, LLMConfig
from agentforge.state.enums import AgentRole

# Try to import tomllib (Python 3.11+) or tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]


CONFIG_FILENAME = "agentforge.toml"
USER_CONFIG_DIR = Path.home() / ".agentforge"


def find_config_file() -> Path | None:
    """Find the config file in order of precedence.

    Search order:
    1. Current directory: ./agentforge.toml
    2. User config: ~/.agentforge/config.toml
    3. None if not found

    Returns:
        Path to config file or None
    """
    # Check current directory
    local_config = Path.cwd() / CONFIG_FILENAME
    if local_config.exists():
        return local_config

    # Check user config directory
    user_config = USER_CONFIG_DIR / "config.toml"
    if user_config.exists():
        return user_config

    return None


def load_toml_config(path: Path) -> dict[str, Any]:
    """Load configuration from a TOML file.

    Args:
        path: Path to the TOML file

    Returns:
        Parsed configuration dictionary
    """
    with open(path, "rb") as f:
        return tomllib.load(f)


def parse_llm_string(llm_str: str) -> LLMConfig:
    """Parse an LLM string in format 'provider:model'.

    Examples:
        - "anthropic:claude-sonnet-4-5"
        - "openai:gpt-4o"
        - "ollama:qwen2.5-coder:7b"

    Args:
        llm_str: String in provider:model format

    Returns:
        Parsed LLMConfig

    Raises:
        ValueError: If format is invalid
    """
    if ":" not in llm_str:
        raise ValueError(
            f"Invalid LLM string format: '{llm_str}'. Expected 'provider:model' "
            f"(e.g., 'anthropic:claude-sonnet-4-5')"
        )

    parts = llm_str.split(":", 1)
    provider = parts[0].lower()
    model = parts[1]

    if provider not in ("anthropic", "openai", "ollama"):
        raise ValueError(f"Unknown provider: '{provider}'. Use anthropic, openai, or ollama.")

    return LLMConfig(provider=provider, model=model)  # type: ignore[arg-type]


def load_env_config() -> dict[str, Any]:
    """Load configuration from environment variables.

    Environment variable mapping:
    - AGENTFORGE_LLM_DEFAULT: default LLM (provider:model)
    - AGENTFORGE_LLM_<ROLE>: per-agent LLM override
    - AGENTFORGE_OUTPUT_DIR: output directory
    - AGENTFORGE_MAX_RETRIES: max QA retries
    - AGENTFORGE_USE_DOCKER_SANDBOX: true/false
    - AGENTFORGE_SANDBOX_TIMEOUT: timeout in seconds
    - AGENTFORGE_SANDBOX_MEMORY_MB: memory limit in MB

    Returns:
        Configuration dictionary from environment
    """
    config: dict[str, Any] = {}

    # Default LLM
    if llm_default := os.getenv("AGENTFORGE_LLM_DEFAULT"):
        config["llm_default"] = parse_llm_string(llm_default)

    # Per-agent LLM overrides
    llm_overrides: dict[AgentRole, LLMConfig] = {}
    role_env_map = {
        "PRODUCT_MANAGER": AgentRole.PRODUCT_MANAGER,
        "ARCHITECT": AgentRole.ARCHITECT,
        "FRONTEND": AgentRole.FRONTEND_DEV,
        "BACKEND": AgentRole.BACKEND_DEV,
        "QA": AgentRole.QA,
        "DEVOPS": AgentRole.DEVOPS,
    }
    for env_suffix, role in role_env_map.items():
        if llm_str := os.getenv(f"AGENTFORGE_LLM_{env_suffix}"):
            llm_overrides[role] = parse_llm_string(llm_str)

    if llm_overrides:
        config["llm_overrides"] = llm_overrides

    # Output directory
    if output_dir := os.getenv("AGENTFORGE_OUTPUT_DIR"):
        config["output_dir"] = output_dir

    # Max retries
    if max_retries := os.getenv("AGENTFORGE_MAX_RETRIES"):
        config["max_retries"] = int(max_retries)

    # Sandbox settings
    if use_docker := os.getenv("AGENTFORGE_USE_DOCKER_SANDBOX"):
        config["use_docker_sandbox"] = use_docker.lower() in ("true", "1", "yes")

    if timeout := os.getenv("AGENTFORGE_SANDBOX_TIMEOUT"):
        config["sandbox_timeout_seconds"] = int(timeout)

    if memory := os.getenv("AGENTFORGE_SANDBOX_MEMORY_MB"):
        config["sandbox_memory_mb"] = int(memory)

    # Cost budget
    if budget := os.getenv("AGENTFORGE_COST_BUDGET_USD"):
        config["cost_budget_usd"] = float(budget)

    return config


def load_config(
    cli_overrides: dict[str, Any] | None = None,
    auto_detect_llm: bool = True,
) -> AgentForgeConfig:
    """Load configuration with priority chain.

    Priority (highest first):
    1. CLI overrides (passed as argument)
    2. Environment variables (AGENTFORGE_*)
    3. TOML config file (agentforge.toml)
    4. Defaults (auto-detected or hardcoded)

    Args:
        cli_overrides: Configuration from CLI flags
        auto_detect_llm: Whether to auto-detect best LLM if none configured

    Returns:
        Merged AgentForgeConfig
    """
    # Start with defaults
    if auto_detect_llm:
        default_llm = auto_detect_default()
    else:
        default_llm = LLMConfig()  # Hardcoded defaults

    config_dict: dict[str, Any] = {"llm_default": default_llm}

    # Load TOML config if exists
    config_file = find_config_file()
    if config_file:
        toml_config = load_toml_config(config_file)

        # Parse llm.default section
        if llm_section := toml_config.get("llm", {}).get("default"):
            config_dict["llm_default"] = LLMConfig(**llm_section)

        # Parse per-agent overrides
        llm_overrides: dict[AgentRole, LLMConfig] = {}
        for role in AgentRole:
            role_key = role.value  # e.g., "product_manager"
            if role_config := toml_config.get("llm", {}).get(role_key):
                llm_overrides[role] = LLMConfig(**role_config)
        if llm_overrides:
            config_dict["llm_overrides"] = llm_overrides

        # Parse build section
        if build_section := toml_config.get("build"):
            for key in ("output_dir", "max_retries", "interactive", "use_llm_supervisor"):
                if key in build_section:
                    config_dict[key] = build_section[key]

        # Parse sandbox section
        if sandbox_section := toml_config.get("sandbox"):
            if "use_docker" in sandbox_section:
                config_dict["use_docker_sandbox"] = sandbox_section["use_docker"]
            if "timeout_seconds" in sandbox_section:
                config_dict["sandbox_timeout_seconds"] = sandbox_section["timeout_seconds"]
            if "memory_mb" in sandbox_section:
                config_dict["sandbox_memory_mb"] = sandbox_section["memory_mb"]

        # Parse observability section
        if obs_section := toml_config.get("observability"):
            for key in ("enable_langsmith", "log_level"):
                if key in obs_section:
                    config_dict[key] = obs_section[key]

        # Parse cost section
        if cost_section := toml_config.get("cost"):
            if "budget_usd" in cost_section:
                config_dict["cost_budget_usd"] = cost_section["budget_usd"]
            if "warn_threshold_usd" in cost_section:
                config_dict["cost_warn_threshold_usd"] = cost_section["warn_threshold_usd"]

    # Merge environment config (overrides TOML)
    env_config = load_env_config()
    config_dict.update(env_config)

    # Merge CLI overrides (highest priority)
    if cli_overrides:
        config_dict.update(cli_overrides)

    return AgentForgeConfig(**config_dict)


def save_config(config: AgentForgeConfig, path: Path | None = None) -> Path:
    """Save configuration to a TOML file.

    Args:
        config: Configuration to save
        path: Path to save to (defaults to ./agentforge.toml)

    Returns:
        Path where config was saved
    """
    if path is None:
        path = Path.cwd() / CONFIG_FILENAME

    # Convert to TOML-friendly structure
    toml_dict: dict[str, Any] = {
        "llm": {
            "default": {
                "provider": config.llm_default.provider,
                "model": config.llm_default.model,
                "temperature": config.llm_default.temperature,
                "max_tokens": config.llm_default.max_tokens,
            }
        },
        "build": {
            "output_dir": config.output_dir,
            "max_retries": config.max_retries,
            "interactive": config.interactive,
            "use_llm_supervisor": config.use_llm_supervisor,
        },
        "sandbox": {
            "use_docker": config.use_docker_sandbox,
            "timeout_seconds": config.sandbox_timeout_seconds,
            "memory_mb": config.sandbox_memory_mb,
        },
        "observability": {
            "enable_langsmith": config.enable_langsmith,
            "log_level": config.log_level,
        },
        "cost": {
            "warn_threshold_usd": config.cost_warn_threshold_usd,
        },
    }

    # Add per-agent overrides
    for role, llm_config in config.llm_overrides.items():
        toml_dict["llm"][role.value] = {
            "provider": llm_config.provider,
            "model": llm_config.model,
            "temperature": llm_config.temperature,
            "max_tokens": llm_config.max_tokens,
        }

    # Add cost budget if set
    if config.cost_budget_usd is not None:
        toml_dict["cost"]["budget_usd"] = config.cost_budget_usd

    with open(path, "wb") as f:
        tomli_w.dump(toml_dict, f)

    return path
