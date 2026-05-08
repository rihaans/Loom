"""Typer CLI application for AgentForge."""

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="agentforge",
    help="Autonomous software development team built on LangGraph.",
    no_args_is_help=True,
)

# Use legacy console mode on Windows to avoid Unicode issues
_is_windows = sys.platform == "win32"
console = Console(legacy_windows=_is_windows, force_terminal=not _is_windows)

# Subcommand groups
sandbox_app = typer.Typer(help="Sandbox management commands")
config_app = typer.Typer(help="Configuration commands")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(config_app, name="config")


@app.command()
def version() -> None:
    """Show AgentForge version."""
    from agentforge import __version__

    console.print(f"AgentForge v{__version__}")


@app.command()
def build(
    description: str = typer.Argument(..., help="Project description"),
    output_dir: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Enable interactive mode"),
    plain: bool = typer.Option(False, "--plain", help="Plain output (no TUI)"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model override (e.g., anthropic:claude-sonnet-4-20250514)"),
) -> None:
    """Build a project from a natural language description."""
    from agentforge import build_sync
    from agentforge.config import load_config

    console.print(Panel(f"[bold blue]Building:[/bold blue] {description}", title="AgentForge"))

    # Load config with optional model override
    config = load_config()
    if model:
        from agentforge.config import parse_llm_string
        config.llm_default = parse_llm_string(model)

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
                )
                progress.update(task, completed=True)

                if result.success:
                    console.print(f"\n[green][OK] Build complete![/green]")
                    console.print(f"  Output: [cyan]{result.output_dir}[/cyan]")
                    console.print(f"  Tokens: {result.total_tokens:,}")
                    console.print(f"  Cost: ${result.total_cost_usd:.4f}")
                    console.print(f"  Duration: {result.duration_seconds:.1f}s")
                else:
                    console.print(f"\n[red][FAIL] Build failed:[/red] {result.error}")
                    raise typer.Exit(1)
            except Exception as e:
                console.print(f"\n[red]Error:[/red] {e}")
                raise typer.Exit(1)
    else:
        # TUI mode
        try:
            from agentforge.cli.tui import run_build_tui
            run_build_tui(description, config, output_dir, interactive)
        except ImportError:
            console.print("[yellow]TUI not available, using plain mode[/yellow]")
            # Fall back to plain mode
            result = build_sync(
                description=description,
                config=config,
                output_dir=output_dir,
                interactive=interactive,
            )
            if result.success:
                console.print(f"[green][OK] Build complete![/green] Output: {result.output_dir}")
            else:
                console.print(f"[red][FAIL] Build failed:[/red] {result.error}")
                raise typer.Exit(1)


@app.command()
def resume(
    thread_id: str = typer.Argument(..., help="Thread ID to resume"),
    output_dir: str = typer.Option("./output", "--output", "-o", help="Output directory"),
) -> None:
    """Resume an interrupted build session."""
    from agentforge import resume_build_sync

    console.print(f"[bold blue]Resuming build:[/bold blue] {thread_id}")

    try:
        result = resume_build_sync(thread_id=thread_id, output_dir=output_dir)

        if result.success:
            console.print(f"\n[green][OK] Build complete![/green]")
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
    from agentforge.sandbox import get_sandbox_info

    console.print("[bold]Building sandbox image...[/bold]")

    try:
        from agentforge.sandbox.runner import SandboxRunner
        runner = SandboxRunner.__new__(SandboxRunner)
        runner.config = None
        runner._initialize_docker()

        # Get project root
        dockerfile = Path(__file__).parent.parent.parent.parent / "docker" / "sandbox.Dockerfile"
        if not dockerfile.exists():
            console.print(f"[red]Dockerfile not found:[/red] {dockerfile}")
            raise typer.Exit(1)

        from agentforge.sandbox.models import SandboxConfig
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
    from agentforge.sandbox import create_sandbox_runner

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
    from agentforge.sandbox import get_sandbox_info

    info = get_sandbox_info()

    table = Table(title="Sandbox Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")

    table.add_row(
        "Docker Available",
        "[green]Yes[/green]" if info["docker_available"] else "[red]No[/red]"
    )
    table.add_row(
        "Sandbox Image",
        "[green]Built[/green]" if info["docker_image_exists"] else "[yellow]Not built[/yellow]"
    )
    table.add_row(
        "Subprocess Fallback",
        "[yellow]Enabled[/yellow]" if info["subprocess_enabled"] else "[dim]Disabled[/dim]"
    )

    console.print(table)

    if not info["docker_available"]:
        console.print("\n[yellow]Tip:[/yellow] Install Docker for secure sandbox execution")
    elif not info["docker_image_exists"]:
        console.print("\n[yellow]Tip:[/yellow] Run 'agentforge sandbox build' to create the image")


# Config commands
@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    from agentforge.config import load_config

    config = load_config()

    table = Table(title="AgentForge Configuration")
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
    config_file = Path("agentforge.toml")

    if config_file.exists() and not force:
        console.print(f"[yellow]Config file already exists:[/yellow] {config_file}")
        console.print("Use --force to overwrite")
        raise typer.Exit(1)

    # Copy example config
    example = Path(__file__).parent.parent.parent.parent / "agentforge.example.toml"
    if example.exists():
        import shutil
        shutil.copy(example, config_file)
        console.print(f"[green][OK] Created config file:[/green] {config_file}")
    else:
        # Create minimal config
        config_file.write_text('''# AgentForge Configuration

[llm]
provider = "ollama"
model = "qwen2.5-coder:7b"
temperature = 0.7

[build]
output_dir = "./output"
max_retries = 2
''')
        console.print(f"[green][OK] Created config file:[/green] {config_file}")


@app.command()
def ui(
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Server host"),
    dev: bool = typer.Option(False, "--dev", help="Development mode (no static files)"),
) -> None:
    """Launch the web dashboard."""
    import uvicorn

    console.print(f"[bold]Starting AgentForge Dashboard[/bold]")
    console.print(f"  Server: http://{host}:{port}")

    if not dev:
        # Check for built frontend
        frontend_dist = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
        if frontend_dist.exists():
            console.print(f"  Frontend: {frontend_dist}")
            from agentforge.server.main import mount_static_files
            mount_static_files(frontend_dist)
        else:
            console.print("[yellow]  Frontend not built. Run 'cd frontend && npm run build' or use --dev[/yellow]")

    console.print("\n[dim]Press Ctrl+C to stop[/dim]\n")

    from agentforge.server.main import app as fastapi_app
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


@app.command()
def doctor() -> None:
    """Diagnose AgentForge setup and check for common issues."""
    import os
    import subprocess

    console.print("[bold]AgentForge Doctor[/bold]\n")

    # Check Python version
    import sys
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        console.print(f"[green][OK][/green] Python {py_version}")
    else:
        console.print(f"[red][FAIL][/red] Python {py_version} (requires 3.10+)")

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
                console.print(f"[green][OK][/green] Ollama running with models: {', '.join(models)}")
            else:
                console.print("[yellow][--][/yellow] Ollama running but no models installed")
        else:
            console.print("[yellow][--][/yellow] Ollama not responding")
    except Exception:
        console.print("[yellow][--][/yellow] Ollama not available")

    # Check Docker
    console.print("\n[bold]Sandbox:[/bold]")
    from agentforge.sandbox import get_sandbox_info
    info = get_sandbox_info()

    if info["docker_available"]:
        console.print("[green][OK][/green] Docker available")
        if info["docker_image_exists"]:
            console.print("[green][OK][/green] Sandbox image built")
        else:
            console.print("[yellow][--][/yellow] Sandbox image not built (run: agentforge sandbox build)")
    else:
        console.print("[yellow][--][/yellow] Docker not available (sandbox will use subprocess fallback)")

    # Summary
    console.print("\n[bold]Recommendation:[/bold]")
    if anthropic_key or openai_key:
        console.print("[green]Ready to build![/green] Run: agentforge build \"your project description\"")
    elif subprocess.run(["curl", "-s", "http://localhost:11434/api/tags"], capture_output=True).returncode == 0:
        console.print("[green]Ready with Ollama![/green] Run: agentforge build \"your project\" --model ollama:mistral")
    else:
        console.print("[yellow]Set ANTHROPIC_API_KEY or OPENAI_API_KEY to get started.[/yellow]")
        console.print("Or install Ollama for local LLM: https://ollama.ai")


@app.command()
def estimate(
    description: str = typer.Argument(..., help="Project description"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model override"),
) -> None:
    """Estimate cost for a build without running it."""
    from agentforge.config import load_config
    from agentforge.llm import estimate_build_cost, format_cost

    config = load_config()
    if model:
        from agentforge.config import parse_llm_string
        config.llm_default = parse_llm_string(model)

    # estimate_build_cost returns a float (total cost in USD)
    estimated_tokens = 80_000  # Default assumption
    estimated_cost = estimate_build_cost(config.llm_default.provider, config.llm_default.model, estimated_tokens)

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
        console.print(f"\n[dim]Actual cost may vary based on project complexity.[/dim]")


if __name__ == "__main__":
    app()
