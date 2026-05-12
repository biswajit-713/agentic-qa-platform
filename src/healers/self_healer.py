"""
src/healers/self_healer.py

Self-healing engine: patches TEST_STALE failures using LLM, verifies the fix by
re-running the test, and logs every attempt to heals.jsonl for governance.
"""

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from src.config.settings import get_settings
from src.healers.failure_classifier import FailedTest, FailureClassification
from src.runners.pytest_runner import run_tests

logger = logging.getLogger(__name__)

HealOutcome = Literal["HEALED", "FAILED"]

_DEFAULT_MODEL = "openai/gpt-oss-120b:free"
_HEALS_LOG = Path("heals.jsonl")

_SYSTEM_PROMPT = """\
You are an expert QA engineer who fixes stale automated tests.

A test is "stale" when the application changed (renamed field, new schema, updated URL,
changed selector) and the test was not updated to match.

You will receive:
- The original test code that is now failing
- The error message from the test run
- A hint about what likely changed
- The current GraphQL schema for the relevant operation (if available)

Your task: return a COMPLETE, WORKING replacement for the test file.

Rules:
1. Return ONLY the full Python test code — no markdown fences, no explanation.
2. The test must be self-contained and importable.
3. Keep the same test structure (imports, fixtures, assertions) but fix what changed.
4. Do not add new test cases — just fix the failing one.
5. Preserve the original test name and any existing parametrize decorators.
"""


class HealEvent(BaseModel):
    """Audit record for a single healing attempt."""

    model_config = ConfigDict(populate_by_name=True)

    timestamp: str
    test_name: str
    original_error: str
    fix_applied: str = Field(description="The patched test code that was attempted")
    confidence: float = Field(description="Classifier confidence that drove this heal")
    outcome: HealOutcome
    failure_reason: Optional[str] = Field(
        default=None,
        description="Why the healed test still failed (only set when outcome=FAILED)",
    )


def _extract_test_file(test_name: str) -> Path:
    """Extract the file path from a pytest node ID like 'tests/foo.py::test_bar'."""
    return Path(test_name.split("::")[0])


def _is_ui_test(test_name: str) -> bool:
    """Return True when the test lives under the UI layer (generated_tests/ui/)."""
    return "generated_tests/ui/" in test_name.replace("\\", "/")


def _build_heal_prompt(
    test: FailedTest,
    classification: FailureClassification,
    schema_context: str = "",
) -> str:
    hint = classification.suggested_fix_hint or "(no specific hint)"
    schema_section = schema_context.strip() if schema_context.strip() else "(schema not available)"
    stack_section = test.stack_trace.strip() if test.stack_trace.strip() else "(not provided)"

    return f"""Test name: {test.test_name}

--- ORIGINAL TEST CODE ---
{test.test_code}

--- ERROR MESSAGE ---
{test.error_message}

--- STACK TRACE ---
{stack_section}

--- FIX HINT ---
{hint}

--- CURRENT SCHEMA (if relevant) ---
{schema_section}

Return the complete fixed test file as plain Python code only."""


def _strip_markdown_fences(text: str) -> str:
    """Remove ```python or ``` fences if the LLM wrapped the response."""
    if not text.startswith("```"):
        return text
    text = text.split("```", 2)[1]
    if text.startswith("python"):
        text = text[6:]
    return text.rsplit("```", 1)[0].strip()


def _append_heal_event(event: HealEvent, log_path: Path = _HEALS_LOG) -> None:
    """Append a HealEvent as a JSON line to the heals log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(event.model_dump_json() + "\n")
    logger.debug("HealEvent logged to %s: test=%s outcome=%s", log_path, event.test_name, event.outcome)


class SelfHealer:
    """LLM-powered self-healing for TEST_STALE test failures."""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        heals_log: Path = _HEALS_LOG,
    ) -> None:
        settings = get_settings()
        self._client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        self._model = model
        self._heals_log = heals_log

    def heal(
        self,
        test: FailedTest,
        classification: FailureClassification,
        schema_context: str = "",
        dry_run: bool = False,
    ) -> HealEvent:
        """Attempt to heal a stale test.

        Args:
            test: The failing test with its code and error context.
            classification: Must have category=TEST_STALE.
            schema_context: Optional GraphQL schema for the operation under test.
            dry_run: If True, show what would be patched without writing any files.

        Returns:
            HealEvent describing the outcome. In dry_run mode the event is returned
            but NOT appended to heals.jsonl and the original file is never touched.

        Raises:
            ValueError: If classification.category is not TEST_STALE.
        """
        if classification.category != "TEST_STALE":
            raise ValueError(
                f"SelfHealer only handles TEST_STALE; got {classification.category}"
            )

        if _is_ui_test(test.test_name):
            raise ValueError(
                f"UI tests cannot be auto-healed (no DOM signal available): {test.test_name}"
            )

        logger.info("Healing test=%s model=%s dry_run=%s", test.test_name, self._model, dry_run)

        patched_code = self._generate_patch(test, classification, schema_context)

        if dry_run:
            logger.info("DRY RUN — would patch %s with:\n%s", test.test_name, patched_code)
            return HealEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                test_name=test.test_name,
                original_error=test.error_message,
                fix_applied=patched_code,
                confidence=classification.confidence,
                outcome="FAILED",
                failure_reason="dry_run=True — patch not applied",
            )

        test_passed, failure_reason = self._run_patched(patched_code)

        if test_passed:
            original_path = _extract_test_file(test.test_name)
            original_path.write_text(patched_code)
            logger.info("HEALED: %s", test.test_name)
            event = HealEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                test_name=test.test_name,
                original_error=test.error_message,
                fix_applied=patched_code,
                confidence=classification.confidence,
                outcome="HEALED",
            )
        else:
            logger.warning("HEAL_FAILED: %s — %s", test.test_name, failure_reason)
            event = HealEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                test_name=test.test_name,
                original_error=test.error_message,
                fix_applied=patched_code,
                confidence=classification.confidence,
                outcome="FAILED",
                failure_reason=failure_reason,
            )

        _append_heal_event(event, self._heals_log)
        return event

    def _generate_patch(
        self,
        test: FailedTest,
        classification: FailureClassification,
        schema_context: str,
    ) -> str:
        """Call LLM and return stripped patched test code."""
        user_prompt = _build_heal_prompt(test, classification, schema_context)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        raw = (response.choices[0].message.content or "").strip()
        patched = _strip_markdown_fences(raw)
        logger.debug("LLM returned %d chars of patched code", len(patched))
        return patched

    def _run_patched(self, patched_code: str) -> tuple[bool, str]:
        """Write patched code to a temp file, run pytest on it, return (passed, reason)."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="heal_",
            delete=False,
        ) as tmp:
            tmp.write(patched_code)
            tmp_path = Path(tmp.name)

        try:
            result = run_tests(test_dir=str(tmp_path))
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            return False, f"Test runner error: {e}"
        finally:
            tmp_path.unlink(missing_ok=True)

        if result.total == 0:
            return False, "No tests were collected from the patched file"

        if result.failed == 0 and result.errors == 0:
            return True, ""

        failed_msgs = [
            r.error_message or "unknown error"
            for r in result.test_results
            if r.status in ("failed", "error")
        ]
        return False, "; ".join(failed_msgs) if failed_msgs else "unknown failure"
