"""Tests for what the Code Reviewer actually re-reads on a revise loop.

The review prompt is dominated by the code dump, and the reviewer is the node
that repeats, so re-sending code it already read is the largest avoidable cost
in the loop. It must still never lose sight of a file.
"""

from loom.agents.reviewer import _dump_code, _revised_bundles
from loom.state.enums import TargetAgent
from loom.state.models import CodeFile, FileBundle, ReviewReport


def _code() -> dict[str, FileBundle]:
    return {
        "backend": FileBundle(
            files=[
                CodeFile(path=f"backend/m{i}.py", content="x = 1\n" * 50, language="python")
                for i in range(3)
            ],
            entry_point="backend/main.py",
        ),
        "frontend": FileBundle(
            files=[
                CodeFile(
                    path=f"frontend/C{i}.tsx", content="const a=1;\n" * 50, language="typescript"
                )
                for i in range(3)
            ],
            entry_point="frontend/main.tsx",
        ),
    }


def _report(target: TargetAgent) -> ReviewReport:
    return ReviewReport(approved=False, summary="needs work", target_agent=target)


class TestRevisedBundles:
    def test_first_review_reads_everything(self) -> None:
        assert _revised_bundles(None) is None

    def test_targeted_revision_narrows_to_one_bundle(self) -> None:
        assert _revised_bundles(_report(TargetAgent.BACKEND_DEV)) == {"backend"}
        assert _revised_bundles(_report(TargetAgent.FRONTEND_DEV)) == {"frontend"}

    def test_both_revised_reads_everything(self) -> None:
        assert _revised_bundles(_report(TargetAgent.BOTH)) is None


class TestDumpCode:
    def test_first_review_includes_every_file_body(self) -> None:
        dump, count = _dump_code(_code())
        assert count == 6
        for name in ("backend/m0.py", "frontend/C0.tsx"):
            assert name in dump
        assert "x = 1" in dump and "const a=1;" in dump

    def test_unchanged_bundle_is_indexed_not_repeated(self) -> None:
        code = _code()
        dump, _count = _dump_code(code, {"backend"})

        # Revised bundle: full content.
        assert "x = 1" in dump
        # Unchanged bundle: paths still listed, bodies omitted.
        assert "const a=1;" not in dump
        assert "frontend/C0.tsx" in dump
        assert "unchanged since your last review" in dump

    def test_no_file_is_hidden_from_the_count(self) -> None:
        """Skipping a body must not make the reviewer think files vanished."""
        _, full_count = _dump_code(_code())
        _, narrowed_count = _dump_code(_code(), {"backend"})
        assert narrowed_count == full_count == 6

    def test_narrowing_actually_saves_tokens(self) -> None:
        code = _code()
        full, _ = _dump_code(code)
        narrowed, _ = _dump_code(code, {"backend"})
        assert len(narrowed) < len(full) * 0.75, "expected a substantial reduction"

    def test_revising_both_saves_nothing_and_that_is_correct(self) -> None:
        code = _code()
        full, _ = _dump_code(code)
        both, _ = _dump_code(code, _revised_bundles(_report(TargetAgent.BOTH)))
        assert both == full
