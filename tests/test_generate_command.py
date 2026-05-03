"""Tests for src/agent/generate_command.py"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agent.generate_command import (
    run_generation,
    GenerationReport,
    FailedGeneration,
)
from src.analyzers.schema_analyzer import GraphQLOperation
from src.runners.pytest_runner import PytestRunResult, SingleTestResult


@pytest.fixture
def mock_coverage_report():
    """Mock CoverageReport with priority queue."""
    report = MagicMock()
    report.coverage_percentage = 20.0
    report.total_operations = 10
    report.covered_operations = 2
    report.priority_queue = [
        GraphQLOperation(name="productCreate", type="mutation", returnType="ProductPayload"),
        GraphQLOperation(name="checkoutCreate", type="mutation", returnType="CheckoutPayload"),
        GraphQLOperation(name="orderCancel", type="mutation", returnType="OrderCancelPayload"),
    ]
    return report


@pytest.fixture
def mock_test_case():
    """Mock TestCase returned by generator."""
    tc = MagicMock()
    tc.test_name = "test_product_create"
    return tc


@pytest.fixture
def mock_run_result():
    """Mock PytestRunResult from test runner."""
    return PytestRunResult(
        total=3,
        passed=3,
        failed=0,
        errors=0,
        duration_seconds=2.5,
        test_results=[
            SingleTestResult(
                test_name="test_product_create",
                status="passed",
                duration=0.5,
                error_message=None,
                stdout="",
            ),
            SingleTestResult(
                test_name="test_checkout_create",
                status="passed",
                duration=1.0,
                error_message=None,
                stdout="",
            ),
            SingleTestResult(
                test_name="test_order_cancel",
                status="passed",
                duration=1.0,
                error_message=None,
                stdout="",
            ),
        ],
    )


def test_run_generation_generates_up_to_count(
    mock_coverage_report, mock_test_case, mock_run_result, tmp_path
):
    """Only top N ops from priority queue are attempted."""
    report_path = tmp_path / "report.json"

    with patch(
        "src.agent.generate_command.CoverageAnalyzer"
    ) as mock_analyzer_class, patch(
        "src.agent.generate_command.ApiTestGenerator"
    ) as mock_generator_class, patch(
        "src.agent.generate_command.run_tests"
    ) as mock_run_tests:
        # Setup coverage analyzer
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.side_effect = [
            mock_coverage_report,  # before
            mock_coverage_report,  # after (simplified: same report)
        ]
        mock_analyzer_class.return_value = mock_analyzer

        # Setup generator
        mock_generator = MagicMock()
        mock_generator.generate.return_value = mock_test_case
        mock_generator.write_test.return_value = Path("generated_tests/api/test_product_create.py")
        mock_generator_class.return_value = mock_generator

        # Setup test runner
        mock_run_tests.return_value = mock_run_result

        # Run with count=2, should only try top 2
        report = run_generation(count=2, test_dir="generated_tests/api", report_path=str(report_path))

        # Verify generator was called exactly 2 times
        assert mock_generator.generate.call_count == 2
        assert len(report.generated) == 2
        assert len(report.failed_generations) == 0


def test_failed_generation_is_skipped(
    mock_coverage_report, mock_test_case, mock_run_result, tmp_path
):
    """One op raises → logged in failed_generations, others continue."""
    report_path = tmp_path / "report.json"

    with patch(
        "src.agent.generate_command.CoverageAnalyzer"
    ) as mock_analyzer_class, patch(
        "src.agent.generate_command.ApiTestGenerator"
    ) as mock_generator_class, patch(
        "src.agent.generate_command.run_tests"
    ) as mock_run_tests:
        # Setup analyzer
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.side_effect = [
            mock_coverage_report,
            mock_coverage_report,
        ]
        mock_analyzer_class.return_value = mock_analyzer

        # Setup generator: first succeeds, second raises, third succeeds
        mock_generator = MagicMock()
        mock_generator.generate.side_effect = [
            mock_test_case,  # first op: success
            ValueError("LLM timeout"),  # second op: failure
            mock_test_case,  # third op: success
        ]
        mock_generator.write_test.return_value = Path("generated_tests/api/test.py")
        mock_generator_class.return_value = mock_generator

        # Setup test runner
        mock_run_tests.return_value = mock_run_result

        # Run with count=3
        report = run_generation(count=3, test_dir="generated_tests/api", report_path=str(report_path))

        # Verify: 2 succeeded, 1 failed
        assert len(report.generated) == 2
        assert len(report.failed_generations) == 1
        assert report.failed_generations[0].operation_name == "checkoutCreate"
        assert "timeout" in report.failed_generations[0].error.lower()


def test_report_written_to_disk(mock_coverage_report, mock_test_case, mock_run_result, tmp_path):
    """report_path is created with valid JSON."""
    report_path = tmp_path / "subdir" / "report.json"

    with patch(
        "src.agent.generate_command.CoverageAnalyzer"
    ) as mock_analyzer_class, patch(
        "src.agent.generate_command.ApiTestGenerator"
    ) as mock_generator_class, patch(
        "src.agent.generate_command.run_tests"
    ) as mock_run_tests:
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.side_effect = [mock_coverage_report, mock_coverage_report]
        mock_analyzer_class.return_value = mock_analyzer

        mock_generator = MagicMock()
        mock_generator.generate.return_value = mock_test_case
        mock_generator.write_test.return_value = Path("generated_tests/api/test.py")
        mock_generator_class.return_value = mock_generator

        mock_run_tests.return_value = mock_run_result

        # Run generation
        run_generation(count=1, test_dir="generated_tests/api", report_path=str(report_path))

        # Verify file exists and is valid JSON
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert "timestamp" in data
        assert "generated" in data
        assert "failed_generations" in data


def test_coverage_before_after_in_report(
    mock_coverage_report, mock_test_case, mock_run_result, tmp_path
):
    """coverage_before and coverage_after populated correctly."""
    report_path = tmp_path / "report.json"

    with patch(
        "src.agent.generate_command.CoverageAnalyzer"
    ) as mock_analyzer_class, patch(
        "src.agent.generate_command.ApiTestGenerator"
    ) as mock_generator_class, patch(
        "src.agent.generate_command.run_tests"
    ) as mock_run_tests:
        # Setup: before coverage 20%, after coverage 50%
        before_report = MagicMock()
        before_report.coverage_percentage = 20.0
        before_report.total_operations = 10
        before_report.priority_queue = mock_coverage_report.priority_queue

        after_report = MagicMock()
        after_report.coverage_percentage = 50.0
        after_report.total_operations = 10

        mock_analyzer = MagicMock()
        mock_analyzer.analyze.side_effect = [before_report, after_report]
        mock_analyzer_class.return_value = mock_analyzer

        mock_generator = MagicMock()
        mock_generator.generate.return_value = mock_test_case
        mock_generator.write_test.return_value = Path("generated_tests/api/test.py")
        mock_generator_class.return_value = mock_generator

        mock_run_tests.return_value = mock_run_result

        # Run
        report = run_generation(count=1, test_dir="generated_tests/api", report_path=str(report_path))

        # Verify coverage changed
        assert report.coverage_before == 20.0
        assert report.coverage_after == 50.0


def test_empty_priority_queue(mock_test_case, mock_run_result, tmp_path):
    """0 ops to generate → 0 generated, run_tests still called."""
    report_path = tmp_path / "report.json"

    with patch(
        "src.agent.generate_command.CoverageAnalyzer"
    ) as mock_analyzer_class, patch(
        "src.agent.generate_command.ApiTestGenerator"
    ) as mock_generator_class, patch(
        "src.agent.generate_command.run_tests"
    ) as mock_run_tests:
        # Setup: empty priority queue
        empty_coverage = MagicMock()
        empty_coverage.coverage_percentage = 100.0
        empty_coverage.total_operations = 10
        empty_coverage.priority_queue = []

        mock_analyzer = MagicMock()
        mock_analyzer.analyze.side_effect = [empty_coverage, empty_coverage]
        mock_analyzer_class.return_value = mock_analyzer

        mock_generator = MagicMock()
        mock_generator_class.return_value = mock_generator

        mock_run_tests.return_value = mock_run_result

        # Run with count=10 (but queue is empty)
        report = run_generation(count=10, test_dir="generated_tests/api", report_path=str(report_path))

        # Verify
        assert len(report.generated) == 0
        assert len(report.failed_generations) == 0
        # But run_tests should still be called
        mock_run_tests.assert_called_once()
