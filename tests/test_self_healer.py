"""
tests/test_self_healer.py

Unit tests for src/healers/self_healer.py.
All LLM calls, file writes, and test runner invocations are mocked.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.healers.failure_classifier import FailedTest, FailureClassification
from src.healers.self_healer import (
    HealEvent,
    SelfHealer,
    _append_heal_event,
    _build_heal_prompt,
    _extract_test_file,
    _is_ui_test,
    _strip_markdown_fences,
)
from src.runners.pytest_runner import PytestRunResult, SingleTestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_failed_test(
    test_name: str = "tests/test_api.py::test_checkout",
    test_code: str = "def test_checkout():\n    assert checkout({'lines': []}) == {'id': '1'}",
    error_message: str = "AssertionError: assert None == {'id': '1'}",
    stack_trace: str = "  File test_api.py, line 2\nAssertionError",
) -> FailedTest:
    return FailedTest(
        test_name=test_name,
        test_code=test_code,
        error_message=error_message,
        stack_trace=stack_trace,
    )


def _make_classification(
    category: str = "TEST_STALE",
    confidence: float = 0.85,
    suggested_fix_hint: str = "Update field name from 'lines' to 'line'",
) -> FailureClassification:
    return FailureClassification(
        category=category,
        confidence=confidence,
        reasoning="Schema renamed field",
        suggested_fix_hint=suggested_fix_hint,
        should_escalate=False,
    )


def _mock_openai_response(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


def _passing_run_result() -> PytestRunResult:
    return PytestRunResult(
        total=1,
        passed=1,
        failed=0,
        errors=0,
        duration_seconds=0.1,
        test_results=[
            SingleTestResult(test_name="heal_tmp.py::test_checkout", status="passed", duration=0.1)
        ],
    )


def _failing_run_result(error_msg: str = "AssertionError: still wrong") -> PytestRunResult:
    return PytestRunResult(
        total=1,
        passed=0,
        failed=1,
        errors=0,
        duration_seconds=0.1,
        test_results=[
            SingleTestResult(
                test_name="heal_tmp.py::test_checkout",
                status="failed",
                duration=0.1,
                error_message=error_msg,
            )
        ],
    )


def _empty_run_result() -> PytestRunResult:
    return PytestRunResult(total=0, passed=0, failed=0, errors=0, duration_seconds=0.0)


# ---------------------------------------------------------------------------
# HealEvent model
# ---------------------------------------------------------------------------

class TestHealEvent:
    def test_healed_outcome(self):
        event = HealEvent(
            timestamp="2026-05-11T00:00:00+00:00",
            test_name="tests/test_api.py::test_foo",
            original_error="AssertionError",
            fix_applied="def test_foo(): assert True",
            confidence=0.9,
            outcome="HEALED",
        )
        assert event.outcome == "HEALED"
        assert event.failure_reason is None

    def test_failed_outcome_with_reason(self):
        event = HealEvent(
            timestamp="2026-05-11T00:00:00+00:00",
            test_name="tests/test_api.py::test_foo",
            original_error="AssertionError",
            fix_applied="def test_foo(): assert False",
            confidence=0.75,
            outcome="FAILED",
            failure_reason="Still asserting False",
        )
        assert event.outcome == "FAILED"
        assert event.failure_reason == "Still asserting False"

    def test_serializes_to_json(self):
        event = HealEvent(
            timestamp="2026-05-11T00:00:00+00:00",
            test_name="tests/test_api.py::test_foo",
            original_error="err",
            fix_applied="code",
            confidence=0.8,
            outcome="HEALED",
        )
        data = json.loads(event.model_dump_json())
        assert data["outcome"] == "HEALED"
        assert data["test_name"] == "tests/test_api.py::test_foo"


# ---------------------------------------------------------------------------
# _extract_test_file
# ---------------------------------------------------------------------------

class TestExtractTestFile:
    def test_with_node_id_separator(self):
        path = _extract_test_file("tests/test_api.py::test_checkout")
        assert path == Path("tests/test_api.py")

    def test_without_separator(self):
        path = _extract_test_file("tests/test_api.py")
        assert path == Path("tests/test_api.py")

    def test_nested_path(self):
        path = _extract_test_file("generated_tests/api/test_foo.py::TestClass::test_method")
        assert path == Path("generated_tests/api/test_foo.py")


# ---------------------------------------------------------------------------
# _strip_markdown_fences
# ---------------------------------------------------------------------------

class TestStripMarkdownFences:
    def test_no_fences_passthrough(self):
        code = "def test_foo():\n    assert True"
        assert _strip_markdown_fences(code) == code

    def test_triple_backtick_fence(self):
        code = "```\ndef test_foo():\n    assert True\n```"
        result = _strip_markdown_fences(code)
        assert "def test_foo" in result
        assert "```" not in result

    def test_python_fence(self):
        code = "```python\ndef test_foo():\n    assert True\n```"
        result = _strip_markdown_fences(code)
        assert "def test_foo" in result
        assert "```" not in result
        assert not result.startswith("python")


# ---------------------------------------------------------------------------
# _build_heal_prompt
# ---------------------------------------------------------------------------

class TestBuildHealPrompt:
    def test_includes_test_name(self):
        test = _make_failed_test(test_name="tests/test_api.py::test_checkout")
        prompt = _build_heal_prompt(test, _make_classification())
        assert "tests/test_api.py::test_checkout" in prompt

    def test_includes_error_message(self):
        test = _make_failed_test(error_message="KeyError: 'newField'")
        prompt = _build_heal_prompt(test, _make_classification())
        assert "KeyError: 'newField'" in prompt

    def test_includes_fix_hint(self):
        cls = _make_classification(suggested_fix_hint="Update field name from x to y")
        prompt = _build_heal_prompt(_make_failed_test(), cls)
        assert "Update field name from x to y" in prompt

    def test_hint_fallback_when_empty(self):
        cls = _make_classification(suggested_fix_hint="")
        prompt = _build_heal_prompt(_make_failed_test(), cls)
        assert "no specific hint" in prompt

    def test_includes_schema_context(self):
        test = _make_failed_test()
        prompt = _build_heal_prompt(test, _make_classification(), schema_context="type Query { checkout: Order }")
        assert "type Query { checkout: Order }" in prompt

    def test_schema_not_available_placeholder(self):
        prompt = _build_heal_prompt(_make_failed_test(), _make_classification(), schema_context="")
        assert "schema not available" in prompt

    def test_stack_trace_not_provided_placeholder(self):
        test = _make_failed_test()
        test = test.model_copy(update={"stack_trace": ""})
        prompt = _build_heal_prompt(test, _make_classification())
        assert "not provided" in prompt


# ---------------------------------------------------------------------------
# _append_heal_event
# ---------------------------------------------------------------------------

class TestAppendHealEvent:
    def test_writes_valid_json_line(self, tmp_path):
        log = tmp_path / "heals.jsonl"
        event = HealEvent(
            timestamp="2026-05-11T00:00:00+00:00",
            test_name="tests/foo.py::test_bar",
            original_error="err",
            fix_applied="code",
            confidence=0.9,
            outcome="HEALED",
        )
        _append_heal_event(event, log)
        lines = log.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["outcome"] == "HEALED"

    def test_appends_multiple_events(self, tmp_path):
        log = tmp_path / "heals.jsonl"
        for i in range(3):
            _append_heal_event(
                HealEvent(
                    timestamp="2026-05-11T00:00:00+00:00",
                    test_name=f"tests/foo.py::test_{i}",
                    original_error="err",
                    fix_applied="code",
                    confidence=0.8,
                    outcome="FAILED",
                    failure_reason="x",
                ),
                log,
            )
        lines = log.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_creates_parent_directory(self, tmp_path):
        log = tmp_path / "subdir" / "heals.jsonl"
        event = HealEvent(
            timestamp="2026-05-11T00:00:00+00:00",
            test_name="tests/foo.py::test_bar",
            original_error="err",
            fix_applied="code",
            confidence=0.9,
            outcome="HEALED",
        )
        _append_heal_event(event, log)
        assert log.exists()


# ---------------------------------------------------------------------------
# SelfHealer.heal — mocked LLM + runner
# ---------------------------------------------------------------------------

PATCHED_CODE = "def test_checkout():\n    assert checkout({'line': []}) == {'id': '1'}"


# ---------------------------------------------------------------------------
# _is_ui_test
# ---------------------------------------------------------------------------

class TestIsUiTest:
    def test_ui_layer_returns_true(self):
        assert _is_ui_test("generated_tests/ui/test_checkout.py::test_flow") is True

    def test_api_layer_returns_false(self):
        assert _is_ui_test("generated_tests/api/test_checkout.py::test_op") is False

    def test_integration_layer_returns_false(self):
        assert _is_ui_test("generated_tests/integration/test_order.py::test_flow") is False

    def test_plain_tests_dir_returns_false(self):
        assert _is_ui_test("tests/test_api.py::test_bar") is False


class TestSelfHealerWrongCategory:
    @patch("src.healers.self_healer.OpenAI")
    def test_raises_for_app_bug(self, mock_openai):
        healer = SelfHealer()
        with pytest.raises(ValueError, match="TEST_STALE"):
            healer.heal(
                _make_failed_test(),
                _make_classification(category="APP_BUG"),
            )
        mock_openai.return_value.chat.completions.create.assert_not_called()

    @patch("src.healers.self_healer.OpenAI")
    def test_raises_for_flaky(self, mock_openai):
        healer = SelfHealer()
        with pytest.raises(ValueError, match="TEST_STALE"):
            healer.heal(
                _make_failed_test(),
                _make_classification(category="FLAKY"),
            )
        mock_openai.return_value.chat.completions.create.assert_not_called()

    @patch("src.healers.self_healer.OpenAI")
    def test_raises_for_ui_test(self, mock_openai):
        healer = SelfHealer()
        with pytest.raises(ValueError, match="UI tests cannot be auto-healed"):
            healer.heal(
                _make_failed_test(test_name="generated_tests/ui/test_checkout.py::test_flow"),
                _make_classification(category="TEST_STALE"),
            )
        mock_openai.return_value.chat.completions.create.assert_not_called()


class TestSelfHealerSuccessPath:
    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    @patch.object(Path, "write_text")
    def test_healed_outcome(self, mock_write, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _passing_run_result()
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        event = healer.heal(_make_failed_test(), _make_classification())

        assert event.outcome == "HEALED"
        assert event.fix_applied == PATCHED_CODE
        assert event.failure_reason is None

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    @patch.object(Path, "write_text")
    def test_healed_event_logged(self, mock_write, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _passing_run_result()
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        log = tmp_path / "heals.jsonl"
        healer = SelfHealer(heals_log=log)

        healer.heal(_make_failed_test(), _make_classification())

        assert log.exists()
        data = json.loads(log.read_text().strip())
        assert data["outcome"] == "HEALED"

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    @patch.object(Path, "write_text")
    def test_original_file_replaced_on_success(self, mock_write, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _passing_run_result()
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        healer.heal(_make_failed_test(), _make_classification())

        mock_write.assert_called_once_with(PATCHED_CODE)


class TestSelfHealerFailedPath:
    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    def test_failed_outcome(self, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _failing_run_result("AssertionError: still wrong")
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        event = healer.heal(_make_failed_test(), _make_classification())

        assert event.outcome == "FAILED"
        assert "AssertionError: still wrong" in (event.failure_reason or "")

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    def test_failed_event_logged(self, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _failing_run_result()
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        log = tmp_path / "heals.jsonl"
        healer = SelfHealer(heals_log=log)

        healer.heal(_make_failed_test(), _make_classification())

        data = json.loads(log.read_text().strip())
        assert data["outcome"] == "FAILED"

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    @patch.object(Path, "write_text")
    def test_original_file_not_replaced_on_failure(self, mock_write, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _failing_run_result()
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        healer.heal(_make_failed_test(), _make_classification())

        mock_write.assert_not_called()

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", side_effect=RuntimeError("runner crashed"))
    def test_runner_exception_returns_failed(self, mock_run, mock_openai_cls, tmp_path):
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        event = healer.heal(_make_failed_test(), _make_classification())

        assert event.outcome == "FAILED"
        assert "runner crashed" in (event.failure_reason or "")

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    def test_no_tests_collected_is_failure(self, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _empty_run_result()
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        event = healer.heal(_make_failed_test(), _make_classification())

        assert event.outcome == "FAILED"
        assert "No tests were collected" in (event.failure_reason or "")


class TestSelfHealerDryRun:
    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests")
    @patch.object(Path, "write_text")
    def test_dry_run_does_not_write_file(self, mock_write, mock_run, mock_openai_cls, tmp_path):
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        healer.heal(_make_failed_test(), _make_classification(), dry_run=True)

        mock_run.assert_not_called()
        mock_write.assert_not_called()

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests")
    def test_dry_run_does_not_log_to_jsonl(self, mock_run, mock_openai_cls, tmp_path):
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        log = tmp_path / "heals.jsonl"
        healer = SelfHealer(heals_log=log)

        healer.heal(_make_failed_test(), _make_classification(), dry_run=True)

        assert not log.exists()

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests")
    def test_dry_run_returns_patch_in_event(self, mock_run, mock_openai_cls, tmp_path):
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        event = healer.heal(_make_failed_test(), _make_classification(), dry_run=True)

        assert event.fix_applied == PATCHED_CODE
        assert "dry_run" in (event.failure_reason or "")


class TestSelfHealerPromptContent:
    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    @patch.object(Path, "write_text")
    def test_schema_context_passed_to_llm(self, mock_write, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _passing_run_result()
        mock_create = mock_openai_cls.return_value.chat.completions.create
        mock_create.return_value = _mock_openai_response(PATCHED_CODE)
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        healer.heal(
            _make_failed_test(),
            _make_classification(),
            schema_context="type Query { checkout: Order }",
        )

        call_kwargs = mock_create.call_args
        user_msg = call_kwargs.kwargs["messages"][1]["content"]
        assert "type Query { checkout: Order }" in user_msg

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    @patch.object(Path, "write_text")
    def test_markdown_fence_stripped_from_llm_response(self, mock_write, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _passing_run_result()
        fenced = "```python\n" + PATCHED_CODE + "\n```"
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(fenced)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        event = healer.heal(_make_failed_test(), _make_classification())

        assert "```" not in event.fix_applied

    @patch("src.healers.self_healer.OpenAI")
    @patch("src.healers.self_healer.run_tests", return_value=None)
    @patch.object(Path, "write_text")
    def test_confidence_recorded_in_event(self, mock_write, mock_run, mock_openai_cls, tmp_path):
        mock_run.return_value = _passing_run_result()
        mock_openai_cls.return_value.chat.completions.create.return_value = (
            _mock_openai_response(PATCHED_CODE)
        )
        healer = SelfHealer(heals_log=tmp_path / "heals.jsonl")

        event = healer.heal(_make_failed_test(), _make_classification(confidence=0.92))

        assert event.confidence == 0.92
