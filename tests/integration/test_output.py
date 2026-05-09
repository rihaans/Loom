"""Integration tests for output file generation.

Tests that the output writer correctly generates all files including ADRs.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from loom.adr.generator import generate_adrs
from loom.output.writer import materialize_state, write_adrs
from loom.state.enums import TechLayer
from loom.state.models import (
    CodeFile,
    DevOpsBundle,
    FileBundle,
    PRD,
)


def create_mock_prd() -> Mock:
    """Create a mock PRD."""
    prd = Mock(spec=PRD)
    prd.project_name = "Test Project"
    prd.project_slug = "test-project"
    prd.project_type = "fullstack_web"
    prd.one_liner = "A test project"
    prd.user_stories = []
    prd.data_entities = []
    prd.must_have_features = ["Feature 1"]
    return prd


def create_mock_architecture() -> Mock:
    """Create a mock architecture with tech stack."""
    arch = Mock()

    # Create mock tech choices
    backend = Mock()
    backend.layer = TechLayer.BACKEND
    backend.technology = "FastAPI"
    backend.version = "0.115"
    backend.rationale = "Modern async Python framework"

    frontend = Mock()
    frontend.layer = TechLayer.FRONTEND
    frontend.technology = "React"
    frontend.version = "18"
    frontend.rationale = "Popular UI library"

    database = Mock()
    database.layer = TechLayer.DATABASE
    database.technology = "SQLite"
    database.version = "3"
    database.rationale = "Simple embedded database"

    arch.stack = [backend, frontend, database]
    arch.api_endpoints = []
    arch.components = []

    return arch


class TestOutputWriter:
    """Test the output writer functionality."""

    def test_materialize_state_creates_directory(self, tmp_path: Path) -> None:
        """Test that materialize_state creates the project directory."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        # code_files is a dict[str, FileBundle] where key is layer name
        state = {
            "prd": prd,
            "architecture": arch,
            "code_files": {
                "backend": FileBundle(files=[
                    CodeFile(path="src/main.py", content="# Main file\nprint('Hello')", language="python"),
                ], entry_point="src/main.py"),
            },
            "devops_files": DevOpsBundle(
                dockerfile="FROM python:3.12",
                docker_compose="version: '3'",
                readme_run_instructions="Run with docker-compose up",
            ),
        }

        output_dir = materialize_state(
            state,
            tmp_path,
            write_adrs_enabled=False,
        )

        assert output_dir.exists()
        assert output_dir.name == "test-project"
        assert (output_dir / "src" / "main.py").exists()

    def test_materialize_state_writes_code_files(self, tmp_path: Path) -> None:
        """Test that code files are written correctly."""
        prd = create_mock_prd()

        state = {
            "prd": prd,
            "architecture": None,
            "code_files": {
                "backend": FileBundle(files=[
                    CodeFile(path="src/main.py", content="print('hello')", language="python"),
                    CodeFile(path="src/utils/helper.py", content="def help(): pass", language="python"),
                ], entry_point="src/main.py"),
                "tests": FileBundle(files=[
                    CodeFile(path="tests/test_main.py", content="def test_main(): pass", language="python"),
                ], entry_point="tests/test_main.py"),
            },
            "devops_files": None,
        }

        output_dir = materialize_state(
            state,
            tmp_path,
            write_adrs_enabled=False,
        )

        assert (output_dir / "src" / "main.py").exists()
        assert (output_dir / "src" / "utils" / "helper.py").exists()
        assert (output_dir / "tests" / "test_main.py").exists()

        # Verify content
        content = (output_dir / "src" / "main.py").read_text()
        assert "print('hello')" in content

    def test_materialize_state_writes_devops_files(self, tmp_path: Path) -> None:
        """Test that DevOps files are written correctly."""
        prd = create_mock_prd()

        state = {
            "prd": prd,
            "architecture": None,
            "code_files": {},
            "devops_files": DevOpsBundle(
                dockerfile_backend="FROM python:3.12\nCOPY . .\nCMD ['python', 'main.py']",
                docker_compose="version: '3'\nservices:\n  app:\n    build: .",
                readme_run_instructions="Run with: docker-compose up",
                github_actions_ci="name: CI\non: push",
            ),
        }

        output_dir = materialize_state(
            state,
            tmp_path,
            write_adrs_enabled=False,
        )

        assert (output_dir / "docker-compose.yml").exists()
        assert (output_dir / "README.md").exists()


class TestADRGeneration:
    """Test ADR file generation in output."""

    def test_write_adrs_creates_adr_files(self, tmp_path: Path) -> None:
        """Test that ADRs are written to disk."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        state = {
            "prd": prd,
            "architecture": arch,
        }

        output_dir = tmp_path / "test-project"
        output_dir.mkdir()

        written_files = write_adrs(state, output_dir)

        assert len(written_files) > 0
        assert (output_dir / "docs" / "adrs").exists()
        assert (output_dir / "docs" / "adrs" / "0000-index.md").exists()

    def test_materialize_with_adrs_enabled(self, tmp_path: Path) -> None:
        """Test full materialize with ADRs enabled."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        state = {
            "prd": prd,
            "architecture": arch,
            "code_files": {
                "backend": FileBundle(files=[
                    CodeFile(path="src/main.py", content="# Code", language="python"),
                ], entry_point="src/main.py"),
            },
            "devops_files": DevOpsBundle(
                dockerfile_backend="FROM python",
                docker_compose="version: '3'",
                readme_run_instructions="Run it",
            ),
        }

        output_dir = materialize_state(
            state,
            tmp_path,
            write_adrs_enabled=True,
            adr_significance="significant",
        )

        # ADRs should be created
        adr_dir = output_dir / "docs" / "adrs"
        assert adr_dir.exists()

        # Should have index and at least one ADR
        adr_files = list(adr_dir.glob("*.md"))
        assert len(adr_files) >= 2  # Index + at least one ADR

    def test_adr_content_is_valid(self, tmp_path: Path) -> None:
        """Test that ADR content follows expected format."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        state = {
            "prd": prd,
            "architecture": arch,
        }

        adrs = generate_adrs(state)

        # Find a non-index ADR
        adr_content = None
        for path, content in adrs.items():
            if "0000-index" not in path:
                adr_content = content
                break

        assert adr_content is not None
        assert "# ADR-" in adr_content
        assert "**Status:** Accepted" in adr_content
        assert "## Context" in adr_content
        assert "## Decision" in adr_content
        assert "## Alternatives Considered" in adr_content
        assert "## Consequences" in adr_content

    def test_adr_index_links_to_all_adrs(self, tmp_path: Path) -> None:
        """Test that the index file lists all ADRs."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        state = {
            "prd": prd,
            "architecture": arch,
        }

        adrs = generate_adrs(state)
        index_content = adrs.get("docs/adrs/0000-index.md", "")

        # Every non-index ADR should be linked
        for path in adrs:
            if "0000-index" not in path:
                filename = Path(path).name
                assert filename in index_content, f"{filename} not found in index"

    def test_no_adrs_when_disabled(self, tmp_path: Path) -> None:
        """Test that ADRs are not created when disabled."""
        prd = create_mock_prd()
        arch = create_mock_architecture()

        state = {
            "prd": prd,
            "architecture": arch,
            "code_files": {},
            "devops_files": None,
        }

        output_dir = materialize_state(
            state,
            tmp_path,
            write_adrs_enabled=False,
        )

        adr_dir = output_dir / "docs" / "adrs"
        assert not adr_dir.exists()


class TestOutputSafety:
    """Test output safety measures."""

    def test_rejects_unsafe_paths(self, tmp_path: Path) -> None:
        """Test that unsafe paths are rejected."""
        prd = create_mock_prd()

        state = {
            "prd": prd,
            "architecture": None,
            "code_files": {
                "backend": FileBundle(files=[
                    CodeFile(path="src/safe.py", content="# Safe file", language="python"),
                ], entry_point="src/safe.py"),
            },
            "devops_files": None,
        }

        output_dir = materialize_state(
            state,
            tmp_path,
            write_adrs_enabled=False,
        )

        # Safe file should exist
        assert (output_dir / "src" / "safe.py").exists()

    def test_creates_nested_directories(self, tmp_path: Path) -> None:
        """Test that nested directories are created."""
        prd = create_mock_prd()

        state = {
            "prd": prd,
            "architecture": None,
            "code_files": {
                "backend": FileBundle(files=[
                    CodeFile(path="src/deep/nested/path/file.py", content="# Deep file", language="python"),
                ], entry_point="src/deep/nested/path/file.py"),
            },
            "devops_files": None,
        }

        output_dir = materialize_state(
            state,
            tmp_path,
            write_adrs_enabled=False,
        )

        assert (output_dir / "src" / "deep" / "nested" / "path" / "file.py").exists()
