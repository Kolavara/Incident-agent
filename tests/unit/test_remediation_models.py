"""Unit tests for remediation data models."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.remediation.models import (
    ChangeType, FixStatus, FixTask, RemediationPlan,
    ValidationResult, PRResult, RemediationResult,
)


class TestChangeType(unittest.TestCase):
    """Test ChangeType enum values."""

    def test_enum_values(self):
        self.assertEqual(ChangeType.CONFIG_EDIT.value, "config_edit")
        self.assertEqual(ChangeType.CODE_EDIT.value, "code_edit")
        self.assertEqual(ChangeType.FILE_CREATE.value, "file_create")
        self.assertEqual(ChangeType.K8S_MANIFEST.value, "k8s_manifest")
        self.assertEqual(ChangeType.SCRIPT_RUN.value, "script_run")

    def test_enum_members_count(self):
        self.assertEqual(len(ChangeType), 5)


class TestFixStatus(unittest.TestCase):
    """Test FixStatus enum values."""

    def test_enum_values(self):
        self.assertEqual(FixStatus.PENDING.value, "pending")
        self.assertEqual(FixStatus.APPLIED.value, "applied")
        self.assertEqual(FixStatus.FAILED.value, "failed")
        self.assertEqual(FixStatus.SKIPPED.value, "skipped")

    def test_enum_members_count(self):
        self.assertEqual(len(FixStatus), 4)


class TestFixTask(unittest.TestCase):
    """Test FixTask dataclass."""

    def test_minimal_creation(self):
        task = FixTask(
            id="fix-001",
            description="Increase connection pool size",
            change_type=ChangeType.CONFIG_EDIT,
            file_path="configs/redis/redis-config.conf",
        )
        self.assertEqual(task.id, "fix-001")
        self.assertEqual(task.description, "Increase connection pool size")
        self.assertEqual(task.change_type, ChangeType.CONFIG_EDIT)
        self.assertEqual(task.file_path, "configs/redis/redis-config.conf")
        self.assertIsNone(task.original_content)
        self.assertIsNone(task.new_content)
        self.assertIsNone(task.command)
        self.assertEqual(task.status, FixStatus.PENDING)
        self.assertEqual(task.priority, 1)

    def test_full_creation(self):
        task = FixTask(
            id="fix-002",
            description="Fix Redis pool",
            change_type=ChangeType.CODE_EDIT,
            file_path="src/RedisPoolManager.java",
            original_content="pool=10",
            new_content="pool=25",
            command=None,
            status=FixStatus.APPLIED,
            priority=2,
        )
        self.assertEqual(task.id, "fix-002")
        self.assertEqual(task.change_type, ChangeType.CODE_EDIT)
        self.assertEqual(task.original_content, "pool=10")
        self.assertEqual(task.new_content, "pool=25")
        self.assertEqual(task.status, FixStatus.APPLIED)
        self.assertEqual(task.priority, 2)

    def test_script_run_task(self):
        task = FixTask(
            id="fix-003",
            description="Run kubectl rollout restart",
            change_type=ChangeType.SCRIPT_RUN,
            file_path="",
            command="kubectl rollout restart deploy/payment-processor",
        )
        self.assertEqual(task.change_type, ChangeType.SCRIPT_RUN)
        self.assertEqual(task.command, "kubectl rollout restart deploy/payment-processor")


class TestRemediationPlan(unittest.TestCase):
    """Test RemediationPlan dataclass."""

    def test_minimal_creation(self):
        plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[],
            branch_name="fix/INC-014-redis-pool",
            pr_title="fix: Redis connection pool exhausted",
        )
        self.assertEqual(plan.incident_id, "INC-014")
        self.assertEqual(plan.incident_type, "NOVEL")
        self.assertEqual(len(plan.tasks), 0)
        self.assertEqual(plan.branch_name, "fix/INC-014-redis-pool")
        self.assertEqual(plan.pr_title, "fix: Redis connection pool exhausted")

    def test_with_tasks(self):
        tasks = [
            FixTask(id="t1", description="Fix 1", change_type=ChangeType.CONFIG_EDIT, file_path="a.conf"),
            FixTask(id="t2", description="Fix 2", change_type=ChangeType.CODE_EDIT, file_path="b.py"),
        ]
        plan = RemediationPlan(
            incident_id="INC-015",
            incident_type="KNOWN",
            tasks=tasks,
            branch_name="fix/INC-015",
            pr_title="fix: test",
            pr_description="Test PR",
            summary="Two fixes applied",
        )
        self.assertEqual(plan.incident_type, "KNOWN")
        self.assertEqual(len(plan.tasks), 2)
        self.assertEqual(plan.pr_description, "Test PR")
        self.assertEqual(plan.summary, "Two fixes applied")


class TestValidationResult(unittest.TestCase):
    """Test ValidationResult dataclass."""

    def test_default_creation(self):
        result = ValidationResult()
        self.assertFalse(result.passed)
        self.assertEqual(result.total_tests, 0)
        self.assertEqual(result.passed_tests, 0)
        self.assertEqual(result.failed_tests, 0)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(result.output, "")

    def test_passed_validation(self):
        result = ValidationResult(
            passed=True,
            total_tests=5,
            passed_tests=5,
            failed_tests=0,
            output="All tests passed",
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.total_tests, 5)
        self.assertEqual(result.passed_tests, 5)
        self.assertEqual(result.failed_tests, 0)

    def test_failed_validation(self):
        result = ValidationResult(
            passed=False,
            total_tests=3,
            passed_tests=1,
            failed_tests=2,
            errors=["Test 2 failed", "Test 3 error"],
            output="2 failures",
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.errors), 2)


class TestPRResult(unittest.TestCase):
    """Test PRResult dataclass."""

    def test_default_creation(self):
        result = PRResult()
        self.assertFalse(result.success)
        self.assertEqual(result.branch_url, "")
        self.assertEqual(result.pr_url, "")
        self.assertIsNone(result.pr_number)
        self.assertIsNone(result.error)

    def test_successful_pr(self):
        result = PRResult(
            success=True,
            branch_url="https://github.com/owner/repo/tree/fix/INC-014",
            pr_url="https://github.com/owner/repo/pull/42",
            pr_number=42,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.pr_number, 42)
        self.assertIsNone(result.error)

    def test_failed_pr(self):
        result = PRResult(
            success=False,
            error="GitHub API returned 401",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "GitHub API returned 401")


class TestRemediationResult(unittest.TestCase):
    """Test RemediationResult dataclass."""

    def test_default_creation(self):
        result = RemediationResult()
        self.assertIsNone(result.plan)
        self.assertEqual(result.applied_tasks, 0)
        self.assertEqual(result.failed_tasks, 0)
        self.assertIsNone(result.validation)
        self.assertIsNone(result.pr)
        self.assertIsNone(result.error)

    def test_partial_result(self):
        plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[],
            branch_name="fix/test",
            pr_title="test",
        )
        result = RemediationResult(
            plan=plan,
            applied_tasks=3,
            failed_tasks=1,
            error="Some fixes failed",
        )
        self.assertIsNotNone(result.plan)
        self.assertEqual(result.applied_tasks, 3)
        self.assertEqual(result.failed_tasks, 1)
        self.assertEqual(result.error, "Some fixes failed")


if __name__ == '__main__':
    unittest.main()
