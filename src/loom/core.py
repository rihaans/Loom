"""Core build functionality for Loom.

This is the main public API for running builds.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from loom._time import now_utc
from loom.cache import get_cache
from loom.config import BuildResult, LoomConfig, load_config
from loom.graph.builder import compile_graph
from loom.graph.checkpoint import (
    generate_thread_id,
    get_async_checkpointer_context,
    get_async_memory_checkpointer_context,
    get_checkpoint_config,
)
from loom.llm.cost import pricing_status
from loom.output import OutputExistsError, materialize_state
from loom.state.enums import Phase

logger = logging.getLogger(__name__)

# Review gates for interactive mode - pause before these nodes
INTERACTIVE_REVIEW_GATES = [
    "architect",  # Review PRD before architecture
    "frontend_dev",  # Review architecture before coding
    "qa_engineer",  # Review code before testing
    "devops_engineer",  # Review tests before deployment
]


async def build(
    description: str,
    config: LoomConfig | None = None,
    output_dir: str | Path | None = None,
    interactive: bool = False,
    thread_id: str | None = None,
    use_persistence: bool = True,
    overwrite: bool = True,
) -> BuildResult:
    """Run the full agent pipeline to build a project.

    This is the main entry point for Loom. It takes a project
    description and runs the full multi-agent pipeline to generate
    a complete project.

    Args:
        description: Natural language description of the project to build
        config: Optional Loom configuration. If not provided,
            configuration will be loaded from environment/files.
        output_dir: Optional output directory. If not provided,
            uses config.output_dir or "output/".
        interactive: If True, pause at review gates for user input.
            Requires checkpointer support for state persistence.
        thread_id: Optional thread ID for this build session.
            If not provided, generates one from description.
        use_persistence: If True, use file-based checkpointing.
            If False, use in-memory checkpointing (for testing).

    Returns:
        BuildResult containing success status, output path, costs, etc.

    Example:
        >>> result = await build("Build a todo app with FastAPI and React")
        >>> print(f"Project created at: {result.output_dir}")
        >>> print(f"Total cost: ${result.total_cost_usd:.2f}")
    """
    start_time = now_utc()
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

    # Generate thread ID for this build
    if thread_id is None:
        thread_id = generate_thread_id(description)

    # Set up interrupt gates for interactive mode
    interrupt_before = INTERACTIVE_REVIEW_GATES if interactive else None

    # Get checkpointer context manager
    if use_persistence:
        checkpointer_ctx = get_async_checkpointer_context()
    else:
        checkpointer_ctx = get_async_memory_checkpointer_context()

    # Compile and run the graph with checkpointer context
    try:
        async with checkpointer_ctx as checkpointer:
            graph = compile_graph(
                config,
                checkpointer=checkpointer,
                interrupt_before=interrupt_before,
            )

            # Create execution config with thread ID
            run_config = get_checkpoint_config(thread_id)

            # Run the graph to completion
            final_state = await graph.ainvoke(initial_state, config=run_config)

            # Extract phase for result
            final_phase = str(final_state.get("phase", Phase.INIT))

            # Check for errors
            error = final_state.get("error")
            if error:
                logger.error(f"Build failed: {error}")
                return BuildResult(
                    success=False,
                    output_dir=None,
                    error=error,
                    phase=final_phase,
                    total_tokens=_calculate_tokens(final_state),
                    total_cost_usd=_calculate_cost(final_state),
                    duration_seconds=_duration_seconds(start_time),
                )

            # Materialize output files
            try:
                project_dir = materialize_state(
                    final_state,
                    output_dir,
                    write_adrs_enabled=config.adr.enabled,
                    adr_significance=config.adr.significance,
                    overwrite=overwrite,
                )
                logger.info(f"Project created at: {project_dir}")
            except OutputExistsError as e:
                logger.error(str(e))
                return BuildResult(
                    success=False,
                    output_dir=None,
                    error=str(e),
                    phase=final_phase,
                    total_tokens=_calculate_tokens(final_state),
                    total_cost_usd=_calculate_cost(final_state),
                    duration_seconds=_duration_seconds(start_time),
                )
            except Exception as e:
                logger.error(f"Failed to write output files: {e}")
                return BuildResult(
                    success=False,
                    output_dir=None,
                    error=f"Failed to write output: {e}",
                    phase=final_phase,
                    total_tokens=_calculate_tokens(final_state),
                    total_cost_usd=_calculate_cost(final_state),
                    duration_seconds=_duration_seconds(start_time),
                )

            # Success
            return BuildResult(
                success=True,
                output_dir=str(project_dir),
                error=None,
                phase=final_phase,
                total_tokens=_calculate_tokens(final_state),
                total_cost_usd=_calculate_cost(final_state),
                duration_seconds=_duration_seconds(start_time),
                test_passed=_test_passed(final_state),
                tests_verified=_tests_verified(final_state),
                cost_status=pricing_status(config.llm_default.provider, config.llm_default.model),
                cache_hits=get_cache().stats.hits,
                cache_misses=get_cache().stats.misses,
            )

    except Exception as e:
        logger.exception(f"Build failed with exception: {e}")
        return BuildResult(
            success=False,
            output_dir=None,
            error=str(e),
            phase=str(Phase.INIT),
            total_tokens=0,
            total_cost_usd=0.0,
            duration_seconds=_duration_seconds(start_time),
        )


def _tests_verified(state: dict[str, Any]) -> bool:
    """True only when a real test run produced the report in state.

    A missing report means QA never ran; a stubbed report means no sandbox was
    available and nothing was executed. Neither counts as verified.
    """
    report = state.get("test_report")
    if report is None:
        return False
    return not getattr(report, "is_stub", False)


def _test_passed(state: dict[str, Any]) -> bool | None:
    """Whether tests passed, or None when nothing was actually executed."""
    report = state.get("test_report")
    if report is None or getattr(report, "is_stub", False):
        return None
    return bool(report.failed == 0 and report.total > 0)


def _calculate_tokens(state: dict[str, Any]) -> int:
    """Calculate total tokens from state costs."""
    costs = state.get("costs", [])
    return sum(c.input_tokens + c.output_tokens for c in costs)


def _calculate_cost(state: dict[str, Any]) -> float:
    """Calculate total cost from state costs."""
    costs = state.get("costs", [])
    return float(sum(c.cost_usd for c in costs))


def _duration_seconds(start_time: datetime) -> float:
    """Calculate duration in seconds from start time."""
    delta = now_utc() - start_time
    return delta.total_seconds()


async def resume_build(
    thread_id: str,
    config: LoomConfig | None = None,
    output_dir: str | Path | None = None,
    user_input: dict[str, Any] | None = None,
    overwrite: bool = True,
) -> BuildResult:
    """Resume an interrupted build session.

    Use this to continue a build that was paused at a review gate
    in interactive mode.

    Args:
        thread_id: The thread ID of the build to resume
        config: Optional Loom configuration
        output_dir: Optional output directory
        user_input: Optional state updates from user review

    Returns:
        BuildResult containing success status, output path, costs, etc.
    """
    start_time = now_utc()
    logger.info(f"Resuming build: {thread_id}")

    # Load config if not provided
    if config is None:
        config = load_config()

    # Determine output directory
    if output_dir is None:
        output_dir = Path(config.output_dir)
    else:
        output_dir = Path(output_dir)

    # Set up checkpointing (must use persistence to resume)
    checkpointer_ctx = get_async_checkpointer_context()

    try:
        async with checkpointer_ctx as checkpointer:
            # Compile graph with checkpointer
            graph = compile_graph(
                config,
                checkpointer=checkpointer,
                interrupt_before=INTERACTIVE_REVIEW_GATES,
            )

            # Create execution config with thread ID
            run_config = get_checkpoint_config(thread_id)

            # Resume execution, optionally with user input
            if user_input is not None:
                # Update state with user input before resuming
                final_state = await graph.ainvoke(user_input, config=run_config)
            else:
                # Resume with None to continue from checkpoint
                final_state = await graph.ainvoke(None, config=run_config)

            # Extract phase for result
            final_phase = str(final_state.get("phase", Phase.INIT))

            # Check for errors
            error = final_state.get("error")
            if error:
                logger.error(f"Build failed: {error}")
                return BuildResult(
                    success=False,
                    output_dir=None,
                    error=error,
                    phase=final_phase,
                    total_tokens=_calculate_tokens(final_state),
                    total_cost_usd=_calculate_cost(final_state),
                    duration_seconds=_duration_seconds(start_time),
                )

            # Materialize output files
            try:
                project_dir = materialize_state(
                    final_state,
                    output_dir,
                    write_adrs_enabled=config.adr.enabled,
                    adr_significance=config.adr.significance,
                    overwrite=overwrite,
                )
                logger.info(f"Project created at: {project_dir}")
            except OutputExistsError as e:
                logger.error(str(e))
                return BuildResult(
                    success=False,
                    output_dir=None,
                    error=str(e),
                    phase=final_phase,
                    total_tokens=_calculate_tokens(final_state),
                    total_cost_usd=_calculate_cost(final_state),
                    duration_seconds=_duration_seconds(start_time),
                )
            except Exception as e:
                logger.error(f"Failed to write output files: {e}")
                return BuildResult(
                    success=False,
                    output_dir=None,
                    error=f"Failed to write output: {e}",
                    phase=final_phase,
                    total_tokens=_calculate_tokens(final_state),
                    total_cost_usd=_calculate_cost(final_state),
                    duration_seconds=_duration_seconds(start_time),
                )

            # Success
            return BuildResult(
                success=True,
                output_dir=str(project_dir),
                error=None,
                phase=final_phase,
                total_tokens=_calculate_tokens(final_state),
                total_cost_usd=_calculate_cost(final_state),
                duration_seconds=_duration_seconds(start_time),
                test_passed=_test_passed(final_state),
                tests_verified=_tests_verified(final_state),
                cost_status=pricing_status(config.llm_default.provider, config.llm_default.model),
                cache_hits=get_cache().stats.hits,
                cache_misses=get_cache().stats.misses,
            )

    except Exception as e:
        logger.exception(f"Resume failed with exception: {e}")
        return BuildResult(
            success=False,
            output_dir=None,
            error=str(e),
            phase=str(Phase.INIT),
            total_tokens=0,
            total_cost_usd=0.0,
            duration_seconds=_duration_seconds(start_time),
        )


# Synchronous wrapper for CLI usage
def build_sync(
    description: str,
    config: LoomConfig | None = None,
    output_dir: str | Path | None = None,
    interactive: bool = False,
    use_persistence: bool = True,
    overwrite: bool = True,
) -> BuildResult:
    """Synchronous wrapper for the build function.

    See build() for full documentation.
    """
    import asyncio

    return asyncio.run(
        build(
            description,
            config,
            output_dir,
            interactive,
            use_persistence=use_persistence,
            overwrite=overwrite,
        )
    )


def resume_build_sync(
    thread_id: str,
    config: LoomConfig | None = None,
    output_dir: str | Path | None = None,
    user_input: dict[str, Any] | None = None,
) -> BuildResult:
    """Synchronous wrapper for resume_build.

    See resume_build() for full documentation.
    """
    import asyncio

    return asyncio.run(resume_build(thread_id, config, output_dir, user_input))
