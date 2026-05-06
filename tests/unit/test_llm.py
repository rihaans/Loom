"""Unit tests for LLM layer."""

from unittest.mock import MagicMock, patch

import pytest

from agentforge.config import (
    AgentForgeConfig,
    LLMConfig,
    auto_detect_default,
    load_config,
    parse_llm_string,
)
from agentforge.llm import (
    MaxRetriesExceededError,
    ParseError,
    calculate_cost,
    create_parse_error_feedback,
    estimate_build_cost,
    format_cost,
    get_llm_for_role,
    get_pricing,
)
from agentforge.state.enums import AgentRole


class TestAutoDetect:
    """Test auto-detection of LLM providers."""

    def test_detect_anthropic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that Anthropic is detected when API key is set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        config = auto_detect_default()
        assert config.provider == "anthropic"

    def test_detect_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that OpenAI is detected when API key is set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        config = auto_detect_default()
        assert config.provider == "openai"

    def test_detect_ollama_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that Ollama is used as fallback."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        config = auto_detect_default()
        assert config.provider == "ollama"


class TestParseLLMString:
    """Test LLM string parsing."""

    def test_parse_anthropic(self) -> None:
        """Test parsing Anthropic LLM string."""
        config = parse_llm_string("anthropic:claude-sonnet-4-5")
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-5"

    def test_parse_openai(self) -> None:
        """Test parsing OpenAI LLM string."""
        config = parse_llm_string("openai:gpt-4o")
        assert config.provider == "openai"
        assert config.model == "gpt-4o"

    def test_parse_ollama_with_tag(self) -> None:
        """Test parsing Ollama LLM string with model tag."""
        config = parse_llm_string("ollama:qwen2.5-coder:7b")
        assert config.provider == "ollama"
        assert config.model == "qwen2.5-coder:7b"

    def test_invalid_format_no_colon(self) -> None:
        """Test that missing colon raises error."""
        with pytest.raises(ValueError, match="Invalid LLM string format"):
            parse_llm_string("anthropic-claude")

    def test_invalid_provider(self) -> None:
        """Test that unknown provider raises error."""
        with pytest.raises(ValueError, match="Unknown provider"):
            parse_llm_string("deepseek:v3")


class TestLoadConfig:
    """Test configuration loading."""

    def test_load_default_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading default config without any overrides."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AGENTFORGE_LLM_DEFAULT", raising=False)

        config = load_config(auto_detect_llm=False)
        assert config.llm_default.provider == "ollama"

    def test_load_with_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that environment variables override defaults."""
        monkeypatch.setenv("AGENTFORGE_LLM_DEFAULT", "openai:gpt-4o-mini")
        monkeypatch.setenv("AGENTFORGE_OUTPUT_DIR", "/custom/output")
        monkeypatch.setenv("AGENTFORGE_MAX_RETRIES", "5")

        config = load_config(auto_detect_llm=False)
        assert config.llm_default.provider == "openai"
        assert config.llm_default.model == "gpt-4o-mini"
        assert config.output_dir == "/custom/output"
        assert config.max_retries == 5

    def test_load_with_cli_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that CLI overrides take highest priority."""
        monkeypatch.setenv("AGENTFORGE_OUTPUT_DIR", "/env/output")

        cli_overrides = {"output_dir": "/cli/output"}
        config = load_config(cli_overrides=cli_overrides, auto_detect_llm=False)

        assert config.output_dir == "/cli/output"

    def test_load_per_agent_llm_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test per-agent LLM override from environment."""
        monkeypatch.setenv("AGENTFORGE_LLM_DEVOPS", "anthropic:claude-haiku-3-5")

        config = load_config(auto_detect_llm=False)
        devops_config = config.get_llm_config(AgentRole.DEVOPS)

        assert devops_config.provider == "anthropic"
        assert devops_config.model == "claude-haiku-3-5"

        # Other roles should use default
        pm_config = config.get_llm_config(AgentRole.PRODUCT_MANAGER)
        assert pm_config.provider == "ollama"


class TestCostCalculation:
    """Test cost calculation functions."""

    def test_anthropic_sonnet_pricing(self) -> None:
        """Test Anthropic Claude Sonnet pricing."""
        pricing = get_pricing("anthropic", "claude-sonnet-4-5")
        assert pricing is not None
        assert pricing.input_per_million == 3.00
        assert pricing.output_per_million == 15.00

    def test_openai_gpt4o_mini_pricing(self) -> None:
        """Test OpenAI GPT-4o-mini pricing."""
        pricing = get_pricing("openai", "gpt-4o-mini")
        assert pricing is not None
        assert pricing.input_per_million == 0.15
        assert pricing.output_per_million == 0.60

    def test_ollama_pricing_is_free(self) -> None:
        """Test that Ollama pricing returns None (free)."""
        pricing = get_pricing("ollama", "qwen2.5-coder:7b")
        assert pricing is None

    def test_calculate_anthropic_cost(self) -> None:
        """Test calculating Anthropic cost."""
        # 10k input, 5k output tokens
        cost = calculate_cost("anthropic", "claude-sonnet-4-5", 10_000, 5_000)
        # 10k * 3.00/1M + 5k * 15.00/1M = 0.03 + 0.075 = 0.105
        assert abs(cost - 0.105) < 0.001

    def test_calculate_openai_cost(self) -> None:
        """Test calculating OpenAI cost."""
        # 50k input, 20k output tokens
        cost = calculate_cost("openai", "gpt-4o-mini", 50_000, 20_000)
        # 50k * 0.15/1M + 20k * 0.60/1M = 0.0075 + 0.012 = 0.0195
        assert abs(cost - 0.0195) < 0.001

    def test_calculate_ollama_cost_is_zero(self) -> None:
        """Test that Ollama cost is always zero."""
        cost = calculate_cost("ollama", "qwen2.5-coder:7b", 100_000, 50_000)
        assert cost == 0.0

    def test_calculate_unknown_model_is_zero(self) -> None:
        """Test that unknown model returns zero cost."""
        cost = calculate_cost("anthropic", "unknown-model-xyz", 10_000, 5_000)
        assert cost == 0.0


class TestFormatCost:
    """Test cost formatting."""

    def test_format_small_cost(self) -> None:
        """Test formatting cost less than $0.01."""
        assert format_cost(0.005) == "<$0.01"

    def test_format_medium_cost(self) -> None:
        """Test formatting cost between $0.01 and $1."""
        assert format_cost(0.05) == "$0.05"
        assert format_cost(0.99) == "$0.99"

    def test_format_large_cost(self) -> None:
        """Test formatting cost over $1."""
        assert format_cost(1.50) == "$1.50"
        assert format_cost(10.00) == "$10.00"


class TestEstimateBuildCost:
    """Test build cost estimation."""

    def test_estimate_anthropic_simple_build(self) -> None:
        """Test estimating simple build with Anthropic."""
        cost = estimate_build_cost("anthropic", "claude-sonnet-4-5", 80_000)
        # 32k input (40%) + 48k output (60%)
        # 32k * 3.00/1M + 48k * 15.00/1M = 0.096 + 0.72 = 0.816
        assert 0.5 < cost < 1.0

    def test_estimate_ollama_is_free(self) -> None:
        """Test that Ollama builds are free."""
        cost = estimate_build_cost("ollama", "qwen2.5-coder:7b", 200_000)
        assert cost == 0.0


class TestRetryLogic:
    """Test retry logic helpers."""

    def test_parse_error_feedback(self) -> None:
        """Test creating parse error feedback message."""
        raw_output = '{"invalid json'
        error_message = "Expecting property name"

        feedback = create_parse_error_feedback(raw_output, error_message)

        assert "could not be parsed" in feedback
        assert error_message in feedback
        assert raw_output in feedback

    def test_parse_error_truncates_long_output(self) -> None:
        """Test that long outputs are truncated in feedback."""
        raw_output = "x" * 1000
        feedback = create_parse_error_feedback(raw_output, "error")

        assert "..." in feedback
        assert len(feedback) < 1500


class TestGetLLMForRole:
    """Test LLM factory function."""

    def test_get_llm_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that get_llm_for_role uses default when no override."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        config = AgentForgeConfig()

        # Mock the create_llm function to avoid actual LLM creation
        with patch("agentforge.llm.factory.create_llm") as mock_create:
            mock_llm = MagicMock()
            mock_create.return_value = mock_llm

            result = get_llm_for_role(AgentRole.ARCHITECT, config)

            assert result == mock_llm
            mock_create.assert_called_once()
            call_args = mock_create.call_args[0][0]
            assert call_args.provider == "ollama"

    def test_get_llm_uses_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that get_llm_for_role uses per-role override."""
        config = AgentForgeConfig(
            llm_overrides={AgentRole.DEVOPS: LLMConfig(provider="openai", model="gpt-4o-mini")}
        )

        with patch("agentforge.llm.factory.create_llm") as mock_create:
            mock_llm = MagicMock()
            mock_create.return_value = mock_llm

            get_llm_for_role(AgentRole.DEVOPS, config)

            call_args = mock_create.call_args[0][0]
            assert call_args.provider == "openai"
            assert call_args.model == "gpt-4o-mini"


class TestParseError:
    """Test ParseError exception."""

    def test_parse_error_stores_raw_output(self) -> None:
        """Test that ParseError stores raw output."""
        raw = '{"bad": json}'
        error = ParseError("Invalid JSON", raw)

        assert error.raw_output == raw
        assert "Invalid JSON" in str(error)


class TestMaxRetriesExceededError:
    """Test MaxRetriesExceededError exception."""

    def test_stores_original_error(self) -> None:
        """Test that MaxRetriesExceededError stores original error."""
        original = ValueError("Original error")
        error = MaxRetriesExceededError(original, 3)

        assert error.original_error == original
        assert error.attempts == 3
        assert "3" in str(error)
