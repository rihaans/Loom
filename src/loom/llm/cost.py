"""Token to USD cost calculation with provider price tables.

Prices are per 1M tokens, current as of 2026-09. Update these when providers
change prices.

Lookup is exact-match only. An unrecognised model returns None rather than
silently falling back to a neighbouring model's price - a wrong number shown
with confidence is worse than an honest "unknown", and the previous prefix
matching quietly billed `claude-opus-4-8` at Opus 4.5 rates.
"""

from dataclasses import dataclass


@dataclass
class ModelPricing:
    """Pricing for a specific model."""

    input_per_million: float  # USD per 1M input tokens
    output_per_million: float  # USD per 1M output tokens
    cached_input_per_million: float | None = None  # For Anthropic prompt caching


def _strip_date_suffix(model: str) -> str:
    """Drop a trailing YYYYMMDD snapshot suffix from a model id.

    "claude-opus-5-20260401" -> "claude-opus-5". Returns the input unchanged
    when there is no such suffix.
    """
    parts = model.rsplit("-", 1)
    if len(parts) == 2 and len(parts[1]) == 8 and parts[1].isdigit():
        return parts[0]
    return model


# Anthropic pricing (as of May 2025)
# https://www.anthropic.com/pricing
ANTHROPIC_PRICING: dict[str, ModelPricing] = {
    # Current generation
    "claude-fable-5-1": ModelPricing(
        input_per_million=10.00,
        output_per_million=50.00,
        cached_input_per_million=1.00,
    ),
    "claude-fable-5": ModelPricing(
        input_per_million=10.00,
        output_per_million=50.00,
        cached_input_per_million=1.00,
    ),
    "claude-opus-5": ModelPricing(
        input_per_million=5.00,
        output_per_million=25.00,
        cached_input_per_million=0.50,
    ),
    "claude-opus-4-8": ModelPricing(
        input_per_million=5.00,
        output_per_million=25.00,
        cached_input_per_million=0.50,
    ),
    "claude-opus-4-7": ModelPricing(
        input_per_million=5.00,
        output_per_million=25.00,
        cached_input_per_million=0.50,
    ),
    "claude-opus-4-6": ModelPricing(
        input_per_million=5.00,
        output_per_million=25.00,
        cached_input_per_million=0.50,
    ),
    "claude-sonnet-5": ModelPricing(
        input_per_million=2.00,
        output_per_million=10.00,
        cached_input_per_million=0.20,
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_per_million=3.00,
        output_per_million=15.00,
        cached_input_per_million=0.30,
    ),
    "claude-haiku-4-5": ModelPricing(
        input_per_million=1.00,
        output_per_million=5.00,
        cached_input_per_million=0.10,
    ),
    # Previous generation
    "claude-opus-4-5": ModelPricing(
        input_per_million=15.00,
        output_per_million=75.00,
        cached_input_per_million=1.50,
    ),
    "claude-sonnet-4-5": ModelPricing(
        input_per_million=3.00,
        output_per_million=15.00,
        cached_input_per_million=0.30,
    ),
    "claude-haiku-3-5": ModelPricing(
        input_per_million=0.80,
        output_per_million=4.00,
        cached_input_per_million=0.08,
    ),
    # Legacy models
    "claude-opus-4": ModelPricing(
        input_per_million=15.00,
        output_per_million=75.00,
    ),
    "claude-sonnet-4": ModelPricing(
        input_per_million=3.00,
        output_per_million=15.00,
    ),
    "claude-3-5-sonnet-20241022": ModelPricing(
        input_per_million=3.00,
        output_per_million=15.00,
    ),
    "claude-3-opus-20240229": ModelPricing(
        input_per_million=15.00,
        output_per_million=75.00,
    ),
    "claude-3-sonnet-20240229": ModelPricing(
        input_per_million=3.00,
        output_per_million=15.00,
    ),
    "claude-3-haiku-20240307": ModelPricing(
        input_per_million=0.25,
        output_per_million=1.25,
    ),
}

# OpenAI pricing (as of May 2025)
# https://openai.com/pricing
OPENAI_PRICING: dict[str, ModelPricing] = {
    "gpt-4o": ModelPricing(
        input_per_million=2.50,
        output_per_million=10.00,
    ),
    "gpt-4o-mini": ModelPricing(
        input_per_million=0.15,
        output_per_million=0.60,
    ),
    "gpt-4-turbo": ModelPricing(
        input_per_million=10.00,
        output_per_million=30.00,
    ),
    "gpt-4": ModelPricing(
        input_per_million=30.00,
        output_per_million=60.00,
    ),
    "gpt-3.5-turbo": ModelPricing(
        input_per_million=0.50,
        output_per_million=1.50,
    ),
    "o1-mini": ModelPricing(
        input_per_million=3.00,
        output_per_million=12.00,
    ),
    "o1-preview": ModelPricing(
        input_per_million=15.00,
        output_per_million=60.00,
    ),
}

# Ollama is free (local)
OLLAMA_PRICING: dict[str, ModelPricing] = {}


def get_pricing(provider: str, model: str) -> ModelPricing | None:
    """Get pricing for a provider/model combination.

    Args:
        provider: LLM provider (anthropic, openai, ollama)
        model: Model name

    Returns:
        ModelPricing if found, None for local models
    """
    if provider == "anthropic":
        # Exact match only. A dated snapshot ("claude-opus-5-20260401") is
        # normalised by stripping the trailing date; anything else unknown
        # returns None so callers can say "unknown" instead of inventing a price.
        if model in ANTHROPIC_PRICING:
            return ANTHROPIC_PRICING[model]
        undated = _strip_date_suffix(model)
        return ANTHROPIC_PRICING.get(undated)

    elif provider == "openai":
        if model in OPENAI_PRICING:
            return OPENAI_PRICING[model]
        undated = _strip_date_suffix(model)
        return OPENAI_PRICING.get(undated)

    elif provider == "ollama":
        return None  # Free

    return None


def calculate_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float:
    """Calculate the cost of an LLM call in USD.

    Args:
        provider: LLM provider
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cached_input_tokens: Number of cached input tokens (Anthropic only)

    Returns:
        Cost in USD (0.0 for local models or unknown pricing)
    """
    pricing = get_pricing(provider, model)
    if pricing is None:
        return 0.0

    # Calculate input cost
    regular_input_tokens = input_tokens - cached_input_tokens
    input_cost = (regular_input_tokens / 1_000_000) * pricing.input_per_million

    # Add cached input cost if applicable
    if cached_input_tokens > 0 and pricing.cached_input_per_million:
        input_cost += (cached_input_tokens / 1_000_000) * pricing.cached_input_per_million

    # Calculate output cost
    output_cost = (output_tokens / 1_000_000) * pricing.output_per_million

    return input_cost + output_cost


def pricing_status(provider: str, model: str) -> str:
    """Classify how much we know about a model's price.

    Returns:
        "free" for local providers that cost nothing to run,
        "priced" when the model is in a price table,
        "unknown" when it is a paid provider we have no price for - callers
        should say so rather than displaying $0.00.
    """
    if provider == "ollama":
        return "free"
    return "priced" if get_pricing(provider, model) is not None else "unknown"


def format_cost(cost_usd: float) -> str:
    """Format a cost value for display.

    Args:
        cost_usd: Cost in USD

    Returns:
        Formatted string (e.g., "$0.05", "$1.23", "<$0.01")
    """
    if cost_usd < 0.01:
        return "<$0.01"
    elif cost_usd < 1.00:
        return f"${cost_usd:.2f}"
    else:
        return f"${cost_usd:.2f}"


def estimate_build_cost(
    provider: str,
    model: str,
    estimated_tokens: int = 80_000,
) -> float:
    """Estimate the cost of a full build.

    Args:
        provider: LLM provider
        model: Model name
        estimated_tokens: Estimated total tokens (default: 80k for simple build)

    Returns:
        Estimated cost in USD
    """
    # Assume roughly 40% input, 60% output split
    input_tokens = int(estimated_tokens * 0.4)
    output_tokens = int(estimated_tokens * 0.6)
    return calculate_cost(provider, model, input_tokens, output_tokens)
