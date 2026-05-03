"""
src/runners/pytest_runner.py

Executes generated pytest tests using pytest's Python API.
Captures structured results: pass/fail/error status, duration, error messages, and output.
"""

import logging
import time
from pathlib import Path
from typing import Optional

import pytest
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)


class SingleTestResult(BaseModel):
    """Result of a single test execution."""

    model_config = ConfigDict(populate_by_name=True)

    test_name: str = Field(..., description="Full test identifier (file::class::function)")
    status: str = Field(..., description="Test status: 'passed', 'failed', or 'error'")
    duration: float = Field(..., description="Execution time in seconds")
    error_message: Optional[str] = Field(
        default=None,
        description="Error or failure message if test did not pass",
    )
    stdout: str = Field(default="", description="Captured stdout during test execution")


class PytestRunResult(BaseModel):
    """Summary of a complete test run."""

    model_config = ConfigDict(populate_by_name=True)

    total: int = Field(..., description="Total number of tests executed")
    passed: int = Field(..., description="Number of passed tests")
    failed: int = Field(..., description="Number of failed tests")
    errors: int = Field(..., description="Number of tests with errors")
    duration_seconds: float = Field(..., description="Total execution time in seconds")
    test_results: list[SingleTestResult] = Field(
        default_factory=list,
        description="Detailed results for each test",
    )


# Backward compatibility alias
TestRunResult = PytestRunResult


class ResultCollector:
    """Custom pytest plugin to collect detailed test results."""

    def __init__(self):
        """Initialize result collector."""
        self.test_results: list[SingleTestResult] = []
        self.current_test_start_time: Optional[float] = None
        self.current_test_nodeid: Optional[str] = None

    def pytest_runtest_setup(self, item):
        """Called before each test runs."""
        self.current_test_nodeid = item.nodeid
        self.current_test_start_time = time.time()

    def pytest_runtest_makereport(self, item, call):
        """Called after each test phase (setup, call, teardown)."""
        if call.when == "call" and self.current_test_start_time is not None:
            # Determine outcome and error message
            outcome = "passed"
            error_message = None

            if call.excinfo is not None:
                if call.excinfo.type is AssertionError:
                    outcome = "failed"
                else:
                    outcome = "error"
                error_message = f"{call.excinfo.typename}: {call.excinfo.value}"

            duration = time.time() - self.current_test_start_time

            result = SingleTestResult(
                test_name=item.nodeid,
                status=outcome,
                duration=duration,
                error_message=error_message,
                stdout="",
            )
            self.test_results.append(result)


def run_tests(
    test_dir: Optional[str] = None,
    pattern: Optional[str] = None,
    verbose: bool = False,
) -> "PytestRunResult":
    """Run pytest tests and capture structured results.

    Args:
        test_dir: Directory containing tests. Defaults to generated_tests/
        pattern: Test filter pattern (e.g., "test_api" to run only tests matching this)
        verbose: If True, print pytest output to stdout

    Returns:
        PytestRunResult with aggregated results and per-test details

    Raises:
        ValueError: If test directory does not exist
    """
    # Default to generated_tests directory
    if test_dir is None:
        test_dir = "generated_tests"

    test_path = Path(test_dir)
    if not test_path.exists():
        raise ValueError(f"Test directory does not exist: {test_dir}")

    # Build pytest arguments
    args = [str(test_path)]

    # Add pattern filter if provided
    if pattern:
        args.append("-k")
        args.append(pattern)

    # Suppress pytest's own output unless verbose
    if not verbose:
        args.append("-q")

    # Disable Python import caching for temp directories
    args.append("--import-mode=importlib")

    # Set up result collector
    collector = ResultCollector()

    # Run pytest with our custom plugin
    start_time = time.time()
    try:
        exit_code = pytest.main(args, plugins=[collector])
    except Exception as e:
        logger.error(f"Error running tests: {e}")
        exit_code = 1

    duration_seconds = time.time() - start_time

    # Aggregate results
    passed = sum(1 for r in collector.test_results if r.status == "passed")
    failed = sum(1 for r in collector.test_results if r.status == "failed")
    errors = sum(1 for r in collector.test_results if r.status == "error")

    return PytestRunResult(
        total=len(collector.test_results),
        passed=passed,
        failed=failed,
        errors=errors,
        duration_seconds=duration_seconds,
        test_results=collector.test_results,
    )
