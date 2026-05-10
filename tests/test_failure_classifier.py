"""
tests/test_failure_classifier.py

Unit tests for src/healers/failure_classifier.py.
All LLM calls are mocked — no network required.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.healers.failure_classifier import (
    FailedTest,
    FailureCategory,
    FailureClassification,
    FailureClassifier,
    _build_user_prompt,
    should_auto_heal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_failed_test(
    test_name: str = "tests/test_foo.py::test_bar",
    test_code: str = "def test_bar():\n    assert get_product() == {'id': 1}",
    error_message: str = "AssertionError: assert None == {'id': 1}",
    stack_trace: str = "  File test_foo.py, line 2\nAssertionError",
    recent_diff: str = "",
    last_passing_run: datetime | None = None,
) -> FailedTest:
    return FailedTest(
        test_name=test_name,
        test_code=test_code,
        error_message=error_message,
        stack_trace=stack_trace,
        recent_diff=recent_diff,
        last_passing_run=last_passing_run,
    )


def _make_classification_payload(
    category: FailureCategory = "APP_BUG",
    confidence: float = 0.9,
    reasoning: str = "App returned None instead of product data.",
    suggested_fix_hint: str = "Check the product resolver.",
) -> dict:
    return {
        "category": category,
        "confidence": confidence,
        "reasoning": reasoning,
        "suggested_fix_hint": suggested_fix_hint,
    }


def _mock_openai_response(payload: dict) -> MagicMock:
    choice = MagicMock()
    choice.message.content = json.dumps(payload)
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# FailedTest model
# ---------------------------------------------------------------------------

class TestFailedTestModel:
    def test_minimal_construction(self):
        t = FailedTest(
            test_name="tests/test_foo.py::test_x",
            test_code="def test_x(): pass",
            error_message="FAILED",
        )
        assert t.recent_diff == ""
        assert t.last_passing_run is None
        assert t.stack_trace == ""

    def test_with_last_passing_run(self):
        ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
        t = _make_failed_test(last_passing_run=ts)
        assert t.last_passing_run == ts


# ---------------------------------------------------------------------------
# FailureClassification model
# ---------------------------------------------------------------------------

class TestFailureClassificationModel:
    def test_should_escalate_defaults_false(self):
        c = FailureClassification(
            category="FLAKY",
            confidence=0.85,
            reasoning="Intermittent timeout",
            suggested_fix_hint="Retry",
        )
        assert c.should_escalate is False

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            FailureClassification(
                category="FLAKY",
                confidence=1.5,
                reasoning="x",
                suggested_fix_hint="y",
            )


# ---------------------------------------------------------------------------
# _build_user_prompt
# ---------------------------------------------------------------------------

class TestBuildUserPrompt:
    def test_includes_test_name(self):
        t = _make_failed_test(test_name="tests/test_api.py::test_checkout")
        prompt = _build_user_prompt(t)
        assert "tests/test_api.py::test_checkout" in prompt

    def test_includes_error_message(self):
        t = _make_failed_test(error_message="ConnectionRefusedError: [Errno 111]")
        prompt = _build_user_prompt(t)
        assert "ConnectionRefusedError" in prompt

    def test_includes_diff_when_present(self):
        t = _make_failed_test(recent_diff="- old_field\n+ new_field")
        prompt = _build_user_prompt(t)
        assert "old_field" in prompt

    def test_no_diff_placeholder(self):
        t = _make_failed_test(recent_diff="")
        prompt = _build_user_prompt(t)
        assert "no diff available" in prompt

    def test_never_passed_placeholder(self):
        t = _make_failed_test(last_passing_run=None)
        prompt = _build_user_prompt(t)
        assert "never" in prompt

    def test_last_passed_iso_format(self):
        ts = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        t = _make_failed_test(last_passing_run=ts)
        prompt = _build_user_prompt(t)
        assert "2026-04-20" in prompt

    def test_includes_test_code(self):
        t = _make_failed_test(test_code="def test_foo():\n    assert 1 == 2")
        prompt = _build_user_prompt(t)
        assert "assert 1 == 2" in prompt


# ---------------------------------------------------------------------------
# FailureClassifier.classify — mocked LLM
# ---------------------------------------------------------------------------

class TestFailureClassifier:
    @patch("src.healers.failure_classifier.OpenAI")
    def test_app_bug_escalates(self, mock_openai_cls):
        payload = _make_classification_payload(category="APP_BUG", confidence=0.92)
        mock_openai_cls.return_value.chat.completions.create.return_value = _mock_openai_response(payload)

        classifier = FailureClassifier()
        result = classifier.classify(_make_failed_test())

        assert result.category == "APP_BUG"
        assert result.should_escalate is True

    @patch("src.healers.failure_classifier.OpenAI")
    def test_unknown_escalates(self, mock_openai_cls):
        payload = _make_classification_payload(category="UNKNOWN", confidence=0.5)
        mock_openai_cls.return_value.chat.completions.create.return_value = _mock_openai_response(payload)

        classifier = FailureClassifier()
        result = classifier.classify(_make_failed_test())

        assert result.category == "UNKNOWN"
        assert result.should_escalate is True

    @patch("src.healers.failure_classifier.OpenAI")
    def test_test_stale_high_confidence_does_not_escalate(self, mock_openai_cls):
        payload = _make_classification_payload(category="TEST_STALE", confidence=0.85)
        mock_openai_cls.return_value.chat.completions.create.return_value = _mock_openai_response(payload)

        classifier = FailureClassifier()
        result = classifier.classify(_make_failed_test())

        assert result.category == "TEST_STALE"
        assert result.should_escalate is False

    @patch("src.healers.failure_classifier.OpenAI")
    def test_flaky_high_confidence_does_not_escalate(self, mock_openai_cls):
        payload = _make_classification_payload(category="FLAKY", confidence=0.8)
        mock_openai_cls.return_value.chat.completions.create.return_value = _mock_openai_response(payload)

        classifier = FailureClassifier()
        result = classifier.classify(_make_failed_test())

        assert result.category == "FLAKY"
        assert result.should_escalate is False

    @patch("src.healers.failure_classifier.OpenAI")
    def test_low_confidence_always_escalates(self, mock_openai_cls):
        # TEST_STALE is normally auto-healed, but low confidence overrides
        payload = _make_classification_payload(category="TEST_STALE", confidence=0.6)
        mock_openai_cls.return_value.chat.completions.create.return_value = _mock_openai_response(payload)

        classifier = FailureClassifier()
        result = classifier.classify(_make_failed_test())

        assert result.should_escalate is True

    @patch("src.healers.failure_classifier.OpenAI")
    def test_environment_high_confidence_does_not_escalate(self, mock_openai_cls):
        # ENVIRONMENT is not in _ESCALATE_CATEGORIES and passes confidence check
        payload = _make_classification_payload(category="ENVIRONMENT", confidence=0.9)
        mock_openai_cls.return_value.chat.completions.create.return_value = _mock_openai_response(payload)

        classifier = FailureClassifier()
        result = classifier.classify(_make_failed_test())

        assert result.category == "ENVIRONMENT"
        assert result.should_escalate is False

    @patch("src.healers.failure_classifier.OpenAI")
    def test_markdown_fence_stripped(self, mock_openai_cls):
        payload = _make_classification_payload(category="FLAKY", confidence=0.75)
        fenced = "```json\n" + json.dumps(payload) + "\n```"
        choice = MagicMock()
        choice.message.content = fenced
        response = MagicMock()
        response.choices = [choice]
        mock_openai_cls.return_value.chat.completions.create.return_value = response

        classifier = FailureClassifier()
        result = classifier.classify(_make_failed_test())

        assert result.category == "FLAKY"

    @patch("src.healers.failure_classifier.OpenAI")
    def test_confidence_threshold_boundary(self, mock_openai_cls):
        # Exactly 0.7 should NOT escalate due to low confidence
        payload = _make_classification_payload(category="FLAKY", confidence=0.7)
        mock_openai_cls.return_value.chat.completions.create.return_value = _mock_openai_response(payload)

        classifier = FailureClassifier()
        result = classifier.classify(_make_failed_test())

        assert result.should_escalate is False

    @patch("src.healers.failure_classifier.OpenAI")
    def test_custom_model_passed_to_openai(self, mock_openai_cls):
        payload = _make_classification_payload()
        mock_openai_cls.return_value.chat.completions.create.return_value = _mock_openai_response(payload)

        classifier = FailureClassifier(model="anthropic/claude-3-haiku")
        classifier.classify(_make_failed_test())

        call_kwargs = mock_openai_cls.return_value.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "anthropic/claude-3-haiku"


# ---------------------------------------------------------------------------
# should_auto_heal
# ---------------------------------------------------------------------------

class TestShouldAutoHeal:
    def _classification(self, category: FailureCategory, confidence: float, escalate: bool) -> FailureClassification:
        return FailureClassification(
            category=category,
            confidence=confidence,
            reasoning="test",
            suggested_fix_hint="hint",
            should_escalate=escalate,
        )

    def test_test_stale_no_escalate_auto_heals(self):
        c = self._classification("TEST_STALE", 0.85, escalate=False)
        assert should_auto_heal(c) is True

    def test_flaky_no_escalate_auto_heals(self):
        c = self._classification("FLAKY", 0.8, escalate=False)
        assert should_auto_heal(c) is True

    def test_app_bug_escalate_no_auto_heal(self):
        c = self._classification("APP_BUG", 0.9, escalate=True)
        assert should_auto_heal(c) is False

    def test_unknown_escalate_no_auto_heal(self):
        c = self._classification("UNKNOWN", 0.4, escalate=True)
        assert should_auto_heal(c) is False

    def test_environment_no_escalate_no_auto_heal(self):
        # ENVIRONMENT is not in the auto-heal set (it should be retried, not healed)
        c = self._classification("ENVIRONMENT", 0.9, escalate=False)
        assert should_auto_heal(c) is False

    def test_test_stale_with_escalate_flag_no_auto_heal(self):
        # Low confidence sets escalate=True even for TEST_STALE
        c = self._classification("TEST_STALE", 0.6, escalate=True)
        assert should_auto_heal(c) is False
