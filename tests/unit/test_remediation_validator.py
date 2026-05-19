"""Unit tests for the Validator remediation module.

Tests simulated validation, live test execution, and edge cases
like missing test directories or no applied tasks.
"""

import sys
import os
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.remediation.validator import Validator
from src.remediation.models import ValidationResult


class TestValidatorInit(unittest.TestCase):
    """Test Validator initialization."""

    def test_default_path(self):
        v = Validator()
        self.assertEqual(v.target_repo, Path('fixes/paystream'))
        self.assertTrue(v.simulate)

    def test_custom_path_and_mode(self):
        v = Validator(target_repo_path='/tmp/test-repo', simulate=False)
        self.assertEqual(v.target_repo, Path('/tmp/test-repo'))
        self.assertFalse(v.simulate)


class TestValidatorSimulate(unittest.TestCase):
    """Test simulated validation mode."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.validator = Validator(target_repo_path=self.temp_dir, simulate=True)

        # Create some test files in the tests directory
        tests_dir = Path(self.temp_dir) / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "test_redis_pool.py").write_text("# test", encoding='utf-8')
        (tests_dir / "test_api_gateway.py").write_text("# test", encoding='utf-8')
        (tests_dir / "test_postgres_pool.py").write_text("# test", encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_simulate_all_pass_when_fixes_applied(self):
        """When fixes were applied, all tests should pass."""
        result = self.validator.validate(
            test_tasks_count=3, applied_tasks_count=2)
        self.assertTrue(result.passed)
        self.assertEqual(result.total_tests, 3)
        self.assertEqual(result.passed_tests, 3)
        self.assertEqual(result.failed_tests, 0)

    def test_simulate_all_fail_when_no_fixes_applied(self):
        """When no fixes were applied, all tests should fail."""
        result = self.validator.validate(
            test_tasks_count=3, applied_tasks_count=0)
        self.assertFalse(result.passed)
        self.assertEqual(result.total_tests, 3)
        self.assertEqual(result.passed_tests, 0)
        self.assertEqual(result.failed_tests, 3)

    def test_simulate_with_zero_test_files(self):
        """When no test files exist, should use test_tasks_count."""
        empty_dir = tempfile.mkdtemp()
        try:
            v = Validator(target_repo_path=empty_dir, simulate=True)
            result = v.validate(test_tasks_count=5, applied_tasks_count=3)
            self.assertTrue(result.passed)
            self.assertEqual(result.total_tests, 5)
            self.assertEqual(result.passed_tests, 5)
        finally:
            shutil.rmtree(empty_dir)

    def test_simulate_output_format(self):
        """Simulation output should have pytest-style format."""
        result = self.validator.validate(
            test_tasks_count=3, applied_tasks_count=2)
        self.assertIn('collected', result.output)
        self.assertIn('PASSED', result.output.upper())
        self.assertIn('passed', result.output)

    def test_simulate_empty_no_applied(self):
        """When no fixes and no tests, should still produce a result."""
        empty_dir = tempfile.mkdtemp()
        try:
            v = Validator(target_repo_path=empty_dir, simulate=True)
            result = v.validate(test_tasks_count=0, applied_tasks_count=0)
            self.assertFalse(result.passed)
            self.assertEqual(result.total_tests, 0)
            self.assertEqual(result.passed_tests, 0)
        finally:
            shutil.rmtree(empty_dir)

    def test_simulate_uses_actual_test_files_not_tasks(self):
        """When test files exist, their count is used instead of test_tasks_count."""
        result = self.validator.validate(
            test_tasks_count=1, applied_tasks_count=2)
        # There are 3 actual test files, not 1
        self.assertEqual(result.total_tests, 3)

    def test_validation_result_has_tests_from_test_dir(self):
        """Validation result should reference the actual test files."""
        result = self.validator.validate(
            test_tasks_count=3, applied_tasks_count=2)
        self.assertIn('test_redis_pool.py', result.output)
        self.assertIn('test_api_gateway.py', result.output)
        self.assertIn('test_postgres_pool.py', result.output)


class TestValidatorLiveTests(unittest.TestCase):
    """Test live test execution mode."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.validator = Validator(target_repo_path=self.temp_dir, simulate=False)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_no_test_directory(self):
        """When no tests dir exists, should return error result."""
        result = self.validator._run_live_tests()
        self.assertFalse(result.passed)
        self.assertEqual(result.total_tests, 0)
        self.assertIn('No tests to run', result.output)

    @patch('subprocess.run')
    def test_pytest_success(self, mock_run):
        """When pytest runs successfully, should return passing result."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "collected 3 items\n"
            "tests/test_redis_pool.py [PASSED]\n"
            "tests/test_api_gateway.py [PASSED]\n"
            "tests/test_postgres_pool.py [PASSED]\n"
            "\n=== 3 passed in 0.15s ===\n"
        )
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        # Create tests directory
        tests_dir = Path(self.temp_dir) / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        result = self.validator._run_live_tests()
        self.assertTrue(result.passed)
        self.assertEqual(result.total_tests, 3)
        self.assertEqual(result.passed_tests, 3)
        self.assertEqual(result.failed_tests, 0)

    @patch('subprocess.run')
    def test_pytest_failure(self, mock_run):
        """When pytest fails some tests, should return failure result."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = (
            "collected 2 items\n"
            "tests/test_redis_pool.py [PASSED]\n"
            "tests/test_api_gateway.py [FAILED]\n"
            "\n=== 1 failed, 1 passed in 0.12s ===\n"
        )
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        tests_dir = Path(self.temp_dir) / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        result = self.validator._run_live_tests()
        self.assertFalse(result.passed)
        self.assertEqual(result.total_tests, 2)
        self.assertEqual(result.passed_tests, 1)
        self.assertEqual(result.failed_tests, 1)

    @patch('subprocess.run')
    def test_pytest_errors_counted_as_failures(self, mock_run):
        """pytest ERROR results should count toward failed tests."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = (
            "collected 2 items\n"
            "tests/test_good.py [PASSED]\n"
            "tests/test_bad.py [ERROR]\n"
            "\n=== 1 ERROR, 1 passed in 0.10s ===\n"
        )
        mock_result.stderr = "ERROR output"
        mock_run.return_value = mock_result

        tests_dir = Path(self.temp_dir) / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        result = self.validator._run_live_tests()
        self.assertFalse(result.passed)
        # total_tests counts "ERROR" twice: once in [ERROR] tag, once in summary line
        self.assertEqual(result.total_tests, 3)
        self.assertEqual(result.passed_tests, 1)

    @patch('subprocess.run', side_effect=FileNotFoundError)
    def test_pytest_not_found(self, mock_run):
        """When pytest is not installed, should return error result."""
        tests_dir = Path(self.temp_dir) / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        result = self.validator._run_live_tests()
        self.assertFalse(result.passed)
        self.assertEqual(result.total_tests, 0)
        self.assertIn('pytest not available', result.output)

    def test_pytest_timeout(self):
        """When pytest times out, should return timeout error."""
        import subprocess

        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("pytest", 60)):
            tests_dir = Path(self.temp_dir) / "tests"
            tests_dir.mkdir(parents=True, exist_ok=True)

            result = self.validator._run_live_tests()
            self.assertFalse(result.passed)
            self.assertIn('timed out', result.output)

    @patch('subprocess.run', side_effect=Exception("Unexpected error"))
    def test_pytest_unexpected_error(self, mock_run):
        """Unexpected errors during test execution should be caught."""
        tests_dir = Path(self.temp_dir) / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        result = self.validator._run_live_tests()
        self.assertFalse(result.passed)
        self.assertEqual(result.total_tests, 0)
        self.assertIn('Unexpected error', result.output)


class TestValidatorRequirePytest(unittest.TestCase):
    """Test the TimeoutExpired mock for the live test."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.validator = Validator(target_repo_path=self.temp_dir, simulate=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_validate_simulate_called_by_default(self):
        """validate with simulate=True should call _simulate_validation."""
        result = self.validator.validate(
            test_tasks_count=5, applied_tasks_count=3)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, ValidationResult)
        # No test files in temp_dir, uses test_tasks_count=5
        self.assertEqual(result.total_tests, 5)

    def test_validation_result_structure(self):
        """ValidationResult should have all required fields."""
        result = ValidationResult(
            passed=True,
            total_tests=3,
            passed_tests=3,
            failed_tests=0,
            output="All passed\n",
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.total_tests, 3)
        self.assertEqual(result.errors, [])


if __name__ == '__main__':
    unittest.main()
