"""Tests for src/agent/core.py"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agent.core import (
    AgentState,
    FailedGeneration,
    RunReport,
    check_quality_gate,
    detect_regressions,
    fetch_schema_ops,
    generate_targeted_tests,
    get_git_diff,
    load_state,
    run_loop,
    save_state,
)
from src.analyzers.risk_scorer import RiskAssessment, OperationRisk
from src.analyzers.schema_analyzer import GraphQLOperation
from src.runners.pytest_runner import PytestRunResult, SingleTestResult


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def empty_run_result() -> PytestRunResult:
    return PytestRunResult(total=0, passed=0, failed=0, errors=0, duration_seconds=0.0)


@pytest.fixture
def run_result_all_pass() -> PytestRunResult:
    return PytestRunResult(
        total=2,
        passed=2,
        failed=0,
        errors=0,
        duration_seconds=1.0,
        test_results=[
            SingleTestResult(test_name="test_foo", status="passed", duration=0.5),
            SingleTestResult(test_name="test_bar", status="passed", duration=0.5),
        ],
    )


@pytest.fixture
def run_result_with_failure() -> PytestRunResult:
    return PytestRunResult(
        total=2,
        passed=1,
        failed=1,
        errors=0,
        duration_seconds=1.0,
        test_results=[
            SingleTestResult(test_name="test_foo", status="passed", duration=0.5),
            SingleTestResult(test_name="test_bar", status="failed", duration=0.5, error_message="assert False"),
        ],
    )


@pytest.fixture
def low_risk_assessment() -> RiskAssessment:
    return RiskAssessment(
        overall_risk="LOW",
        rationale="Minor changes.",
        recommended_test_count=0,
        operation_risks=[],
    )


@pytest.fixture
def high_risk_assessment() -> RiskAssessment:
    return RiskAssessment(
        overall_risk="HIGH",
        rationale="Payment mutation changed.",
        recommended_test_count=3,
        operation_risks=[
            OperationRisk(
                operation_name="checkoutComplete",
                risk_level="HIGH",
                reason="Payment flow.",
                suggested_test_focus=["happy path", "payment error"],
            ),
            OperationRisk(
                operation_name="productCreate",
                risk_level="LOW",
                reason="Catalog only.",
                suggested_test_focus=[],
            ),
        ],
    )


@pytest.fixture
def schema_op() -> GraphQLOperation:
    return GraphQLOperation(
        name="checkoutComplete",
        type="mutation",
        returnType="CheckoutComplete",
    )


# ─── get_git_diff ─────────────────────────────────────────────────────────────


def test_get_git_diff_returns_stdout(tmp_path):
    with patch("src.agent.core.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="diff --git a/foo.py b/foo.py\n", stderr="")
        result = get_git_diff("HEAD~1..HEAD", repo_path=tmp_path)
    assert "diff --git" in result


def test_get_git_diff_nonzero_returns_stdout_anyway(tmp_path):
    with patch("src.agent.core.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="bad revision")
        result = get_git_diff("bad..range", repo_path=tmp_path)
    assert result == ""


# ─── load_state / save_state ──────────────────────────────────────────────────


def test_load_state_missing_file_returns_empty(tmp_path):
    state = load_state(tmp_path / "nonexistent.json")
    assert state.last_run_timestamp is None
    assert state.last_run_results == {}


def test_load_state_reads_existing_file(tmp_path):
    state_file = tmp_path / "state.json"
    data = {
        "last_run_timestamp": "2026-05-07T00:00:00+00:00",
        "last_run_results": {"test_foo": "passed"},
    }
    state_file.write_text(json.dumps(data))
    state = load_state(state_file)
    assert state.last_run_results["test_foo"] == "passed"


def test_load_state_corrupt_json_returns_empty(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text("{not valid json}")
    state = load_state(state_file)
    assert state.last_run_results == {}


def test_save_state_writes_json(tmp_path, run_result_all_pass):
    state_file = tmp_path / "state.json"
    save_state(state_file, run_result_all_pass)
    data = json.loads(state_file.read_text())
    assert data["last_run_results"]["test_foo"] == "passed"
    assert data["last_run_results"]["test_bar"] == "passed"
    assert "last_run_timestamp" in data


def test_save_state_creates_parent_dirs(tmp_path, empty_run_result):
    state_file = tmp_path / "subdir" / "state.json"
    save_state(state_file, empty_run_result)
    assert state_file.exists()


# ─── detect_regressions ───────────────────────────────────────────────────────


def test_detect_regressions_none_when_no_history(run_result_with_failure):
    state = AgentState()
    regressions = detect_regressions(run_result_with_failure, state)
    assert regressions == []


def test_detect_regressions_finds_newly_broken_test(run_result_with_failure):
    state = AgentState(last_run_results={"test_bar": "passed"})
    regressions = detect_regressions(run_result_with_failure, state)
    assert "test_bar" in regressions


def test_detect_regressions_ignores_already_failing(run_result_with_failure):
    state = AgentState(last_run_results={"test_bar": "failed"})
    regressions = detect_regressions(run_result_with_failure, state)
    assert regressions == []


def test_detect_regressions_empty_when_all_pass(run_result_all_pass):
    state = AgentState(last_run_results={"test_foo": "passed", "test_bar": "passed"})
    regressions = detect_regressions(run_result_all_pass, state)
    assert regressions == []


# ─── check_quality_gate ───────────────────────────────────────────────────────


def test_quality_gate_passes_with_no_failures(low_risk_assessment, run_result_all_pass):
    assert check_quality_gate(low_risk_assessment, run_result_all_pass, []) is True


def test_quality_gate_fails_with_regressions(low_risk_assessment, run_result_all_pass):
    assert check_quality_gate(low_risk_assessment, run_result_all_pass, ["test_foo"]) is False


def test_quality_gate_fails_when_critical_op_test_fails():
    risk = RiskAssessment(
        overall_risk="CRITICAL",
        rationale="Critical payment change.",
        recommended_test_count=5,
        operation_risks=[
            OperationRisk(
                operation_name="checkoutComplete",
                risk_level="CRITICAL",
                reason="Payment.",
                suggested_test_focus=[],
            )
        ],
    )
    run_result = PytestRunResult(
        total=1,
        passed=0,
        failed=1,
        errors=0,
        duration_seconds=0.5,
        test_results=[
            SingleTestResult(
                test_name="test_checkoutcomplete_happy_path",
                status="failed",
                duration=0.5,
                error_message="AssertionError",
            )
        ],
    )
    assert check_quality_gate(risk, run_result, []) is False


def test_quality_gate_passes_when_low_op_fails():
    risk = RiskAssessment(
        overall_risk="LOW",
        rationale="Trivial change.",
        recommended_test_count=1,
        operation_risks=[
            OperationRisk(
                operation_name="productList",
                risk_level="LOW",
                reason="Read-only.",
                suggested_test_focus=[],
            )
        ],
    )
    run_result = PytestRunResult(
        total=1,
        passed=0,
        failed=1,
        errors=0,
        duration_seconds=0.5,
        test_results=[
            SingleTestResult(
                test_name="test_product_list",
                status="failed",
                duration=0.5,
                error_message="AssertionError",
            )
        ],
    )
    assert check_quality_gate(risk, run_result, []) is True


# ─── generate_targeted_tests ──────────────────────────────────────────────────


def test_generate_targeted_tests_only_high_critical(high_risk_assessment, schema_op):
    schema_ops = {"checkoutcomplete": schema_op}
    mock_generator = MagicMock()
    mock_tc = MagicMock()
    mock_tc.test_name = "test_checkout_complete"
    mock_generator.generate.return_value = mock_tc
    mock_generator.write_test.return_value = Path("generated_tests/api/test_checkout_complete.py")

    generated, failures = generate_targeted_tests(high_risk_assessment, schema_ops, mock_generator)

    # Only checkoutComplete (HIGH) should be generated — productCreate (LOW) skipped
    assert "test_checkout_complete" in generated
    assert mock_generator.generate.call_count == 1
    assert len(failures) == 0


def test_generate_targeted_tests_skips_missing_schema_op(high_risk_assessment):
    schema_ops: dict = {}  # nothing in schema
    mock_generator = MagicMock()

    generated, failures = generate_targeted_tests(high_risk_assessment, schema_ops, mock_generator)

    assert generated == []
    assert len(failures) == 1
    assert failures[0].operation_name == "checkoutComplete"
    assert "not found in schema" in failures[0].error
    mock_generator.generate.assert_not_called()


def test_generate_targeted_tests_no_high_risk_ops(low_risk_assessment):
    mock_generator = MagicMock()
    generated, failures = generate_targeted_tests(low_risk_assessment, {}, mock_generator)
    assert generated == []
    assert failures == []
    mock_generator.generate.assert_not_called()


def test_generate_targeted_tests_handles_generator_exception(high_risk_assessment, schema_op):
    schema_ops = {"checkoutcomplete": schema_op}
    mock_generator = MagicMock()
    mock_generator.generate.side_effect = ValueError("LLM timeout")

    generated, failures = generate_targeted_tests(high_risk_assessment, schema_ops, mock_generator)

    assert generated == []
    assert len(failures) == 1
    assert "LLM timeout" in failures[0].error


# ─── fetch_schema_ops ─────────────────────────────────────────────────────────


def test_fetch_schema_ops_returns_combined_map():
    mock_analyzer = MagicMock()
    q1 = GraphQLOperation(name="products", type="query", returnType="ProductCountableConnection")
    m1 = GraphQLOperation(name="productCreate", type="mutation", returnType="ProductCreate")
    mock_analyzer.get_all_queries.return_value = [q1]
    mock_analyzer.get_all_mutations.return_value = [m1]

    ops = fetch_schema_ops(mock_analyzer)

    assert "products" in ops
    assert "productcreate" in ops


def test_fetch_schema_ops_returns_empty_on_exception():
    mock_analyzer = MagicMock()
    mock_analyzer.get_all_queries.side_effect = RuntimeError("connection refused")

    ops = fetch_schema_ops(mock_analyzer)

    assert ops == {}


# ─── run_loop (integration) ───────────────────────────────────────────────────


def test_run_loop_writes_report(tmp_path, low_risk_assessment, empty_run_result):
    report_path = str(tmp_path / "report.json")
    state_file = str(tmp_path / "state.json")
    test_dir = str(tmp_path / "tests")
    Path(test_dir).mkdir()

    with patch("src.agent.core.get_git_diff", return_value=""), patch(
        "src.agent.core.DiffAnalyzer"
    ) as mock_diff_cls, patch("src.agent.core.RiskScorer") as mock_scorer_cls, patch(
        "src.agent.core.SchemaAnalyzer"
    ) as mock_schema_cls, patch(
        "src.agent.core.ApiTestGenerator"
    ) as mock_gen_cls, patch(
        "src.agent.core.run_tests", return_value=empty_run_result
    ):
        mock_diff_cls.return_value.analyze_diff_text.return_value = MagicMock(
            changed_files=[], affected_operations=[]
        )
        mock_scorer_cls.return_value.score.return_value = low_risk_assessment
        mock_schema_cls.return_value.get_all_queries.return_value = []
        mock_schema_cls.return_value.get_all_mutations.return_value = []
        mock_gen_cls.return_value = MagicMock()

        report = run_loop(
            diff_range="HEAD~1..HEAD",
            test_dir=test_dir,
            state_file=state_file,
            report_path=report_path,
        )

    assert Path(report_path).exists()
    data = json.loads(Path(report_path).read_text())
    assert data["diff_range"] == "HEAD~1..HEAD"
    assert data["overall_risk"] == "LOW"
    assert "quality_gate_passed" in data


def test_run_loop_gate_fails_on_regression(tmp_path):
    report_path = str(tmp_path / "report.json")
    state_file = str(tmp_path / "state.json")
    test_dir = str(tmp_path / "tests")
    Path(test_dir).mkdir()

    # Seed state: test_foo was passing
    Path(state_file).write_text(
        json.dumps({"last_run_timestamp": "2026-05-07T00:00:00+00:00", "last_run_results": {"test_foo": "passed"}})
    )

    run_result = PytestRunResult(
        total=1,
        passed=0,
        failed=1,
        errors=0,
        duration_seconds=0.1,
        test_results=[SingleTestResult(test_name="test_foo", status="failed", duration=0.1, error_message="oops")],
    )
    risk = RiskAssessment(overall_risk="LOW", rationale=".", recommended_test_count=0, operation_risks=[])

    with patch("src.agent.core.get_git_diff", return_value=""), patch(
        "src.agent.core.DiffAnalyzer"
    ) as mock_diff_cls, patch("src.agent.core.RiskScorer") as mock_scorer_cls, patch(
        "src.agent.core.SchemaAnalyzer"
    ) as mock_schema_cls, patch(
        "src.agent.core.ApiTestGenerator"
    ), patch(
        "src.agent.core.run_tests", return_value=run_result
    ):
        mock_diff_cls.return_value.analyze_diff_text.return_value = MagicMock(
            changed_files=[], affected_operations=[]
        )
        mock_scorer_cls.return_value.score.return_value = risk
        mock_schema_cls.return_value.get_all_queries.return_value = []
        mock_schema_cls.return_value.get_all_mutations.return_value = []

        report = run_loop(
            diff_range="HEAD~1..HEAD",
            test_dir=test_dir,
            state_file=state_file,
            report_path=report_path,
        )

    assert report.quality_gate_passed is False
    assert "test_foo" in report.regressions


def test_run_loop_missing_test_dir_skips_run(tmp_path, low_risk_assessment):
    report_path = str(tmp_path / "report.json")
    state_file = str(tmp_path / "state.json")
    test_dir = str(tmp_path / "nonexistent")  # does not exist

    with patch("src.agent.core.get_git_diff", return_value=""), patch(
        "src.agent.core.DiffAnalyzer"
    ) as mock_diff_cls, patch("src.agent.core.RiskScorer") as mock_scorer_cls, patch(
        "src.agent.core.SchemaAnalyzer"
    ) as mock_schema_cls, patch(
        "src.agent.core.ApiTestGenerator"
    ), patch(
        "src.agent.core.run_tests"
    ) as mock_run:
        mock_diff_cls.return_value.analyze_diff_text.return_value = MagicMock(
            changed_files=[], affected_operations=[]
        )
        mock_scorer_cls.return_value.score.return_value = low_risk_assessment
        mock_schema_cls.return_value.get_all_queries.return_value = []
        mock_schema_cls.return_value.get_all_mutations.return_value = []

        report = run_loop(
            diff_range="HEAD~1..HEAD",
            test_dir=test_dir,
            state_file=state_file,
            report_path=report_path,
        )

    mock_run.assert_not_called()
    assert report.run_result.total == 0
