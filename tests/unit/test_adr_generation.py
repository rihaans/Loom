"""Tests for ADR (Architectural Decision Record) generation."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from loom.adr.generator import (
    build_alternatives,
    build_consequences,
    build_context,
    build_references,
    filter_significant_decisions,
    generate_adrs,
    generate_readme_adr_section,
    slugify,
)
from loom.adr.knowledge import ADR_KNOWLEDGE, get_knowledge, has_knowledge
from loom.state.enums import TechLayer


class TestSlugify:
    """Tests for the slugify helper function."""

    def test_basic_text(self) -> None:
        """Test basic text slugification."""
        assert slugify("FastAPI") == "fastapi"
        assert slugify("React+Vite") == "reactvite"

    def test_with_spaces(self) -> None:
        """Test text with spaces."""
        assert slugify("Hello World") == "hello-world"
        assert slugify("Some Long Name") == "some-long-name"

    def test_with_special_chars(self) -> None:
        """Test text with special characters."""
        assert slugify("React.js") == "reactjs"
        assert slugify("C++") == "c"

    def test_with_underscores(self) -> None:
        """Test text with underscores."""
        assert slugify("some_name") == "some-name"

    def test_multiple_hyphens(self) -> None:
        """Test collapsing multiple hyphens."""
        assert slugify("hello--world") == "hello-world"
        assert slugify("a - b - c") == "a-b-c"


class TestKnowledge:
    """Tests for the ADR knowledge base."""

    def test_get_knowledge_known_tech(self) -> None:
        """Test getting knowledge for a known technology."""
        knowledge = get_knowledge("backend", "FastAPI")
        assert knowledge is not None
        assert len(knowledge["alternatives"]) > 0
        assert len(knowledge["positives"]) > 0
        assert len(knowledge["negatives"]) > 0

    def test_get_knowledge_case_insensitive(self) -> None:
        """Test case-insensitive lookup."""
        knowledge = get_knowledge("BACKEND", "FASTAPI")
        assert knowledge is not None

    def test_get_knowledge_unknown_tech(self) -> None:
        """Test getting knowledge for unknown technology."""
        knowledge = get_knowledge("backend", "UnknownFramework")
        assert knowledge is None

    def test_has_knowledge(self) -> None:
        """Test has_knowledge check."""
        assert has_knowledge("backend", "fastapi") is True
        assert has_knowledge("backend", "flask") is True
        assert has_knowledge("backend", "unknown") is False

    def test_knowledge_has_required_fields(self) -> None:
        """Test that all knowledge entries have required fields."""
        for key, knowledge in ADR_KNOWLEDGE.items():
            assert "alternatives" in knowledge, f"Missing alternatives for {key}"
            assert "positives" in knowledge, f"Missing positives for {key}"
            assert "negatives" in knowledge, f"Missing negatives for {key}"
            assert "docs_url" in knowledge, f"Missing docs_url for {key}"


class TestFilterSignificantDecisions:
    """Tests for filtering tech choices."""

    @pytest.fixture
    def full_stack(self) -> list[Mock]:
        """Create a full stack of tech choices."""
        choices = []
        for layer in [
            TechLayer.BACKEND,
            TechLayer.FRONTEND,
            TechLayer.DATABASE,
            TechLayer.AUTH,
            TechLayer.TESTING,
            TechLayer.DEPLOYMENT,
            TechLayer.OTHER,
        ]:
            choice = Mock()
            choice.layer = layer
            choice.technology = f"{layer.value}_tech"
            choice.version = "1.0"
            choice.rationale = f"Using {layer.value} tech"
            choices.append(choice)
        return choices

    def test_filter_significant(self, full_stack: list[Mock]) -> None:
        """Test significant filter includes correct layers."""
        result = filter_significant_decisions(full_stack, "significant")
        layers = {c.layer for c in result}

        assert TechLayer.BACKEND in layers
        assert TechLayer.FRONTEND in layers
        assert TechLayer.DATABASE in layers
        assert TechLayer.AUTH in layers
        assert TechLayer.TESTING in layers
        assert TechLayer.DEPLOYMENT not in layers
        assert TechLayer.OTHER not in layers

    def test_filter_critical(self, full_stack: list[Mock]) -> None:
        """Test critical filter only includes core layers."""
        result = filter_significant_decisions(full_stack, "critical")
        layers = {c.layer for c in result}

        assert TechLayer.BACKEND in layers
        assert TechLayer.FRONTEND in layers
        assert TechLayer.DATABASE in layers
        assert TechLayer.AUTH in layers
        assert TechLayer.TESTING not in layers

    def test_filter_all(self, full_stack: list[Mock]) -> None:
        """Test all filter includes everything."""
        result = filter_significant_decisions(full_stack, "all")
        assert len(result) == len(full_stack)


class TestBuildContext:
    """Tests for building ADR context section."""

    def test_with_prd_and_rationale(self) -> None:
        """Test context with PRD and rationale."""
        prd = Mock()
        prd.project_type = "rest_api"
        prd.one_liner = "A bookstore management API"

        choice = Mock()
        choice.layer = TechLayer.BACKEND
        choice.rationale = "FastAPI provides excellent performance."

        state = {"prd": prd, "architecture": None}
        context = build_context(state, choice)

        assert "rest_api" in context or "bookstore" in context.lower()
        assert "FastAPI provides excellent performance" in context

    def test_with_api_endpoints(self) -> None:
        """Test context includes endpoint count for backend."""
        prd = Mock()
        prd.project_type = "rest_api"
        prd.one_liner = "API project"

        arch = Mock()
        arch.api_endpoints = [Mock() for _ in range(5)]

        choice = Mock()
        choice.layer = TechLayer.BACKEND
        choice.rationale = "Selected for performance."

        state = {"prd": prd, "architecture": arch}
        context = build_context(state, choice)

        assert "5 endpoints" in context

    def test_fallback_without_prd(self) -> None:
        """Test context fallback when no PRD."""
        choice = Mock()
        choice.layer = TechLayer.BACKEND
        choice.rationale = ""

        state = {"prd": None, "architecture": None}
        context = build_context(state, choice)

        assert "backend" in context.lower()


class TestBuildAlternatives:
    """Tests for building alternatives section."""

    def test_with_knowledge(self) -> None:
        """Test alternatives with curated knowledge."""
        choice = Mock()
        choice.layer = TechLayer.BACKEND
        choice.technology = "FastAPI"
        choice.rationale = "Good framework"

        alternatives = build_alternatives(choice)

        assert "Flask" in alternatives
        assert "Express" in alternatives

    def test_without_knowledge(self) -> None:
        """Test alternatives fallback for unknown tech."""
        choice = Mock()
        choice.layer = TechLayer.BACKEND
        choice.technology = "UnknownFramework"
        choice.rationale = "Custom reason for selection"

        alternatives = build_alternatives(choice)

        assert "Custom reason for selection" in alternatives


class TestBuildConsequences:
    """Tests for building consequences section."""

    def test_with_knowledge(self) -> None:
        """Test consequences with curated knowledge."""
        choice = Mock()
        choice.layer = TechLayer.BACKEND
        choice.technology = "FastAPI"
        choice.rationale = "Good framework"

        consequences = build_consequences(choice)

        assert "**Positive:**" in consequences
        assert "**Negative:**" in consequences
        assert "Pydantic" in consequences or "async" in consequences.lower()

    def test_without_knowledge(self) -> None:
        """Test consequences fallback for unknown tech."""
        choice = Mock()
        choice.layer = TechLayer.BACKEND
        choice.technology = "UnknownFramework"
        choice.rationale = "Custom reason"

        consequences = build_consequences(choice)

        assert "**Positive:**" in consequences
        assert "**Negative:**" in consequences
        assert "Custom reason" in consequences


class TestBuildReferences:
    """Tests for building references section."""

    def test_with_docs_url(self) -> None:
        """Test references include docs URL."""
        choice = Mock()
        choice.layer = TechLayer.BACKEND
        choice.technology = "FastAPI"

        references = build_references(choice, [choice])

        assert "fastapi.tiangolo.com" in references

    def test_without_docs_url(self) -> None:
        """Test references fallback without docs URL."""
        choice = Mock()
        choice.layer = TechLayer.BACKEND
        choice.technology = "UnknownFramework"

        references = build_references(choice, [choice])

        assert "documentation" in references.lower()


class TestGenerateAdrs:
    """Tests for the main ADR generation function."""

    @pytest.fixture
    def sample_state(self) -> dict:
        """Create a sample state with architecture."""
        prd = Mock()
        prd.project_name = "Test Project"
        prd.project_type = "fullstack_web"
        prd.one_liner = "A test application"
        prd.data_entities = []

        backend = Mock()
        backend.layer = TechLayer.BACKEND
        backend.technology = "FastAPI"
        backend.version = "0.115"
        backend.rationale = "Modern async framework"

        frontend = Mock()
        frontend.layer = TechLayer.FRONTEND
        frontend.technology = "React"
        frontend.version = "18"
        frontend.rationale = "Popular UI library"

        database = Mock()
        database.layer = TechLayer.DATABASE
        database.technology = "SQLite"
        database.version = "3"
        database.rationale = "Simple embedded database"

        arch = Mock()
        arch.stack = [backend, frontend, database]
        arch.api_endpoints = []

        return {"prd": prd, "architecture": arch}

    def test_generates_adrs_for_each_significant_choice(self, sample_state: dict) -> None:
        """Test ADR generation creates files for each choice."""
        adrs = generate_adrs(sample_state)

        # Index plus per-decision ADRs
        assert "docs/adrs/0000-index.md" in adrs
        assert any("backend" in path for path in adrs)
        assert any("frontend" in path for path in adrs)
        assert any("database" in path for path in adrs)

    def test_adrs_numbered_sequentially(self, sample_state: dict) -> None:
        """Test ADRs are numbered sequentially."""
        adrs = generate_adrs(sample_state)

        numbered = sorted(p for p in adrs if p != "docs/adrs/0000-index.md")
        nums = [int(Path(p).stem.split("-")[0]) for p in numbered]
        assert nums == list(range(1, len(nums) + 1))

    def test_adr_content_format(self, sample_state: dict) -> None:
        """Test ADR content follows expected format."""
        adrs = generate_adrs(sample_state)

        backend_adr = next(c for p, c in adrs.items() if "backend" in p and "0001" in p)

        assert "# ADR-0001:" in backend_adr
        assert "**Status:** Accepted" in backend_adr
        assert "## Context" in backend_adr
        assert "## Decision" in backend_adr
        assert "## Alternatives Considered" in backend_adr
        assert "## Consequences" in backend_adr
        assert "## References" in backend_adr
        assert "FastAPI" in backend_adr

    def test_index_lists_all_adrs(self, sample_state: dict) -> None:
        """Test index file lists all ADRs."""
        adrs = generate_adrs(sample_state)
        index = adrs["docs/adrs/0000-index.md"]

        # Every ADR file should be linked from the index
        for path in adrs:
            if path != "docs/adrs/0000-index.md":
                filename = Path(path).name
                assert filename in index

    def test_unknown_tech_falls_back_to_generic(self) -> None:
        """Test unknown technology uses generic template."""
        prd = Mock()
        prd.project_name = "Test"
        prd.project_type = "rest_api"
        prd.one_liner = "Test project"

        unknown = Mock()
        unknown.layer = TechLayer.BACKEND
        unknown.technology = "RocketRails"
        unknown.version = "1.0"
        unknown.rationale = "Custom framework choice"

        arch = Mock()
        arch.stack = [unknown]
        arch.api_endpoints = []

        state = {"prd": prd, "architecture": arch}
        adrs = generate_adrs(state)

        backend_adr = next(c for p, c in adrs.items() if "backend" in p and "0001" in p)

        # Should still be a valid ADR
        assert "RocketRails" in backend_adr
        assert "## Decision" in backend_adr
        assert "## Alternatives Considered" in backend_adr

    def test_no_architecture_returns_empty(self) -> None:
        """Test no ADRs when no architecture."""
        state = {"prd": None, "architecture": None}
        adrs = generate_adrs(state)
        assert adrs == {}

    def test_empty_stack_returns_empty(self) -> None:
        """Test no ADRs when stack is empty."""
        arch = Mock()
        arch.stack = []

        state = {"prd": None, "architecture": arch}
        adrs = generate_adrs(state)
        assert adrs == {}

    def test_significance_filter(self, sample_state: dict) -> None:
        """Test significance filter affects ADR count."""
        # Add non-significant choices
        other = Mock()
        other.layer = TechLayer.OTHER
        other.technology = "SomeTool"
        other.version = "1.0"
        other.rationale = "Helper tool"

        sample_state["architecture"].stack.append(other)

        significant_adrs = generate_adrs(sample_state, significance="significant")
        all_adrs = generate_adrs(sample_state, significance="all")

        # "all" should include more ADRs
        assert len(all_adrs) > len(significant_adrs)


class TestGenerateReadmeAdrSection:
    """Tests for README ADR section generation."""

    @pytest.fixture
    def sample_state(self) -> dict:
        """Create a sample state."""
        backend = Mock()
        backend.layer = TechLayer.BACKEND
        backend.technology = "FastAPI"
        backend.version = "0.115"
        backend.rationale = "Modern framework"

        arch = Mock()
        arch.stack = [backend]

        return {"architecture": arch}

    def test_generates_readme_section(self, sample_state: dict) -> None:
        """Test README section generation."""
        section = generate_readme_adr_section(sample_state)

        assert "## Architecture Decisions" in section
        assert "docs/adrs/" in section
        assert "FastAPI" in section

    def test_no_architecture_returns_empty(self) -> None:
        """Test empty section when no architecture."""
        state = {"architecture": None}
        section = generate_readme_adr_section(state)
        assert section == ""

    def test_no_significant_decisions_returns_empty(self) -> None:
        """Test empty section when no significant decisions."""
        other = Mock()
        other.layer = TechLayer.OTHER
        other.technology = "Tool"

        arch = Mock()
        arch.stack = [other]

        state = {"architecture": arch}
        section = generate_readme_adr_section(state, significance="significant")
        assert section == ""
