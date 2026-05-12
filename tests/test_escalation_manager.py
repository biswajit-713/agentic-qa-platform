"""
tests/test_escalation_manager.py

Unit tests for src/healers/escalation_manager.py.
All filesystem I/O is scoped to a tmp_path fixture — no writes to the project root.
"""

import json
from pathlib import Path

import pytest

from src.healers.escalation_manager import (
    EscalationEntry,
    EscalationManager,
)
from src.healers.failure_classifier import FailedTest, FailureClassification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_failed_test(
    test_name: str = "tests/test_foo.py::test_bar",
    error_message: str = "AssertionError: unexpected None",
) -> FailedTest:
    return FailedTest(
        test_name=test_name,
        test_code="def test_bar():\n    assert result is not None",
        error_message=error_message,
    )


def _make_classification(
    category: str = "APP_BUG",
    confidence: float = 0.9,
    reasoning: str = "App returned None unexpectedly.",
    suggested_fix_hint: str = "Check the resolver.",
    should_escalate: bool = True,
) -> FailureClassification:
    return FailureClassification(
        category=category,
        confidence=confidence,
        reasoning=reasoning,
        suggested_fix_hint=suggested_fix_hint,
        should_escalate=should_escalate,
    )


def _manager(tmp_path: Path) -> EscalationManager:
    return EscalationManager(queue_file=tmp_path / "needs_review.json")


# ---------------------------------------------------------------------------
# EscalationEntry model
# ---------------------------------------------------------------------------

class TestEscalationEntry:
    def test_defaults(self):
        entry = EscalationEntry(
            test_name="tests/test_x.py::test_y",
            category="APP_BUG",
            confidence=0.9,
            reasoning="r",
            escalated_at="2026-01-01T00:00:00+00:00",
        )
        assert entry.status == "pending"
        assert entry.resolution is None
        assert entry.resolved_at is None

    def test_model_dump_round_trip(self):
        entry = EscalationEntry(
            test_name="tests/test_x.py::test_y",
            category="UNKNOWN",
            confidence=0.5,
            reasoning="r",
            escalated_at="2026-01-01T00:00:00+00:00",
        )
        data = entry.model_dump()
        restored = EscalationEntry.model_validate(data)
        assert restored == entry


# ---------------------------------------------------------------------------
# EscalationManager.push
# ---------------------------------------------------------------------------

class TestPush:
    def test_push_creates_queue_file(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        assert (tmp_path / "needs_review.json").exists()

    def test_push_adds_entry(self, tmp_path):
        m = _manager(tmp_path)
        entry = m.push(_make_failed_test(), _make_classification())
        assert entry.test_name == "tests/test_foo.py::test_bar"
        assert entry.status == "pending"
        assert entry.category == "APP_BUG"

    def test_push_captures_error_message(self, tmp_path):
        m = _manager(tmp_path)
        test = _make_failed_test(error_message="TypeError: NoneType is not subscriptable")
        entry = m.push(test, _make_classification())
        assert entry.original_error == "TypeError: NoneType is not subscriptable"

    def test_push_multiple_tests(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test("t1.py::test_a"), _make_classification())
        m.push(_make_failed_test("t2.py::test_b"), _make_classification())
        assert len(m.list_pending()) == 2

    def test_push_idempotent_replaces_pending(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification(confidence=0.8))
        m.push(_make_failed_test(), _make_classification(confidence=0.6))
        pending = m.list_pending()
        assert len(pending) == 1
        assert pending[0].confidence == 0.6

    def test_push_does_not_replace_resolved(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        m.resolve("tests/test_foo.py::test_bar", "accept")
        m.push(_make_failed_test(), _make_classification())
        all_entries = m.list_all()
        assert len(all_entries) == 2
        assert sum(1 for e in all_entries if e.status == "resolved") == 1
        assert sum(1 for e in all_entries if e.status == "pending") == 1

    def test_push_persists_to_disk(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        # Re-load from a fresh manager instance
        m2 = _manager(tmp_path)
        assert len(m2.list_pending()) == 1

    def test_push_queue_file_is_valid_json(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        data = json.loads((tmp_path / "needs_review.json").read_text())
        assert isinstance(data, list)
        assert data[0]["status"] == "pending"


# ---------------------------------------------------------------------------
# EscalationManager.list_pending / list_all
# ---------------------------------------------------------------------------

class TestListPending:
    def test_empty_when_no_file(self, tmp_path):
        m = _manager(tmp_path)
        assert m.list_pending() == []

    def test_only_returns_pending(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test("t.py::test_a"), _make_classification())
        m.push(_make_failed_test("t.py::test_b"), _make_classification())
        m.resolve("t.py::test_a", "reject")
        pending = m.list_pending()
        assert len(pending) == 1
        assert pending[0].test_name == "t.py::test_b"

    def test_list_all_includes_resolved(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test("t.py::test_a"), _make_classification())
        m.push(_make_failed_test("t.py::test_b"), _make_classification())
        m.resolve("t.py::test_a", "accept")
        all_entries = m.list_all()
        assert len(all_entries) == 2

    def test_pending_count(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test("t.py::test_a"), _make_classification())
        m.push(_make_failed_test("t.py::test_b"), _make_classification())
        assert m.pending_count() == 2


# ---------------------------------------------------------------------------
# EscalationManager.resolve
# ---------------------------------------------------------------------------

class TestResolve:
    def test_resolve_accept(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        entry = m.resolve("tests/test_foo.py::test_bar", "accept")
        assert entry.status == "resolved"
        assert entry.resolution == "accept"
        assert entry.resolved_at is not None

    def test_resolve_reject(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        entry = m.resolve("tests/test_foo.py::test_bar", "reject")
        assert entry.resolution == "reject"

    def test_resolve_with_note(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        entry = m.resolve("tests/test_foo.py::test_bar", "accept", note="Verified manually")
        assert entry.resolution_note == "Verified manually"

    def test_resolve_removes_from_pending(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        m.resolve("tests/test_foo.py::test_bar", "accept")
        assert m.pending_count() == 0

    def test_resolve_persists_to_disk(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        m.resolve("tests/test_foo.py::test_bar", "accept")
        m2 = _manager(tmp_path)
        all_entries = m2.list_all()
        assert all_entries[0].status == "resolved"

    def test_resolve_unknown_test_raises_key_error(self, tmp_path):
        m = _manager(tmp_path)
        with pytest.raises(KeyError, match="no_such_test"):
            m.resolve("no_such_test", "accept")

    def test_resolve_already_resolved_raises_key_error(self, tmp_path):
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        m.resolve("tests/test_foo.py::test_bar", "accept")
        with pytest.raises(KeyError):
            m.resolve("tests/test_foo.py::test_bar", "reject")

    def test_resolve_only_pending_entry_not_resolved_duplicate(self, tmp_path):
        """Resolving re-escalated test targets the new pending entry, not the old resolved one."""
        m = _manager(tmp_path)
        m.push(_make_failed_test(), _make_classification())
        m.resolve("tests/test_foo.py::test_bar", "reject")
        m.push(_make_failed_test(), _make_classification())
        entry = m.resolve("tests/test_foo.py::test_bar", "accept")
        assert entry.resolution == "accept"
        # old resolved entry is still there
        all_entries = m.list_all()
        assert len(all_entries) == 2


# ---------------------------------------------------------------------------
# Corrupt / missing queue file
# ---------------------------------------------------------------------------

class TestQueueFileFaults:
    def test_corrupt_file_returns_empty_list(self, tmp_path):
        queue = tmp_path / "needs_review.json"
        queue.write_text("not valid json{{{")
        m = EscalationManager(queue_file=queue)
        assert m.list_pending() == []

    def test_missing_file_returns_empty_list(self, tmp_path):
        m = _manager(tmp_path)
        assert m.list_all() == []
