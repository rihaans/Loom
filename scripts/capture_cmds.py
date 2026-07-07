"""Capture the slash-menu dropdown + /help, /status, /cost panels."""

import io
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loom.cli.chat import renderer as R  # noqa: E402
from loom.cli.chat.commands import HELP_ENTRIES  # noqa: E402
from loom.cli.chat.renderer import ChatRenderer  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
WIDTH = 92


def con() -> Console:
    return Console(record=True, width=WIDTH, color_system="truecolor", file=io.StringIO())


def mock_dropdown(c: Console) -> None:
    """Approximate the prompt_toolkit slash-completion popup."""
    items = [
        ("/help", "Show command reference", "session"),
        ("/status", "Show current build state", "config"),
        ("/cost", "Running token & dollar cost", "config"),
        ("/done", "Tell the current agent to commit", "workflow"),
        ("/show prd", "Render the PRD artifact", "artifacts"),
    ]
    # The input line the user is typing.
    line = Text("  ▌ ", style=R.C_FAINT)
    line.append("❯ ", style=f"bold {R.C_ACCENT}")
    line.append("/", style=R.C_INK)
    c.print(line)
    rows = []
    cmdw = max(len(d) for d, _, _ in items) + 4
    sel_bg, base_bg = "#c9b68c", "#15171c"
    for i, (disp, meta, _cat) in enumerate(items):
        sel = i == 0
        row = Text("  ")
        bg = f" on {sel_bg}" if sel else f" on {base_bg}"
        row.append("◇ ", style=f"{'#15171c' if sel else R.C_ACCENT}{bg}")
        ink = "#15171c" if sel else "#a2a7b0"
        row.append(f"{disp:<{cmdw}}", style=f"{'bold ' if sel else ''}{ink}{bg}")
        mcol = "#15171c" if sel else "#6a707a"
        row.append(f"{meta}  ", style=f"italic {mcol}{bg}")
        rows.append(row)
    for row in rows:
        c.print(row)


def main() -> None:
    c = con()
    r = ChatRenderer(console=c)

    c.print()
    c.print(Text("  typing ", style=R.C_FAINT) + Text("/", style=R.C_ACCENT)
            + Text(" pops the command menu:", style=R.C_FAINT))
    mock_dropdown(c)

    r.render_help(HELP_ENTRIES)

    r.render_status_panel(
        phase="review",
        active_role="code_reviewer",
        tokens=142318,
        cost_usd=0.1284,
        retries=1,
        max_retries=2,
        artifacts={"PRD": True, "Architecture": True, "Code": True,
                   "Tests": False, "DevOps": False},
        model_label="anthropic:claude-sonnet-4-5",
    )

    r.render_cost_table(
        {
            "product_manager": (3200, 1400, 0.021),
            "architect": (5100, 3800, 0.058),
            "backend_dev": (8800, 9200, 0.121),
            "frontend_dev": (7400, 8100, 0.104),
            "code_reviewer": (4200, 1900, 0.039),
        },
        total_tokens=66900,
        total_cost_usd=0.343,
    )

    svg = c.export_svg(title="loom · commands", font_aspect_ratio=0.61)
    (OUT / "commands.svg").write_text(svg, encoding="utf-8")
    print("wrote", OUT / "commands.svg")


if __name__ == "__main__":
    main()
