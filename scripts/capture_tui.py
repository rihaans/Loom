"""Render the chat REPL surfaces to an SVG so we can see the terminal UI."""

import io
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loom.cli.chat import renderer as R  # noqa: E402
from loom.cli.chat.renderer import ChatRenderer  # noqa: E402
from loom.state.enums import (  # noqa: E402
    Priority,
    ProjectType,
    ReviewSeverity,
    TargetAgent,
    TechLayer,
)
from loom.state.models import (  # noqa: E402
    PRD,
    ArchitectureDoc,
    ReviewIssue,
    ReviewReport,
    TechChoice,
    UserStory,
)
from loom.state.models import TestReport  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
WIDTH = 104


def prd() -> PRD:
    return PRD(
        project_name="Finsight",
        project_slug="finsight",
        project_type=ProjectType.FULLSTACK_WEB,
        one_liner="A personal finance tracker with CSV import and monthly summaries.",
        target_users=["individuals tracking personal spending"],
        user_stories=[
            UserStory(id="US-001", role="user", goal="import a bank CSV",
                      benefit="avoid manual entry", acceptance_criteria=["file parses"],
                      priority=Priority.P0),
        ],
        must_have_features=["CSV import", "Category breakdown", "Monthly summary"],
    )


def arch() -> ArchitectureDoc:
    return ArchitectureDoc(
        stack=[
            TechChoice(layer=TechLayer.BACKEND, technology="FastAPI", version="0.115", rationale="async"),
            TechChoice(layer=TechLayer.FRONTEND, technology="React", version="18", rationale="popular"),
            TechChoice(layer=TechLayer.DATABASE, technology="SQLite", version="3", rationale="simple"),
        ],
        api_endpoints=[],
        components=[],
    )


def make_console() -> Console:
    return Console(record=True, width=WIDTH, color_system="truecolor", file=io.StringIO())


def input_box(con: Console, text: str = "") -> None:
    """Draw the prompt exactly like input.py renders it: ▌ ❯ text."""
    line = Text()
    line.append("▌ ", style=R.C_ACCENT)
    line.append("❯ ", style=f"bold {R.C_ACCENT}")
    line.append(text if text else "", style=R.C_INK)
    con.print(line)


def main() -> None:
    con = make_console()
    r = ChatRenderer(console=con)

    r.render_banner("0.1.0", "anthropic:claude-sonnet-4-5")
    input_box(con, "build me a personal finance tracker that imports bank CSVs")

    r.render_agent_speaker("product_manager")
    r.render_agent_message(
        "product_manager",
        "Got it — a personal finance tracker. A few quick questions:\n"
        "- Single user, or multi-user with login?\n"
        "- Manual entry only, or should it import bank CSVs?\n"
        "- Categories, tags, both, or neither?",
    )
    con.print()
    input_box(con, "single user, CSV import, simple categories")

    r.render_agent_speaker("architect")
    r.render_agent_message(
        "architect",
        "Proposed stack: **FastAPI + React + SQLite**. CSV parsing via pandas, "
        "monthly rollups computed server-side. Sound good?",
    )

    r.render_prd_panel(prd())
    r.render_architecture_panel(arch())
    con.print()
    r.render_phase_breadcrumb("code_reviewer")
    r.render_review_panel(
        ReviewReport(
            approved=False,
            summary="Frontend calls an endpoint the backend doesn't expose.",
            issues=[
                ReviewIssue(severity=ReviewSeverity.MAJOR, file="frontend/api.ts",
                            description="POST /transactions is missing on the API",
                            suggested_fix="Add the route in backend/app/main.py"),
            ],
            target_agent=TargetAgent.BACKEND_DEV,
        )
    )
    r.render_completion(
        "output/finsight", 0.1284, 142318,
        test_report=TestReport(total=12, passed=12, failed=0, duration_ms=820.0),
        review_report=ReviewReport(approved=True, summary="ok"),
        files=17,
    )
    con.print()
    input_box(con)

    svg = con.export_svg(title="loom", font_aspect_ratio=0.61)
    (OUT / "terminal.svg").write_text(svg, encoding="utf-8")
    print("wrote", OUT / "terminal.svg")


if __name__ == "__main__":
    main()
