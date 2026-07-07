"""Vector store implementations for the memory system."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from loom.memory.embedder import EMBEDDING_DIM
from loom.memory.models import MemoryRecord

logger = logging.getLogger(__name__)


class MemoryStore(ABC):
    """Abstract base class for memory stores."""

    @abstractmethod
    def upsert(self, record: MemoryRecord, embedding: list[float]) -> None:
        """Insert or update a record.

        Args:
            record: The memory record to store.
            embedding: The embedding vector for the record.
        """
        ...

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[MemoryRecord, float]]:
        """Search for similar records.

        Args:
            query_embedding: The query embedding vector.
            k: Number of results to return.
            filters: Optional filters to apply.

        Returns:
            List of (record, similarity_score) tuples.
        """
        ...

    @abstractmethod
    def count(self) -> int:
        """Count total records in the store.

        Returns:
            Number of records.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Delete all records from the store."""
        ...

    @abstractmethod
    def export(self, path: Path) -> int:
        """Export all records to a JSONL file.

        Args:
            path: Path to the output file.

        Returns:
            Number of records exported.
        """
        ...

    @abstractmethod
    def import_(self, path: Path, embedder: Any) -> int:
        """Import records from a JSONL file.

        Args:
            path: Path to the input file.
            embedder: Embedder to generate embeddings for imported records.

        Returns:
            Number of records imported.
        """
        ...


class LanceDBStore(MemoryStore):
    """LanceDB-based memory store.

    Uses LanceDB for efficient vector storage and retrieval.
    Data is stored as files that can be inspected or deleted.
    """

    TABLE_NAME = "build_memory"

    def __init__(self, db_path: Path):
        """Initialize the LanceDB store.

        Args:
            db_path: Path to the LanceDB directory.
        """
        self.db_path = Path(db_path)
        # External LanceDB handles, connected lazily; typed Any since the lib is untyped.
        self._db: Any = None
        self._table: Any = None

    def _ensure_db(self) -> None:
        """Lazy-load the database connection."""
        if self._db is None:
            try:
                import lancedb

                self.db_path.mkdir(parents=True, exist_ok=True)
                self._db = lancedb.connect(str(self.db_path))
                logger.debug(f"Connected to LanceDB at {self.db_path}")
            except ImportError as e:
                raise ImportError(
                    "lancedb is required for memory storage. "
                    "Install with: pip install 'loom[memory]'"
                ) from e

    def _ensure_table(self) -> None:
        """Ensure the table exists, creating if necessary."""
        self._ensure_db()

        if self.TABLE_NAME not in self._db.table_names():
            # Create table with schema
            import pyarrow as pa

            schema = pa.schema(
                [
                    pa.field("run_id", pa.string()),
                    pa.field("timestamp", pa.string()),
                    pa.field("descriptor", pa.string()),
                    pa.field("project_type", pa.string()),
                    pa.field("stack_summary", pa.string()),
                    pa.field("test_passed", pa.bool_()),
                    pa.field("retry_count", pa.int64()),
                    pa.field("file_count", pa.int64()),
                    pa.field("total_cost_usd", pa.float64()),
                    pa.field("one_liner", pa.string()),
                    pa.field("must_have_features", pa.string()),  # JSON encoded
                    pa.field("data_entity_names", pa.string()),  # JSON encoded
                    pa.field("chosen_stack", pa.string()),  # JSON encoded
                    pa.field("api_endpoint_summary", pa.string()),  # JSON encoded
                    pa.field("folder_structure_keys", pa.string()),  # JSON encoded
                    pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
                ]
            )
            self._db.create_table(self.TABLE_NAME, schema=schema)
            logger.info(f"Created table {self.TABLE_NAME}")

        self._table = self._db.open_table(self.TABLE_NAME)

    def _record_to_row(self, record: MemoryRecord, embedding: list[float]) -> dict[str, Any]:
        """Convert a MemoryRecord to a LanceDB row.

        Args:
            record: The memory record.
            embedding: The embedding vector.

        Returns:
            Dict suitable for LanceDB insertion.
        """
        return {
            "run_id": record.run_id,
            "timestamp": record.timestamp.isoformat(),
            "descriptor": record.descriptor,
            "project_type": record.project_type,
            "stack_summary": record.stack_summary,
            "test_passed": record.test_passed,
            "retry_count": record.retry_count,
            "file_count": record.file_count,
            "total_cost_usd": record.total_cost_usd,
            "one_liner": record.one_liner,
            "must_have_features": json.dumps(record.must_have_features),
            "data_entity_names": json.dumps(record.data_entity_names),
            "chosen_stack": json.dumps(record.chosen_stack),
            "api_endpoint_summary": json.dumps(record.api_endpoint_summary),
            "folder_structure_keys": json.dumps(record.folder_structure_keys),
            "vector": embedding,
        }

    def _row_to_record(self, row: dict[str, Any]) -> MemoryRecord:
        """Convert a LanceDB row to a MemoryRecord.

        Args:
            row: The raw row from LanceDB.

        Returns:
            A MemoryRecord instance.
        """
        from datetime import datetime

        return MemoryRecord(
            run_id=row["run_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            descriptor=row["descriptor"],
            project_type=row["project_type"],
            stack_summary=row["stack_summary"],
            test_passed=row["test_passed"],
            retry_count=row["retry_count"],
            file_count=row["file_count"],
            total_cost_usd=row["total_cost_usd"],
            one_liner=row["one_liner"],
            must_have_features=json.loads(row["must_have_features"]),
            data_entity_names=json.loads(row["data_entity_names"]),
            chosen_stack=json.loads(row["chosen_stack"]),
            api_endpoint_summary=json.loads(row["api_endpoint_summary"]),
            folder_structure_keys=json.loads(row["folder_structure_keys"]),
        )

    def upsert(self, record: MemoryRecord, embedding: list[float]) -> None:
        """Insert or update a record.

        Args:
            record: The memory record to store.
            embedding: The embedding vector for the record.
        """
        self._ensure_table()
        row = self._record_to_row(record, embedding)

        # Delete existing record with same run_id if present
        try:
            self._table.delete(f"run_id = '{record.run_id}'")
        except Exception:
            pass  # No matching record

        # Insert new record
        self._table.add([row])
        logger.debug(f"Upserted memory record: {record.run_id}")

    def search(
        self,
        query_embedding: list[float],
        k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[MemoryRecord, float]]:
        """Search for similar records.

        Args:
            query_embedding: The query embedding vector.
            k: Number of results to return.
            filters: Optional filters to apply.

        Returns:
            List of (record, similarity_score) tuples.
        """
        self._ensure_table()

        if self._table.count_rows() == 0:
            return []

        # Build query
        query = self._table.search(query_embedding).limit(k * 3)  # Over-fetch for filtering

        # Build where clause - always exclude failures
        where_parts = ["test_passed = true"]
        if filters:
            if "project_type" in filters:
                where_parts.append(f"project_type = '{filters['project_type']}'")

        if where_parts:
            query = query.where(" AND ".join(where_parts))

        # Execute search
        try:
            results = query.to_list()
        except Exception as e:
            logger.warning(f"Search failed: {e}")
            return []

        # Convert to records with similarity scores
        output = []
        for row in results[:k]:
            record = self._row_to_record(row)
            # LanceDB returns _distance (L2 distance), convert to similarity
            distance = row.get("_distance", 0.0)
            similarity = 1.0 / (1.0 + distance)  # Convert distance to similarity
            output.append((record, similarity))

        return output

    def count(self) -> int:
        """Count total records in the store.

        Returns:
            Number of records.
        """
        self._ensure_table()
        count: int = self._table.count_rows()
        return count

    def clear(self) -> None:
        """Delete all records from the store."""
        self._ensure_db()
        if self.TABLE_NAME in self._db.table_names():
            self._db.drop_table(self.TABLE_NAME)
            logger.info(f"Cleared table {self.TABLE_NAME}")
        self._table = None
        self._ensure_table()

    def export(self, path: Path) -> int:
        """Export all records to a JSONL file.

        Args:
            path: Path to the output file.

        Returns:
            Number of records exported.
        """
        self._ensure_table()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows = self._table.to_pandas().to_dict("records")
        count = 0

        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                # Remove vector from export
                row_copy = {k: v for k, v in row.items() if k != "vector"}
                f.write(json.dumps(row_copy, default=str) + "\n")
                count += 1

        logger.info(f"Exported {count} records to {path}")
        return count

    def import_(self, path: Path, embedder: Any) -> int:
        """Import records from a JSONL file.

        Args:
            path: Path to the input file.
            embedder: Embedder to generate embeddings for imported records.

        Returns:
            Number of records imported.
        """
        self._ensure_table()
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Import file not found: {path}")

        count = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                row = json.loads(line)
                record = self._row_to_record(row)

                # Generate embedding
                embedding = embedder.embed(record.descriptor)

                # Upsert
                self.upsert(record, embedding)
                count += 1

        logger.info(f"Imported {count} records from {path}")
        return count

    def list_all(self, limit: int = 100, offset: int = 0) -> list[MemoryRecord]:
        """List all records with pagination.

        Args:
            limit: Maximum records to return.
            offset: Number of records to skip.

        Returns:
            List of MemoryRecord instances.
        """
        self._ensure_table()

        if self._table.count_rows() == 0:
            return []

        df = self._table.to_pandas()
        df = df.sort_values("timestamp", ascending=False)
        df = df.iloc[offset : offset + limit]

        return [self._row_to_record(row) for row in df.to_dict("records")]


class InMemoryStore(MemoryStore):
    """In-memory store for testing purposes."""

    def __init__(self) -> None:
        """Initialize the in-memory store."""
        self._records: dict[str, tuple[MemoryRecord, list[float]]] = {}

    def upsert(self, record: MemoryRecord, embedding: list[float]) -> None:
        """Insert or update a record."""
        self._records[record.run_id] = (record, embedding)

    def search(
        self,
        query_embedding: list[float],
        k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[MemoryRecord, float]]:
        """Search for similar records using cosine similarity."""
        import math

        def cosine_similarity(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b, strict=True))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        results = []
        for record, embedding in self._records.values():
            # Apply filters
            if not record.test_passed:
                continue
            if filters:
                if "project_type" in filters and record.project_type != filters["project_type"]:
                    continue

            similarity = cosine_similarity(query_embedding, embedding)
            results.append((record, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]

    def count(self) -> int:
        """Count total records."""
        return len(self._records)

    def clear(self) -> None:
        """Delete all records."""
        self._records.clear()

    def export(self, path: Path) -> int:
        """Export all records to a JSONL file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with open(path, "w", encoding="utf-8") as f:
            for record, _ in self._records.values():
                f.write(record.model_dump_json() + "\n")
                count += 1
        return count

    def import_(self, path: Path, embedder: Any) -> int:
        """Import records from a JSONL file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Import file not found: {path}")

        count = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = MemoryRecord.model_validate_json(line)
                embedding = embedder.embed(record.descriptor)
                self.upsert(record, embedding)
                count += 1
        return count
