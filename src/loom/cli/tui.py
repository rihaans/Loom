"""Textual TUI for Loom build visualization."""

import asyncio
from typing import Any, ClassVar

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, Log, Static

from loom._time import now_utc
from loom.config import LoomConfig
from loom.observability import BuildObserver, StreamEvent, StreamEventType
from loom.state.enums import AgentRole, Priority

# Agent display info
AGENT_INFO = {
    AgentRole.PRODUCT_MANAGER: ("PM", "blue"),
    AgentRole.ARCHITECT: ("ARCH", "green"),
    AgentRole.FRONTEND_DEV: ("FE", "cyan"),
    AgentRole.BACKEND_DEV: ("BE", "magenta"),
    AgentRole.QA: ("QA", "yellow"),
    AgentRole.DEVOPS: ("OPS", "red"),
    AgentRole.SUPERVISOR: ("MGR", "white"),
}


class AgentStatus(Static):
    """Widget showing status of a single agent."""

    status = reactive("idle")

    def __init__(self, agent: AgentRole, **kwargs: Any):
        super().__init__(**kwargs)
        self.agent = agent
        self.label, self.color = AGENT_INFO.get(agent, ("???", "white"))

    def render(self) -> Text:
        if self.status == "active":
            icon = "●"
            style = f"bold {self.color}"
        elif self.status == "done":
            icon = "✓"
            style = f"dim {self.color}"
        elif self.status == "error":
            icon = "✗"
            style = "bold red"
        else:
            icon = "○"
            style = "dim"

        return Text(f" {icon} {self.label} ", style=style)


class PipelineView(Static):
    """Shows the agent pipeline status."""

    def compose(self) -> ComposeResult:
        with Horizontal(id="pipeline"):
            for agent in [
                AgentRole.PRODUCT_MANAGER,
                AgentRole.ARCHITECT,
                AgentRole.FRONTEND_DEV,
                AgentRole.BACKEND_DEV,
                AgentRole.QA,
                AgentRole.DEVOPS,
            ]:
                yield AgentStatus(agent, id=f"agent-{agent.value}")
                yield Label(" → ", classes="arrow")

    def set_active(self, agent: AgentRole | None) -> None:
        """Set the active agent."""
        for child in self.query(AgentStatus):
            if agent and child.agent == agent:
                child.status = "active"
            elif child.status == "active":
                child.status = "done"

    def set_error(self, agent: AgentRole) -> None:
        """Mark an agent as errored."""
        for child in self.query(AgentStatus):
            if child.agent == agent:
                child.status = "error"


class StatsPanel(Static):
    """Shows build statistics."""

    tokens = reactive(0)
    cost = reactive(0.0)
    elapsed = reactive(0.0)

    def render(self) -> Text:
        return Text.from_markup(
            f"[bold]Tokens:[/bold] {self.tokens:,}  "
            f"[bold]Cost:[/bold] ${self.cost:.4f}  "
            f"[bold]Time:[/bold] {self.elapsed:.1f}s"
        )


class LiveOutput(Log):
    """Shows live LLM output."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs, highlight=True, markup=True)  # type: ignore[call-arg]


class EventLog(Log):
    """Shows event timeline."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs, highlight=True, markup=True)  # type: ignore[call-arg]

    def add_event(self, event: StreamEvent) -> None:
        """Add an event to the log."""
        time_str = event.timestamp.strftime("%H:%M:%S")

        if event.type == StreamEventType.NODE_START:
            agent_name = event.agent.value if event.agent else event.node
            self.write_line(f"[dim]{time_str}[/dim] [bold green]▶[/bold green] {agent_name}")
        elif event.type == StreamEventType.NODE_END:
            agent_name = event.agent.value if event.agent else event.node
            self.write_line(f"[dim]{time_str}[/dim] [bold blue]✓[/bold blue] {agent_name}")
        elif event.type == StreamEventType.ERROR:
            self.write_line(f"[dim]{time_str}[/dim] [bold red]✗[/bold red] {event.error}")
        elif event.type == StreamEventType.GRAPH_START:
            self.write_line(f"[dim]{time_str}[/dim] [bold]Build started[/bold]")
        elif event.type == StreamEventType.GRAPH_END:
            self.write_line(f"[dim]{time_str}[/dim] [bold]Build complete[/bold]")


class BuildApp(App):
    """Main TUI application for build visualization."""

    CSS = """
    #pipeline {
        height: 3;
        background: $surface;
        padding: 1;
    }

    .arrow {
        width: auto;
        color: $text-muted;
    }

    #main {
        height: 1fr;
    }

    #output-panel {
        width: 2fr;
        border: solid $primary;
        padding: 1;
    }

    #sidebar {
        width: 1fr;
    }

    #stats {
        height: 3;
        background: $surface;
        padding: 1;
    }

    #events {
        height: 1fr;
        border: solid $secondary;
        padding: 1;
    }

    Footer {
        background: $surface;
    }
    """

    BINDINGS: ClassVar[list[Any]] = [
        ("q", "quit", "Quit"),
        ("s", "toggle_stats", "Stats"),
        ("e", "toggle_events", "Events"),
    ]

    def __init__(
        self,
        description: str,
        config: LoomConfig,
        output_dir: str,
        interactive: bool = False,
    ):
        super().__init__()
        self.description = description
        self.config = config
        self.output_dir = output_dir
        self.interactive = interactive
        self.observer = BuildObserver()
        self.start_time = now_utc()
        self.result: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield PipelineView(id="pipeline-view")
        with Horizontal(id="main"):
            yield LiveOutput(id="output-panel")
            with Vertical(id="sidebar"):
                yield StatsPanel(id="stats")
                yield EventLog(id="events")
        yield Footer()

    async def on_mount(self) -> None:
        """Start the build when the app mounts."""
        self.title = f"Loom - {self.description[:40]}..."
        self.run_worker(self._run_build())

    async def _run_build(self) -> None:
        """Run the build with event streaming."""
        from loom.graph.builder import compile_graph
        from loom.graph.checkpoint import (
            create_memory_checkpointer,
            generate_thread_id,
            get_checkpoint_config,
        )
        from loom.state.enums import Phase

        pipeline = self.query_one(PipelineView)
        output = self.query_one("#output-panel", LiveOutput)
        events_log = self.query_one("#events", EventLog)
        stats = self.query_one("#stats", StatsPanel)

        # Set up observer callbacks
        self.observer.on(StreamEventType.NODE_START, lambda e: pipeline.set_active(e.agent))
        self.observer.on(StreamEventType.NODE_END, lambda e: None)
        self.observer.on(
            StreamEventType.LLM_TOKEN,
            lambda e: output.write(e.token or ""),  # type: ignore[arg-type]
        )
        self.observer.on(
            StreamEventType.ERROR, lambda e: pipeline.set_error(e.agent) if e.agent else None
        )

        # All events go to event log
        for event_type in StreamEventType:
            self.observer.on(event_type, lambda e: events_log.add_event(e))

        # Create initial state
        initial_state = {
            "description": self.description,
            "phase": Phase.INIT,
            "interactive": self.interactive,
            "retry_count": 0,
            "max_retries": self.config.max_retries,
            "events": [],
            "costs": [],
            "code_files": {},
        }

        # Compile graph
        checkpointer = create_memory_checkpointer()
        graph = compile_graph(self.config, checkpointer=checkpointer)
        thread_id = generate_thread_id(self.description)
        run_config = get_checkpoint_config(thread_id)

        # Update elapsed time periodically
        async def update_stats() -> None:
            while True:
                elapsed = (now_utc() - self.start_time).total_seconds()
                stats.elapsed = elapsed
                await asyncio.sleep(0.5)

        stats_task = asyncio.create_task(update_stats())

        try:
            # Run with observation
            final_state = await self.observer.observe(graph, initial_state, run_config)
            self.result = final_state

            # Update final stats
            costs = final_state.get("costs", [])
            stats.tokens = sum(c.input_tokens + c.output_tokens for c in costs)
            stats.cost = sum(c.cost_usd for c in costs)

            # Check for success
            if final_state.get("error"):
                output.write_line(f"\n[bold red]Error:[/bold red] {final_state['error']}")
            else:
                output.write_line("\n[bold green]Build complete![/bold green]")

        except Exception as e:
            output.write_line(f"\n[bold red]Error:[/bold red] {e}")
        finally:
            stats_task.cancel()

    def action_toggle_stats(self) -> None:
        """Toggle stats panel visibility."""
        stats = self.query_one("#stats")
        stats.display = not stats.display

    def action_toggle_events(self) -> None:
        """Toggle events panel visibility."""
        events = self.query_one("#events")
        events.display = not events.display


def run_build_tui(
    description: str,
    config: LoomConfig,
    output_dir: str,
    interactive: bool = False,
) -> None:
    """Run the build TUI.

    Args:
        description: Project description.
        config: Loom configuration.
        output_dir: Output directory.
        interactive: Enable interactive mode.
    """
    app = BuildApp(description, config, output_dir, interactive)
    app.run()


class PlanRenderer:
    """Rich-based renderer for plan output."""

    def __init__(self, console: Console | None = None):
        """Initialize the plan renderer.

        Args:
            console: Optional Rich console. Creates one if not provided.
        """
        self.console = console or Console()

    def render(
        self,
        state: dict[str, Any],
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        """Render the plan to the console.

        Args:
            state: The agent state with PRD and architecture.
            provider: LLM provider for cost estimation.
            model: LLM model for cost estimation.
        """
        from loom.cost.estimator import estimate_build_cost, estimate_duration

        prd = state.get("prd")
        architecture = state.get("architecture")
        memory_context = state.get("memory_context")

        if prd is None:
            self.console.print("[red]No PRD available[/red]")
            return

        # Header panel
        project_name = getattr(prd, "project_name", "Unknown")
        one_liner = getattr(prd, "one_liner", "")
        self.console.print(
            Panel(
                f"[bold]{project_name}[/bold]\n{one_liner}",
                title="PLAN",
                border_style="cyan",
            )
        )

        # Scope (P0 features)
        self.console.print("\n[bold]Scope (P0)[/bold]")
        user_stories = getattr(prd, "user_stories", [])
        p0_count = 0
        for story in user_stories:
            priority = getattr(story, "priority", None)
            if priority == Priority.P0:
                goal = getattr(story, "goal", "")
                self.console.print(f"   * {goal}")
                p0_count += 1
        if p0_count == 0:
            must_have = getattr(prd, "must_have_features", [])
            for feature in must_have[:6]:
                self.console.print(f"   * {feature}")

        # Stack
        if architecture:
            self.console.print("\n[bold]Stack[/bold]")
            stack_table = Table(show_header=False, box=None, padding=(0, 1))
            stack_table.add_column(style="bold cyan", width=12)
            stack_table.add_column(width=25)
            stack_table.add_column(style="dim", width=40)

            stack = getattr(architecture, "stack", [])
            for tech in stack:
                layer = getattr(tech, "layer", "")
                technology = getattr(tech, "technology", "")
                version = getattr(tech, "version", "")
                rationale = getattr(tech, "rationale", "")

                layer_str = str(layer).replace("TechLayer.", "").title() if layer else ""
                tech_str = f"{technology}"
                if version and version != "latest":
                    tech_str += f" {version}"

                stack_table.add_row(
                    layer_str,
                    tech_str,
                    rationale[:40] + "..." if len(rationale) > 40 else rationale,
                )

            self.console.print(stack_table)

            # API Endpoints
            endpoints = getattr(architecture, "api_endpoints", [])
            if endpoints:
                self.console.print(f"\n[bold]API Endpoints ({len(endpoints)})[/bold]")
                for ep in endpoints[:8]:
                    method = getattr(ep, "method", "")
                    path = getattr(ep, "path", "")
                    description = getattr(ep, "description", "")
                    method_str = str(method).replace("HttpMethod.", "")
                    self.console.print(
                        f"   [bold]{method_str:6}[/bold] {path:30} {description[:30]}"
                    )
                if len(endpoints) > 8:
                    self.console.print(f"   [dim]... {len(endpoints) - 8} more[/dim]")

        # Data entities
        data_entities = getattr(prd, "data_entities", [])
        if data_entities:
            self.console.print("\n[bold]Data Entities[/bold]")
            for entity in data_entities[:5]:
                name = getattr(entity, "name", "")
                fields = getattr(entity, "fields", {})
                field_names = ", ".join(list(fields.keys())[:4])
                if len(fields) > 4:
                    field_names += ", ..."
                self.console.print(f"   [cyan]{name}[/cyan]  {field_names}")

        # Cost and duration estimates
        cost_low, cost_high = estimate_build_cost(state, provider, model)
        dur_low, dur_high = estimate_duration(state, provider)

        self.console.print()
        if cost_low == 0 and cost_high == 0:
            self.console.print("[bold]Estimated cost:[/bold] $0.00 (local model)")
        else:
            self.console.print(f"[bold]Estimated cost:[/bold] ${cost_low:.2f}-${cost_high:.2f}")

        dur_low_min = dur_low // 60
        dur_high_min = dur_high // 60
        self.console.print(f"[bold]Estimated time:[/bold] {dur_low_min}-{dur_high_min} min")

        # Memory context
        if memory_context:
            examples = getattr(memory_context, "examples", [])
            if examples:
                n = len(examples)
                self.console.print(
                    f"[bold]Memory:[/bold] {n} similar past build{'s' if n != 1 else ''} used as references"
                )
