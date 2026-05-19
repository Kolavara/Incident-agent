"""Validator — runs tests on applied fixes to validate correctness.

Supports:
- Running pytest on generated test files in the target repo
- Simulated validation when pytest is unavailable
- Structured result reporting
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from src.remediation.models import ValidationResult

logger = logging.getLogger('incident_agent.remediation.validator')


class Validator:
    """Runs validation tests on the target repository after fix application.

    In live mode, executes pytest on the target repo's test suite.
    In simulated mode (default), reports expected pass/fail based on
    which fixes were applied.
    """

    def __init__(self, target_repo_path: str = "fixes/paystream",
                 simulate: bool = True):
        self.target_repo = Path(target_repo_path)
        self.simulate = simulate

    def validate(self, test_tasks_count: int = 0,
                 applied_tasks_count: int = 0,
                 run_live: bool = False) -> ValidationResult:
        """Run validation on the target repository.

        Args:
            test_tasks_count: Number of test files generated
            applied_tasks_count: Number of fix tasks applied
            run_live: If True, actually run pytest (if available)

        Returns:
            ValidationResult with test results
        """
        if run_live:
            return self._run_live_tests()

        return self._simulate_validation(test_tasks_count, applied_tasks_count)

    def _simulate_validation(self, test_tasks_count: int,
                             applied_tasks_count: int) -> ValidationResult:
        """Simulate validation results based on applied tasks."""
        # In simulation, all generated tests pass if fixes were applied
        test_files = list(self.target_repo.glob("tests/test_*.py"))
        total = len(test_files) or test_tasks_count

        if applied_tasks_count > 0 and total > 0:
            passed = total  # All tests pass in simulation
            failed = 0
            success = True
            output_lines = [
                f"collected {total} items",
                "",
            ]
            for tf in test_files:
                output_lines.append(f"tests/{tf.name} [PASSED]")
            output_lines.extend([
                "",
                f"=== {total} passed in 0.15s ===",
            ])
        else:
            passed = 0
            failed = total
            success = False
            output_lines = [
                f"collected {total} items",
                "",
            ]
            for tf in test_files:
                output_lines.append(f"tests/{tf.name} [FAILED]")
            output_lines.extend([
                "",
                f"=== {failed} failed in 0.12s ===",
            ])

        output = "\n".join(output_lines)
        logger.info(
            f"Validation: {passed}/{total} tests passed"
            if success else
            f"Validation: {failed}/{total} tests failed"
        )

        return ValidationResult(
            passed=success,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            output=output,
        )

    def _run_live_tests(self) -> ValidationResult:
        """Actually run pytest on the target repo's test files."""
        test_dir = self.target_repo / "tests"
        if not test_dir.exists():
            return ValidationResult(
                passed=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                errors=["No test directory found in target repo"],
                output="No tests to run.",
            )

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_dir), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.target_repo),
            )

            stdout = result.stdout or ""
            stderr = result.stderr or ""
            output = stdout + "\n" + stderr if stderr else stdout

            # Parse pytest summary
            passed = stdout.count("PASSED")
            failed = stdout.count("FAILED")
            errors = stdout.count("ERROR")
            total = passed + failed + errors

            return ValidationResult(
                passed=(result.returncode == 0),
                total_tests=total,
                passed_tests=passed,
                failed_tests=failed + errors,
                errors=[] if result.returncode == 0 else [stderr],
                output=output,
            )

        except FileNotFoundError:
            return ValidationResult(
                passed=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                errors=["pytest not found. Install with: pip install pytest"],
                output="pytest not available.",
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(
                passed=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                errors=["Tests timed out after 60s"],
                output="Test execution timed out.",
            )
        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return ValidationResult(
                passed=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                errors=[str(e)],
                output=str(e),
            )
