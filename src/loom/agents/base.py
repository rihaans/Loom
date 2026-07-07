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

    # Append format instructions to human template
    human_with_format = f"{human_template}\n\n{{format_instructions}}"
    messages.append(("human", human_with_format))

    # Create prompt template
    prompt = ChatPromptTemplate.from_messages(messages)

    structured_llm = _bind_structured_output(llm, output_model) if use_structured_output else None
    if structured_llm is not None:
        # Native path: the model is constrained to the schema and returns a
        # validated instance directly — no text parsing step.
        chain = prompt | structured_llm
    else:
        # Legacy path: parse JSON out of the model's free-text response.
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
