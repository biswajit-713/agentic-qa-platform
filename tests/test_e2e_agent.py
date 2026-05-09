"""
tests/test_e2e_agent.py

End-to-end scenarios for the agent loop (all external I/O mocked).
Covers: empty diff, Saleor unreachable, LLM rate limit at risk-scoring step,
full HIGH-risk pipeline, and regression detection across two consecutive runs.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agent.core import run_loop, score_risk_with_fallback
from src.analyzers.diff_analyzer import DiffAnalysis
from src.analyzers.risk_scorer import OperationRisk, RiskAssessment
from src.runners.pytest_runner import PytestRunResult, SingleTestResult

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SALEOR_MUTATION_DIFF = """\
diff --git a/saleor/graphql/checkout/mutations/checkout.py b/saleor/graphql/checkout/mutations/checkout.py
index 0000001..0000002 100644
--- a/saleor/graphql/checkout/mutations/checkout.py
+++ b/saleor/graphql/checkout/mutations/checkout.py
@@ -10,6 +10,7 @@ class CheckoutComplete(BaseMutation):
+    def perform_mutation(cls, _root, info, /, **data):
+        # added risk-bearing payment logic
+        pass
"""


def _make_run_result(passed: int = 2, failed: int = 0) -> PytestRunResult:
    results = [
        SingleTestResult(test_name=f"test_op_{i}", status="passed", duration=0.1)
        for i in range(passed)
    ] + [
        SingleTestResult(
            test_name=f"test_fail_{i}", status="failed", duration=0.1, error_message="AssertionError"
        )
        for i in range(failed)
    ]
    return PytestRunResult(
        total=passed + failed,
        passed=passed,
        failed=failed,
        errors=0,
        duration_seconds=0.5,
        test_results=results,
    )


def _low_risk() -> RiskAssessment:
    return RiskAssessment(
        overall_risk="LOW", rationale="Trivial.", recommended_test_count=0, operation_risks=[]
    )


def _high_risk() -> RiskAssessment:
    return RiskAssessment(
        overall_risk="HIGH",
        rationale="Payment mutation changed.",
        recommended_test_count=2,
        operation_risks=[
            OperationRisk(
                operation_name="checkoutComplete",
                risk_level="HIGH",
                reason="Payment flow.",
                suggested_test_focus=["happy path"],
            )
        ],
    )


# ---------------------------------------------------------------------------
# Scenario 1: Empty diff
# ---------------------------------------------------------------------------


def test_e2e_empty_diff_produces_report(tmp_path):
    report_path = str(tmp_path / "report.json")
    state_file = str(tmp_path / "state.json")
    test_dir = str(tmp_path / "tests")
    Path(test_dir).mkdir()

    with (
        patch("src.agent.core.get_git_diff", return_value=""),
        patch("src.agent.core.score_risk_with_fallback", return_value=_low_risk()),
        patch("src.agent.core.SchemaAnalyzer") as mock_schema,
        patch("src.agent.core.ApiTestGenerator"),
        patch("src.agent.core.run_tests", return_value=_make_run_result()),
    ):
        mock_schema.return_value.get_all_queries.return_value = []
        mock_schema.return_value.get_all_mutations.return_value = []

        report = run_loop(
            diff_range="HEAD~1..HEAD",
            test_dir=test_dir,
            state_file=state_file,
            report_path=report_path,
        )

    assert Path(report_path).exists()
    assert report.overall_risk == "LOW"
    assert report.new_tests_generated == []
    assert report.quality_gate_passed is True


# ---------------------------------------------------------------------------
# Scenario 2: Saleor unreachable — schema fetch fails, report still produced
# ---------------------------------------------------------------------------


def test_e2e_saleor_unreachable_still_produces_report(tmp_path):
    report_path = str(tmp_path / "report.json")
    state_file = str(tmp_path / "state.json")
    test_dir = str(tmp_path / "tests")
    Path(test_dir).mkdir()

    with (
        patch("src.agent.core.get_git_diff", return_value=_SALEOR_MUTATION_DIFF),
        patch("src.agent.core.score_risk_with_fallback", return_value=_high_risk()),
        patch("src.agent.core.SchemaAnalyzer") as mock_schema,
        patch("src.agent.core.ApiTestGenerator"),
        patch("src.agent.core.run_tests", return_value=_make_run_result()),
    ):
        mock_schema.return_value.get_all_queries.side_effect = ConnectionRefusedError("Saleor down")

        report = run_loop(
            diff_range="HEAD~1..HEAD",
            test_dir=test_dir,
            state_file=state_file,
            report_path=report_path,
        )

    assert Path(report_path).exists()
    # No schema ops → generation fails gracefully (checkoutComplete not found)
    assert report.new_tests_generated == []
    assert len(report.failed_generations) == 1
    assert report.failed_generations[0].operation_name == "checkoutComplete"


# ---------------------------------------------------------------------------
# Scenario 3: LLM rate limit during risk scoring — MEDIUM fallback used
# ---------------------------------------------------------------------------


def test_e2e_risk_scoring_rate_limit_uses_fallback():
    """score_risk_with_fallback returns MEDIUM when LLM raises."""
    diff = DiffAnalysis(changed_files=[], affected_operations=[], untraced_changes=[])

    with patch("src.agent.core.RiskScorer") as mock_scorer_cls:
        mock_scorer_cls.return_value.score.side_effect = RuntimeError("429 rate limit")
        result = score_risk_with_fallback(diff)

    assert result.overall_risk == "MEDIUM"
    assert "429 rate limit" in result.rationale
    assert result.operation_risks == []


def test_e2e_rate_limit_fallback_still_writes_report(tmp_path):
    report_path = str(tmp_path / "report.json")
    state_file = str(tmp_path / "state.json")
    test_dir = str(tmp_path / "tests")
    Path(test_dir).mkdir()

    medium_risk = RiskAssessment(
        overall_risk="MEDIUM",
        rationale="Risk scoring unavailable (RuntimeError): 429 rate limit",
        recommended_test_count=0,
        operation_risks=[],
    )

    with (
        patch("src.agent.core.get_git_diff", return_value=_SALEOR_MUTATION_DIFF),
        patch("src.agent.core.RiskScorer") as mock_scorer_cls,
        patch("src.agent.core.SchemaAnalyzer") as mock_schema,
        patch("src.agent.core.ApiTestGenerator"),
        patch("src.agent.core.run_tests", return_value=_make_run_result()),
    ):
        mock_scorer_cls.return_value.score.side_effect = RuntimeError("429 rate limit")
        mock_schema.return_value.get_all_queries.return_value = []
        mock_schema.return_value.get_all_mutations.return_value = []

        report = run_loop(
            diff_range="HEAD~1..HEAD",
            test_dir=test_dir,
            state_file=state_file,
            report_path=report_path,
        )

    assert Path(report_path).exists()
    assert report.overall_risk == "MEDIUM"
    assert "rate limit" in report.run_result.model_dump_json() or report.new_tests_generated == []


# ---------------------------------------------------------------------------
# Scenario 4: Simulated Saleor mutation change — full HIGH-risk pipeline
# ---------------------------------------------------------------------------


def test_e2e_simulated_mutation_change_generates_and_reports(tmp_path):
    report_path = str(tmp_path / "report.json")
    state_file = str(tmp_path / "state.json")
    test_dir = str(tmp_path / "tests")
    Path(test_dir).mkdir()

    from src.analyzers.schema_analyzer import GraphQLOperation

    schema_op = GraphQLOperation(name="checkoutComplete", type="mutation", returnType="CheckoutComplete")

    mock_tc = MagicMock()
    mock_tc.test_name = "test_checkout_complete_happy_path"

    with (
        patch("src.agent.core.get_git_diff", return_value=_SALEOR_MUTATION_DIFF),
        patch("src.agent.core.score_risk_with_fallback", return_value=_high_risk()),
        patch("src.agent.core.SchemaAnalyzer") as mock_schema,
        patch("src.agent.core.ApiTestGenerator") as mock_gen_cls,
        patch("src.agent.core.run_tests", return_value=_make_run_result(passed=3)),
    ):
        mock_schema.return_value.get_all_queries.return_value = []
        mock_schema.return_value.get_all_mutations.return_value = [schema_op]
        mock_gen_cls.return_value.generate.return_value = mock_tc
        mock_gen_cls.return_value.write_test.return_value = Path(
            "generated_tests/api/test_checkout_complete_happy_path.py"
        )

        report = run_loop(
            diff_range="HEAD~1..HEAD",
            test_dir=test_dir,
            state_file=state_file,
            report_path=report_path,
        )

    assert Path(report_path).exists()
    assert report.overall_risk == "HIGH"
    assert "test_checkout_complete_happy_path" in report.new_tests_generated
    assert report.run_result.passed == 3
    assert report.quality_gate_passed is True

    data = json.loads(Path(report_path).read_text())
    assert data["overall_risk"] == "HIGH"
    assert len(data["operation_risks"]) == 1
    assert data["operation_risks"][0]["operation_name"] == "checkoutComplete"


# ---------------------------------------------------------------------------
# Scenario 5: Regression detected across two consecutive runs
# ---------------------------------------------------------------------------


def test_e2e_regression_across_consecutive_runs(tmp_path):
    """First run: test_foo passes. Second run: test_foo fails → gate fails."""
    report_path = str(tmp_path / "report.json")
    state_file = str(tmp_path / "state.json")
    test_dir = str(tmp_path / "tests")
    Path(test_dir).mkdir()

    first_run_result = PytestRunResult(
        total=1,
        passed=1,
        failed=0,
        errors=0,
        duration_seconds=0.1,
        test_results=[SingleTestResult(test_name="test_foo", status="passed", duration=0.1)],
    )

    def _patched_loop(run_result: PytestRunResult):
        with (
            patch("src.agent.core.get_git_diff", return_value=""),
            patch("src.agent.core.score_risk_with_fallback", return_value=_low_risk()),
            patch("src.agent.core.SchemaAnalyzer") as mock_schema,
            patch("src.agent.core.ApiTestGenerator"),
            patch("src.agent.core.run_tests", return_value=run_result),
        ):
            mock_schema.return_value.get_all_queries.return_value = []
            mock_schema.return_value.get_all_mutations.return_value = []
            return run_loop(
                diff_range="HEAD~1..HEAD",
                test_dir=test_dir,
                state_file=state_file,
                report_path=report_path,
            )

    report1 = _patched_loop(first_run_result)
    assert report1.quality_gate_passed is True

    second_run_result = PytestRunResult(
        total=1,
        passed=0,
        failed=1,
        errors=0,
        duration_seconds=0.1,
        test_results=[
            SingleTestResult(
                test_name="test_foo", status="failed", duration=0.1, error_message="regression"
            )
        ],
    )

    report2 = _patched_loop(second_run_result)
    assert report2.quality_gate_passed is False
    assert "test_foo" in report2.regressions
