"""Typer CLI application for Loom."""

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Spinner detection: cmd.exe and older Windows terminals don't render
# Braille spinner glyphs, so fall back to ASCII line spinner there.
_is_windows = sys.platform == "win32"


def _ensure_utf8_output() -> None:
    """Make stdout/stderr UTF-8 so redirected output isn't mojibake.

    On Windows, piping to a file gives stdout the ANSI code page (cp1252),
    which mangles the em-dashes and box glyphs used throughout Loom's output.
    Reconfiguring is a no-op where the encoding is already UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):  # pragma: no cover - detached/odd streams
            pass


_ensure_utf8_output()

app = typer.Typer(
    name="loom",
    help="Autonomous software development team built on LangGraph.",
    no_args_is_help=False,  # `loom` with no args opens the chat REPL
    invoke_without_command=True,
)

# Modern Windows Terminal / PowerShell support truecolor + Unicode natively, so
# we force terminal mode to keep the gradient logo - but only when stdout really
# is a TTY. Forcing it unconditionally made Rich animate into pipes and log
# files, emitting one spinner frame per redraw (hundreds of lines per build).
_stdout_is_tty = sys.stdout.isatty()
console = Console(
    force_terminal=True if _stdout_is_tty else None,
    color_system="truecolor" if _stdout_is_tty else None,
)

if TYPE_CHECKING:
    from loom.config import BuildResult, LoomConfig

# Subcommand groups
sandbox_app = typer.Typer(help="Sandbox management commands")
config_app = typer.Typer(help="Configuration commands")
memory_app = typer.Typer(help="Memory system commands")
cache_app = typer.Typer(help="Artifact cache commands")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(config_app, name="config")
app.add_typer(memory_app, name="memory")
app.add_typer(cache_app, name="cache")


@app.callback()
def main(
    ctx: typer.Context,
    plain: bool = typer.Option(False, "--plain", help="Disable rich rendering"),
    model: str | None = typer.Option(
        None, "--model", "-m", help="LLM model override for this session"
    ),
) -> None:
    """Loom — type `loom` to chat, or use one of the subcommands."""
    if ctx.invoked_subcommand is not None:
        return
    # No subcommand → launch the chat REPL
    from loom.cli.chat import ChatRenderer, ChatSession
    from loom.config import load_config

    config = load_config()
    if model:
        from loom.config import parse_llm_string

        config.llm_default = parse_llm_string(model)

    _preflight_or_exit(config)

    renderer = ChatRenderer(console=console, plain=plain)
    session = ChatSession(config=config, renderer=renderer)
    try:
        asyncio.run(session.run())
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")


def _preflight_or_exit(config: "LoomConfig") -> None:
    """Abort with a readable message when no LLM provider is usable."""
    from loom.llm.preflight import ProviderUnavailableError, check_provider

    try:
        check_provider(config.llm_default)
    except ProviderUnavailableError as e:
        console.print()
        console.print(f"[red]Cannot start:[/red] {e}")
        raise typer.Exit(1)


def _render_build_result(result: "BuildResult") -> None:
    """Print a build result, making test verification status unmissable.

    A build whose tests never actually ran is reported as such - we never let
    a stubbed QA report read like a passing test run.
    """
    console.print("\n[green][OK] Build complete![/green]")
    console.print(f"  Output: [cyan]{result.output_dir}[/cyan]")
    console.print(f"  Tokens: {result.total_tokens:,}")
    if result.total_cost_usd > 0:
        console.print(f"  Cost: ${result.total_cost_usd:.4f}")
    elif result.cost_status == "free":
        console.print("  Cost: $0.00 [dim](local model)[/dim]")
    else:
        console.print("  Cost: [dim]unknown - no published price for this model[/dim]")
    console.print(f"  Duration: {result.duration_seconds:.1f}s")

    total_stages = result.cache_hits + result.cache_misses
    if total_stages:
        if result.cache_hits:
            console.print(
                f"  Reused: {result.cache_hits}/{total_stages} stages from cache "
                f"[dim](no tokens, no wait)[/dim]"
            )
        else:
            console.print(f"  Reused: 0/{total_stages} stages [dim](all regenerated)[/dim]")

    if result.tests_verified:
        verdict = "passed" if result.test_passed else "FAILED"
        console.print(f"  Tests: {verdict} (ran in sandbox)")
    else:
        console.print(
            "\n[yellow]  WARNING: tests were NOT run.[/yellow] No sandbox was "
            "available, so the generated code is [bold]unverified[/bold]."
        )
        console.print(
            "[dim]  Install Docker and run `loom sandbox build` to test for real, "
            "or pass --require-sandbox to fail instead of continuing.[/dim]"
        )


@app.command()
def version() -> None:
    """Show Loom version."""
    from loom import __version__

    console.print(f"Loom v{__version__}")


@app.command()
def build(
    description: str = typer.Argument(..., help="Project description"),
    output_dir: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Enable interactive mode"),
    plain: bool = typer.Option(False, "--plain", help="Plain output (no TUI)"),
    model: str = typer.Option(
        None, "--model", "-m", help="LLM model override (e.g., anthropic:claude-sonnet-4-20250514)"
    ),
    no_memory: bool = typer.Option(
        False, "--no-memory", help="Disable memory system for this build"
    ),
    no_adrs: bool = typer.Option(False, "--no-adrs", help="Disable ADR generation in output"),
    require_sandbox: bool = typer.Option(
        False,
        "--require-sandbox",
        help="Fail if no test sandbox is available instead of leaving code unverified",
    ),
    no_overwrite: bool = typer.Option(
        False,
        "--no-overwrite",
        help="Refuse to write into an output directory that already has files",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Ignore cached artifacts and regenerate every stage from the model",
    ),
) -> None:
    """Build a project from a natural language description."""
    from loom import build_sync
    from loom.config import load_config

    console.print(Panel(f"[bold blue]Building:[/bold blue] {description}", title="Loom"))

    # Load config with optional model override
    config = load_config()
    if model:
        from loom.config import parse_llm_string

        config.llm_default = parse_llm_string(model)

    # Disable memory if requested
    if no_memory:
        config.memory.enabled = False

    # Disable ADRs if requested
    if no_adrs:
        config.adr.enabled = False

    if require_sandbox:
        config.require_sandbox = True

    if no_cache:
        from loom.cache import ArtifactCache, set_cache

        set_cache(ArtifactCache(enabled=False))

    # Fail fast with an actionable message rather than a transport error from
    # deep inside the graph.
    _preflight_or_exit(config)

    if plain:
        # Simple progress output (use ASCII spinner on Windows)
        spinner = SpinnerColumn(spinner_name="line" if _is_windows else "dots")
        with Progress(
            spinner,
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running agent pipeline...", total=None)
            try:
                result = build_sync(
                    description=description,
                    config=config,
                    output_dir=output_dir,
                    interactive=interactive,
                    use_persistence=not plain,
                    overwrite=not no_overwrite,
                )
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"\n[red]Error:[/red] {e}")
                raise typer.Exit(1)

            progress.update(task, completed=True)

        # Outside the try/progress block: typer.Exit is control flow, not an
        # error, and must not be swallowed by the handler above.
        if result.success:
            _render_build_result(result)
        else:
            console.print(f"\n[red][FAIL] Build failed:[/red] {result.error}")
            raise typer.Exit(1)
    else:
        # TUI mode
        try:
            from loom.cli.tui import run_build_tui

            run_build_tui(description, config, output_dir, interactive)
        except ImportError:
            console.print("[yellow]TUI not available, using plain mode[/yellow]")
            # Fall back to plain mode
            result = build_sync(
                description=description,
                config=config,
                output_dir=output_dir,
                interactive=interactive,
                overwrite=not no_overwrite,
            )
            if result.success:
                _render_build_result(result)
            else:
                console.print(f"[red][FAIL] Build failed:[/red] {result.error}")
                raise typer.Exit(1)


@app.command()
def resume(
    thread_id: str = typer.Argument(..., help="Thread ID to resume"),
    output_dir: str = typer.Option("./output", "--output", "-o", help="Output directory"),
) -> None:
    """Resume an interrupted build session."""
    from loom import resume_build_sync

    console.print(f"[bold blue]Resuming build:[/bold blue] {thread_id}")

    try:
        result = resume_build_sync(thread_id=thread_id, output_dir=output_dir)

        if result.success:
            console.print("\n[green][OK] Build complete![/green]")
            console.print(f"  Output: [cyan]{result.output_dir}[/cyan]")
        else:
            console.print(f"\n[red][FAIL] Build failed:[/red] {result.error}")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# Sandbox commands
@sandbox_app.command("build")
def sandbox_build() -> None:
    """Build the sandbox Docker image."""

    console.print("[bold]Building sandbox image...[/bold]")

    try:
        from loom.sandbox.models import SandboxConfig
        from loom.sandbox.runner import SandboxRunner

        runner = SandboxRunner.__new__(SandboxRunner)
        runner.config = SandboxConfig()
        runner._initialize_docker()

        # Get project root
        dockerfile = Path(__file__).parent.parent.parent.parent / "docker" / "sandbox.Dockerfile"
        if not dockerfile.exists():
            console.print(f"[red]Dockerfile not found:[/red] {dockerfile}")
            raise typer.Exit(1)

        from loom.sandbox.models import SandboxConfig

        runner.config = SandboxConfig()
        if runner.build_image(dockerfile):
            console.print("[green][OK] Sandbox image built successfully[/green]")
        else:
            console.print("[red][FAIL] Failed to build sandbox image[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@sandbox_app.command("test")
def sandbox_test(
    command: str = typer.Argument("python --version", help="Command to run"),
) -> None:
    """Run a test command in the sandbox."""
    from loom.sandbox import create_sandbox_runner

    console.print(f"[bold]Running in sandbox:[/bold] {command}")

    try:
        runner = create_sandbox_runner()
        result = asyncio.run(runner.run(command))

        console.print(f"\n[dim]Exit code:[/dim] {result.exit_code}")
        console.print(f"[dim]Duration:[/dim] {result.duration_seconds:.2f}s")
        if result.stdout:
            console.print(f"\n[bold]stdout:[/bold]\n{result.stdout}")
        if result.stderr:
            console.print(f"\n[bold]stderr:[/bold]\n{result.stderr}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@sandbox_app.command("info")
def sandbox_info() -> None:
    """Show sandbox status and availability."""
    from loom.sandbox import get_sandbox_info

    info = get_sandbox_info()

    table = Table(title="Sandbox Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")

    table.add_row(
        "Docker Available", "[green]Yes[/green]" if info["docker_available"] else "[red]No[/red]"
    )
    table.add_row(
        "Sandbox Image",
        "[green]Built[/green]" if info["docker_image_exists"] else "[yellow]Not built[/yellow]",
    )
    table.add_row(
        "Subprocess Fallback",
        "[yellow]Enabled[/yellow]" if info["subprocess_enabled"] else "[dim]Disabled[/dim]",
    )

    console.print(table)

    if not info["docker_available"]:
        console.print("\n[yellow]Tip:[/yellow] Install Docker for secure sandbox execution")
    elif not info["docker_image_exists"]:
        console.print("\n[yellow]Tip:[/yellow] Run 'loom sandbox build' to create the image")


# Config commands
@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    from loom.config import load_config

    config = load_config()

    table = Table(title="Loom Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Default Provider", config.llm_default.provider)
    table.add_row("Default Model", config.llm_default.model)
    table.add_row("Temperature", str(config.llm_default.temperature))
    table.add_row("Max Retries", str(config.max_retries))
    table.add_row("Output Directory", config.output_dir)

    console.print(table)

    if config.llm_overrides:
        override_table = Table(title="Agent LLM Overrides")
        override_table.add_column("Agent", style="cyan")
        override_table.add_column("Provider", style="green")
        override_table.add_column("Model", style="green")

        for agent, llm in config.llm_overrides.items():
            override_table.add_row(agent, llm.provider, llm.model)

        console.print(override_table)


@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
) -> None:
    """Create a default configuration file."""
    config_file = Path("loom.toml")

    if config_file.exists() and not force:
        console.print(f"[yellow]Config file already exists:[/yellow] {config_file}")
        console.print("Use --force to overwrite")
        raise typer.Exit(1)

    # Copy example config
    example = Path(__file__).parent.parent.parent.parent / "loom.example.toml"
    if example.exists():
        import shutil

        shutil.copy(example, config_file)
        console.print(f"[green][OK] Created config file:[/green] {config_file}")
    else:
        # Create minimal config
        config_file.write_text("""# Loom Configuration

[llm]
provider = "ollama"
model = "qwen2.5-coder:7b"
temperature = 0.7

[build]
output_dir = "./output"
max_retries = 2
""")
        console.print(f"[green][OK] Created config file:[/green] {config_file}")


@app.command()
def ui(
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Server host"),
    dev: bool = typer.Option(False, "--dev", help="Development mode (no static files)"),
) -> None:
    """Launch the web dashboard."""
    import uvicorn

    console.print("[bold]Starting Loom Dashboard[/bold]")
    console.print(f"  Server: http://{host}:{port}")

    if not dev:
        from loom.server.main import find_dashboard_dist, mount_static_files

        frontend_dist = find_dashboard_dist()
        if frontend_dist is not None:
            console.print(f"  Frontend: {frontend_dist}")
            mount_static_files(frontend_dist)
        else:
            console.print("[yellow]  Dashboard not built - serving the API only.[/yellow]")
            console.print("[dim]  Build it with: cd frontend && npm install && npm run build[/dim]")
            console.print("[dim]  Or run the Vite dev server separately with --dev.[/dim]")

    console.print("\n[dim]Press Ctrl+C to stop[/dim]\n")

    from loom.server.main import app as fastapi_app

    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


@app.command()
def doctor() -> None:
    """Diagnose Loom setup and check for common issues."""
    import os
    import subprocess

    console.print("[bold]Loom Doctor[/bold]\n")

    # Python version — pyproject's requires-python gate means we wouldn't have
    # reached this code on < 3.11, so the version is always acceptable here.
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    console.print(f"[green][OK][/green] Python {py_version}")

    # Check API keys
    console.print("\n[bold]API Keys:[/bold]")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        console.print(f"[green][OK][/green] ANTHROPIC_API_KEY set ({anthropic_key[:8]}...)")
    else:
        console.print("[yellow][--][/yellow] ANTHROPIC_API_KEY not set")

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        console.print(f"[green][OK][/green] OPENAI_API_KEY set ({openai_key[:8]}...)")
    else:
        console.print("[yellow][--][/yellow] OPENAI_API_KEY not set")

    # Check Ollama
    console.print("\n[bold]Local LLMs:[/bold]")
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and "models" in result.stdout:
            import json

            data = json.loads(result.stdout)
            models = [m["name"] for m in data.get("models", [])]
            if models:
                console.print(
                    f"[green][OK][/green] Ollama running with models: {', '.join(models)}"
                )
            else:
                console.print("[yellow][--][/yellow] Ollama running but no models installed")
        else:
            console.print("[yellow][--][/yellow] Ollama not responding")
    except Exception:
        console.print("[yellow][--][/yellow] Ollama not available")

    # Check Docker
    console.print("\n[bold]Sandbox:[/bold]")
    from loom.sandbox import get_sandbox_info

    info = get_sandbox_info()

    if info["docker_available"]:
        console.print("[green][OK][/green] Docker available")
        if info["docker_image_exists"]:
            console.print("[green][OK][/green] Sandbox image built")
        else:
            console.print("[yellow][--][/yellow] Sandbox image not built (run: loom sandbox build)")
    else:
        console.print(
            "[yellow][--][/yellow] Docker not available - tests will NOT run; "
            "results are reported as unverified"
        )

    # Chat-mode prerequisites (Phase 9)
    console.print("\n[bold]Chat REPL:[/bold]")
    try:
        import prompt_toolkit  # noqa: F401

        console.print("[green][OK][/green] prompt_toolkit installed")
    except ImportError:
        console.print(
            "[red][FAIL][/red] prompt_toolkit missing — install with: pip install prompt_toolkit"
        )
    try:
        import rich  # noqa: F401

        console.print("[green][OK][/green] rich installed")
    except ImportError:
        console.print("[red][FAIL][/red] rich missing — required for chat rendering")
    try:
        import aiosqlite  # noqa: F401

        console.print("[green][OK][/green] aiosqlite installed (chat checkpointing)")
    except ImportError:
        console.print(
            "[yellow][--][/yellow] aiosqlite missing — chat will use in-memory checkpoints only"
        )

    # Terminal capabilities
    if sys.stdout.isatty():
        console.print("[green][OK][/green] Running in a TTY (chat will render correctly)")
    else:
        console.print("[yellow][--][/yellow] Not a TTY — use --plain for accessibility / CI mode")

    # Summary
    console.print("\n[bold]Recommendation:[/bold]")
    if anthropic_key or openai_key:
        console.print(
            "[green]Ready to build![/green] Run: [cyan]loom[/cyan] (chat) "
            'or [cyan]loom build "…"[/cyan] (one-shot)'
        )
    elif (
        subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"], capture_output=True
        ).returncode
        == 0
    ):
        console.print(
            "[green]Ready with Ollama![/green] Run: [cyan]loom --model ollama:qwen2.5-coder:7b[/cyan]"
        )
    else:
        console.print("[yellow]Set ANTHROPIC_API_KEY or OPENAI_API_KEY to get started.[/yellow]")
        console.print("Or install Ollama for local LLM: https://ollama.ai")


@app.command()
def estimate(
    description: str = typer.Argument(..., help="Project description"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model override"),
) -> None:
    """Estimate cost for a build without running it."""
    from loom.config import load_config
    from loom.llm import estimate_build_cost, format_cost

    config = load_config()
    if model:
        from loom.config import parse_llm_string

        config.llm_default = parse_llm_string(model)

    # estimate_build_cost returns a float (total cost in USD)
    estimated_tokens = 80_000  # Default assumption
    estimated_cost = estimate_build_cost(
        config.llm_default.provider, config.llm_default.model, estimated_tokens
    )

    console.print(f"[bold]Cost Estimate for:[/bold] {description[:50]}...")
    console.print()

    table = Table(title="Estimated Build Cost")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Provider", config.llm_default.provider)
    table.add_row("Model", config.llm_default.model)
    table.add_row("Est. Input Tokens", f"~{int(estimated_tokens * 0.4):,}")
    table.add_row("Est. Output Tokens", f"~{int(estimated_tokens * 0.6):,}")
    table.add_row("Est. Total Cost", format_cost(estimated_cost))

    console.print(table)

    if estimated_cost == 0:
        console.print("\n[dim]Note: Local models (Ollama) have no API cost.[/dim]")
    else:
        console.print("\n[dim]Actual cost may vary based on project complexity.[/dim]")


# Plan commands
@app.command()
def plan(
    description: str = typer.Argument(..., help="Project description"),
    save: Path = typer.Option(None, "--save", "-s", help="Save plan to this path"),
    auto_build: bool = typer.Option(
        False, "--auto-build", help="Skip prompt and build immediately"
    ),
    model: str = typer.Option(None, "--model", "-m", help="LLM model override"),
    no_memory: bool = typer.Option(False, "--no-memory", help="Disable memory system"),
) -> None:
    """Generate a plan without building. Review before committing to a full build."""
    import asyncio
    import uuid

    from rich.prompt import Prompt

    from loom.cli.tui import PlanRenderer
    from loom.config import load_config
    from loom.plan import default_plan_path, save_plan

    console.print(Panel(f"[bold blue]Planning:[/bold blue] {description}", title="Loom Plan"))

    # Load config
    config = load_config()
    if model:
        from loom.config import parse_llm_string

        config.llm_default = parse_llm_string(model)
    if no_memory:
        config.memory.enabled = False

    thread_id = str(uuid.uuid4())

    async def run_plan() -> tuple[Any, Any, Any]:
        from loom.graph.builder import compile_graph
        from loom.graph.checkpoint import create_memory_checkpointer, get_checkpoint_config
        from loom.state.enums import Phase

        # Initial state
        initial_state = {
            "description": description,
            "phase": Phase.INIT,
            "interactive": True,
            "retry_count": 0,
            "max_retries": config.max_retries,
            "events": [],
            "costs": [],
            "code_files": {},
        }

        # Compile graph with interrupt after architect
        checkpointer = create_memory_checkpointer()
        graph = compile_graph(
            config,
            checkpointer=checkpointer,
            interrupt_before=["frontend_dev", "backend_dev"],  # Stop before dev agents
        )
        run_config = get_checkpoint_config(thread_id)

        # Run PM and Architect only
        with Progress(
            SpinnerColumn(spinner_name="line" if _is_windows else "dots"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running Product Manager...", total=None)

            async for event in graph.astream_events(initial_state, config=run_config, version="v2"):
                event_type = event.get("event")
                if event_type == "on_chain_start":
                    name = event.get("name", "")
                    if "product_manager" in name.lower():
                        progress.update(task, description="Running Product Manager...")
                    elif "architect" in name.lower():
                        progress.update(task, description="Running Architect...")
                    elif "memory" in name.lower():
                        progress.update(task, description="Retrieving memory...")

            progress.update(task, completed=True, description="Planning complete")

        # Get state
        state_snapshot = graph.get_state(run_config)
        state = state_snapshot.values

        return state, graph, run_config

    # Run the plan
    try:
        state, graph, run_config = asyncio.run(run_plan())
    except Exception as e:
        console.print(f"[red]Error during planning:[/red] {e}")
        raise typer.Exit(1)

    # Render the plan
    renderer = PlanRenderer(console)
    provider = config.llm_default.provider
    llm_model = config.llm_default.model
    renderer.render(state, provider, llm_model)

    # Auto-build or prompt
    if auto_build:
        choice = "B"
    else:
        console.print("\n[bold]What next?[/bold]")
        console.print("  [B] Build now")
        console.print("  [E] Edit & rebuild plan")
        console.print("  [S] Save plan, build later")
        console.print("  [Q] Quit")
        choice = Prompt.ask(
            "Choice", choices=["B", "E", "S", "Q", "b", "e", "s", "q"], default="B"
        ).upper()

    if choice == "Q":
        console.print("[dim]Plan discarded.[/dim]")
        raise typer.Exit(0)

    if choice == "S":
        plan_path = save if save else default_plan_path(state)
        save_plan(state, plan_path, thread_id, description, config)
        console.print("[green][OK] Plan saved.[/green]")
        console.print(f"Resume with: [cyan]loom build --from-plan {plan_path}[/cyan]")
        raise typer.Exit(0)

    if choice == "E":
        feedback = Prompt.ask("What would you like to change?")

        async def rerun_architect() -> Any:
            # Update state with feedback
            graph.update_state(run_config, {"architecture_feedback": feedback})

            # Re-run from architect
            with Progress(
                SpinnerColumn(spinner_name="line" if _is_windows else "dots"),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Re-running Architect with feedback...", total=None)
                async for _ in graph.astream_events(None, config=run_config, version="v2"):
                    pass
                progress.update(task, completed=True, description="Revision complete")

            return graph.get_state(run_config).values

        try:
            state = asyncio.run(rerun_architect())
        except Exception as e:
            console.print(f"[red]Error during revision:[/red] {e}")
            raise typer.Exit(1)

        # Re-render
        renderer.render(state, provider, llm_model)

        # Ask again
        choice = Prompt.ask("Build now?", choices=["Y", "N", "y", "n"], default="Y").upper()
        if choice == "N":
            plan_path = save if save else default_plan_path(state)
            save_plan(state, plan_path, thread_id, description, config)
            console.print("[green][OK] Plan saved.[/green]")
            console.print(f"Resume with: [cyan]loom build --from-plan {plan_path}[/cyan]")
            raise typer.Exit(0)

    # Build
    if choice == "B" or choice == "Y":
        console.print("\n[bold]Starting build...[/bold]")

        async def continue_build() -> Any:
            with Progress(
                SpinnerColumn(spinner_name="line" if _is_windows else "dots"),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Running build pipeline...", total=None)
                async for event in graph.astream_events(None, config=run_config, version="v2"):
                    event_type = event.get("event")
                    if event_type == "on_chain_start":
                        name = event.get("name", "")
                        if "frontend" in name.lower():
                            progress.update(task, description="Running Frontend Dev...")
                        elif "backend" in name.lower():
                            progress.update(task, description="Running Backend Dev...")
                        elif "qa" in name.lower():
                            progress.update(task, description="Running QA Engineer...")
                        elif "devops" in name.lower():
                            progress.update(task, description="Running DevOps Engineer...")
                progress.update(task, completed=True, description="Build complete")

            return graph.get_state(run_config).values

        try:
            final_state = asyncio.run(continue_build())

            if final_state.get("error"):
                console.print(f"\n[red][FAIL] Build failed:[/red] {final_state['error']}")
                raise typer.Exit(1)
            else:
                console.print("\n[green][OK] Build complete![/green]")
                output_dir = final_state.get("output_dir", "./output")
                console.print(f"  Output: [cyan]{output_dir}[/cyan]")

                costs = final_state.get("costs", [])
                total_tokens = sum(c.input_tokens + c.output_tokens for c in costs)
                total_cost = sum(c.cost_usd for c in costs)
                console.print(f"  Tokens: {total_tokens:,}")
                console.print(f"  Cost: ${total_cost:.4f}")

        except Exception as e:
            console.print(f"[red]Error during build:[/red] {e}")
            raise typer.Exit(1)


@app.command("build-from-plan")
def build_from_plan(
    plan_path: Path = typer.Argument(..., help="Path to a saved plan.json"),
    output_dir: str = typer.Option("./output", "--output", "-o", help="Output directory"),
) -> None:
    """Build a project from a saved plan file."""
    import asyncio

    from loom.config import LoomConfig
    from loom.plan import load_plan
    from loom.state.enums import Phase
    from loom.state.models import PRD, ArchitectureDoc

    console.print(f"[bold blue]Building from plan:[/bold blue] {plan_path}")

    # Load plan
    try:
        plan_data = load_plan(plan_path)
    except FileNotFoundError:
        console.print(f"[red]Plan file not found:[/red] {plan_path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Invalid plan file:[/red] {e}")
        raise typer.Exit(1)

    # Reconstruct config
    config = LoomConfig()
    if "config" in plan_data:
        if "llm_default" in plan_data["config"]:
            from loom.config.models import LLMConfig

            config.llm_default = LLMConfig(**plan_data["config"]["llm_default"])

    # Reconstruct state
    prd = PRD(**plan_data["prd"]) if plan_data.get("prd") else None
    architecture = (
        ArchitectureDoc(**plan_data["architecture"]) if plan_data.get("architecture") else None
    )

    memory_context = None
    if plan_data.get("memory_context"):
        from loom.memory.models import MemoryContext

        memory_context = MemoryContext(**plan_data["memory_context"])

    initial_state = {
        "description": plan_data["description"],
        "prd": prd,
        "architecture": architecture,
        "memory_context": memory_context,
        "phase": Phase.DEVELOPMENT,  # Skip PM and Architect
        "interactive": False,
        "retry_count": 0,
        "max_retries": config.max_retries,
        "events": [],
        "costs": [],
        "code_files": {},
    }

    async def run_build() -> Any:
        from loom.graph.builder import compile_graph
        from loom.graph.checkpoint import create_memory_checkpointer, get_checkpoint_config

        checkpointer = create_memory_checkpointer()
        graph = compile_graph(config, checkpointer=checkpointer)
        run_config = get_checkpoint_config(plan_data["thread_id"])

        with Progress(
            SpinnerColumn(spinner_name="line" if _is_windows else "dots"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running build pipeline...", total=None)

            async for event in graph.astream_events(initial_state, config=run_config, version="v2"):
                event_type = event.get("event")
                if event_type == "on_chain_start":
                    name = event.get("name", "")
                    if "frontend" in name.lower():
                        progress.update(task, description="Running Frontend Dev...")
                    elif "backend" in name.lower():
                        progress.update(task, description="Running Backend Dev...")
                    elif "qa" in name.lower():
                        progress.update(task, description="Running QA Engineer...")
                    elif "devops" in name.lower():
                        progress.update(task, description="Running DevOps Engineer...")
                    elif "memory_persist" in name.lower():
                        progress.update(task, description="Saving to memory...")

            progress.update(task, completed=True, description="Build complete")

        return graph.get_state(run_config).values

    try:
        final_state = asyncio.run(run_build())

        if final_state.get("error"):
            console.print(f"\n[red][FAIL] Build failed:[/red] {final_state['error']}")
            raise typer.Exit(1)
        else:
            console.print("\n[green][OK] Build complete![/green]")
            out_dir = final_state.get("output_dir", output_dir)
            console.print(f"  Output: [cyan]{out_dir}[/cyan]")

            costs = final_state.get("costs", [])
            total_tokens = sum(c.input_tokens + c.output_tokens for c in costs)
            total_cost = sum(c.cost_usd for c in costs)
            console.print(f"  Tokens: {total_tokens:,}")
            console.print(f"  Cost: ${total_cost:.4f}")

    except Exception as e:
        console.print(f"[red]Error during build:[/red] {e}")
        raise typer.Exit(1)


# Memory commands
@memory_app.command("status")
def memory_status() -> None:
    """Show memory system status."""
    from loom.config import load_config
    from loom.memory.factory import get_memory_store, is_memory_available

    config = load_config()
    memory_config = config.memory

    table = Table(title="Memory System Status")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Enabled", "[green]Yes[/green]" if memory_config.enabled else "[red]No[/red]")
    table.add_row(
        "Dependencies",
        "[green]Available[/green]" if is_memory_available() else "[yellow]Not installed[/yellow]",
    )
    table.add_row("Embedder", memory_config.embedder)
    table.add_row("Model", memory_config.embedder_model)
    table.add_row("Database Path", memory_config.db_path)
    table.add_row("Top-K Results", str(memory_config.top_k))
    table.add_row("Min Similarity", str(memory_config.min_similarity))

    console.print(table)

    # Show record count if available
    if is_memory_available() and memory_config.enabled:
        try:
            store = get_memory_store(memory_config)
            count = store.count()
            console.print(f"\n[bold]Records stored:[/bold] {count}")
        except Exception as e:
            console.print(f"\n[yellow]Could not get record count:[/yellow] {e}")
    elif not is_memory_available():
        console.print(
            "\n[yellow]Tip:[/yellow] Install memory dependencies with: pip install 'loom[memory]'"
        )


@memory_app.command("list")
def memory_list(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of records to show"),
) -> None:
    """List stored memory records."""
    from loom.config import load_config
    from loom.memory.factory import get_memory_store, is_memory_available

    if not is_memory_available():
        console.print("[yellow]Memory dependencies not installed.[/yellow]")
        console.print("Install with: pip install 'loom[memory]'")
        raise typer.Exit(1)

    config = load_config()
    memory_config = config.memory

    try:
        store = get_memory_store(memory_config)

        # Check if store has list_all method (LanceDBStore)
        if hasattr(store, "list_all"):
            records = store.list_all(limit=limit)
        else:
            console.print("[yellow]List not supported for in-memory store.[/yellow]")
            raise typer.Exit(1)

        if not records:
            console.print("[dim]No records found.[/dim]")
            return

        table = Table(title=f"Memory Records (showing {len(records)})")
        table.add_column("Run ID", style="cyan", max_width=12)
        table.add_column("Project", style="green", max_width=30)
        table.add_column("Stack", style="blue")
        table.add_column("Tests", style="green")
        table.add_column("Date", style="dim")

        for record in records:
            test_status = "[green]Pass[/green]" if record.test_passed else "[red]Fail[/red]"
            date_str = record.timestamp.strftime("%Y-%m-%d")
            table.add_row(
                record.run_id[:12],
                record.one_liner[:30] if record.one_liner else "",
                record.stack_summary,
                test_status,
                date_str,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
) -> None:
    """Search for similar past builds."""
    from loom.config import load_config
    from loom.memory.factory import get_embedder, get_memory_store, is_memory_available

    if not is_memory_available():
        console.print("[yellow]Memory dependencies not installed.[/yellow]")
        console.print("Install with: pip install 'loom[memory]'")
        raise typer.Exit(1)

    config = load_config()
    memory_config = config.memory

    try:
        embedder = get_embedder(memory_config)
        store = get_memory_store(memory_config)

        # Embed the query
        console.print(f"[dim]Searching for:[/dim] {query}")
        query_embedding = embedder.embed(query)

        # Search
        results = store.search(query_embedding, k=top_k)

        if not results:
            console.print("[dim]No similar builds found.[/dim]")
            return

        table = Table(title=f"Similar Builds (top {len(results)})")
        table.add_column("Similarity", style="cyan")
        table.add_column("Project", style="green", max_width=30)
        table.add_column("Stack", style="blue")
        table.add_column("Type", style="dim")

        for record, score in results:
            table.add_row(
                f"{score:.3f}",
                record.one_liner[:30] if record.one_liner else "",
                record.stack_summary,
                record.project_type,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@memory_app.command("clear")
def memory_clear(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete all memory records."""
    from loom.config import load_config
    from loom.memory.factory import get_memory_store, is_memory_available

    if not is_memory_available():
        console.print("[yellow]Memory dependencies not installed.[/yellow]")
        raise typer.Exit(1)

    config = load_config()
    memory_config = config.memory

    try:
        store = get_memory_store(memory_config)
        count = store.count()

        if count == 0:
            console.print("[dim]No records to delete.[/dim]")
            return

        if not force:
            confirm = typer.confirm(f"Delete {count} memory records?")
            if not confirm:
                console.print("[dim]Cancelled.[/dim]")
                raise typer.Exit(0)

        store.clear()
        console.print(f"[green][OK] Deleted {count} records.[/green]")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@memory_app.command("export")
def memory_export(
    path: Path = typer.Argument(..., help="Output file path (JSONL format)"),
) -> None:
    """Export memory records to a file."""
    from loom.config import load_config
    from loom.memory.factory import get_memory_store, is_memory_available

    if not is_memory_available():
        console.print("[yellow]Memory dependencies not installed.[/yellow]")
        raise typer.Exit(1)

    config = load_config()
    memory_config = config.memory

    try:
        store = get_memory_store(memory_config)
        count = store.export(path)
        console.print(f"[green][OK] Exported {count} records to {path}[/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@memory_app.command("import")
def memory_import(
    path: Path = typer.Argument(..., help="Input file path (JSONL format)"),
) -> None:
    """Import memory records from a file."""
    from loom.config import load_config
    from loom.memory.factory import get_embedder, get_memory_store, is_memory_available

    if not is_memory_available():
        console.print("[yellow]Memory dependencies not installed.[/yellow]")
        raise typer.Exit(1)

    if not path.exists():
        console.print(f"[red]File not found:[/red] {path}")
        raise typer.Exit(1)

    config = load_config()
    memory_config = config.memory

    try:
        embedder = get_embedder(memory_config)
        store = get_memory_store(memory_config)

        console.print(f"[dim]Importing from {path}...[/dim]")
        count = store.import_(path, embedder)
        console.print(f"[green][OK] Imported {count} records[/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# =============================================================================
# Chat history (Phase 9.5)
# =============================================================================

history_app = typer.Typer(help="Browse and replay chat sessions")
app.add_typer(history_app, name="history")


@history_app.callback(invoke_without_command=True)
def history_root(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum sessions to list"),
) -> None:
    """List recent chat sessions (default action when no subcommand given)."""
    if ctx.invoked_subcommand is not None:
        return
    from loom.cli.chat.transcript import list_transcripts

    sessions = list_transcripts()
    if not sessions:
        console.print("[dim]No chat sessions found.[/dim]")
        return

    table = Table(title="Chat sessions")
    table.add_column("Thread ID", style="cyan")
    table.add_column("Modified", style="dim")
    table.add_column("Size", justify="right", style="dim")
    for entry in sessions[:limit]:
        size_kb = entry["size_bytes"] / 1024
        table.add_row(
            entry["thread_id"],
            entry["modified_at"],
            f"{size_kb:.1f} KB",
        )
    console.print(table)


@history_app.command("show")
def history_show(
    thread_id: str = typer.Argument(..., help="Thread ID to replay"),
) -> None:
    """Replay the events of a chat session."""
    from loom.cli.chat.transcript import read_transcript

    events = read_transcript(thread_id)
    if not events:
        console.print(f"[red]No transcript found for thread:[/red] {thread_id}")
        raise typer.Exit(1)

    for ev in events:
        ts = ev.get("timestamp", "")
        role = ev.get("role", "?")
        if role == "user":
            console.print(f"[dim]{ts}[/dim] [cyan]You[/cyan] ▸ {ev.get('content', '')}")
        elif role == "assistant":
            agent = ev.get("agent", "agent")
            console.print(f"[dim]{ts}[/dim] [magenta]{agent}[/magenta] ▸ {ev.get('content', '')}")
        elif role == "system":
            cmd = ev.get("command", "")
            args = " ".join(ev.get("args", []))
            console.print(f"[dim]{ts}[/dim] [yellow]/{cmd} {args}[/yellow]")


if __name__ == "__main__":
    app()


@cache_app.command("status")
def cache_status() -> None:
    """Show what the artifact cache is holding."""
    from loom.cache import get_cache

    cache = get_cache()
    count = cache.entry_count()
    size_kb = cache.size_bytes() / 1024

    table = Table(title="Artifact Cache", show_header=False, box=None)
    table.add_row("Location", str(cache.cache_dir))
    table.add_row("Enabled", "yes" if cache.enabled else "no")
    table.add_row("Entries", str(count))
    table.add_row("Size", f"{size_kb:,.1f} KB")
    console.print(table)

    if count == 0:
        console.print()
        console.print(
            "[dim]Empty. Artifacts are cached automatically as builds run; "
            "re-running an identical build then costs nothing.[/dim]"
        )


@cache_app.command("clear")
def cache_clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
) -> None:
    """Delete every cached artifact."""
    from loom.cache import get_cache

    cache = get_cache()
    count = cache.entry_count()
    if count == 0:
        console.print("[dim]Cache is already empty.[/dim]")
        return

    if not yes:
        confirmed = typer.confirm(f"Delete {count} cached artifact(s)?")
        if not confirmed:
            console.print("[dim]Left unchanged.[/dim]")
            return

    removed = cache.clear()
    console.print(f"[green]Removed {removed} cached artifact(s).[/green]")
