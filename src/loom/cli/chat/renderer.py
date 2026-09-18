"""Rich-based renderer for the chat REPL.

A deliberately restrained, premium look: near-monochrome on a dark ground with a
single soft accent, generous whitespace, and one quiet nod to the name — a woven
"thread" hairline. No rainbows, no boxes-everywhere.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, ClassVar

from rich.box import ROUNDED, Box
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Palette — monochrome + one soft accent
# ---------------------------------------------------------------------------
C_INK = "#ecedf0"  # primary text
C_SOFT = "#a2a7b0"  # secondary text
C_MUTED = "#6a707a"  # labels / tertiary
C_FAINT = "#454a53"  # dim hints / dividers
C_LINE = "#2a2e36"  # borders / dividers
C_ACCENT = "#c9b68c"  # the single accent — soft champagne
C_ACCENT_HI = "#e6d9b0"  # light gold (sheen highlight)
C_ACCENT_LO = "#a68f63"  # deep gold (sheen low)
C_RAIL = "#5a4f38"  # dim gold thread (message rails)
C_OK = "#8fb08a"  # muted sage (success)
C_WARN = "#cbae74"  # muted amber (warning)
C_ERR = "#c58a8a"  # muted rose (error)

# A narrow warm sheen used on the wordmark — gold foil, not a rainbow.
WARM = [C_ACCENT_HI, C_ACCENT, C_ACCENT_LO, C_ACCENT]


def _warm(pos: float) -> str:
    """Interpolate the warm gold sheen (pos 0..1)."""
    pos = max(0.0, min(1.0, pos))
    x = pos * (len(WARM) - 1)
    i = min(int(x), len(WARM) - 2)
    t = x - i
    a = tuple(int(WARM[i][k : k + 2], 16) for k in (1, 3, 5))
    b = tuple(int(WARM[i + 1][k : k + 2], 16) for k in (1, 3, 5))
    r, g, bl = (round(a[j] + (b[j] - a[j]) * t) for j in range(3))
    return f"#{r:02x}{g:02x}{bl:02x}"


# Back-compat aliases (referenced by a few older call sites / tests).
BRAND_PRIMARY = f"bold {C_ACCENT}"
BRAND_ACCENT = f"bold {C_ACCENT}"
BRAND_DIM = f"dim {C_SOFT}"
BRAND_MUTED = C_MUTED

# Agent identity is name-only now (monochrome). The tuple shape is kept for
# call-site compatibility; the colour is unused in the restrained theme.
_AGENT_STYLES: dict[str, tuple[str, str, str]] = {
    "product_manager": ("◇", "Product Manager", C_ACCENT),
    "architect": ("◇", "Architect", C_ACCENT),
    "frontend_dev": ("◇", "Frontend Dev", C_ACCENT),
    "backend_dev": ("◇", "Backend Dev", C_ACCENT),
    "code_reviewer": ("◇", "Code Reviewer", C_ACCENT),
    "qa_engineer": ("◇", "QA Engineer", C_ACCENT),
    "devops_engineer": ("◇", "DevOps", C_ACCENT),
    "supervisor": ("◇", "Supervisor", C_ACCENT),
}

# Slash-command categories all share the accent now (kept for input.py sync).
CAT_COLORS = {"session": C_ACCENT, "workflow": C_ACCENT, "artifacts": C_ACCENT, "config": C_ACCENT}

# A box that draws ONLY a thin left rail — a quiet gutter beside a message.
LEFT_RAIL = Box("    \n▏   \n    \n▏   \n    \n    \n▏   \n    \n")


def _agent(role_key: str) -> tuple[str, str, str]:
    """(mark, label, colour) for a role, with a safe fallback."""
    return _AGENT_STYLES.get(role_key, ("◇", role_key, C_ACCENT))


def _thread(width: int, reveal: float = 1.0) -> Text:
    """The one flourish: a fine woven hairline that starts as a lit accent thread
    and settles into a dim rule. ``reveal`` (0..1) draws it left→right."""
    out = Text()
    lit = round(reveal * width)
    for i in range(width):
        if i >= lit:
            break
        # a short bright head, fading back into a faint rule
        if lit - i <= 2 and reveal < 1.0:
            out.append("─", style=f"bold {C_ACCENT}")
        elif i < 10:
            out.append("─", style=C_ACCENT)
        else:
            out.append("─", style=C_FAINT)
    return out


# A compact, flat wordmark — "loom" in a clean half-block font, one accent colour.
_WM = [
    "█    ▄▄▄  ▄▄▄  █▄ ▄█",
    "█    █ █  █ █  █ █ █",
    "█▄▄  ▀▀▀  ▀▀▀  █   █",
]


def _wordmark() -> Text:
    """The wordmark with a subtle horizontal gold sheen (foil, not rainbow)."""
    width = max(len(line) for line in _WM)
    out = Text()
    for i, line in enumerate(_WM):
        for c, ch in enumerate(line):
            if ch == " ":
                out.append(" ")
            else:
                out.append(ch, style=f"bold {_warm(c / width)}")
        if i < len(_WM) - 1:
            out.append("\n")
    return out


class _ThinkingIndicator:
    """A quiet loading line: a single braille spinner + label + elapsed seconds."""

    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str) -> None:
        self.message = message
        self._start = time.monotonic()
        self._frame = itertools.count()

    def __rich__(self) -> Text:
        i = next(self._frame)
        line = Text("  ")
        line.append(self._FRAMES[i % len(self._FRAMES)], style=C_ACCENT)
        line.append(f"  {self.message}", style=C_SOFT)
        elapsed = time.monotonic() - self._start
        if elapsed >= 1:
            line.append(f"   {elapsed:.0f}s", style=C_FAINT)
        return line


class ChatRenderer:
    """Renders chat output to a rich Console."""

    def __init__(self, console: Console | None = None, plain: bool = False) -> None:
        self.console = console or Console(highlight=False, soft_wrap=True)
        self.plain = plain
        self._first_agent_render = True

    # ---- Banner / footer ------------------------------------------------

    def render_banner(self, version: str, model_label: str) -> None:
        """Render a minimal, premium welcome card."""
        if self.plain:
            self.console.print("Loom", style="bold")
            self.console.print(f"v{version} · {model_label}", style="dim")
            self.console.print("Type your idea, or /help for commands.")
            self.console.print()
            return

        if getattr(self.console, "is_terminal", False):
            self._animate_intro()

        self.console.print()
        self.console.print(self._banner_card(version, model_label))
        self.console.print()

    def _banner_card(self, version: str, model_label: str) -> Panel:
        cwd = os.getcwd()
        home = os.path.expanduser("~")
        if cwd.startswith(home):
            cwd = "~" + cwd[len(home) :]

        def kv(key: str, val: str, val_style: str = C_SOFT) -> Text:
            t = Text(f"{key:<7}", style=C_MUTED)
            t.append(val, style=val_style)
            return t

        # Left column — brand + environment.
        left = Group(
            _wordmark(),
            _thread(19),
            Text(""),
            Text("your autonomous software team", style=C_SOFT),
            Text("idea in — working, tested build out", style=C_MUTED),
            Text(""),
            kv("model", model_label),
            kv("dir", cwd),
        )

        # Right column — how to start + the cast (name-only, no colour noise).
        def bullet(s: str) -> Text:
            t = Text("· ", style=C_ACCENT)
            t.append(s, style=C_SOFT)
            return t

        team_rows = []
        row: Text | None = None
        for i, (_key, (mark, label, _c)) in enumerate(
            (k, v) for k, v in _AGENT_STYLES.items() if k != "supervisor"
        ):
            if i % 2 == 0:
                row = Text()
                team_rows.append(row)
            assert row is not None
            row.append(f"{mark} ", style=C_ACCENT)
            row.append(f"{label:<16}", style=C_SOFT)

        right = Group(
            Text("GETTING STARTED", style=f"bold {C_ACCENT}"),
            bullet("Type an idea — the team scopes, builds & tests it"),
            bullet("/help  ·  /plan to preview cost  ·  /status"),
            Text(""),
            Text("THE TEAM", style=f"bold {C_ACCENT}"),
            *team_rows,
        )

        foot = Text("Type an idea to begin", style=C_MUTED)
        foot.append("      ", style=C_FAINT)
        foot.append("Ctrl-D", style=C_MUTED)
        foot.append(" to exit", style=C_FAINT)

        # Two columns on wide terminals; stack to one column on narrow ones so it
        # never overflows (e.g. an 80-col session).
        if self.console.width >= 96:
            grid = Table.grid(padding=(0, 7))
            grid.add_column()
            grid.add_column()
            grid.add_row(left, right)
            body: Any = Group(grid, _thread(58), foot)
        else:
            body = Group(left, Text(""), right, Text(""), _thread(40), foot)

        title = Text(" loom ", style=f"bold {C_ACCENT}")
        title.append(f"v{version} ", style=C_FAINT)
        return Panel(
            Padding(body, (1, 4)),
            title=title,
            title_align="left",
            border_style=C_LINE,
            box=ROUNDED,
            padding=0,
        )

    def _animate_intro(self) -> None:
        """A quiet thread weaves across, then the card lands. Interruptible."""
        try:
            with Live(
                Text(""), console=self.console, refresh_per_second=60, transient=True
            ) as live:
                self.console.print()
                for k in range(21):
                    live.update(Padding(_thread(40, k / 20), (1, 0, 1, 4)))
                    time.sleep(0.02)
        except (KeyboardInterrupt, Exception):
            return

    def render_completion(
        self,
        output_dir: str,
        total_cost: float,
        total_tokens: int,
        *,
        test_report: Any | None = None,
        review_report: Any | None = None,
        files: int | None = None,
    ) -> None:
        """Render the build-complete summary as a quiet section."""

        def row(body: Text, label: str, value: str, style: str) -> None:
            body.append(f"{label:<8}", style=C_MUTED)
            body.append(f"{value}\n", style=style)

        body = Text()
        for i, (label, _role) in enumerate(self._BREADCRUMB_STAGES):
            body.append("✓ ", style=C_OK)
            body.append(label, style=C_SOFT)
            if i < len(self._BREADCRUMB_STAGES) - 1:
                body.append("  ·  ", style=C_LINE)
        body.append("\n\n")

        row(body, "Output", output_dir, C_ACCENT)
        if files is not None:
            row(body, "Files", str(files), C_INK)
        if test_report is not None:
            # A stubbed report means no sandbox was available and nothing ran -
            # showing a pass count here would be a straight lie.
            if getattr(test_report, "is_stub", False):
                row(body, "Tests", "NOT RUN - no sandbox available", C_WARN)
            else:
                passed = getattr(test_report, "passed", 0)
                total = getattr(test_report, "total", 0)
                ok = passed == total and total > 0
                row(body, "Tests", f"{passed}/{total} passing", C_OK if ok else C_WARN)
        if review_report is not None:
            approved = getattr(review_report, "approved", False)
            row(
                body,
                "Review",
                "approved" if approved else "shipped with notes",
                C_OK if approved else C_WARN,
            )
        row(body, "Tokens", f"{total_tokens:,}", C_INK)
        row(body, "Cost", f"${total_cost:.4f}", C_INK)
        body.append("\n")
        body.append(f"{'Next':<8}", style=C_MUTED)
        body.append(f"cd {output_dir} && docker compose up", style=C_ACCENT)

        unverified = test_report is not None and getattr(test_report, "is_stub", False)
        subtitle = (
            "generated, but untested - no sandbox was available"
            if unverified
            else "your project is ready to run"
        )
        self._section("Build complete", subtitle, body)

    def render_error(self, message: str, hint: str | None = None) -> None:
        """Render a quiet error section."""
        self.console.print()
        head = Text("✕ ", style=f"bold {C_ERR}")
        head.append("error", style=f"bold {C_ERR}")
        self.console.print(head)
        body = Text(message, style=C_INK)
        if hint:
            body.append(f"\n{hint}", style=C_FAINT)
        self._rail(body)

    # ---- Per-turn rendering ---------------------------------------------

    def render_user_message(self, text: str) -> None:
        """Echo the user's message — only in plain mode."""
        if self.plain:
            self.console.print(f"You > {text}", style=C_ACCENT)

    def render_agent_speaker(self, role_key: str) -> None:
        """Render the speaker: a small accent mark + the agent's name."""
        mark, label, _ = _agent(role_key)
        self.console.print()
        if self.plain:
            self.console.print(f"{label}:", style="bold")
            return
        line = Text(f"{mark} ", style=C_ACCENT)
        line.append(label, style=f"bold {C_INK}")
        line.append("  ", style=C_LINE)
        line.append("─" * max(4, 30 - len(label)), style=C_LINE)  # trailing hairline
        self.console.print(line)

    def render_agent_message(self, role_key: str, text: str) -> None:
        """Render an agent message in a quiet left-rail thread."""
        if self.plain:
            self.console.print(text)
            return
        self._rail(text)

    def _rail(self, content: Any) -> None:
        """Print text/markdown inside the thin left-rail."""
        if isinstance(content, str):
            try:
                content = Markdown(content)
            except Exception:
                content = Text(content, style=C_INK)
        self.console.print(self._rail_panel(content))

    def _rail_panel(self, content: Any) -> Panel:
        return Panel(content, box=LEFT_RAIL, border_style=C_RAIL, padding=(0, 2), expand=True)

    async def render_agent_message_animated(
        self,
        role_key: str,
        text: str,
        chars_per_second: int = 260,
    ) -> None:
        """Typewriter reveal inside the rail, then settle into markdown."""
        if self.plain:
            self.console.print(text)
            return
        if not text or not text.strip():
            return

        chunk = max(1, chars_per_second // 60)
        delay = chunk / chars_per_second
        with Live(
            self._rail_panel(Text("")),
            console=self.console,
            refresh_per_second=60,
            transient=True,
        ) as live:
            for i in range(0, len(text), chunk):
                revealed = Text(text[: i + chunk], style=C_INK)
                revealed.append(" ▌", style=C_ACCENT)
                live.update(self._rail_panel(revealed))
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    break
        self._rail(text)

    @contextmanager
    def thinking(self, message: str = "thinking") -> Iterator[None]:
        """Show a quiet spinner while a block runs."""
        if self.plain:
            self.console.print(f"  · {message}…", style="dim italic")
            yield
            return
        with Live(
            _ThinkingIndicator(message),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        ):
            yield

    def render_status(self, message: str) -> None:
        """Render a transient status line."""
        self.console.print()
        self.console.print(Text(f"  ⠋ {message}", style=f"italic {C_MUTED}"))

    def render_turn_separator(self) -> None:
        """A faint hairline between major conversation turns."""
        if self.plain:
            return
        self.console.print()
        self.console.print(Padding(Text("─" * 24, style=C_LINE), (0, 0, 0, 2)))

    # ---- Artifact sections ----------------------------------------------

    def _section(self, title: str, subtitle: str, body: Text) -> None:
        """A quiet artifact section: an accent-marked heading + a rail body."""
        self.console.print()
        head = Text("◇ ", style=C_ACCENT)
        head.append(title, style=f"bold {C_INK}")
        if subtitle:
            head.append(f"  {subtitle}", style=C_FAINT)
        used = len(title) + (len(subtitle) + 2 if subtitle else 0)
        head.append("  ", style=C_LINE)
        head.append("─" * max(4, 30 - used), style=C_LINE)
        self.console.print(head)
        self._rail(body)

    def render_prd_panel(self, prd: Any) -> None:
        if prd is None:
            return
        body = Text(prd.project_name, style=f"bold {C_INK}")
        body.append("\n")
        body.append(prd.one_liner, style=C_SOFT)
        body.append("\n\nRequired features", style=C_MUTED)
        for feat in prd.must_have_features:
            body.append("\n  · ", style=C_ACCENT)
            body.append(feat, style=C_INK)
        if prd.user_stories:
            count = len(prd.user_stories)
            body.append(f"\n\n{count} user stor{'y' if count == 1 else 'ies'}", style=C_FAINT)
        self._section("PRD", prd.project_slug, body)

    def render_architecture_panel(self, arch: Any) -> None:
        if arch is None:
            return
        body = Text("Stack", style=C_MUTED)
        for tech in arch.stack:
            body.append(f"\n  {tech.layer:<9}", style=C_FAINT)
            body.append(tech.technology, style=C_INK)
            if tech.version:
                body.append(f"  {tech.version}", style=C_FAINT)
        body.append(
            f"\n\n{len(arch.api_endpoints)} endpoints   ·   {len(arch.components)} components",
            style=C_FAINT,
        )
        self._section("Architecture", "", body)

    def render_review_panel(self, report: Any) -> None:
        if report is None:
            return
        approved = getattr(report, "approved", False)
        issues = getattr(report, "issues", []) or []
        summary = getattr(report, "summary", "")

        body = Text()
        if approved:
            body.append("Approved", style=f"bold {C_OK}")
        else:
            body.append("Changes requested", style=f"bold {C_WARN}")
            if getattr(report, "escalate_to_architect", False):
                body.append("   → escalated to Architect", style=C_FAINT)
        if summary:
            body.append(f"\n{summary}", style=C_SOFT)

        sev = {"critical": f"bold {C_ERR}", "major": f"bold {C_WARN}", "minor": C_FAINT}
        for issue in issues:
            s = str(getattr(issue, "severity", "minor"))
            file = getattr(issue, "file", "") or "(cross-cutting)"
            desc = getattr(issue, "description", "")
            body.append(f"\n  {s:<8} ", style=sev.get(s, C_SOFT))
            body.append(file, style=C_INK)
            body.append(f"  {desc}", style=C_FAINT)
        self._section("Code Review", "", body)

    def render_progress_parallel(self, statuses: dict[str, str]) -> None:
        """Render a snapshot of parallel agent statuses."""
        self.console.print()
        for role, status in statuses.items():
            _, label, _ = _agent(role)
            if status == "running":
                glyph, style = "⠋", C_ACCENT
            elif status == "done":
                glyph, style = "✓", C_OK
            else:
                glyph, style = "·", C_FAINT
            line = Text(f"  {glyph}  ", style=style)
            line.append(label, style=C_INK if status != "pending" else C_FAINT)
            line.append(f"   {status}", style=C_FAINT)
            self.console.print(line)

    def render_test_report(self, report: Any) -> None:
        if report is None:
            return
        passed = getattr(report, "passed", 0)
        total = getattr(report, "total", 0)
        if passed == total and total > 0:
            glyph, color = "✓", C_OK
        elif total == 0:
            glyph, color = "·", C_FAINT
        else:
            glyph, color = "✕", C_ERR
        self.console.print()
        self.console.print(
            Text(f"  {glyph}  Tests: {passed}/{total} passing", style=f"bold {color}")
        )

    def clear(self) -> None:
        """Clear the terminal screen. Transcript on disk is untouched."""
        self.console.clear()

    # ---- Command panels --------------------------------------------------

    def _panel(self, body: Any, title: str) -> None:
        """A quiet titled panel used by /help, /status, /cost."""
        t = Text("◇ ", style=C_ACCENT)
        t.append(title, style=f"bold {C_INK}")
        self.console.print()
        self.console.print(
            Panel(
                Padding(body, (0, 1)),
                title=t,
                title_align="left",
                border_style=C_LINE,
                box=ROUNDED,
                expand=False,
            )
        )

    def render_help(self, entries: list[tuple[str, str, str, str]]) -> None:
        """Render the /help command reference."""
        if self.plain:
            for canonical, aliases, desc, _cat in entries:
                line = canonical + (f"  ({aliases})" if aliases else "")
                self.console.print(f"  {line:<32} {desc}")
            self.console.print("\n  Anything else you type is a message to the active agent.")
            return

        by_cat: dict[str, list[tuple[str, str, str, str]]] = {}
        for row in entries:
            by_cat.setdefault(row[3], []).append(row)

        groups: list[Any] = []
        for cat, rows in by_cat.items():
            table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 2))
            table.add_column(no_wrap=True)
            table.add_column(no_wrap=True)
            table.add_column()
            for canonical, aliases, desc, _cat in rows:
                cmd = Text(canonical, style=f"bold {C_INK}")
                table.add_row(
                    cmd,
                    Text(aliases, style=C_FAINT) if aliases else Text(""),
                    Text(desc, style=C_SOFT),
                )
            header = Text(cat.upper(), style=f"bold {C_ACCENT}")
            groups.append(Group(header, Padding(table, (0, 0, 1, 1))))

        footer = Text(
            "Anything else you type goes to the active agent.\n", style=f"italic {C_FAINT}"
        )
        for k, sep in [("Esc-Enter", " newline   "), ("Ctrl-C", " abort   "), ("Ctrl-D", " exit")]:
            footer.append(k, style=C_MUTED)
            footer.append(sep, style=C_FAINT)

        self._panel(Group(*groups, footer), "Commands")

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
        """Render `/status` — a quiet at-a-glance view of the build state."""
        left = Table(box=None, show_header=False, pad_edge=False, padding=(0, 2))
        left.add_column(style=C_MUTED, no_wrap=True)
        left.add_column()

        if phase:
            left.add_row("phase", Text(phase, style=f"bold {C_ACCENT}"))
        if active_role:
            _, label, _ = _agent(active_role)
            left.add_row("agent", Text(label, style=f"bold {C_INK}"))
        if model_label:
            left.add_row("model", Text(model_label, style=C_SOFT))
        retry_color = C_ERR if retries >= max_retries else C_WARN if retries > 0 else C_OK
        left.add_row("retries", Text(f"{retries}/{max_retries}", style=f"bold {retry_color}"))
        left.add_row("tokens", Text(f"{tokens:,}", style=C_INK))
        left.add_row("cost", Text(f"${cost_usd:.4f}", style=C_INK))

        right_renderable: Any | None = None
        if artifacts:
            right = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
            right.add_column(no_wrap=True)
            for name, present in artifacts.items():
                chip = Text("✓ " if present else "· ", style=C_OK if present else C_FAINT)
                chip.append(name, style=C_INK if present else C_FAINT)
                right.add_row(chip)
            right_renderable = Group(Text("artifacts", style=C_MUTED), Text(""), right)

        body = (
            Columns([left, right_renderable], padding=(0, 6), expand=False)
            if right_renderable is not None
            else left
        )
        self._panel(body, "Status")

    def render_cost_table(
        self,
        per_role: dict[str, tuple[int, int, float]],
        total_tokens: int,
        total_cost_usd: float,
    ) -> None:
        """Render `/cost` — a per-role breakdown with a quiet share bar."""
        if not per_role:
            self.render_status(f"Tokens: {total_tokens:,}  ·  Cost: ${total_cost_usd:.4f}")
            return

        table = Table(box=None, show_header=True, header_style=C_MUTED, padding=(0, 2))
        table.add_column("agent", no_wrap=True)
        table.add_column("share", no_wrap=True)
        table.add_column("tokens", justify="right")
        table.add_column("cost", justify="right")

        max_cost = max((c for _, _, c in per_role.values()), default=0.0) or 1.0
        for role, (in_tok, out_tok, cost) in per_role.items():
            _, label, _ = _agent(role)
            fill = round(cost / max_cost * 16)
            bar = Text("▬" * fill, style=C_ACCENT)
            bar.append("▬" * (16 - fill), style=C_LINE)
            table.add_row(
                Text(label, style=C_INK),
                bar,
                Text(f"{in_tok + out_tok:,}", style=C_SOFT),
                Text(f"${cost:.4f}", style=C_INK),
            )
        table.add_section()
        table.add_row(
            Text("Total", style=f"bold {C_ACCENT}"),
            "",
            Text(f"{total_tokens:,}", style=f"bold {C_INK}"),
            Text(f"${total_cost_usd:.4f}", style=f"bold {C_ACCENT}"),
        )
        self._panel(table, "Cost")

    # ---- Phase breadcrumb -------------------------------------------------

    _BREADCRUMB_STAGES: ClassVar[list[tuple[str, str]]] = [
        ("PM", "product_manager"),
        ("Architect", "architect"),
        ("Devs", "frontend_dev"),
        ("Review", "code_reviewer"),
        ("QA", "qa_engineer"),
        ("DevOps", "devops_engineer"),
    ]

    def render_phase_breadcrumb(self, active_role: str | None) -> None:
        """Render a single-line pipeline breadcrumb, active stage highlighted."""
        if self.plain:
            return
        norm = "frontend_dev" if active_role == "backend_dev" else active_role
        idx = -1
        for i, (_label, role) in enumerate(self._BREADCRUMB_STAGES):
            if role == norm:
                idx = i
                break

        line = Text()
        for i, (label, _role) in enumerate(self._BREADCRUMB_STAGES):
            if idx != -1 and i < idx:
                style, glyph = C_OK, "✓"
            elif i == idx:
                style, glyph = f"bold {C_ACCENT}", "●"
            else:
                style, glyph = C_FAINT, "○"
            line.append(f"{glyph} ", style=style)
            line.append(label, style=style)
            if i < len(self._BREADCRUMB_STAGES) - 1:
                line.append("   ·   ", style=C_LINE)
        self.console.print(Padding(line, (0, 0, 1, 2)))
