"""
src/healers/escalation_manager.py

Audit trail and human-review queue for test failures that cannot be auto-healed.

When should_auto_heal() returns False, callers push the failing test + classification
here. The entry lands in needs_review.json and stays until a human resolves it via
`python -m src.agent resolve --test <name> --action accept|reject`.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.healers.failure_classifier import FailedTest, FailureClassification

logger = logging.getLogger(__name__)

EscalationStatus = Literal["pending", "resolved"]
ResolutionAction = Literal["accept", "reject"]

_DEFAULT_QUEUE_FILE = Path("needs_review.json")


class EscalationEntry(BaseModel):
    """A single test failure waiting for human review."""

    model_config = ConfigDict(populate_by_name=True)

    test_name: str
    category: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    suggested_fix_hint: str = ""
    original_error: str = ""
    escalated_at: str = Field(description="ISO-8601 UTC timestamp when the entry was created")
    status: EscalationStatus = "pending"
    resolved_at: Optional[str] = None
    resolution: Optional[ResolutionAction] = None
    resolution_note: str = ""


class EscalationManager:
    """Manages the needs_review.json queue of escalated test failures."""

    def __init__(self, queue_file: Path = _DEFAULT_QUEUE_FILE) -> None:
        self._queue_file = queue_file

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> list[EscalationEntry]:
        if not self._queue_file.exists():
            return []
        try:
            data = json.loads(self._queue_file.read_text())
            return [EscalationEntry.model_validate(item) for item in data]
        except Exception as e:
            logger.warning("Failed to load escalation queue from %s: %s", self._queue_file, e)
            return []

    def _save(self, entries: list[EscalationEntry]) -> None:
        self._queue_file.parent.mkdir(parents=True, exist_ok=True)
        payload = [e.model_dump() for e in entries]
        self._queue_file.write_text(json.dumps(payload, indent=2))
        logger.debug("Escalation queue saved: %d entries", len(entries))

    # ── public API ────────────────────────────────────────────────────────────

    def push(
        self,
        test: FailedTest,
        classification: FailureClassification,
    ) -> EscalationEntry:
        """Add a failed test to the review queue.

        Idempotent for the same test_name: if a pending entry already exists,
        updates its classification data rather than creating a duplicate.
        """
        entries = self._load()

        # Replace any existing pending entry for the same test.
        entries = [e for e in entries if not (e.test_name == test.test_name and e.status == "pending")]

        entry = EscalationEntry(
            test_name=test.test_name,
            category=classification.category,
            confidence=classification.confidence,
            reasoning=classification.reasoning,
            suggested_fix_hint=classification.suggested_fix_hint,
            original_error=test.error_message,
            escalated_at=datetime.now(timezone.utc).isoformat(),
        )
        entries.append(entry)
        self._save(entries)

        logger.info(
            "Escalated: test=%s category=%s confidence=%.2f",
            test.test_name,
            classification.category,
            classification.confidence,
        )
        return entry

    def list_pending(self) -> list[EscalationEntry]:
        """Return all entries still awaiting human review."""
        return [e for e in self._load() if e.status == "pending"]

    def list_all(self) -> list[EscalationEntry]:
        """Return every entry (pending and resolved)."""
        return self._load()

    def resolve(
        self,
        test_name: str,
        action: ResolutionAction,
        note: str = "",
    ) -> EscalationEntry:
        """Mark a pending escalation as resolved.

        Args:
            test_name: Exact pytest node ID of the test to resolve.
            action: 'accept' means the fix/change is approved; 'reject' means revert.
            note: Optional free-text note recorded with the resolution.

        Returns:
            The updated EscalationEntry.

        Raises:
            KeyError: If no pending entry exists for test_name.
        """
        entries = self._load()
        for entry in entries:
            if entry.test_name == test_name and entry.status == "pending":
                entry.status = "resolved"
                entry.resolution = action
                entry.resolved_at = datetime.now(timezone.utc).isoformat()
                entry.resolution_note = note
                self._save(entries)
                logger.info(
                    "Resolved: test=%s action=%s", test_name, action
                )
                return entry

        raise KeyError(f"No pending escalation found for test: {test_name!r}")

    def pending_count(self) -> int:
        """Return the number of unresolved escalations."""
        return len(self.list_pending())
