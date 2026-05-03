"""
src/agent/generate_command.py

Week 1 orchestrator: orchestrates schema analysis → coverage check → test generation →
test execution → reporting in a single CLI command.

Usage: uv run python -m src.agent.generate_command --count 10
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from pydantic import BaseModel, Field, ConfigDict

from src.analyzers.coverage_analyzer import CoverageAnalyzer
from src.generators.api_test_generator import ApiTestGenerator
from src.runners.pytest_runner import run_tests, PytestRunResult

logger = logging.getLogger(__name__)


class FailedGeneration(BaseModel):
    """Record of a failed test generation attempt."""

    model_config = ConfigDict(populate_by_name=True)

    operation_name: str = Field(..., description="GraphQL operation that failed to generate")
    error: str = Field(..., description="Error message from the failure")


class GenerationReport(BaseModel):
    """Summary of a test generation run."""

    model_config = ConfigDict(populate_by_name=True)

    timestamp: str = Field(
        ..., description="ISO 8601 timestamp of when the generation ran"
    )
    count_requested: int = Field(..., description="Number of tests requested")
    generated: list[str] = Field(
        default_factory=list, description="Test names that were successfully written"
    )
    failed_generations: list[FailedGeneration] = Field(
        default_factory=list, description="Operations that failed to generate"
    )
    coverage_before: float = Field(..., description="API coverage % before generation")
    coverage_after: float = Field(..., description="API coverage % after generation")
    total_operations: int = Field(..., description="Total GraphQL operations in schema")
    run_result: PytestRunResult = Field(..., description="Full pytest execution results")


def run_generation(count: int, test_dir: str, report_path: str) -> GenerationReport:
    """Orchestrate the test generation pipeline.

    Steps:
    1. Analyze schema and existing test coverage
    2. Take top N uncovered operations by priority
    3. Generate tests for each, skipping failures
    4. Execute all generated tests
    5. Recalculate coverage
    6. Write JSON report

    Args:
        count: Number of tests to generate
        test_dir: Directory where generated tests live (default: generated_tests/api)
        report_path: Path to write the JSON report

    Returns:
        GenerationReport with full results
    """
    logger.info("Starting test generation: count=%d, test_dir=%s", count, test_dir)

    # Step 1: Coverage before
    coverage_before = CoverageAnalyzer(test_dir=Path(test_dir)).analyze()
    logger.info(
        "Coverage before: %.1f%% (%d/%d operations)",
        coverage_before.coverage_percentage,
        coverage_before.covered_operations,
        coverage_before.total_operations,
    )

    # Step 2: Take top N from priority queue
    ops_to_generate = coverage_before.priority_queue[:count]
    logger.info("Targeting %d operations for generation", len(ops_to_generate))

    # Step 3: Generate tests — skip and log on failure
    generator = ApiTestGenerator()
    generated: list[str] = []
    failures: list[FailedGeneration] = []

    for i, op in enumerate(ops_to_generate, 1):
        try:
            logger.info("[%d/%d] Generating test for %s", i, len(ops_to_generate), op.name)
            test_case = generator.generate(op)
            test_file = generator.write_test(test_case)
            generated.append(test_case.test_name)
            logger.info("✓ Generated %s → %s", op.name, test_file)
        except Exception as e:
            logger.warning("✗ Skipping %s: %s", op.name, str(e))
            failures.append(FailedGeneration(operation_name=op.name, error=str(e)))

    logger.info("Generation complete: %d passed, %d failed", len(generated), len(failures))

    # Step 4: Run all tests
    logger.info("Running all tests in %s", test_dir)
    run_result = run_tests(test_dir=test_dir)
    logger.info(
        "Test run complete: %d passed, %d failed, %d errors (%.2fs)",
        run_result.passed,
        run_result.failed,
        run_result.errors,
        run_result.duration_seconds,
    )

    # Step 5: Coverage after
    coverage_after = CoverageAnalyzer(test_dir=Path(test_dir)).analyze()
    logger.info(
        "Coverage after: %.1f%% (%d/%d operations)",
        coverage_after.coverage_percentage,
        coverage_after.covered_operations,
        coverage_after.total_operations,
    )

    # Step 6: Build report
    report = GenerationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        count_requested=count,
        generated=generated,
        failed_generations=failures,
        coverage_before=coverage_before.coverage_percentage,
        coverage_after=coverage_after.coverage_percentage,
        total_operations=coverage_before.total_operations,
        run_result=run_result,
    )

    # Step 7: Write report
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(report.model_dump_json(indent=2))
    logger.info("Report written to %s", report_path)

    return report


app = typer.Typer()


@app.command()
def generate(
    count: int = typer.Option(10, "--count", "-n", help="Number of tests to generate"),
    test_dir: str = typer.Option(
        "generated_tests/api", "--test-dir", help="Directory for generated tests"
    ),
    report_path: str = typer.Option(
        "reports/generation_report.json", "--report", help="Path to write JSON report"
    ),
) -> None:
    """Generate N tests from uncovered GraphQL operations and report results."""
    report = run_generation(count=count, test_dir=test_dir, report_path=report_path)

    # Print summary to stdout
    print()
    print("=" * 70)
    print("TEST GENERATION REPORT")
    print("=" * 70)
    print(f"Timestamp:         {report.timestamp}")
    print(f"Tests Requested:   {report.count_requested}")
    print(f"Tests Generated:   {len(report.generated)}")
    print(f"Generation Failed: {len(report.failed_generations)}")
    print(f"Coverage Before:   {report.coverage_before:.1f}%")
    print(f"Coverage After:    {report.coverage_after:.1f}%")
    print()
    print("TEST EXECUTION")
    print(f"  Passed:  {report.run_result.passed}")
    print(f"  Failed:  {report.run_result.failed}")
    print(f"  Errors:  {report.run_result.errors}")
    print(f"  Total:   {report.run_result.total}")
    print(f"  Time:    {report.run_result.duration_seconds:.2f}s")
    print()
    print(f"Report saved to {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    app()
