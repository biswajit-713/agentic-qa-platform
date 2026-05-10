"""
src/healers/failure_classifier.py

LLM-powered test failure classifier. Takes a failed test with its error context
and recent diff, then classifies the root cause so the agent can decide whether
to auto-heal or escalate to a human.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

FailureCategory = Literal["APP_BUG", "TEST_STALE", "ENVIRONMENT", "FLAKY", "UNKNOWN"]

_ESCALATE_CATEGORIES: set[FailureCategory] = {"APP_BUG", "UNKNOWN"}
_CONFIDENCE_THRESHOLD = 0.7

_DEFAULT_MODEL = "openai/gpt-4o-mini"


class FailedTest(BaseModel):
    """All context available about a failing test."""

    model_config = ConfigDict(populate_by_name=True)

    test_name: str = Field(..., description="Full pytest node ID, e.g. tests/test_foo.py::test_bar")
    test_code: str = Field(..., description="Full source of the test function")
    error_message: str = Field(..., description="One-line error or assertion message")
    stack_trace: str = Field(default="", description="Full traceback from pytest output")
    recent_diff: str = Field(
        default="",
        description="git diff that preceded the failure; empty string if unavailable",
    )
    last_passing_run: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the most recent successful run of this test",
    )


class FailureClassification(BaseModel):
    """Structured result returned by the classifier."""

    model_config = ConfigDict(populate_by_name=True)

    category: FailureCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., description="Step-by-step explanation of the classification")
    suggested_fix_hint: str = Field(
        default="",
        description="Concrete hint for fixing or retrying the test",
    )
    should_escalate: bool = Field(
        default=False,
        description="True when the category or confidence requires human review",
    )


_SYSTEM_PROMPT = """\
You are a senior QA engineer diagnosing why an automated test failed.

You will receive:
- The full test source code
- The error message and stack trace
- The git diff that was applied just before the failure (may be empty)
- When the test last passed

Classify the failure into exactly one of these categories:
- APP_BUG: The application code is broken; the test is correct. Evidence: app throws unexpected exceptions, returns wrong data, or violates an invariant the test is checking.
- TEST_STALE: The application changed (renamed field, new URL, changed selector, updated schema) and the test was not updated. Evidence: diff renames/removes something the test references.
- ENVIRONMENT: Saleor is down, misconfigured, or a network issue occurred. Evidence: ConnectionRefused, timeout, DNS failure, 503 with no diff correlation.
- FLAKY: Timing issue, race condition, or intermittent failure. Evidence: TimeoutError, StaleElementReference, AssertionError on dynamic data; test was passing recently and diff does not explain it.
- UNKNOWN: Signals conflict, are absent, or you cannot confidently identify the cause.

Reasoning approach:
1. Scan the diff — does it rename/remove something referenced in the test? → likely TEST_STALE
2. Is there a network/infra error with no code change? → likely ENVIRONMENT
3. Is the error a timing/intermittent pattern and the test passed recently? → likely FLAKY
4. Does the test logic look correct but the app returns wrong data or crashes? → likely APP_BUG
5. If none of the above fit cleanly → UNKNOWN

Respond with valid JSON only — no markdown fences, no explanation outside the JSON:
{
  "category": "<APP_BUG|TEST_STALE|ENVIRONMENT|FLAKY|UNKNOWN>",
  "confidence": <0.0-1.0>,
  "reasoning": "<step-by-step explanation>",
  "suggested_fix_hint": "<concrete actionable hint>"
}"""


def _build_user_prompt(test: FailedTest) -> str:
    last_passed = (
        test.last_passing_run.isoformat()
        if test.last_passing_run
        else "never (or unknown)"
    )
    diff_section = test.recent_diff.strip() if test.recent_diff.strip() else "(no diff available)"
    stack_section = test.stack_trace.strip() if test.stack_trace.strip() else "(not provided)"

    return f"""Test name: {test.test_name}
Last passed: {last_passed}

--- TEST CODE ---
{test.test_code}

--- ERROR MESSAGE ---
{test.error_message}

--- STACK TRACE ---
{stack_section}

--- RECENT DIFF ---
{diff_section}

Classify this failure."""


class FailureClassifier:
    """Classifies test failures using an LLM via OpenRouter."""

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        settings = get_settings()
        self._client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        self._model = model

    def classify(self, test: FailedTest) -> FailureClassification:
        """Return a FailureClassification for the given failed test."""
        user_prompt = _build_user_prompt(test)

        logger.debug("Classifying failure for test=%s model=%s", test.test_name, self._model)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )

        raw = response.choices[0].message.content or ""
        logger.debug("Raw LLM response: %s", raw)

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        data = json.loads(cleaned)
        classification = FailureClassification.model_validate(data)

        should_escalate = (
            classification.category in _ESCALATE_CATEGORIES
            or classification.confidence < _CONFIDENCE_THRESHOLD
        )
        classification = classification.model_copy(update={"should_escalate": should_escalate})

        logger.info(
            "Classified %s → category=%s confidence=%.2f escalate=%s",
            test.test_name,
            classification.category,
            classification.confidence,
            classification.should_escalate,
        )
        return classification


def should_auto_heal(classification: FailureClassification) -> bool:
    """Return True when the classification permits auto-healing (no escalation needed)."""
    return not classification.should_escalate and classification.category in {"TEST_STALE", "FLAKY"}
