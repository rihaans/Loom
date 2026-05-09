"""Retry policies for LLM calls using tenacity.

Handles:
- Rate limit errors (429, 529)
- Parse errors (invalid JSON from LLM)
- Transient network errors
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# Exception types that indicate rate limiting
class RateLimitError(Exception):
    """Rate limit exceeded error."""

    pass


class ParseError(Exception):
    """Failed to parse LLM output."""

    def __init__(self, message: str, raw_output: str):
        super().__init__(message)
        self.raw_output = raw_output


class MaxRetriesExceededError(Exception):
    """Maximum retry attempts exceeded."""

    def __init__(self, original_error: Exception, attempts: int):
        super().__init__(f"Max retries ({attempts}) exceeded: {original_error}")
        self.original_error = original_error
        self.attempts = attempts


def is_rate_limit_error(exception: BaseException) -> bool:
    """Check if an exception is a rate limit error.

    Handles various provider-specific error formats.
    """
    error_str = str(exception).lower()
    return any(
        indicator in error_str
        for indicator in [
            "rate limit",
            "ratelimit",
            "429",
            "529",
            "too many requests",
            "quota exceeded",
            "capacity",
        ]
    )


def is_transient_error(exception: BaseException) -> bool:
    """Check if an exception is a transient error worth retrying."""
    error_str = str(exception).lower()
    return any(
        indicator in error_str
        for indicator in [
            "timeout",
            "connection",
            "network",
            "503",
            "502",
            "500",
            "overloaded",
        ]
    )


# Retry decorator for rate limits
rate_limit_retry = retry(
    retry=retry_if_exception_type((RateLimitError, Exception)),
    wait=wait_random_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda retry_state: logger.warning(
        f"Rate limited, retrying in {retry_state.next_action.sleep}s "
        f"(attempt {retry_state.attempt_number}/5)"
    ),
)


# Retry decorator for parse errors (fewer attempts, no backoff)
parse_retry = retry(
    retry=retry_if_exception_type(ParseError),
    wait=wait_exponential(multiplier=0.5, min=1, max=4),
    stop=stop_after_attempt(3),
    before_sleep=lambda retry_state: logger.warning(
        f"Parse error, retrying (attempt {retry_state.attempt_number}/3)"
    ),
)


def with_retry(
    func: Callable[..., T],
    max_attempts: int = 3,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[..., T]:
    """Wrap a function with retry logic.

    Args:
        func: Function to wrap
        max_attempts: Maximum retry attempts
        on_retry: Optional callback called before each retry

    Returns:
        Wrapped function with retry logic
    """

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return func(*args, **kwargs)

    return wrapper


async def retry_llm_call(
    call_fn: Callable[..., Any],
    max_attempts: int = 3,
    on_parse_error: Callable[[str, int], str] | None = None,
) -> Any:
    """Execute an LLM call with retry logic.

    Args:
        call_fn: Async function that makes the LLM call
        max_attempts: Maximum retry attempts
        on_parse_error: Optional callback to modify prompt on parse error
            Takes (raw_output, attempt_number) and returns modified prompt

    Returns:
        Result from successful LLM call

    Raises:
        MaxRetriesExceeded: If all retries fail
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await call_fn()
        except ParseError as e:
            last_error = e
            logger.warning(f"Parse error on attempt {attempt}/{max_attempts}: {e}")
            if attempt < max_attempts and on_parse_error:
                # Let caller modify prompt based on error
                on_parse_error(e.raw_output, attempt)
        except Exception as e:
            last_error = e
            if is_rate_limit_error(e):
                logger.warning(f"Rate limit on attempt {attempt}/{max_attempts}")
                # Exponential backoff for rate limits
                import asyncio

                await asyncio.sleep(2**attempt)
            elif is_transient_error(e):
                logger.warning(f"Transient error on attempt {attempt}/{max_attempts}: {e}")
                import asyncio

                await asyncio.sleep(attempt)
            else:
                # Non-retryable error
                raise

    raise MaxRetriesExceededError(last_error or Exception("Unknown error"), max_attempts)


def create_parse_error_feedback(raw_output: str, error_message: str) -> str:
    """Create feedback message to help LLM fix parse errors.

    Args:
        raw_output: The raw output that failed to parse
        error_message: The parse error message

    Returns:
        Feedback string to append to next prompt
    """
    return f"""
Your previous response could not be parsed as valid JSON.

Error: {error_message}

Your response was:
```
{raw_output[:500]}{'...' if len(raw_output) > 500 else ''}
```

Please provide a valid JSON response matching the required schema.
"""
