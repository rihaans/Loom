"""Tests for durable dashboard run history and the output overwrite gate."""

from pathlib import Path

import pytest

from loom.output.writer import OutputExistsError, directory_has_content, materialize_state
from loom.server.history import RunHistory, RunRecord


@pytest.fixture
def history(tmp_path: Path) -> RunHistory:
    return RunHistory(tmp_path / "runs.db")


def _record(run_id: str = "r1", **kw: object) -> RunRecord:
    base: dict[str, object] = {
        "run_id": run_id,
        "thread_id": "t1",
        "description": "build a thing",
        "status": "running",
        "started_at": "2026-09-18T00:00:00",
    }
    base.update(kw)
    return RunRecord(**base)  # type: ignore[arg-type]


class TestRunHistory:
    def test_empty_history_lists_nothing(self, history: RunHistory) -> None:
        assert history.list() == []

    def test_save_then_read_back(self, history: RunHistory) -> None:
        history.save(_record())
        rows = history.list()
        assert len(rows) == 1
        assert rows[0].run_id == "r1"
        assert rows[0].description == "build a thing"

    def test_history_survives_a_new_connection(self, tmp_path: Path) -> None:
        """The point of the store: a restart must not lose the list."""
        db = tmp_path / "runs.db"
        RunHistory(db).save(_record())
        assert len(RunHistory(db).list()) == 1

    def test_same_run_updates_rather_than_duplicates(self, history: RunHistory) -> None:
        history.save(_record(status="running"))
        history.save(_record(status="completed", total_tokens=99, tests_verified=True))
        rows = history.list()
        assert len(rows) == 1
        assert rows[0].status == "completed"
        assert rows[0].total_tokens == 99
        assert rows[0].tests_verified is True

    def test_newest_first(self, history: RunHistory) -> None:
        history.save(_record("old", started_at="2026-09-01T00:00:00"))
        history.save(_record("new", started_at="2026-09-17T00:00:00"))
        assert [r.run_id for r in history.list()] == ["new", "old"]

    def test_get_missing_run_is_none(self, history: RunHistory) -> None:
        assert history.get("nope") is None


class TestOverwriteGate:
    def test_counts_nothing_for_missing_dir(self, tmp_path: Path) -> None:
        assert directory_has_content(tmp_path / "absent") == 0

    def test_counts_nested_files(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "b.md").write_text("y", encoding="utf-8")
        assert directory_has_content(tmp_path) == 2

    def test_refuses_to_clobber_when_overwrite_disabled(self, tmp_path: Path) -> None:
        project = tmp_path / "my-app"
        project.mkdir()
        (project / "important.py").write_text("do not lose me", encoding="utf-8")

        class _PRD:
            project_slug = "my-app"

        with pytest.raises(OutputExistsError) as exc:
            materialize_state({"prd": _PRD()}, tmp_path, overwrite=False)

        assert "already contains" in str(exc.value)
        # The existing file must still be there.
        assert (project / "important.py").read_text(encoding="utf-8") == "do not lose me"
