"""
tests/test_risk_scorer.py

Unit tests for src/analyzers/risk_scorer.py.
All LLM calls are mocked — no network required.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.analyzers.diff_analyzer import ChangeType, CodeChange, DiffAnalysis
from src.analyzers.risk_scorer import (
    OperationRisk,
    RiskAssessment,
    RiskConfig,
    RiskScorer,
    _build_rubric_text,
    _build_system_prompt,
    _build_user_prompt,
    load_risk_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analysis(
    files: list[tuple[str, ChangeType]] | None = None,
    operations: list[str] | None = None,
    untraced: list[str] | None = None,
) -> DiffAnalysis:
    changes = [
        CodeChange(file_path=fp, change_type=ct, added_lines=["x"], removed_lines=[])
        for fp, ct in (files or [])
    ]
    return DiffAnalysis(
        changed_files=changes,
        affected_operations=operations or [],
        untraced_changes=untraced or [],
    )


def _make_assessment_payload(
    overall: str = "HIGH",
    count: int = 3,
    ops: list[dict] | None = None,
) -> dict:
    return {
        "overall_risk": overall,
        "rationale": "Some rationale sentence. Another sentence here.",
        "recommended_test_count": count,
        "operation_risks": ops or [
            {
                "operation_name": "CheckoutCreate",
                "risk_level": "HIGH",
                "reason": "Core checkout flow.",
                "suggested_test_focus": ["happy path", "invalid input"],
            }
        ],
    }


def _mock_openai_response(payload: dict) -> MagicMock:
    """Build a mock OpenAI response object returning payload as JSON."""
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# load_risk_config
# ---------------------------------------------------------------------------

class TestLoadRiskConfig:
    def test_loads_default_config(self):
        config = load_risk_config()
        assert "CRITICAL" in config.risk_levels
        assert "HIGH" in config.risk_levels
        assert "MEDIUM" in config.risk_levels
        assert "LOW" in config.risk_levels

    def test_returns_default_when_file_missing(self, tmp_path):
        config = load_risk_config(tmp_path / "nonexistent.yml")
        assert isinstance(config, RiskConfig)
        assert config.fallback_level == "MEDIUM"

    def test_model_loaded_from_config(self):
        config = load_risk_config()
        assert isinstance(config.model, str)
        assert len(config.model) > 0

    def test_custom_config_file(self, tmp_path):
        custom = tmp_path / "custom.yml"
        custom.write_text(
            "risk_levels:\n  CRITICAL:\n    description: 'bad'\n    keywords: [pay]\n"
            "model: mymodel\nfallback_level: LOW\n"
        )
        config = load_risk_config(custom)
        assert "CRITICAL" in config.risk_levels
        assert config.model == "mymodel"
        assert config.fallback_level == "LOW"


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

class TestPromptBuilders:
    def test_rubric_text_contains_all_levels(self):
        config = load_risk_config()
        rubric = _build_rubric_text(config)
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            assert level in rubric

    def test_system_prompt_contains_json_schema(self):
        config = load_risk_config()
        prompt = _build_system_prompt(config)
        assert "overall_risk" in prompt
        assert "operation_risks" in prompt
        assert "recommended_test_count" in prompt

    def test_user_prompt_lists_operations(self):
        analysis = _make_analysis(
            files=[("saleor/graphql/checkout/mutations/checkout_create.py", ChangeType.MODIFIED)],
            operations=["CheckoutCreate", "CheckoutAddPromoCode"],
        )
        prompt = _build_user_prompt(analysis, ["CheckoutCreate", "CheckoutAddPromoCode"])
        assert "CheckoutCreate" in prompt
        assert "CheckoutAddPromoCode" in prompt

    def test_user_prompt_handles_no_operations(self):
        analysis = _make_analysis(
            files=[("src/utils/helpers.py", ChangeType.MODIFIED)],
            untraced=["src/utils/helpers.py"],
        )
        prompt = _build_user_prompt(analysis, [])
        assert "none detected" in prompt

    def test_user_prompt_shows_untraced_files(self):
        analysis = _make_analysis(
            untraced=["src/utils/cache.py", "src/utils/queue.py"],
        )
        prompt = _build_user_prompt(analysis, [])
        assert "cache.py" in prompt
        assert "queue.py" in prompt


# ---------------------------------------------------------------------------
# RiskScorer.score — mocked LLM
# ---------------------------------------------------------------------------

class TestRiskScorerScore:
    @pytest.fixture
    def scorer(self):
        with patch("src.analyzers.risk_scorer.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                openrouter_api_key="test-key",
                openrouter_base_url="https://openrouter.ai/api/v1",
            )
            with patch("src.analyzers.risk_scorer.OpenAI"):
                s = RiskScorer()
        return s

    def test_empty_diff_returns_low_risk(self, scorer):
        analysis = DiffAnalysis()
        result = scorer.score(analysis)
        assert result.overall_risk == "LOW"
        assert result.recommended_test_count == 0
        assert result.operation_risks == []

    def test_score_returns_risk_assessment(self, scorer):
        payload = _make_assessment_payload(overall="CRITICAL", count=5)
        scorer._client.chat.completions.create.return_value = _mock_openai_response(payload)

        analysis = _make_analysis(
            files=[("saleor/graphql/payment/mutations/payment_capture.py", ChangeType.MODIFIED)],
            operations=["PaymentCapture"],
        )
        result = scorer.score(analysis)

        assert isinstance(result, RiskAssessment)
        assert result.overall_risk == "CRITICAL"
        assert result.recommended_test_count == 5
        assert len(result.operation_risks) == 1
        assert result.operation_risks[0].operation_name == "CheckoutCreate"

    def test_score_uses_analysis_operations_when_none_passed(self, scorer):
        payload = _make_assessment_payload(overall="HIGH", count=3)
        scorer._client.chat.completions.create.return_value = _mock_openai_response(payload)

        analysis = _make_analysis(
            files=[("saleor/graphql/checkout/mutations/checkout_create.py", ChangeType.ADDED)],
            operations=["CheckoutCreate"],
        )
        result = scorer.score(analysis)
        assert result.overall_risk == "HIGH"

    def test_score_accepts_explicit_operations_override(self, scorer):
        payload = _make_assessment_payload(overall="MEDIUM", count=2)
        scorer._client.chat.completions.create.return_value = _mock_openai_response(payload)

        analysis = _make_analysis(operations=["SomeOp"])
        result = scorer.score(analysis, operations=["OverrideOp"])

        call_args = scorer._client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "OverrideOp" in user_msg

    def test_score_strips_markdown_fences(self, scorer):
        payload = _make_assessment_payload()
        raw = f"```json\n{json.dumps(payload)}\n```"
        msg = MagicMock()
        msg.content = raw
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        scorer._client.chat.completions.create.return_value = resp

        analysis = _make_analysis(operations=["CheckoutCreate"])
        result = scorer.score(analysis)
        assert result.overall_risk == "HIGH"

    def test_operation_risk_fields(self, scorer):
        payload = _make_assessment_payload(
            ops=[{
                "operation_name": "TokenCreate",
                "risk_level": "CRITICAL",
                "reason": "Auth token creation.",
                "suggested_test_focus": ["invalid credentials", "expired tokens"],
            }]
        )
        scorer._client.chat.completions.create.return_value = _mock_openai_response(payload)

        analysis = _make_analysis(operations=["TokenCreate"])
        result = scorer.score(analysis)
        op = result.operation_risks[0]
        assert op.operation_name == "TokenCreate"
        assert op.risk_level == "CRITICAL"
        assert "invalid credentials" in op.suggested_test_focus
