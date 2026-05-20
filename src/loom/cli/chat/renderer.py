"""Rich-based renderer for the chat REPL.

Owns all visual output:
  - Big LOOM banner on session start
  - User message echo
  - Agent speaker headers and message bodies
  - Artifact panels (PRD, ArchitectureDoc, code summary, test report)
  - Progress bars for parallel execution
  - Error and completion footers
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, ClassVar

from rich.align import Align
from rich.box import ROUNDED, SIMPLE
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Brand colors
# ---------------------------------------------------------------------------

# Loom uses a cool gradient (cyan → magenta) — symbolic of the "weave"
# happening between agents.
BRAND_PRIMARY = "bold #00d9ff"   # bright cyan
BRAND_ACCENT = "bold #ff5fd2"    # bright magenta
BRAND_DIM = "dim #88c0d0"
BRAND_MUTED = "#5e81ac"

# ASCII logo — "ANSI Shadow" font
_LOGO_LINES = [
    "██╗      ██████╗  ██████╗ ███╗   ███╗",
    "██║     ██╔═══██╗██╔═══██╗████╗ ████║",
    "██║     ██║   ██║██║   ██║██╔████╔██║",
    "██║     ██║   ██║██║   ██║██║╚██╔╝██║",
    "███████╗╚██████╔╝╚██████╔╝██║ ╚═╝ ██║",
    "╚══════╝ ╚═════╝  ╚═════╝ ╚═╝     ╚═╝",
]

# Per-agent visual style: (emoji+label, role color, accent border)
_AGENT_STYLES: dict[str, tuple[str, str]] = {
    "product_manager": ("📋  Product Manager", "#00d9ff"),
    "architect":       ("🏗   Architect",       "#ff5fd2"),
    "frontend_dev":    ("💻  Frontend Dev",     "#88c0d0"),
    "backend_dev":     ("⚙   Backend Dev",      "#a3be8c"),
    "qa_engineer":     ("🧪  QA Engineer",      "#ebcb8b"),
    "devops_engineer": ("🚀  DevOps",           "#b48ead"),
    "supervisor":      ("🎯  Supervisor",       "white"),
}


def _gradient_logo() -> Text:
    """Build the LOOM logo as a Text object with a cyan-to-magenta gradient."""
    # Six gradient stops across six lines of the logo.
    colors = [
        "#00d9ff",  # cyan
        "#33cdff",
        "#7ab9ff",
        "#c79bff",
        "#f176f3",
        "#ff5fd2",  # magenta
    ]
    out = Text()
    for line, color in zip(_LOGO_LINES, colors, strict=True):
        out.append(line + "\n", style=f"bold {color}")
    return out


class ChatRenderer:
    """Renders chat output to a rich Console."""

    def __init__(self, console: Console | None = None, plain: bool = False) -> None:
        self.console = console or Console(highlight=False, soft_wrap=True)
        self.plain = plain
        self._first_agent_render = True

    # ---- Banner / footer ------------------------------------------------

    def render_banner(self, version: str, model_label: str) -> None:
        """Render the startup banner with the big LOOM logo."""
        if self.plain:
            self.console.print("LOOM", style="bold")
            self.console.print(f"v{version} · {model_label}", style="dim")
            self.console.print("Type your idea, or /help for commands.")
            self.console.print()
            return

        # Logo with gradient
        logo = _gradient_logo()

        # Tagline
        tagline = Text()
        tagline.append("your AI software team", style=f"italic {BRAND_DIM}")

        # Meta line: version · model
        meta = Text()
        meta.append(f"v{version}", style=BRAND_MUTED)
        meta.append("  ·  ", style="dim")
        meta.append(model_label, style=BRAND_MUTED)

        # Help line
        help_line = Text()
        help_line.append("Type your idea, or ", style="white")
        help_line.append("/help", style=BRAND_PRIMARY)
        help_line.append(" for commands\n", style="white")
        help_line.append("Ctrl+C", style="dim")
        help_line.append(" abort step  ·  ", style="dim")
        help_line.append("Ctrl+D", style="dim")
        help_line.append(" exit", style="dim")

        # Stack vertically with proper spacing
        body = Group(
            Align.center(logo),
            Align.center(tagline),
            Text(""),
            Align.center(meta),
            Text(""),
            Rule(style=BRAND_MUTED),
            Text(""),
            Align.center(help_line),
        )

        # Panel wraps everything with a rounded border in brand cyan
        self.console.print()
        self.console.print(
            Panel(
                Padding(body, (1, 4)),
                border_style=BRAND_PRIMARY,
                box=ROUNDED,
                padding=(0, 0),
            )
        )
        self.console.print()

    def render_completion(
        self, output_dir: str, total_cost: float, total_tokens: int
    ) -> None:
        """Render the build-complete footer."""
        body = Text()
        body.append("✓ Build complete\n\n", style="bold green")
        body.append("Output:  ", style="dim")
        body.append(f"{output_dir}\n", style=BRAND_PRIMARY)
        body.append("Tokens:  ", style="dim")
        body.append(f"{total_tokens:,}\n", style="white")
        body.append("Cost:    ", style="dim")
        body.append(f"${total_cost:.4f}", style="white")
        self.console.print()
        self.console.print(
            Panel(
                Padding(body, (0, 2)),
                border_style="green",
                box=ROUNDED,
                expand=False,
            )
        )

    def render_error(self, message: str, hint: str | None = None) -> None:
        """Render an error panel."""
        body = Text()
        body.append("⚠  ", style="bold red")
        body.append(message, style="red")
        if hint:
            body.append("\n\n")
            body.append(hint, style="dim")
        self.console.print()
        self.console.print(
            Panel(
                Padding(body, (0, 2)),
                border_style="red",
                box=ROUNDED,
                expand=False,
            )
        )

    # ---- Per-turn rendering ---------------------------------------------

    def render_user_message(self, text: str) -> None:
        """Echo the user's message — only in plain mode (prompt_toolkit shows
        it interactively otherwise)."""
        if self.plain:
            self.console.print(f"You ▸ {text}", style=BRAND_PRIMARY)

    def render_agent_speaker(self, role_key: str) -> None:
        """Render the speaker header, e.g. '📋 Product Manager'."""
        label, color = _AGENT_STYLES.get(role_key, (role_key, "white"))
        # Soft separator so successive agent messages don't run together
        self.console.print()
        speaker = Text()
        speaker.append("│ ", style=f"bold {color}")
        speaker.append(label, style=f"bold {color}")
        self.console.print(speaker)
        self.console.print(Text("│", style=color))

    def render_agent_message(self, role_key: str, text: str) -> None:
        """Render a complete agent message body, indented to match speaker.

        Sync version — used in tests and plain mode. For animated typewriter
        rendering use `render_agent_message_animated` from async code.
        """
        _, color = _AGENT_STYLES.get(role_key, (role_key, "white"))
        if self.plain:
            self.console.print(text, style=color)
            return

        try:
            md = Markdown(text)
            self.console.print(Padding(md, (0, 0, 0, 2)))
        except Exception:
            self.console.print(Text(text, style="white"))

    async def render_agent_message_animated(
        self,
        role_key: str,
        text: str,
        chars_per_second: int = 240,
    ) -> None:
        """Render an agent message with a typewriter effect.

        Uses rich.live to progressively reveal the message. Chunks the text
        for performance — at 240 cps with a 60 Hz refresh, that's 4 chars
        per frame. Markdown is rendered once at the end so list bullets and
        bolds appear correctly without flickering.
        """
        if self.plain:
            self.console.print(text, style="white")
            return

        # Empty / whitespace text — nothing to animate
        if not text or not text.strip():
            return

        chunk_size = max(1, chars_per_second // 60)
        delay = chunk_size / chars_per_second

        # Phase 1: typewriter as plain (fast, monotype-feel) text
        revealed = ""
        with Live(
            Padding(Text(""), (0, 0, 0, 2)),
            console=self.console,
            refresh_per_second=60,
            transient=True,  # cleared when done so phase 2 can render markdown
        ) as live:
            for i in range(0, len(text), chunk_size):
                revealed = text[: i + chunk_size]
                live.update(Padding(Text(revealed, style="white"), (0, 0, 0, 2)))
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    break

        # Phase 2: print the FINAL message as proper markdown (so bullets,
        # bold, code blocks render correctly).
        try:
            self.console.print(Padding(Markdown(text), (0, 0, 0, 2)))
        except Exception:
            self.console.print(Padding(Text(text, style="white"), (0, 0, 0, 2)))

    @contextmanager
    def thinking(self, message: str = "thinking") -> Iterator[None]:
        """Show an animated spinner while a block runs.

        Use as: `with renderer.thinking("drafting PRD"): await graph.ainvoke(...)`.
        Falls back to a plain status line in `plain` mode.
        """
        if self.plain:
            self.console.print(f"  · {message}…", style="dim italic")
            yield
            return

        spinner = Spinner(
            "dots",
            text=Text(f" {message}…", style=f"italic {BRAND_DIM}"),
            style=BRAND_PRIMARY,
        )
        with Live(
            Padding(spinner, (0, 0, 0, 2)),
            console=self.console,
            refresh_per_second=12,
            transient=True,  # cleared when context exits
        ):
            yield

    def render_status(self, message: str) -> None:
        """Render a transient status line (e.g. 'drafting PRD…')."""
        self.console.print()
        self.console.print(Text(f"  ⠋ {message}", style=f"italic {BRAND_DIM}"))

    def render_turn_separator(self) -> None:
        """Subtle separator drawn between major conversation turns."""
        if self.plain:
            return
        self.console.print()
        self.console.print(
            Text("  · · ·", style=f"dim {BRAND_MUTED}"), justify="left"
        )

    # ---- Artifact panels ------------------------------------------------

    def render_prd_panel(self, prd: Any) -> None:
        """Render a compact PRD panel."""
        if prd is None:
            return

        body = Text()
        body.append(prd.project_name, style="bold white")
        body.append("\n")
        body.append(prd.one_liner, style="dim")
        body.append("\n\n")
        body.append("P0 features\n", style=f"bold {BRAND_PRIMARY}")
        for feat in prd.must_have_features:
            body.append("  • ", style=BRAND_PRIMARY)
            body.append(f"{feat}\n", style="white")
        if prd.user_stories:
            count = len(prd.user_stories)
            body.append("\n")
            body.append(
                f"{count} user stor{'y' if count == 1 else 'ies'}",
                style="dim",
            )

        title = Text("📋  PRD", style=BRAND_PRIMARY)
        title.append(f"  ·  {prd.project_slug}", style="dim")

        self.console.print()
        self.console.print(
            Panel(
                Padding(body, (0, 1)),
                title=title,
                title_align="left",
                border_style=BRAND_PRIMARY,
                box=ROUNDED,
                expand=False,
            )
        )

    def render_architecture_panel(self, arch: Any) -> None:
        """Render a compact architecture panel."""
        if arch is None:
            return

        body = Text()
        body.append("Stack\n", style=f"bold {BRAND_ACCENT}")
        for tech in arch.stack:
            body.append("  ", style="dim")
            body.append(f"{tech.layer:<10}", style=BRAND_MUTED)
            body.append(tech.technology, style="white")
            if tech.version:
                body.append(f"  {tech.version}", style="dim")
            body.append("\n")
        body.append("\n")
        body.append(
            f"{len(arch.api_endpoints)} endpoints  ·  "
            f"{len(arch.components)} components",
            style="dim",
        )

        title = Text("🏗   Architecture", style=BRAND_ACCENT)

        self.console.print()
        self.console.print(
            Panel(
                Padding(body, (0, 1)),
                title=title,
                title_align="left",
                border_style=BRAND_ACCENT,
                box=ROUNDED,
                expand=False,
            )
        )

    def render_progress_parallel(self, statuses: dict[str, str]) -> None:
        """Render a snapshot of parallel agent statuses."""
        self.console.print()
        for role, status in statuses.items():
            label, color = _AGENT_STYLES.get(role, (role, "white"))
            if status == "running":
                symbol = "⠋"
                style = f"italic {color}"
            elif status == "done":
                symbol = "✓"
                style = f"bold {color}"
            else:
                symbol = "•"
                style = f"dim {color}"
            self.console.print(
                Text(f"  {symbol}  {label}", style=style)
                + Text(f"   {status}", style="dim")
            )

    def render_test_report(self, report: Any) -> None:
        """Render a brief test report summary."""
        if report is None:
            return
        passed = getattr(report, "passed", 0)
        total = getattr(report, "total", 0)
        if passed == total and total > 0:
            symbol, color = "✓", "green"
        elif total == 0:
            symbol, color = "•", "dim"
        else:
            symbol, color = "✗", "red"
        self.console.print()
        self.console.print(
            Text(f"  {symbol}  Tests: {passed}/{total} passing",
                 style=f"bold {color}")
        )

    # ---- Claude-Code-style panels --------------------------------------

    def clear(self) -> None:
        """Clear the terminal screen. Transcript on disk is untouched."""
        # rich's clear() emits the right ANSI sequences for the host terminal.
        self.console.clear()

    def render_help(self, entries: list[tuple[str, str, str, str]]) -> None:
        """Render the /help command reference as a categorized table.

        Args:
            entries: list of (canonical, aliases, description, category) tuples.
                Typically supplied as `commands.HELP_ENTRIES`.
        """
        if self.plain:
            # Plain mode: simple list, one command per line.
            for canonical, aliases, desc, _cat in entries:
                line = canonical
                if aliases:
                    line += f"  ({aliases})"
                self.console.print(f"  {line:<32} {desc}")
            self.console.print(
                "\n  Anything else you type is a message to the active agent."
            )
            return

        # Group entries by category, preserving insertion order.
        by_cat: dict[str, list[tuple[str, str, str, str]]] = {}
        for row in entries:
            by_cat.setdefault(row[3], []).append(row)

        groups: list[Any] = []
        for cat, rows in by_cat.items():
            table = Table(
                box=SIMPLE,
                show_header=False,
                pad_edge=False,
                padding=(0, 1),
                expand=False,
            )
            table.add_column(style=BRAND_PRIMARY, no_wrap=True)
            table.add_column(style="dim", no_wrap=True)
            table.add_column(style="white")
            for canonical, aliases, desc, _cat in rows:
                table.add_row(canonical, aliases or "—", desc)

            header = Text(cat, style=f"bold {BRAND_ACCENT}")
            groups.append(Group(header, table, Text("")))

        footer = Text()
        footer.append("Anything else you type is a message to the active agent.\n",
                      style="dim italic")
        footer.append("Esc-Enter", style=BRAND_DIM)
        footer.append(" inserts newline  ·  ", style="dim")
        footer.append("Ctrl-C", style=BRAND_DIM)
        footer.append(" abort step  ·  ", style="dim")
        footer.append("Ctrl-D", style=BRAND_DIM)
        footer.append(" exit", style="dim")

        self.console.print()
        self.console.print(
            Panel(
                Padding(Group(*groups, footer), (0, 1)),
                title=Text("Commands", style=f"bold {BRAND_PRIMARY}"),
                title_align="left",
                border_style=BRAND_MUTED,
                box=ROUNDED,
                expand=False,
            )
        )

    def render_status_panel(
        self,
        *,
        phase: str | None,
        active_role: str | None,
        tokens: int,
        cost_usd: float,
        retries: int,
        max_retries: int,
        artifacts: dict[str, bool] | None = None,
        model_label: str | None = None,
    ) -> None:
        """Render `/status` — a compact at-a-glance view of the build state.

        Args:
            phase: Current pipeline phase (e.g. "design", "development").
            active_role: Role key of the agent currently working / waiting.
            tokens: Total tokens spent so far.
            cost_usd: Total dollar cost so far.
            retries: Number of QA-triggered dev retries used.
            max_retries: Retry budget.
            artifacts: Optional map of artifact name -> exists (e.g.
                {"PRD": True, "Architecture": False, "Tests": False}).
            model_label: Optional "provider:model" string.
        """
        # Left column: build state
        left = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
        left.add_column(style="dim", no_wrap=True)
        left.add_column(style="white")

        if phase:
            left.add_row("Phase",  Text(phase, style=f"bold {BRAND_PRIMARY}"))
        if active_role:
            label, color = _AGENT_STYLES.get(active_role, (active_role, "white"))
            left.add_row("Agent", Text(label, style=f"bold {color}"))
        if model_label:
            left.add_row("Model",  Text(model_label, style="white"))

        retry_color = (
            "red" if retries >= max_retries
            else "yellow" if retries > 0
            else "green"
        )
        left.add_row(
            "Retries",
            Text(f"{retries}/{max_retries}", style=f"bold {retry_color}"),
        )
        left.add_row("Tokens", Text(f"{tokens:,}", style="white"))
        left.add_row("Cost",   Text(f"${cost_usd:.4f}", style="white"))

        # Right column: artifact checklist (skipped if not provided)
        right_renderable: Any | None = None
        if artifacts:
            right = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
            right.add_column(no_wrap=True)
            right.add_column(no_wrap=True)
            for name, present in artifacts.items():
                symbol = "✓" if present else "·"
                color = "green" if present else "dim"
                right.add_row(
                    Text(symbol, style=f"bold {color}"),
                    Text(name, style="white" if present else "dim"),
                )
            right_renderable = right

        body = (
            Columns([left, right_renderable], padding=(0, 4), expand=False)
            if right_renderable is not None
            else left
        )

        self.console.print()
        self.console.print(
            Panel(
                Padding(body, (0, 1)),
                title=Text("Status", style=f"bold {BRAND_PRIMARY}"),
                title_align="left",
                border_style=BRAND_MUTED,
                box=ROUNDED,
                expand=False,
            )
        )

    def render_cost_table(
        self,
        per_role: dict[str, tuple[int, int, float]],
        total_tokens: int,
        total_cost_usd: float,
    ) -> None:
        """Render `/cost` — a per-role breakdown table.

        Args:
            per_role: Mapping role_key -> (input_tokens, output_tokens, cost_usd).
                Roles with zero activity should be omitted by the caller.
            total_tokens: Sum of input+output across all roles.
            total_cost_usd: Sum of cost across all roles.
        """
        if not per_role:
            # Empty state — collapse into a one-liner so we don't print an empty panel.
            self.render_status(
                f"Tokens: {total_tokens:,}  ·  Cost: ${total_cost_usd:.4f}"
            )
            return

        table = Table(
            box=SIMPLE,
            show_header=True,
            header_style=f"bold {BRAND_DIM}",
            padding=(0, 1),
            expand=False,
        )
        table.add_column("Agent", style="white", no_wrap=True)
        table.add_column("Input", justify="right", style="dim")
        table.add_column("Output", justify="right", style="dim")
        table.add_column("Cost", justify="right", style="white")

        for role, (in_tok, out_tok, cost) in per_role.items():
            label, color = _AGENT_STYLES.get(role, (role, "white"))
            table.add_row(
                Text(label, style=color),
                f"{in_tok:,}",
                f"{out_tok:,}",
                f"${cost:.4f}",
            )

        # Total row
        table.add_section()
        table.add_row(
            Text("Total", style=f"bold {BRAND_PRIMARY}"),
            "",
            f"{total_tokens:,}",
            Text(f"${total_cost_usd:.4f}", style=f"bold {BRAND_PRIMARY}"),
        )

        self.console.print()
        self.console.print(
            Panel(
                table,
                title=Text("Cost", style=f"bold {BRAND_PRIMARY}"),
                title_align="left",
                border_style=BRAND_MUTED,
                box=ROUNDED,
                expand=False,
            )
        )

    # ---- Phase breadcrumb -------------------------------------------------

    # Pipeline stages in order. Each entry is (label, role_key it represents).
    _BREADCRUMB_STAGES: ClassVar[list[tuple[str, str]]] = [
        ("PM",        "product_manager"),
        ("Architect", "architect"),
        ("Devs",      "frontend_dev"),   # represents the parallel dev fan-out
        ("QA",        "qa_engineer"),
        ("DevOps",    "devops_engineer"),
    ]

    def render_phase_breadcrumb(self, active_role: str | None) -> None:
        """Render a single-line pipeline breadcrumb: PM → Architect → Devs → QA → DevOps.

        The stage matching `active_role` is highlighted; earlier stages are
        rendered as completed (✓), later stages as pending (dim).
        """
        if self.plain:
            return

        # Devs covers both frontend_dev and backend_dev — collapse.
        norm = "frontend_dev" if active_role == "backend_dev" else active_role

        # Find the active index. -1 if not in the pipeline (e.g. supervisor).
        idx = -1
        for i, (_label, role) in enumerate(self._BREADCRUMB_STAGES):
            if role == norm:
                idx = i
                break

        line = Text()
        for i, (label, _role) in enumerate(self._BREADCRUMB_STAGES):
            if idx == -1:
                # No clear active stage — render everything dim.
                style = "dim"
                glyph = "·"
            elif i < idx:
                style = "green"
                glyph = "✓"
            elif i == idx:
                style = f"bold {BRAND_PRIMARY}"
                glyph = "●"
            else:
                style = "dim"
                glyph = "○"
            line.append(f" {glyph} ", style=style)
            line.append(label, style=style)
            if i < len(self._BREADCRUMB_STAGES) - 1:
                line.append("  →", style="dim")

        self.console.print(Padding(line, (0, 0, 1, 2)))
