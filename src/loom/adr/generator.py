"""ADR generator for creating Architectural Decision Records.

Generates ADRs from architecture state without additional LLM calls.
Uses curated knowledge base for rich content about common technology choices.
"""

import re
from datetime import date
from typing import Any

from loom.adr.knowledge import get_knowledge
from loom.state.enums import TechLayer

# Layers that warrant ADRs (significant downstream impact)
SIGNIFICANT_LAYERS = {
    TechLayer.BACKEND,
    TechLayer.FRONTEND,
    TechLayer.DATABASE,
    TechLayer.AUTH,
    TechLayer.TESTING,
}

ADR_TEMPLATE = """# ADR-{number:04d}: {title}

**Status:** Accepted
**Date:** {date}
**Decided by:** Loom Architect agent

## Context

{context}

## Decision

We will use **{technology}{version_str}** for {layer_desc}.

## Alternatives Considered

{alternatives}

## Consequences

{consequences}

## References

{references}
"""

INDEX_TEMPLATE = """# Architecture Decision Records

This directory contains ADRs (Architectural Decision Records) for {project_name}.
Each ADR captures a significant design decision: the context, what was decided,
alternatives considered, and consequences.

## ADRs

| # | Decision | Status |
|---|---|---|
{adr_table}

## When to Add a New ADR

Add a new ADR when you make a decision that:
- Has significant downstream impact on contributors
- A reasonable engineer might second-guess
- Future maintainers would benefit from understanding the reasoning

## Format

We follow Michael Nygard's ADR format: Context -> Decision -> Alternatives ->
Consequences -> References. Number files sequentially. Mark superseded ADRs
with `Status: Superseded by ADR-NNNN`.
"""


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    # Convert to lowercase and replace spaces/underscores with hyphens
    slug = text.lower().replace(" ", "-").replace("_", "-")
    # Remove non-alphanumeric characters (except hyphens)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    return slug.strip("-")


def filter_significant_decisions(stack: list[Any], significance: str = "significant") -> list[Any]:
    """Filter tech choices to those warranting ADRs.

    Args:
        stack: List of TechChoice objects from architecture
        significance: Filter level - "all", "significant", or "critical"

    Returns:
        Filtered list of significant tech choices
    """
    if significance == "all":
        return list(stack)

    if significance == "critical":
        # Only the most impactful: backend, frontend, database, auth
        critical_layers = {
            TechLayer.BACKEND,
            TechLayer.FRONTEND,
            TechLayer.DATABASE,
            TechLayer.AUTH,
        }
        return [choice for choice in stack if choice.layer in critical_layers]

    # Default: "significant" - filter out cosmetic choices
    return [choice for choice in stack if choice.layer in SIGNIFICANT_LAYERS]


def build_context(state: dict[str, Any], choice: Any) -> str:
    """Build the context section for an ADR.

    Args:
        state: Agent state with PRD and architecture
        choice: The TechChoice being documented

    Returns:
        Context paragraph for the ADR
    """
    prd = state.get("prd")
    architecture = state.get("architecture")

    # Start with project description
    parts = []

    if prd:
        project_type = getattr(prd, "project_type", "application")
        one_liner = getattr(prd, "one_liner", "")
        if one_liner:
            parts.append(f"This project is a {project_type} for {one_liner.lower().rstrip('.')}.")

        # Add relevant stats based on layer
        if choice.layer == TechLayer.BACKEND and architecture:
            endpoints = getattr(architecture, "api_endpoints", [])
            if endpoints:
                parts.append(f"The API requires {len(endpoints)} endpoints.")

        if choice.layer == TechLayer.DATABASE and prd:
            entities = getattr(prd, "data_entities", [])
            if entities:
                parts.append(f"The system manages {len(entities)} data entities.")

    # Add the architect's rationale
    rationale = getattr(choice, "rationale", "")
    if rationale:
        parts.append(rationale)

    if not parts:
        parts.append(
            f"The project requires a {choice.layer.value} solution that balances "
            "simplicity, maintainability, and feature completeness."
        )

    return " ".join(parts)


def build_alternatives(choice: Any) -> str:
    """Build the alternatives section for an ADR.

    Args:
        choice: The TechChoice being documented

    Returns:
        Formatted alternatives list
    """
    knowledge = get_knowledge(choice.layer.value, choice.technology)

    if knowledge and knowledge["alternatives"]:
        lines = []
        for alt_name, alt_reason in knowledge["alternatives"]:
            lines.append(f"- **{alt_name}** - {alt_reason}")
        return "\n".join(lines)

    # Generic fallback when we don't have curated knowledge
    return (
        f"Other options were considered based on project requirements. "
        f"{choice.technology} was selected because: {choice.rationale}"
    )


def build_consequences(choice: Any) -> str:
    """Build the consequences section for an ADR.

    Args:
        choice: The TechChoice being documented

    Returns:
        Formatted consequences (positives and negatives)
    """
    knowledge = get_knowledge(choice.layer.value, choice.technology)

    parts = []

    if knowledge:
        if knowledge["positives"]:
            parts.append("**Positive:**")
            for pos in knowledge["positives"]:
                parts.append(f"- {pos}")

        if knowledge["negatives"]:
            parts.append("")
            parts.append("**Negative:**")
            for neg in knowledge["negatives"]:
                parts.append(f"- {neg}")

        return "\n".join(parts)

    # Generic fallback
    rationale = getattr(choice, "rationale", "meets project requirements")
    return (
        f"**Positive:**\n"
        f"- {rationale}\n"
        f"- Widely adopted with good community support.\n\n"
        f"**Negative:**\n"
        f"- Specific trade-offs depend on project evolution and team expertise."
    )


def build_references(choice: Any, all_choices: list[Any]) -> str:
    """Build the references section for an ADR.

    Args:
        choice: The TechChoice being documented
        all_choices: All TechChoices (for cross-references)

    Returns:
        Formatted references section
    """
    knowledge = get_knowledge(choice.layer.value, choice.technology)
    refs = []

    # Add documentation link if available
    if knowledge and knowledge.get("docs_url"):
        refs.append(f"- {choice.technology} documentation: {knowledge['docs_url']}")

    # Add cross-references to related ADRs
    related_layers = {
        TechLayer.BACKEND: [TechLayer.DATABASE, TechLayer.AUTH],
        TechLayer.FRONTEND: [TechLayer.AUTH],
        TechLayer.DATABASE: [TechLayer.BACKEND],
        TechLayer.AUTH: [TechLayer.BACKEND, TechLayer.FRONTEND],
        TechLayer.TESTING: [TechLayer.BACKEND, TechLayer.FRONTEND],
    }

    related = related_layers.get(choice.layer, [])
    for i, other in enumerate(all_choices, start=1):
        if other.layer in related and other != choice:
            refs.append(f"- See also: ADR-{i:04d} ({other.technology})")

    if not refs:
        refs.append(f"- {choice.technology} official documentation")

    return "\n".join(refs)


def generate_adrs(
    state: dict[str, Any],
    significance: str = "significant",
) -> dict[str, str]:
    """Generate ADR files from architecture state.

    Args:
        state: Agent state with PRD and architecture
        significance: Filter level - "all", "significant", or "critical"

    Returns:
        Dict mapping file path to content for each ADR file
    """
    architecture = state.get("architecture")
    prd = state.get("prd")

    if not architecture:
        return {}

    stack = getattr(architecture, "stack", [])
    if not stack:
        return {}

    # Filter to significant decisions
    decisions = filter_significant_decisions(stack, significance)
    if not decisions:
        return {}

    adrs: dict[str, str] = {}
    today = date.today().isoformat()

    # Generate individual ADRs
    for i, choice in enumerate(decisions, start=1):
        layer_desc = choice.layer.value.replace("_", " ")
        tech_slug = slugify(choice.technology)
        layer_slug = slugify(choice.layer.value)

        # Build version string
        version = getattr(choice, "version", "latest")
        version_str = f" {version}" if version and version != "latest" else ""

        # Build ADR content
        content = ADR_TEMPLATE.format(
            number=i,
            title=f"Use {choice.technology} for the {layer_desc.title()}",
            date=today,
            context=build_context(state, choice),
            technology=choice.technology,
            version_str=version_str,
            layer_desc=layer_desc,
            alternatives=build_alternatives(choice),
            consequences=build_consequences(choice),
            references=build_references(choice, decisions),
        )

        filename = f"{i:04d}-{layer_slug}-{tech_slug}.md"
        adrs[f"docs/adrs/{filename}"] = content

    # Generate index
    project_name = prd.project_name if prd else "this project"
    adr_table_rows = []
    for i, choice in enumerate(decisions, start=1):
        layer_slug = slugify(choice.layer.value)
        tech_slug = slugify(choice.technology)
        filename = f"{i:04d}-{layer_slug}-{tech_slug}.md"
        layer_desc = choice.layer.value.replace("_", " ").title()
        title = f"Use {choice.technology} for the {layer_desc}"
        adr_table_rows.append(f"| {i:04d} | [{title}]({filename}) | Accepted |")

    index_content = INDEX_TEMPLATE.format(
        project_name=project_name,
        adr_table="\n".join(adr_table_rows),
    )
    adrs["docs/adrs/0000-index.md"] = index_content

    return adrs


def generate_readme_adr_section(state: dict[str, Any], significance: str = "significant") -> str:
    """Generate the ADR section for the project README.

    Args:
        state: Agent state with PRD and architecture
        significance: Filter level for decisions

    Returns:
        Markdown section for README, or empty string if no ADRs
    """
    architecture = state.get("architecture")

    if not architecture:
        return ""

    stack = getattr(architecture, "stack", [])
    decisions = filter_significant_decisions(stack, significance)

    if not decisions:
        return ""

    lines = [
        "## Architecture Decisions",
        "",
        "This project's design choices are documented as ADRs in `docs/adrs/`:",
        "",
        "| # | Decision |",
        "|---|---|",
    ]

    for i, choice in enumerate(decisions, start=1):
        layer_slug = slugify(choice.layer.value)
        tech_slug = slugify(choice.technology)
        filename = f"{i:04d}-{layer_slug}-{tech_slug}.md"
        layer_desc = choice.layer.value.replace("_", " ").title()
        title = f"Use {choice.technology} for the {layer_desc}"
        lines.append(f"| [{i:04d}](docs/adrs/{filename}) | {title} |")

    return "\n".join(lines)
