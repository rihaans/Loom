"""Output file writer for materializing generated code to disk."""

import logging
from pathlib import Path
from typing import Any

from loom.adr.generator import generate_adrs
from loom.output.slugify import ensure_directory, safe_path
from loom.state.models import DevOpsBundle, FileBundle

logger = logging.getLogger(__name__)


def write_file_bundle(bundle: FileBundle, output_dir: Path) -> list[str]:
    """Write a file bundle to disk.

    Args:
        bundle: FileBundle containing code files
        output_dir: Root output directory

    Returns:
        List of written file paths (relative to output_dir)
    """
    written_files = []

    for code_file in bundle.files:
        try:
            # Get safe relative path
            rel_path = safe_path(code_file.path)
            full_path = output_dir / rel_path

            # Ensure parent directory exists
            ensure_directory(full_path.parent)

            # Write file content
            full_path.write_text(code_file.content, encoding="utf-8")
            written_files.append(str(rel_path))

            logger.debug(f"Wrote: {rel_path}")

        except ValueError as e:
            logger.warning(f"Skipping unsafe path {code_file.path}: {e}")
        except OSError as e:
            logger.error(f"Failed to write {code_file.path}: {e}")

    return written_files


def write_devops_bundle(bundle: DevOpsBundle, output_dir: Path) -> list[str]:
    """Write DevOps bundle files to disk.

    Args:
        bundle: DevOpsBundle containing DevOps configs
        output_dir: Root output directory

    Returns:
        List of written file paths
    """
    written_files = []

    # Write Dockerfiles
    if bundle.dockerfile_backend:
        path = output_dir / "backend" / "Dockerfile"
        ensure_directory(path.parent)
        path.write_text(bundle.dockerfile_backend, encoding="utf-8")
        written_files.append("backend/Dockerfile")

    if bundle.dockerfile_frontend:
        path = output_dir / "frontend" / "Dockerfile"
        ensure_directory(path.parent)
        path.write_text(bundle.dockerfile_frontend, encoding="utf-8")
        written_files.append("frontend/Dockerfile")

    # Write docker-compose.yml
    if bundle.docker_compose:
        path = output_dir / "docker-compose.yml"
        path.write_text(bundle.docker_compose, encoding="utf-8")
        written_files.append("docker-compose.yml")

    # Write GitHub Actions CI
    if bundle.github_actions_ci:
        ci_dir = output_dir / ".github" / "workflows"
        ensure_directory(ci_dir)
        path = ci_dir / "ci.yml"
        path.write_text(bundle.github_actions_ci, encoding="utf-8")
        written_files.append(".github/workflows/ci.yml")

    # Write README run instructions
    if bundle.readme_run_instructions:
        path = output_dir / "README.md"
        path.write_text(bundle.readme_run_instructions, encoding="utf-8")
        written_files.append("README.md")

    # Write .env.example
    if bundle.env_example:
        path = output_dir / ".env.example"
        path.write_text(bundle.env_example, encoding="utf-8")
        written_files.append(".env.example")

    # Write additional files
    for file_path, content in bundle.other_files.items():
        try:
            rel_path = safe_path(file_path)
            full_path = output_dir / rel_path
            ensure_directory(full_path.parent)
            full_path.write_text(content, encoding="utf-8")
            written_files.append(str(rel_path))
        except ValueError as e:
            logger.warning(f"Skipping unsafe path {file_path}: {e}")

    return written_files


def write_all_output(
    code_files: dict[str, FileBundle],
    devops_files: DevOpsBundle | None,
    output_dir: Path,
) -> dict[str, list[str]]:
    """Write all generated files to disk.

    Args:
        code_files: Dict mapping layer (frontend/backend) to FileBundle
        devops_files: Optional DevOpsBundle
        output_dir: Root output directory

    Returns:
        Dict mapping category to list of written file paths
    """
    ensure_directory(output_dir)
    result: dict[str, list[str]] = {}

    # Write code files
    for layer, bundle in code_files.items():
        files = write_file_bundle(bundle, output_dir)
        result[layer] = files
        logger.info(f"Wrote {len(files)} {layer} files")

    # Write devops files
    if devops_files:
        files = write_devops_bundle(devops_files, output_dir)
        result["devops"] = files
        logger.info(f"Wrote {len(files)} devops files")

    total_files = sum(len(f) for f in result.values())
    logger.info(f"Total: {total_files} files written to {output_dir}")

    return result


def write_adrs(
    state: dict[str, Any], output_dir: Path, significance: str = "significant"
) -> list[str]:
    """Generate and write ADR files to disk.

    Args:
        state: Agent state with architecture
        output_dir: Root output directory
        significance: ADR filter level

    Returns:
        List of written ADR file paths
    """
    adrs = generate_adrs(state, significance=significance)
    written_files = []

    for file_path, content in adrs.items():
        try:
            rel_path = safe_path(file_path)
            full_path = output_dir / rel_path
            ensure_directory(full_path.parent)
            full_path.write_text(content, encoding="utf-8")
            written_files.append(str(rel_path))
            logger.debug(f"Wrote ADR: {rel_path}")
        except ValueError as e:
            logger.warning(f"Skipping unsafe ADR path {file_path}: {e}")
        except OSError as e:
            logger.error(f"Failed to write ADR {file_path}: {e}")

    if written_files:
        logger.info(f"Wrote {len(written_files)} ADR files")

    return written_files


class OutputExistsError(Exception):
    """Raised when the target project directory already has content.

    Generated builds are whole-directory writes, so materializing over an
    existing project silently destroys whatever was there. Callers decide
    whether to overwrite.
    """

    def __init__(self, path: Path, file_count: int):
        self.path = path
        self.file_count = file_count
        super().__init__(
            f"{path} already contains {file_count} file(s). Writing here would overwrite them."
        )


def directory_has_content(path: Path) -> int:
    """Count existing files under a directory (0 when absent or empty)."""
    if not path.is_dir():
        return 0
    return sum(1 for p in path.rglob("*") if p.is_file())


def materialize_state(
    state: dict[str, Any],
    output_base: Path,
    write_adrs_enabled: bool = True,
    adr_significance: str = "significant",
    overwrite: bool = True,
) -> Path:
    """Materialize all artifacts from state to disk.

    Creates a project directory under output_base using the project slug.

    Args:
        state: Final graph state
        output_base: Base output directory (e.g., "output/")
        write_adrs_enabled: Whether to generate ADR files
        adr_significance: ADR filter level ("all", "significant", "critical")

    Returns:
        Path to the created project directory
    """
    # Get project slug from PRD
    prd = state.get("prd")
    if prd is None:
        raise ValueError("No PRD in state, cannot determine project slug")

    project_slug = prd.project_slug
    output_dir: Path = output_base / project_slug

    # Refuse to clobber an existing project unless explicitly allowed.
    if not overwrite:
        existing = directory_has_content(output_dir)
        if existing:
            raise OutputExistsError(output_dir, existing)

    # Ensure output directory exists
    ensure_directory(output_dir)

    # Write all files
    code_files = state.get("code_files", {})
    devops_files = state.get("devops_files")

    write_all_output(code_files, devops_files, output_dir)

    # Write ADRs if enabled
    if write_adrs_enabled:
        write_adrs(state, output_dir, significance=adr_significance)

    return output_dir
