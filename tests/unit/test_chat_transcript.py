"""Unit tests for chat transcript persistence (Phase 9.5)."""

import json
from pathlib import Path

from loom.cli.chat.transcript import (
    append_event,
    get_chat_path,
    list_transcripts,
    read_transcript,
)


class TestGetChatPath:
    def test_returns_jsonl_path(self, tmp_path: Path) -> None:
        path = get_chat_path("abc123", base_dir=tmp_path)
        assert path.suffix == ".jsonl"
        assert path.stem == "abc123"

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        base = tmp_path / "chats"
        get_chat_path("xyz", base_dir=base)
        assert base.exists()


class TestAppendEvent:
    def test_appends_user_event(self, tmp_path: Path) -> None:
        path = tmp_path / "chat.jsonl"
        append_event(path, {"role": "user", "content": "hello"})

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        ev = json.loads(lines[0])
        assert ev["role"] == "user"
        assert ev["content"] == "hello"
        assert "timestamp" in ev

    def test_multiple_events_in_order(self, tmp_path: Path) -> None:
        path = tmp_path / "chat.jsonl"
        append_event(path, {"role": "user", "content": "first"})
        append_event(path, {"role": "assistant", "content": "second"})
        append_event(path, {"role": "user", "content": "third"})

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        events = [json.loads(line) for line in lines]
        assert events[0]["content"] == "first"
        assert events[1]["content"] == "second"
        assert events[2]["content"] == "third"

    def test_handles_pydantic_model(self, tmp_path: Path) -> None:
        from loom.state.models import (
            PRD,
            Priority,
            ProjectType,
            UserStory,
        )

        prd = PRD(
            project_name="X",
            project_slug="x",
            project_type=ProjectType.REST_API,
            one_liner="x",
            target_users=["u"],
            user_stories=[
                UserStory(
                    id="US-001",
                    role="u",
                    goal="g",
                    benefit="b",
                    acceptance_criteria=["a"],
                    priority=Priority.P0,
                )
            ],
            must_have_features=["f"],
        )
        path = tmp_path / "chat.jsonl"
        append_event(path, {"role": "system", "snapshot": {"prd": prd}})

        ev = json.loads(path.read_text(encoding="utf-8").strip())
        # PRD should have been serialized via model_dump
        assert ev["snapshot"]["prd"]["project_slug"] == "x"


class TestReadTranscript:
    def test_returns_empty_for_missing(self, tmp_path: Path) -> None:
        events = read_transcript("nonexistent", base_dir=tmp_path)
        assert events == []

    def test_reads_events_in_order(self, tmp_path: Path) -> None:
        path = get_chat_path("test-thread", base_dir=tmp_path)
        append_event(path, {"role": "user", "content": "a"})
        append_event(path, {"role": "assistant", "content": "b"})

        events = read_transcript("test-thread", base_dir=tmp_path)
        assert len(events) == 2
        assert events[0]["content"] == "a"
        assert events[1]["content"] == "b"

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        path = get_chat_path("test-bad", base_dir=tmp_path)
        path.write_text(
            '{"role": "user", "content": "good"}\n'
            "this is not json\n"
            '{"role": "user", "content": "also good"}\n',
            encoding="utf-8",
        )
        events = read_transcript("test-bad", base_dir=tmp_path)
        assert len(events) == 2


class TestListTranscripts:
    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        # No files yet
        assert list_transcripts(base_dir=tmp_path) == []

    def test_lists_jsonl_files(self, tmp_path: Path) -> None:
        get_chat_path("alpha", base_dir=tmp_path).write_text("{}\n", encoding="utf-8")
        get_chat_path("beta", base_dir=tmp_path).write_text("{}\n", encoding="utf-8")

        entries = list_transcripts(base_dir=tmp_path)
        thread_ids = {e["thread_id"] for e in entries}
        assert thread_ids == {"alpha", "beta"}

    def test_sorted_most_recent_first(self, tmp_path: Path) -> None:
        import time

        first_path = get_chat_path("old", base_dir=tmp_path)
        first_path.write_text("{}\n", encoding="utf-8")
        time.sleep(0.05)  # ensure mtime difference
        second_path = get_chat_path("new", base_dir=tmp_path)
        second_path.write_text("{}\n", encoding="utf-8")

        entries = list_transcripts(base_dir=tmp_path)
        # Newest first
        assert entries[0]["thread_id"] == "new"
        assert entries[1]["thread_id"] == "old"

    def test_returns_size_and_modified(self, tmp_path: Path) -> None:
        path = get_chat_path("sizetest", base_dir=tmp_path)
        path.write_text("hello world\n", encoding="utf-8")

        entries = list_transcripts(base_dir=tmp_path)
        assert entries[0]["size_bytes"] > 0
        assert "modified_at" in entries[0]
