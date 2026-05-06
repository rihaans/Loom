"""Core build functionality for AgentForge.

This is the main public API for running builds.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from agentforge.config import AgentForgeConfig, BuildResult, load_config
from agentforge.graph.builder import compile_graph
from agentforge.output import materialize_state
from agentforge.state.enums import Phase

logger = logging.getLogger(__name__)


async def build(
    description: str,
    config: AgentForgeConfig | None = None,
    output_dir: str | Path | None = None,
    interactive: bool = False,
) -> BuildResult:
    """Run the full agent pipeline to build a project.

    This is the main entry point for AgentForge. It takes a project
    description and runs the full multi-agent pipeline to generate
    a complete project.

    Args:
        description: Natural language description of the project to build
        config: Optional AgentForge configuration. If not provided,
            configuration will be loaded from environment/files.
        output_dir: Optional output directory. If not provided,
            uses config.output_dir or "output/".
        interactive: If True, pause at review gates for user input.
            (Not implemented in linear graph - Phase 5 feature)

    Returns:
        BuildResult containing success status, output path, costs, etc.

    Example:
        >>> result = await build("Build a todo app with FastAPI and React")
        >>> print(f"Project created at: {result.output_dir}")
        >>> print(f"Total cost: ${result.total_cost_usd:.2f}")
    """
    start_time = datetime.utcnow()
    logger.info(f"Starting build: {description[:50]}...")

    # Load config if not provided
    if config is None:
        config = load_config()

    # Determine output directory
    if output_dir is None:
        output_dir = Path(config.output_dir)
    else:
        output_dir = Path(output_dir)

    # Create initial state
    initial_state: dict[str, Any] = {
        "description": description,
        "phase": Phase.INIT,
        "interactive": interactive,
        "retry_count": 0,
        "max_retries": config.max_retries,
        "events": [],
        "costs": [],
        "code_files": {},
    }

    # Compile and run the graph
    try:
        graph = compile_graph(config)

        # Run the graph to completion
        final_state = await graph.ainvoke(initial_state)

        # Check for errors
        error = final_state.get("error")
        if error:
            logger.error(f"Build failed: {error}")
            return BuildResult(
                success=False,
                output_dir=None,
                error=error,
                total_tokens=_calculate_tokens(final_state),
                total_cost_usd=_calculate_cost(final_state),
                duration_seconds=_duration_seconds(start_time),
            )

        # Materialize output files
        try:
            project_dir = materialize_state(final_state, output_dir)
            logger.info(f"Project created at: {project_dir}")
        except Exception as e:
            logger.error(f"Failed to write output files: {e}")
            return BuildResult(
                success=False,
                output_dir=None,
                error=f"Failed to write output: {e}",
                total_tokens=_calculate_tokens(final_state),
                total_cost_usd=_calculate_cost(final_state),
                duration_seconds=_duration_seconds(start_time),
            )

        # Success
        return BuildResult(
            success=True,
            output_dir=str(project_dir),
            error=None,
            total_tokens=_calculate_tokens(final_state),
            total_cost_usd=_calculate_cost(final_state),
            duration_seconds=_duration_seconds(start_time),
        )

    except Exception as e:
        logger.exception(f"Build failed with exception: {e}")
        return BuildResult(
            success=False,
            output_dir=None,
            error=str(e),
            total_tokens=0,
            total_cost_usd=0.0,
            duration_seconds=_duration_seconds(start_time),
        )


def _calculate_tokens(state: dict[str, Any]) -> int:
    """Calculate total tokens from state costs."""
    costs = state.get("costs", [])
    return sum(c.input_tokens + c.output_tokens for c in costs)


def _calculate_cost(state: dict[str, Any]) -> float:
    """Calculate total cost from state costs."""
    costs = state.get("costs", [])
    return sum(c.cost_usd for c in costs)


def _duration_seconds(start_time: datetime) -> float:
    """Calculate duration in seconds from start time."""
    delta = datetime.utcnow() - start_time
    return delta.total_seconds()


# Synchronous wrapper for CLI usage
def build_sync(
    description: str,
    config: AgentForgeConfig | None = None,
    output_dir: str | Path | None = None,
    interactive: bool = False,
) -> BuildResult:
    """Synchronous wrapper for the build function.

    See build() for full documentation.
    """
    import asyncio

    return asyncio.run(build(description, config, output_dir, interactive))
