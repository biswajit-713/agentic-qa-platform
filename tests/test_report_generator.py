"""Tests for src/reporters/report_generator.py"""

import json
from pathlib import Path

import pytest

from src.agent.core import FailedGeneration, RunReport
from src.reporters.report_generator import generate_reports, _detect_layer
from src.runners.pytest_runner import PytestRunResult, SingleTestResult


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_run_result(passed=3, failed=1, errors=0) -> PytestRunResult:
    results = []
    for i in range(passed):
        results.append(SingleTestResult(
            test_name=f"generated_tests/api/test_op_{i}.py::test_op_{i}",
            status="passed",
            duration=0.1,
        ))
    for i in range(failed):
        results.append(SingleTestResult(
            test_name=f"generated_tests/ui/test_flow_{i}.py::test_flow_{i}",
            status="failed",
            duration=0.05,
            error_message="AssertionError: expected True",
        ))
    for i in range(errors):
        results.append(SingleTestResult(
            test_name=f"generated_tests/integration/test_int_{i}.py::test_int_{i}",
            status="error",
            duration=0.02,
            error_message="RuntimeError",
        ))
    return PytestRunResult(
        total=passed + failed + errors,
        passed=passed,
        failed=failed,
        errors=errors,
        duration_seconds=1.23,
        test_results=results,
    )


def _make_report(**overrides) -> RunReport:
    defaults = dict(
        timestamp="2026-05-09T10:00:00+00:00",
        diff_range="HEAD~3..HEAD",
        overall_risk="HIGH",
        recommended_test_count=5,
        new_tests_generated=["test_create_product", "test_checkout"],
        failed_generations=[FailedGeneration(operation_name="deleteFoo", error="not found")],
        run_result=_make_run_result(),
        regressions=[],
        quality_gate_passed=True,
        operation_risks=[
            {
                "operation_name": "productCreate",
                "risk_level": "HIGH",
                "reason": "Core mutation modified",
                "suggested_test_focus": ["happy path", "validation"],
            }
        ],
    )
    defaults.update(overrides)
    return RunReport(**defaults)


# ─── _detect_layer ────────────────────────────────────────────────────────────


def test_detect_layer_api():
    r = SingleTestResult(test_name="generated_tests/api/test_foo.py::test_foo", status="passed", duration=0.1)
    assert _detect_layer(r) == "api"


def test_detect_layer_ui():
    r = SingleTestResult(test_name="generated_tests/ui/test_homepage.py::test_homepage", status="passed", duration=0.1)
    assert _detect_layer(r) == "ui"


def test_detect_layer_integration():
    r = SingleTestResult(test_name="generated_tests/integration/test_cart.py::test_cart", status="passed", duration=0.1)
    assert _detect_layer(r) == "integration"


def test_detect_layer_playwright_fallback():
    r = SingleTestResult(test_name="tests/test_playwright_checkout.py::test_checkout", status="passed", duration=0.1)
    assert _detect_layer(r) == "ui"


# ─── JSON report ─────────────────────────────────────────────────────────────


def test_json_report_created(tmp_path):
    report = _make_report()
    json_path, _ = generate_reports(report, output_dir=tmp_path)
    assert json_path.exists()
    assert json_path.name == "latest.json"


def test_json_report_valid_json(tmp_path):
    report = _make_report()
    json_path, _ = generate_reports(report, output_dir=tmp_path)
    data = json.loads(json_path.read_text())
    assert data["diff_range"] == "HEAD~3..HEAD"
    assert data["overall_risk"] == "HIGH"
    assert data["quality_gate_passed"] is True


def test_json_report_includes_coverage(tmp_path):
    report = _make_report()
    json_path, _ = generate_reports(report, output_dir=tmp_path, coverage_before=40.0, coverage_after=55.5)
    data = json.loads(json_path.read_text())
    assert data["coverage_before"] == pytest.approx(40.0)
    assert data["coverage_after"] == pytest.approx(55.5)


def test_json_report_includes_rationale(tmp_path):
    report = _make_report()
    json_path, _ = generate_reports(report, output_dir=tmp_path, rationale="Risk was elevated due to auth changes.")
    data = json.loads(json_path.read_text())
    assert "rationale" in data
    assert "auth" in data["rationale"]


def test_json_report_null_coverage_when_omitted(tmp_path):
    report = _make_report()
    json_path, _ = generate_reports(report, output_dir=tmp_path)
    data = json.loads(json_path.read_text())
    assert data["coverage_before"] is None
    assert data["coverage_after"] is None


# ─── HTML report ─────────────────────────────────────────────────────────────


def test_html_report_created(tmp_path):
    report = _make_report()
    _, html_path = generate_reports(report, output_dir=tmp_path)
    assert html_path.exists()
    assert html_path.name == "latest.html"


def test_html_report_contains_diff_range(tmp_path):
    report = _make_report()
    _, html_path = generate_reports(report, output_dir=tmp_path)
    content = html_path.read_text()
    assert "HEAD~3..HEAD" in content


def test_html_report_quality_gate_pass(tmp_path):
    report = _make_report(quality_gate_passed=True)
    _, html_path = generate_reports(report, output_dir=tmp_path)
    assert "QUALITY GATE PASSED" in html_path.read_text()


def test_html_report_quality_gate_fail(tmp_path):
    report = _make_report(quality_gate_passed=False, regressions=["test_foo"])
    _, html_path = generate_reports(report, output_dir=tmp_path)
    content = html_path.read_text()
    assert "QUALITY GATE FAILED" in content
    assert "test_foo" in content


def test_html_report_contains_risk_level(tmp_path):
    report = _make_report()
    _, html_path = generate_reports(report, output_dir=tmp_path)
    assert "HIGH" in html_path.read_text()


def test_html_report_contains_operation_name(tmp_path):
    report = _make_report()
    _, html_path = generate_reports(report, output_dir=tmp_path)
    assert "productCreate" in html_path.read_text()


def test_html_report_shows_coverage(tmp_path):
    report = _make_report()
    _, html_path = generate_reports(report, output_dir=tmp_path, coverage_after=72.5)
    assert "72.5" in html_path.read_text()


def test_html_report_shows_rationale(tmp_path):
    report = _make_report()
    _, html_path = generate_reports(report, output_dir=tmp_path, rationale="High risk: payment flow modified.")
    assert "payment flow" in html_path.read_text()


def test_html_report_no_coverage_shows_placeholder(tmp_path):
    report = _make_report()
    _, html_path = generate_reports(report, output_dir=tmp_path)
    assert "Coverage data not available" in html_path.read_text()


def test_output_dir_created_automatically(tmp_path):
    nested = tmp_path / "deep" / "nested"
    report = _make_report()
    json_path, html_path = generate_reports(report, output_dir=nested)
    assert json_path.exists()
    assert html_path.exists()
