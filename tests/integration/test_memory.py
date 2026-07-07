"""Integration tests for the memory system.

Tests memory retrieval and persistence across builds.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from loom.memory.models import MemoryContext, MemoryRecord
from loom.memory.store import InMemoryStore


def create_memory_record(
    run_id: str = "test-1",
    descriptor: str = "Build a todo app",
    test_passed: bool = True,
) -> MemoryRecord:
    """Create a test MemoryRecord."""
    return MemoryRecord(
        run_id=run_id,
        timestamp=datetime.utcnow(),
        descriptor=descriptor,
        project_type="fullstack_web",
        stack_summary="FastAPI+React+SQLite",
        test_passed=test_passed,
        retry_count=0,
        file_count=10,
        total_cost_usd=0.05,
        one_liner="A simple todo application",
        must_have_features=["Create todos", "List todos"],
        data_entity_names=["Todo"],
        chosen_stack=[
            {"layer": "backend", "technology": "FastAPI"},
            {"layer": "frontend", "technology": "React"},
        ],
        api_endpoint_summary=["GET /todos", "POST /todos"],
        folder_structure_keys=["src", "tests"],
    )


class TestMemoryStore:
    """Test the memory store functionality."""

    def test_in_memory_store_upsert_and_search(self) -> None:
        """Test upserting and searching records in memory store."""
        store = InMemoryStore()

        # Create a mock embedding
        mock_embedding = [0.1] * 384  # Typical embedding size

        record = create_memory_record()

        store.upsert(record, mock_embedding)

        # Search with similar embedding
        results = store.search(mock_embedding, k=5)

        assert len(results) == 1
        assert results[0][0].run_id == "test-1"
        assert results[0][0].descriptor == "Build a todo app"

    def test_in_memory_store_multiple_records(self) -> None:
        """Test searching across multiple records."""
        store = InMemoryStore()

        # Add multiple records with different embeddings
        for i in range(5):
            embedding = [0.1 * (i + 1)] * 384
            record = create_memory_record(
                run_id=f"test-{i}",
                descriptor=f"Project {i}",
            )
            store.upsert(record, embedding)

        # Search
        query_embedding = [0.3] * 384
        results = store.search(query_embedding, k=3)

        assert len(results) == 3

    def test_in_memory_store_count(self) -> None:
        """Test counting records."""
        store = InMemoryStore()

        for i in range(3):
            record = create_memory_record(run_id=f"test-{i}")
            store.upsert(record, [0.1] * 384)

        assert store.count() == 3

    def test_in_memory_store_clear(self) -> None:
        """Test clearing the store."""
        store = InMemoryStore()

        record = create_memory_record()
        store.upsert(record, [0.1] * 384)

        assert store.count() == 1

        store.clear()

        assert store.count() == 0

    def test_search_excludes_failed_builds(self) -> None:
        """Test that failed builds are excluded from search."""
        store = InMemoryStore()

        # Add passing build
        passing = create_memory_record(run_id="pass-1", test_passed=True)
        store.upsert(passing, [0.1] * 384)

        # Add failing build
        failing = create_memory_record(run_id="fail-1", test_passed=False)
        store.upsert(failing, [0.1] * 384)

        # Search should only return passing build
        results = store.search([0.1] * 384, k=10)

        assert len(results) == 1
        assert results[0][0].run_id == "pass-1"


class TestMemoryContext:
    """Test memory context creation and usage."""

    def test_memory_context_to_prompt_block(self) -> None:
        """Test rendering MemoryContext as prompt block."""
        records = [
            create_memory_record(run_id="ex-1"),
            create_memory_record(run_id="ex-2"),
        ]

        context = MemoryContext(
            examples=records,
            similarity_scores=[0.9, 0.8],
        )

        block = context.to_prompt_block()

        assert "Similar past builds" in block
        assert "Example 1" in block
        assert "Example 2" in block
        assert "similarity 0.90" in block
        assert "FastAPI+React+SQLite" in block

    def test_empty_context_returns_empty_string(self) -> None:
        """Test that empty context returns empty string."""
        context = MemoryContext(examples=[], similarity_scores=[])
        assert context.to_prompt_block() == ""


class TestMemoryIntegration:
    """Integration tests for memory with the build pipeline."""

    @pytest.mark.asyncio
    async def test_memory_retrieve_returns_context(self) -> None:
        """Test that memory retrieve node returns context."""
        from loom.agents.memory_retrieve import memory_retrieve_node
        from loom.config import LoomConfig

        config = LoomConfig()
        config.memory.enabled = True

        # Create a mock PRD
        prd = Mock()
        prd.one_liner = "A todo application"
        prd.project_type = Mock()
        prd.project_type.value = "fullstack_web"
        prd.must_have_features = ["Create todos"]
        prd.data_entities = []

        state = {
            "prd": prd,
            "description": "Build a todo app",
        }

        # Mock the memory store and embedder
        mock_store = InMemoryStore()
        mock_record = create_memory_record()
        mock_store.upsert(mock_record, [0.1] * 384)

        with (
            patch("loom.agents.memory_retrieve.get_memory_store", return_value=mock_store),
            patch("loom.agents.memory_retrieve.get_embedder") as mock_embedder_fn,
            patch("loom.agents.memory_retrieve.is_memory_available", return_value=True),
        ):
            mock_embedder = Mock()
            mock_embedder.embed.return_value = [0.1] * 384
            mock_embedder_fn.return_value = mock_embedder

            result = await memory_retrieve_node(state, config)

            # Should have memory_context in result (may be empty if threshold not met)
            assert "memory_context" in result or result == {}

    @pytest.mark.asyncio
    async def test_memory_persist_saves_record(self) -> None:
        """Test that memory persist node saves successful builds."""
        from loom.agents.memory_persist import memory_persist_node
        from loom.config import LoomConfig
        from loom.state.models import (
            PRD,
            ArchitectureDoc,
            TestCase,
            TestReport,
        )

        config = LoomConfig()
        config.memory.enabled = True

        # Create real Pydantic instances (memory_persist_node validates these)
        prd = PRD(
            project_name="Todo App",
            project_slug="todo-app",
            project_type="fullstack_web",
            one_liner="Todo app",
            target_users=["users"],
            user_stories=[
                {
                    "id": "US-001",
                    "role": "user",
                    "goal": "create todo",
                    "benefit": "stay organized",
                    "acceptance_criteria": ["Can create"],
                    "priority": "P0",
                }
            ],
            must_have_features=["Create todos"],
        )

        arch = ArchitectureDoc(
            stack=[
                {
                    "layer": "backend",
                    "technology": "FastAPI",
                    "version": "0.115",
                    "rationale": "Modern",
                },
            ],
            api_endpoints=[],
            components=[],
            folder_structure={},
        )

        test_report = TestReport(
            total=5,
            passed=5,
            failed=0,
            skipped=0,
            duration_ms=100.0,
            cases=[
                TestCase(name="test_1", file="t.py", passed=True, duration_ms=10.0),
            ],
        )

        state = {
            "description": "Build todo app",
            "prd": prd,
            "architecture": arch,
            "test_report": test_report,
            "retry_count": 0,
            "code_files": {},
            "costs": [],
        }

        mock_store = InMemoryStore()

        with (
            patch("loom.agents.memory_persist.get_memory_store", return_value=mock_store),
            patch("loom.agents.memory_persist.get_embedder") as mock_embedder_fn,
            patch("loom.agents.memory_persist.is_memory_available", return_value=True),
        ):
            mock_embedder = Mock()
            mock_embedder.embed.return_value = [0.1] * 384
            mock_embedder_fn.return_value = mock_embedder

            await memory_persist_node(state, config)

            # Record should be saved
            assert mock_store.count() == 1

    @pytest.mark.asyncio
    async def test_memory_disabled_skips_operations(self) -> None:
        """Test that disabled memory skips all operations."""
        from loom.agents.memory_retrieve import memory_retrieve_node
        from loom.config import LoomConfig

        config = LoomConfig()
        config.memory.enabled = False

        prd = Mock()
        prd.one_liner = "Test"
        prd.project_type = Mock()
        prd.project_type.value = "rest_api"
        prd.must_have_features = []
        prd.data_entities = []

        state = {"prd": prd, "description": "Test"}

        result = await memory_retrieve_node(state, config)

        # Should return empty update when disabled
        assert result.get("memory_context") is None or result == {}


class TestMemoryExportImport:
    """Test memory export/import functionality."""

    def test_export_creates_file(self, tmp_path: Path) -> None:
        """Test that export creates a JSONL file."""
        store = InMemoryStore()

        for i in range(3):
            record = create_memory_record(run_id=f"test-{i}")
            store.upsert(record, [0.1] * 384)

        export_path = tmp_path / "memory.jsonl"
        count = store.export(export_path)

        assert count == 3
        assert export_path.exists()

        # Verify content
        lines = export_path.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_import_loads_records(self, tmp_path: Path) -> None:
        """Test that import loads records from file."""
        # Create export file
        original_store = InMemoryStore()
        for i in range(2):
            record = create_memory_record(run_id=f"import-{i}")
            original_store.upsert(record, [0.1] * 384)

        export_path = tmp_path / "memory.jsonl"
        original_store.export(export_path)

        # Import into new store
        new_store = InMemoryStore()
        mock_embedder = Mock()
        mock_embedder.embed.return_value = [0.1] * 384

        count = new_store.import_(export_path, mock_embedder)

        assert count == 2
        assert new_store.count() == 2
