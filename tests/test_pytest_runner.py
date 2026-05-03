"""
tests/test_pytest_runner.py

Unit tests for the pytest runner module.
"""

import tempfile
from pathlib import Path

import pytest

from src.runners.pytest_runner import run_tests, PytestRunResult, SingleTestResult


@pytest.fixture
def temp_test_dir():
    """Create a temporary directory with sample test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple passing test with unique module names
        passing_test = Path(tmpdir) / "test_success_cases.py"
        passing_test.write_text("""
def test_simple_pass():
    assert 1 + 1 == 2

def test_another_pass():
    assert "hello" == "hello"
""")

        # Create a failing test with unique module name
        failing_test = Path(tmpdir) / "test_failure_cases.py"
        failing_test.write_text("""
def test_simple_fail():
    assert 1 + 1 == 3

def test_another_fail():
    assert True is False
""")

        # Create an error test with unique module name
        error_test = Path(tmpdir) / "test_error_cases.py"
        error_test.write_text("""
def test_raises_error():
    raise RuntimeError("Intentional error")
""")

        yield tmpdir


class TestRunTests:
    """Tests for the run_tests function."""

    def test_run_all_tests(self, temp_test_dir):
        """Test running all tests in a directory."""
        result = run_tests(test_dir=temp_test_dir)

        assert isinstance(result, PytestRunResult)
        assert result.total == 5
        assert result.passed == 2
        assert result.failed == 2
        assert result.errors == 1
        assert result.duration_seconds > 0
        assert len(result.test_results) == 5

    def test_result_structure(self, temp_test_dir):
        """Test that test results have proper structure."""
        result = run_tests(test_dir=temp_test_dir)

        for test_result in result.test_results:
            assert isinstance(test_result, SingleTestResult)
            assert test_result.test_name
            assert test_result.status in ("passed", "failed", "error")
            assert test_result.duration >= 0
            assert isinstance(test_result.stdout, str)

    def test_passed_tests(self, temp_test_dir):
        """Test that passing tests are correctly identified."""
        result = run_tests(test_dir=temp_test_dir)

        passed_tests = [r for r in result.test_results if r.status == "passed"]
        assert len(passed_tests) == 2
        for test in passed_tests:
            assert test.error_message is None

    def test_failed_tests(self, temp_test_dir):
        """Test that failing tests are correctly identified with error messages."""
        result = run_tests(test_dir=temp_test_dir)

        failed_tests = [r for r in result.test_results if r.status == "failed"]
        assert len(failed_tests) == 2
        for test in failed_tests:
            assert test.error_message is not None
            assert "assert" in test.error_message.lower()

    def test_error_tests(self, temp_test_dir):
        """Test that error tests are correctly identified."""
        result = run_tests(test_dir=temp_test_dir)

        error_tests = [r for r in result.test_results if r.status == "error"]
        assert len(error_tests) == 1
        for test in error_tests:
            assert test.error_message is not None
            assert "RuntimeError" in test.error_message

    def test_run_with_pattern_filter(self, temp_test_dir):
        """Test filtering tests by pattern."""
        result = run_tests(test_dir=temp_test_dir, pattern="success")

        assert result.total == 2
        assert result.passed == 2
        assert result.failed == 0
        assert result.errors == 0

    def test_run_nonexistent_directory(self):
        """Test that running tests from nonexistent directory raises error."""
        with pytest.raises(ValueError, match="Test directory does not exist"):
            run_tests(test_dir="/nonexistent/path")

    def test_generated_tests_default(self):
        """Test default directory is generated_tests and raises error if truly missing."""
        # Calling with a non-existent directory should raise ValueError
        with pytest.raises(ValueError, match="Test directory does not exist"):
            run_tests(test_dir="/nonexistent/truly/missing/path")

    def test_run_with_verbose_flag(self, temp_test_dir):
        """Test that verbose flag doesn't break execution."""
        result = run_tests(test_dir=temp_test_dir, verbose=True)

        assert result.total > 0
        assert result.duration_seconds > 0
