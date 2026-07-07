"""Tests for agent chain construction, including native structured-output binding."""

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnableLambda

from loom.agents.base import _bind_structured_output, build_agent_chain
from loom.state.models import ReviewReport


class _NoStructured:
    """Stands in for a provider that doesn't implement structured output."""

    def with_structured_output(self, model):
        raise NotImplementedError


class _HasStructured:
    """Stands in for a provider with native structured output."""

    def __init__(self) -> None:
        self.requested: type | None = None

    def with_structured_output(self, model):
        self.requested = model
        # Return a real Runnable so the chain (prompt | runnable) composes.
        return RunnableLambda(lambda _: model)


class TestBindStructuredOutput:
    def test_returns_none_when_unsupported(self) -> None:
        assert _bind_structured_output(_NoStructured(), ReviewReport) is None

    def test_returns_runnable_when_supported(self) -> None:
        llm = _HasStructured()
        bound = _bind_structured_output(llm, ReviewReport)
        assert bound is not None
        assert llm.requested is ReviewReport


class TestBuildAgentChain:
    def test_uses_structured_output_when_available(self) -> None:
        llm = _HasStructured()
        chain, parser = build_agent_chain(
            system_prompt="sys",
            human_template="do {x}",
            output_model=ReviewReport,
            llm=llm,
            use_structured_output=True,
        )
        # The parser is always returned for format_instructions / fallback.
        assert isinstance(parser, PydanticOutputParser)
        # The native structured runnable was bound for the requested model.
        assert llm.requested is ReviewReport
        assert hasattr(chain, "invoke")

    def test_falls_back_to_parser_when_disabled(self) -> None:
        # A real fake chat model that is a Runnable so the fallback chain composes.
        llm = FakeListChatModel(responses=["{}"])
        chain, parser = build_agent_chain(
            system_prompt="sys",
            human_template="do {x}",
            output_model=ReviewReport,
            llm=llm,
            use_structured_output=False,
        )
        assert isinstance(parser, PydanticOutputParser)
        assert hasattr(chain, "invoke")
