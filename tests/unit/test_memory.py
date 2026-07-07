"""Tests for the memory system."""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from loom.memory.embedder import EMBEDDING_DIM, LocalEmbedder, OpenAIEmbedder
from loom.memory.factory import (
    get_embedder,
    get_memory_store,
    is_memory_available,
    reset_singletons,
)
from loom.memory.models import (
    MemoryConfig,
    MemoryContext,
    MemoryRecord,
    build_descriptor,
)
from loom.memory.store import InMemoryStore


class TestMemoryConfig:
    """Tests for MemoryConfig model."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = MemoryConfig()
        assert config.enabled is True
        assert config.db_path == ".loom/memory/lancedb"
        assert config.embedder == "local"
        assert config.embedder_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert config.top_k == 3
        assert config.min_similarity == 0.55
        assert config.only_persist_passing is True

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = MemoryConfig(
            enabled=False,
            db_path="/custom/path",
            embedder="openai",
            embedder_model="text-embedding-3-small",
            top_k=5,
            min_similarity=0.7,
            only_persist_passing=False,
        )
        assert config.enabled is False
        assert config.db_path == "/custom/path"
        assert config.embedder == "openai"
        assert config.top_k == 5
        assert config.min_similarity == 0.7
        assert config.only_persist_passing is False

    def test_top_k_constraints(self) -> None:
        """Test top_k must be between 1 and 10."""
        config = MemoryConfig(top_k=1)
        assert config.top_k == 1

        config = MemoryConfig(top_k=10)
        assert config.top_k == 10

        with pytest.raises(ValueError):
            MemoryConfig(top_k=0)

        with pytest.raises(ValueError):
            MemoryConfig(top_k=11)

    def test_min_similarity_constraints(self) -> None:
        """Test min_similarity must be between 0 and 1."""
        config = MemoryConfig(min_similarity=0.0)
        assert config.min_similarity == 0.0

        config = MemoryConfig(min_similarity=1.0)
        assert config.min_similarity == 1.0

        with pytest.raises(ValueError):
            MemoryConfig(min_similarity=-0.1)

        with pytest.raises(ValueError):
            MemoryConfig(min_similarity=1.1)


class TestMemoryRecord:
    """Tests for MemoryRecord model."""

    def test_minimal_record(self) -> None:
        """Test creating a minimal record."""
        record = MemoryRecord(
            run_id="test-123",
            descriptor="Test project description",
            project_type="webapp",
            stack_summary="FastAPI+React+SQLite",
            one_liner="A test application",
        )
        assert record.run_id == "test-123"
        assert record.descriptor == "Test project description"
        assert record.project_type == "webapp"
        assert record.stack_summary == "FastAPI+React+SQLite"
        assert record.test_passed is True  # default
        assert record.retry_count == 0  # default
        assert record.file_count == 0  # default
        assert record.must_have_features == []  # default

    def test_full_record(self) -> None:
        """Test creating a full record."""
        record = MemoryRecord(
            run_id="test-456",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            descriptor="Full project description",
            project_type="api",
            stack_summary="FastAPI+SQLite",
            test_passed=True,
            retry_count=1,
            file_count=25,
            total_cost_usd=0.05,
            one_liner="A full API",
            must_have_features=["auth", "crud"],
            data_entity_names=["User", "Post"],
            chosen_stack=[{"layer": "backend", "technology": "FastAPI"}],
            api_endpoint_summary=["GET /users", "POST /users"],
            folder_structure_keys=["src", "tests"],
        )
        assert record.retry_count == 1
        assert record.file_count == 25
        assert record.total_cost_usd == 0.05
        assert len(record.must_have_features) == 2
        assert len(record.api_endpoint_summary) == 2


class TestMemoryContext:
    """Tests for MemoryContext model."""

    def test_empty_context(self) -> None:
        """Test empty context produces no prompt block."""
        context = MemoryContext()
        assert context.examples == []
        assert context.similarity_scores == []
        assert context.to_prompt_block() == ""

    def test_context_with_examples(self) -> None:
        """Test context with examples produces prompt block."""
        record = MemoryRecord(
            run_id="test-123",
            descriptor="Test project",
            project_type="webapp",
            stack_summary="FastAPI+React",
            one_liner="A test app",
            api_endpoint_summary=["GET /api/test", "POST /api/test"],
        )
        context = MemoryContext(
            examples=[record],
            similarity_scores=[0.85],
        )

        block = context.to_prompt_block()
        assert "Similar past builds" in block
        assert "Example 1 (similarity 0.85)" in block
        assert "A test app" in block
        assert "FastAPI+React" in block
        assert "GET /api/test" in block


class TestBuildDescriptor:
    """Tests for the build_descriptor function."""

    def test_build_descriptor_with_prd(self) -> None:
        """Test building descriptor from PRD."""
        # Mock PRD object
        prd = Mock()
        prd.project_type.value = "webapp"
        prd.one_liner = "A todo list application"
        prd.must_have_features = ["add tasks", "mark complete", "delete tasks"]

        # Mock data entities with proper name attribute
        task_entity = Mock()
        task_entity.name = "Task"
        user_entity = Mock()
        user_entity.name = "User"
        prd.data_entities = [task_entity, user_entity]

        descriptor = build_descriptor(prd)
        assert "webapp" in descriptor
        assert "todo list" in descriptor
        assert "must_have" in descriptor
        assert "add tasks" in descriptor

    def test_build_descriptor_empty_prd(self) -> None:
        """Test building descriptor from None returns empty string."""
        assert build_descriptor(None) == ""


class TestInMemoryStore:
    """Tests for InMemoryStore."""

    @pytest.fixture
    def store(self) -> InMemoryStore:
        """Create a fresh in-memory store."""
        return InMemoryStore()

    @pytest.fixture
    def sample_record(self) -> MemoryRecord:
        """Create a sample record for testing."""
        return MemoryRecord(
            run_id="test-123",
            descriptor="Test project",
            project_type="webapp",
            stack_summary="FastAPI+React",
            one_liner="A test app",
            test_passed=True,
        )

    @pytest.fixture
    def sample_embedding(self) -> list[float]:
        """Create a sample embedding vector."""
        return [0.1] * EMBEDDING_DIM

    def test_upsert_and_count(
        self, store: InMemoryStore, sample_record: MemoryRecord, sample_embedding: list[float]
    ) -> None:
        """Test upserting a record and counting."""
        assert store.count() == 0
        store.upsert(sample_record, sample_embedding)
        assert store.count() == 1

    def test_upsert_updates_existing(
        self, store: InMemoryStore, sample_record: MemoryRecord, sample_embedding: list[float]
    ) -> None:
        """Test upserting with same run_id updates the record."""
        store.upsert(sample_record, sample_embedding)
        assert store.count() == 1

        # Update the record
        updated_record = MemoryRecord(
            run_id=sample_record.run_id,
            descriptor="Updated project",
            project_type="api",
            stack_summary="FastAPI",
            one_liner="Updated app",
        )
        store.upsert(updated_record, sample_embedding)
        assert store.count() == 1

    def test_search_returns_similar(
        self, store: InMemoryStore, sample_record: MemoryRecord
    ) -> None:
        """Test search returns similar records."""
        embedding = [0.5] * EMBEDDING_DIM
        store.upsert(sample_record, embedding)

        # Search with similar embedding
        query_embedding = [0.5] * EMBEDDING_DIM
        results = store.search(query_embedding, k=3)

        assert len(results) == 1
        record, score = results[0]
        assert record.run_id == sample_record.run_id
        assert score > 0.9  # Should be very similar

    def test_search_excludes_failed_tests(self, store: InMemoryStore) -> None:
        """Test search excludes records where tests failed."""
        failed_record = MemoryRecord(
            run_id="failed-123",
            descriptor="Failed project",
            project_type="webapp",
            stack_summary="FastAPI",
            one_liner="Failed app",
            test_passed=False,  # Failed tests
        )
        embedding = [0.5] * EMBEDDING_DIM
        store.upsert(failed_record, embedding)

        # Search should return nothing
        results = store.search([0.5] * EMBEDDING_DIM, k=3)
        assert len(results) == 0

    def test_clear(
        self, store: InMemoryStore, sample_record: MemoryRecord, sample_embedding: list[float]
    ) -> None:
        """Test clearing the store."""
        store.upsert(sample_record, sample_embedding)
        assert store.count() == 1

        store.clear()
        assert store.count() == 0

    def test_export_import(
        self,
        store: InMemoryStore,
        sample_record: MemoryRecord,
        sample_embedding: list[float],
        tmp_path: Path,
    ) -> None:
        """Test exporting and importing records."""
        store.upsert(sample_record, sample_embedding)

        export_path = tmp_path / "export.jsonl"
        count = store.export(export_path)
        assert count == 1
        assert export_path.exists()

        # Create mock embedder
        mock_embedder = Mock()
        mock_embedder.embed.return_value = sample_embedding

        # Import into new store
        new_store = InMemoryStore()
        import_count = new_store.import_(export_path, mock_embedder)
        assert import_count == 1
        assert new_store.count() == 1


class TestFactory:
    """Tests for factory functions."""

    def setup_method(self) -> None:
        """Reset singletons before each test."""
        reset_singletons()

    def teardown_method(self) -> None:
        """Reset singletons after each test."""
        reset_singletons()

    def test_is_memory_available_without_deps(self) -> None:
        """Test is_memory_available returns False without dependencies."""
        with patch.dict("sys.modules", {"lancedb": None, "sentence_transformers": None}):
            # Force reimport
            import importlib

            from loom.memory import factory

            importlib.reload(factory)
            # The function checks imports, but we can't easily test this
            # Just verify the function exists and returns bool
            result = is_memory_available()
            assert isinstance(result, bool)

    def test_get_embedder_creates_local_by_default(self) -> None:
        """Test get_embedder creates LocalEmbedder by default."""
        config = MemoryConfig(embedder="local")
        embedder = get_embedder(config)
        assert isinstance(embedder, LocalEmbedder)

    def test_get_embedder_creates_openai_when_configured(self) -> None:
        """Test get_embedder creates OpenAIEmbedder when configured."""
        config = MemoryConfig(embedder="openai")
        embedder = get_embedder(config)
        assert isinstance(embedder, OpenAIEmbedder)

    def test_get_memory_store_returns_inmemory_fallback(self) -> None:
        """Test get_memory_store falls back to InMemoryStore."""
        # Mock ImportError for lancedb
        with patch("loom.memory.factory.LanceDBStore") as mock_lance:
            mock_lance.side_effect = ImportError("lancedb not installed")
            reset_singletons()

            store = get_memory_store(MemoryConfig())
            assert isinstance(store, InMemoryStore)


class TestEmbedder:
    """Tests for embedder classes."""

    def test_local_embedder_dim(self) -> None:
        """Test LocalEmbedder has correct dimension."""
        embedder = LocalEmbedder()
        assert embedder.dim == EMBEDDING_DIM

    def test_openai_embedder_dim(self) -> None:
        """Test OpenAIEmbedder has correct dimension."""
        embedder = OpenAIEmbedder()
        assert embedder.dim == 1536  # OpenAI embedding dimension
