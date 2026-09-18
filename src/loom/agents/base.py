"""Base agent factory and utilities."""

import logging
from typing import Any, TypeVar, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from loom.cache import cache_key, get_cache
from loom.config import LoomConfig
from loom.llm import get_llm_for_role
from loom.state.enums import AgentRole

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Reserved key an agent may put in its prompt input to name the *logical*
# request, independent of which retry attempt is being made. Parse retries
# append feedback to the prompt, so without this the artifact would be cached
# under the retried prompt and a rerun - which starts from attempt 1 - would
# always miss, then cascade misses through every downstream agent.
CACHE_SCOPE_KEY = "__cache_scope__"


class StructuredOutputError(RuntimeError):
    """Raised when a model cannot produce a usable structured artifact.

    Carries guidance about the likely cause, since the common trigger is a
    small local model that cannot reliably emit tool calls.
    """


def _bind_structured_output(llm: BaseChatModel, output_model: type[T]) -> Any | None:
    """Return an LLM runnable that emits ``output_model`` via native structured output.

    Modern chat models (Anthropic tool calling, OpenAI JSON/function mode, recent
    Ollama JSON mode) can be constrained to a schema directly, which is far more
    reliable than asking the model to emit JSON as free text and regex-parsing it.

    Returns None if the provider doesn't implement ``with_structured_output`` so the
    caller can fall back to the textual-parser chain. We keep the fallback because the
    full provider matrix (incl. older local models) isn't guaranteed to support it.
    """
    try:
        return llm.with_structured_output(output_model)
    except (NotImplementedError, AttributeError, TypeError) as exc:
        logger.warning(
            "Provider does not support native structured output for %s (%s); "
            "falling back to text parser.",
            output_model.__name__,
            exc,
        )
        return None


def build_revision_feedback(qa_feedback: Any | None, review_report: Any | None) -> str:
    """Compose the revision-instructions block injected into a developer's prompt.

    A developer node runs in REVISION mode when either QA tests failed or the Code
    Reviewer requested changes. This merges both sources into one section so the dev
    addresses every outstanding issue in a single regeneration.

    Returns an empty string when there is nothing to revise (initial generation).
    """
    sections: list[str] = []

    if qa_feedback is not None:
        sections.append(
            "QA Feedback (REVISION MODE):\n"
            f"Failed tests: {[t.name for t in qa_feedback.failed_tests]}\n"
            f"Suspected files: {qa_feedback.suspected_files}\n"
            f"Suggested fixes: {qa_feedback.suggested_fixes}\n"
            f"Error excerpt: {qa_feedback.raw_error_excerpt[:500]}\n\n"
            "Make SURGICAL fixes only to address these specific issues."
        )

    if review_report is not None and not review_report.approved:
        issues = review_report.blocking_issues or review_report.issues
        issue_lines = "\n".join(
            f"  - [{i.severity}] {i.file or '(cross-cutting)'}: {i.description}\n"
            f"    FIX: {i.suggested_fix}"
            for i in issues
        )
        sections.append(
            "Code Review feedback (REVISION MODE):\n"
            f"{review_report.summary}\n"
            f"{issue_lines}\n\n"
            "Make SURGICAL fixes only to address these specific issues."
        )

    return "\n\n".join(sections)


def build_agent_chain(
    system_prompt: str,
    human_template: str,
    output_model: type[T],
    llm: BaseChatModel,
    include_history: bool = False,
    use_structured_output: bool = True,
    agent_name: str = "",
) -> tuple[Any, PydanticOutputParser[T]]:
    """Build a LangChain chain for an agent.

    By default the chain uses the model's *native* structured-output mode
    (tool/JSON calling) so the LLM is constrained to ``output_model`` directly.
    If the provider can't do that, it transparently falls back to the legacy
    ``prompt | llm | PydanticOutputParser`` chain that parses JSON from text.

    Either way the returned ``parser`` is usable for ``get_format_instructions``
    (we still inject a schema hint into the prompt — it improves reliability for
    weaker models and keeps the fallback path identical).

    Args:
        system_prompt: The system prompt for the agent
        human_template: The human message template with placeholders
        output_model: Pydantic model class for structured output
        llm: The language model to use
        include_history: Whether to include message history placeholder
        use_structured_output: Prefer native structured output when available

    Returns:
        Tuple of (chain, parser) where chain can be invoked and parser
        can be used to parse outputs or get format instructions
    """
    # Create the output parser (used for the fallback chain + format instructions)
    parser = PydanticOutputParser(pydantic_object=output_model)

    # Build message list
    messages: list[Any] = [("system", system_prompt)]

    if include_history:
        messages.append(MessagesPlaceholder("history", optional=True))

    # Two prompt variants. Native structured output already constrains the
    # model to the schema, so repeating the JSON schema in the prompt is dead
    # weight - roughly 400-1000 tokens per call, on every agent and every
    # retry. The text parser genuinely needs it, so the fallback keeps it.
    human_with_format = (
        human_template
        + """

{format_instructions}"""
    )
    native_prompt = ChatPromptTemplate.from_messages([*messages, ("human", human_template)])
    text_prompt = ChatPromptTemplate.from_messages([*messages, ("human", human_with_format)])

    # Content-addressed caching. The key covers the prompts, the rendered
    # inputs, the model and the schema, so a hit is only ever returned for a
    # request that would have produced the same artifact anyway.
    label = agent_name or output_model.__name__
    model_id = _model_identity(llm)

    def _key(prompt_input: dict[str, Any]) -> str:
        # Key off the caller's canonical request when it named one, so every
        # retry attempt for the same logical request shares a cache entry.
        scope = prompt_input.get(CACHE_SCOPE_KEY)
        basis = scope if isinstance(scope, dict) else prompt_input
        return cache_key(
            agent=label,
            system_prompt=system_prompt,
            human_template=human_template,
            prompt_input={k: v for k, v in basis.items() if k != CACHE_SCOPE_KEY},
            model_id=model_id,
            output_model=output_model.__name__,
        )

    def _render_input(prompt_input: dict[str, Any]) -> dict[str, Any]:
        """Drop Loom-internal keys before the prompt template sees the input."""
        if CACHE_SCOPE_KEY not in prompt_input:
            return prompt_input
        return {k: v for k, v in prompt_input.items() if k != CACHE_SCOPE_KEY}

    def _estimate_tokens(prompt_input: dict[str, Any]) -> int:
        """Rough input size, recorded so a cache hit can report what it saved."""
        size = len(system_prompt) + len(human_template)
        size += sum(len(str(v)) for v in prompt_input.values())
        return size // 4

    structured_llm = _bind_structured_output(llm, output_model) if use_structured_output else None

    # Built on demand: composing it requires `llm` to be a Runnable, which only
    # matters if we actually need the text path.
    def text_chain() -> Any:
        return text_prompt | llm | parser

    def _no_output() -> StructuredOutputError:
        return StructuredOutputError(
            f"Model produced no usable {output_model.__name__}. This usually means "
            f"the model is too small or not tuned for tool calling - try a larger "
            f"model (e.g. ollama:llama3.1:8b) or a hosted provider."
        )

    if structured_llm is None:
        # Provider can't do native structured output at all: parse JSON out of
        # the model's free-text response.
        def _generate(prompt_input: dict[str, Any]) -> Any:
            return text_chain().invoke(_render_input(prompt_input))

        async def _agenerate(prompt_input: dict[str, Any]) -> Any:
            return await text_chain().ainvoke(_render_input(prompt_input))

    else:
        # Native path: the model is constrained to the schema and returns a
        # validated instance directly - no text parsing step, and no schema text.
        #
        # Some providers (notably Ollama) return None instead of raising when
        # the model fails to emit a usable tool call, which would otherwise
        # surface as an AttributeError deep in a caller. Fall back to text
        # parsing there so weaker local models still work.
        structured_chain = native_prompt | structured_llm

        def _generate(prompt_input: dict[str, Any]) -> Any:
            result = structured_chain.invoke(_render_input(prompt_input))
            if result is None:
                logger.warning(
                    "Native structured output returned no %s; retrying via text parser.",
                    output_model.__name__,
                )
                result = text_chain().invoke(_render_input(prompt_input))
            return result

        async def _agenerate(prompt_input: dict[str, Any]) -> Any:
            result = await structured_chain.ainvoke(_render_input(prompt_input))
            if result is None:
                logger.warning(
                    "Native structured output returned no %s; retrying via text parser.",
                    output_model.__name__,
                )
                result = await text_chain().ainvoke(_render_input(prompt_input))
            return result

    def _invoke(prompt_input: dict[str, Any]) -> T:
        cache = get_cache()
        key = _key(prompt_input)
        hit = cache.get(key, output_model, agent=label)
        if hit is not None:
            return hit
        result = _generate(prompt_input)
        if result is None:
            raise _no_output()
        cache.put(key, result, agent=label, input_tokens_estimate=_estimate_tokens(prompt_input))
        return cast(T, result)

    async def _ainvoke(prompt_input: dict[str, Any]) -> T:
        cache = get_cache()
        key = _key(prompt_input)
        hit = cache.get(key, output_model, agent=label)
        if hit is not None:
            return hit
        result = await _agenerate(prompt_input)
        if result is None:
            raise _no_output()
        cache.put(key, result, agent=label, input_tokens_estimate=_estimate_tokens(prompt_input))
        return cast(T, result)

    return RunnableLambda(_invoke, afunc=_ainvoke), parser


def _model_identity(llm: BaseChatModel) -> str:
    """A stable string identifying the model behind `llm`, for cache keys.

    Two different models must never share a cache entry, so this errs toward
    being over-specific: an unrecognised model contributes its class name plus
    whatever model attribute it exposes.
    """
    for attr in ("model", "model_name", "model_id"):
        value = getattr(llm, attr, None)
        if isinstance(value, str) and value:
            return f"{type(llm).__name__}:{value}"
    return type(llm).__name__


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
        agent_name=str(role),
    )
    return chain, parser, llm
