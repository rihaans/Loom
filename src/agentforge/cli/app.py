"""Typer CLI application for AgentForge."""

import typer
from rich.console import Console

app = typer.Typer(
    name="agentforge",
    help="Autonomous software development team built on LangGraph.",
    no_args_is_help=True,
)
console = Console()


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
) -> None:
    """Build a project from a natural language description."""
    console.print(f"[bold blue]Building:[/bold blue] {description}")
    console.print("[yellow]Build command not yet implemented (Phase 4+)[/yellow]")


if __name__ == "__main__":
    app()
