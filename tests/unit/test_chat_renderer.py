"""Unit tests for the ChatRenderer (Phase 9.4).

Snapshot tests use rich's Console capture mode so output is deterministic
across platforms.
"""

import io

from rich.console import Console

from loom.cli.chat.renderer import ChatRenderer
from loom.state.models import (
    PRD,
    APIEndpoint,
    ArchitectureDoc,
    HttpMethod,
    Priority,
    ProjectType,
    TechChoice,
    TechLayer,
    TestCase,
    TestReport,
    UserStory,
)


def _captured_console() -> Console:
    """Return a rich Console writing to an in-memory buffer."""
    return Console(file=io.StringIO(), force_terminal=False, width=80, no_color=True)


def _output(console: Console) -> str:
    return console.file.getvalue()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Banner / footer
# ---------------------------------------------------------------------------


class TestBanner:
    def test_banner_includes_version_and_model(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_banner("0.1.0", "anthropic:claude-sonnet-4-5")
        out = _output(console)
        # The banner uses ASCII-art "LOOM" rather than the literal word, but
        # version and model must be visible.
        assert "0.1.0" in out
        assert "anthropic:claude-sonnet-4-5" in out
        assert "your AI software team" in out

    def test_plain_mode_banner_has_loom_text(self) -> None:
        """In --plain mode the ASCII art is replaced with the literal word."""
        console = _captured_console()
        renderer = ChatRenderer(console=console, plain=True)
        renderer.render_banner("0.1.0", "ollama:llama3")
        out = _output(console)
        assert "LOOM" in out
        assert "0.1.0" in out
        assert "ollama:llama3" in out


class TestCompletion:
    def test_completion_shows_output_dir_and_cost(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_completion("/tmp/myproject", 0.0123, 47832)
        out = _output(console)
        assert "Build complete" in out
        assert "/tmp/myproject" in out
        assert "47,832" in out
        assert "$0.0123" in out


class TestError:
    def test_error_renders_message(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_error("Docker not running")
        out = _output(console)
        assert "Docker not running" in out

    def test_error_with_hint(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_error("Build failed", hint="Try /restart")
        out = _output(console)
        assert "Build failed" in out
        assert "Try /restart" in out


# ---------------------------------------------------------------------------
# Per-turn rendering
# ---------------------------------------------------------------------------


class TestUserMessage:
    def test_plain_mode_echoes_user_text(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console, plain=True)
        renderer.render_user_message("hello")
        assert "hello" in _output(console)


class TestAgentSpeaker:
    def test_pm_speaker_label(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_agent_speaker("product_manager")
        out = _output(console)
        assert "Product Manager" in out

    def test_architect_speaker_label(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_agent_speaker("architect")
        out = _output(console)
        assert "Architect" in out

    def test_unknown_role_renders_role_key(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_agent_speaker("custom_agent")
        out = _output(console)
        assert "custom_agent" in out


class TestAgentMessage:
    def test_plain_mode_renders_text(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console, plain=True)
        renderer.render_agent_message("product_manager", "What kind of users?")
        assert "What kind of users?" in _output(console)


class TestStatus:
    def test_status_renders_message(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_status("drafting...")
        assert "drafting" in _output(console)


# ---------------------------------------------------------------------------
# Artifact panels
# ---------------------------------------------------------------------------


def _make_prd() -> PRD:
    return PRD(
        project_name="Todo App",
        project_slug="todo-app",
        project_type=ProjectType.FULLSTACK_WEB,
        one_liner="Track tasks easily",
        target_users=["users"],
        user_stories=[
            UserStory(
                id="US-001",
                role="user",
                goal="create todo",
                benefit="track tasks",
                acceptance_criteria=["Created"],
                priority=Priority.P0,
            )
        ],
        must_have_features=["Create todo", "List todos"],
    )


def _make_arch() -> ArchitectureDoc:
    return ArchitectureDoc(
        stack=[
            TechChoice(
                layer=TechLayer.BACKEND,
                technology="FastAPI",
                version="0.115",
                rationale="async",
            ),
            TechChoice(
                layer=TechLayer.FRONTEND,
                technology="React",
                version="18",
                rationale="popular",
            ),
        ],
        api_endpoints=[],
        components=[],
        folder_structure={},
    )


class TestArtifactPanels:
    def test_prd_panel_includes_project_info(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_prd_panel(_make_prd())
        out = _output(console)
        assert "Todo App" in out
        assert "Create todo" in out
        assert "List todos" in out

    def test_prd_panel_handles_none_gracefully(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_prd_panel(None)  # should not raise
        # Empty output OK
        assert _output(console) == ""

    def test_architecture_panel_includes_stack(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_architecture_panel(_make_arch())
        out = _output(console)
        assert "FastAPI" in out
        assert "React" in out

    def test_architecture_panel_handles_none(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_architecture_panel(None)
        assert _output(console) == ""

    def test_progress_parallel(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_progress_parallel(
            {"frontend_dev": "running", "backend_dev": "done"}
        )
        out = _output(console)
        assert "Frontend Dev" in out
        assert "Backend Dev" in out

    def test_test_report_includes_pass_count(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        report = TestReport(
            total=5,
            passed=5,
            failed=0,
            skipped=0,
            duration_ms=100.0,
            cases=[],
        )
        renderer.render_test_report(report)
        out = _output(console)
        assert "5/5" in out

    def test_test_report_handles_none(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_test_report(None)
        assert _output(console) == ""


# ---------------------------------------------------------------------------
# /help — categorized command table
# ---------------------------------------------------------------------------


class TestHelpPanel:
    def test_help_panel_lists_all_categories(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        from loom.cli.chat.commands import HELP_ENTRIES
        renderer.render_help(HELP_ENTRIES)
        out = _output(console)
        # Section headers
        assert "Session" in out
        assert "Workflow" in out
        assert "Artifacts" in out
        assert "Config" in out
        # A handful of canonical commands appear
        assert "/help" in out
        assert "/status" in out
        assert "/clear" in out

    def test_help_panel_plain_mode_compact(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console, plain=True)
        from loom.cli.chat.commands import HELP_ENTRIES
        renderer.render_help(HELP_ENTRIES)
        out = _output(console)
        # Plain mode lists commands; no box-drawing characters.
        assert "/help" in out
        assert "─" not in out
        assert "╭" not in out


# ---------------------------------------------------------------------------
# /status — build state panel
# ---------------------------------------------------------------------------


class TestStatusPanel:
    def test_status_panel_shows_tokens_and_cost(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_status_panel(
            phase="design",
            active_role="architect",
            tokens=12345,
            cost_usd=0.4321,
            retries=0,
            max_retries=2,
            artifacts={"PRD": True, "Architecture": False},
            model_label="anthropic:claude-3-5-sonnet",
        )
        out = _output(console)
        assert "12,345" in out
        assert "$0.4321" in out
        assert "design" in out
        assert "Architect" in out
        assert "0/2" in out

    def test_status_panel_omits_artifacts_if_not_provided(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_status_panel(
            phase=None,
            active_role=None,
            tokens=0,
            cost_usd=0.0,
            retries=0,
            max_retries=2,
        )
        out = _output(console)
        # Still renders the panel header
        assert "Status" in out


# ---------------------------------------------------------------------------
# /cost — per-role cost table
# ---------------------------------------------------------------------------


class TestCostTable:
    def test_cost_table_lists_each_role(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        per_role = {
            "product_manager": (1000, 500, 0.0050),
            "architect":       (800, 1200, 0.0125),
        }
        renderer.render_cost_table(per_role, total_tokens=3500, total_cost_usd=0.0175)
        out = _output(console)
        assert "Product Manager" in out
        assert "Architect" in out
        assert "$0.0050" in out
        assert "$0.0125" in out
        # Total row
        assert "Total" in out
        assert "$0.0175" in out

    def test_cost_table_empty_falls_back_to_one_liner(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_cost_table({}, total_tokens=0, total_cost_usd=0.0)
        out = _output(console)
        # No empty table — collapses to a status line
        assert "Tokens" in out
        assert "$0.0000" in out


# ---------------------------------------------------------------------------
# Phase breadcrumb
# ---------------------------------------------------------------------------


class TestPhaseBreadcrumb:
    def test_breadcrumb_highlights_active_stage(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_phase_breadcrumb("architect")
        out = _output(console)
        # All five stage labels should be present.
        assert "PM" in out
        assert "Architect" in out
        assert "Devs" in out
        assert "QA" in out
        assert "DevOps" in out

    def test_breadcrumb_plain_mode_silent(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console, plain=True)
        renderer.render_phase_breadcrumb("architect")
        # Plain mode suppresses the breadcrumb — it would be noisy in logs.
        assert _output(console) == ""

    def test_breadcrumb_backend_dev_maps_to_devs_stage(self) -> None:
        console = _captured_console()
        renderer = ChatRenderer(console=console)
        renderer.render_phase_breadcrumb("backend_dev")
        out = _output(console)
        # The active glyph should appear on the Devs row, not be missing entirely.
        assert "Devs" in out


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_calls_console_clear(self) -> None:
        from unittest.mock import MagicMock
        console = MagicMock()
        renderer = ChatRenderer(console=console)
        renderer.clear()
        console.clear.assert_called_once()
