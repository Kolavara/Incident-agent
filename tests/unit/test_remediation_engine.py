"""Unit tests for the RemediationEngine orchestrator."""

import sys
import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.remediation.engine import RemediationEngine
from src.remediation.models import (
    ChangeType, FixStatus, FixTask, RemediationPlan,
    ValidationResult, PRResult, RemediationResult,
)


class TestRemediationEngineInit(unittest.TestCase):
    """Test RemediationEngine initialization."""

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_init_defaults(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        engine = RemediationEngine()
        self.assertFalse(engine.dry_run)
        mock_tk.assert_called_once()
        mock_fixer.assert_called_once_with("fixes/paystream", dry_run=False)
        mock_tg.assert_called_once()
        mock_val.assert_called_once()
        mock_gh.assert_called_once()

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_init_dry_run(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        engine = RemediationEngine(dry_run=True, simulate_validation=False)
        self.assertTrue(engine.dry_run)
        mock_fixer.assert_called_once_with("fixes/paystream", dry_run=True)

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_init_custom_path(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        engine = RemediationEngine(target_repo_path="/tmp/custom-repo")
        self.assertEqual(engine.target_repo, Path("/tmp/custom-repo"))


class TestRemediationEnginePlan(unittest.TestCase):
    """Test the plan method."""

    def setUp(self):
        self.diagnosis = {
            'diagnosis': {
                'root_cause': 'Redis connection pool exhausted',
                'confidence': 'High',
                'fix_steps': [
                    'Set CONNECTION_POOL_SIZE=25 in ConfigMap',
                    'Add exponential backoff on connection retry',
                ],
                'notes': 'Standard fix',
            },
            'incident_id': 'INC-014',
            'incident_type': 'KNOWN',
        }

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_plan_creates_valid_plan(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        # Mock task generator to return tasks
        mock_gen = MagicMock()
        mock_gen.generate.return_value = ([
            FixTask(id="fix-001", description="Set CONNECTION_POOL_SIZE=25",
                    change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs/redis/redis-config.conf"),
        ], "fix/INC-014-redis-pool")
        mock_tk.return_value = mock_gen

        engine = RemediationEngine()
        plan = engine.plan(self.diagnosis, "original raw log")

        self.assertIsNotNone(plan)
        self.assertEqual(plan.incident_id, "INC-014")
        self.assertEqual(plan.incident_type, "KNOWN")
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].id, "fix-001")
        self.assertIn("Redis connection pool exhausted", plan.pr_title)
        self.assertIsNotNone(engine._last_plan)

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_plan_no_diagnosis_key(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_gen = MagicMock()
        mock_gen.generate.return_value = ([], "fix/unknown")
        mock_tk.return_value = mock_gen

        engine = RemediationEngine()
        plan = engine.plan({}, "")
        self.assertEqual(len(plan.tasks), 0)
        self.assertEqual(plan.incident_id, "unknown")

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_plan_no_fix_steps(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_gen = MagicMock()
        mock_gen.generate.return_value = ([], "fix/unknown")
        mock_tk.return_value = mock_gen

        engine = RemediationEngine()
        plan = engine.plan({'diagnosis': {'root_cause': 'test'}}, "")
        self.assertEqual(len(plan.tasks), 0)


class TestRemediationEngineApply(unittest.TestCase):
    """Test the apply method."""

    def setUp(self):
        self.task = FixTask(
            id="fix-001",
            description="Fix pool size",
            change_type=ChangeType.CONFIG_EDIT,
            file_path="configs/redis/redis-config.conf",
            new_content="maxclients 100",
        )
        self.plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[self.task],
            branch_name="fix/INC-014",
            pr_title="fix: test",
        )

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_apply_success(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        # Mock fixer
        # Mock fixer with side_effect that updates task statuses
        def apply_all_side_effect(tasks):
            for t in tasks:
                t.status = FixStatus.APPLIED
            return (1, 0)
        mock_fixer_instance = MagicMock()
        mock_fixer_instance.apply_all.side_effect = apply_all_side_effect
        mock_fixer.return_value = mock_fixer_instance

        # Mock test generator
        mock_tg_instance = MagicMock()
        mock_tg_instance.generate.return_value = [
            FixTask(id="test-001", description="Test file",
                    change_type=ChangeType.FILE_CREATE,
                    file_path="tests/test_fix.py",
                    status=FixStatus.APPLIED),
        ]
        mock_tg.return_value = mock_tg_instance

        engine = RemediationEngine()
        result = engine.apply(self.plan)

        self.assertTrue(result)
        self.assertEqual(len(self.plan.tasks), 2)  # original + test task
        mock_fixer_instance.apply_all.assert_called_once()
        mock_tg_instance.generate.assert_called_once()

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_apply_all_failed(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_fixer_instance = MagicMock()
        mock_fixer_instance.apply_all.return_value = (0, 1)
        mock_fixer.return_value = mock_fixer_instance

        engine = RemediationEngine()
        result = engine.apply(self.plan)

        self.assertFalse(result)
        # No test generation when all fixes failed
        mock_tg.return_value.generate.assert_not_called()


class TestRemediationEngineValidate(unittest.TestCase):
    """Test the validate method."""

    def setUp(self):
        self.applied = FixTask(
            id="fix-001", description="Fix",
            change_type=ChangeType.CONFIG_EDIT,
            file_path="config.conf", status=FixStatus.APPLIED,
        )
        self.test_task = FixTask(
            id="test-001", description="Test",
            change_type=ChangeType.FILE_CREATE,
            file_path="tests/test_fix.py", status=FixStatus.APPLIED,
        )
        self.plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[self.applied, self.test_task],
            branch_name="fix/test",
            pr_title="test",
        )

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_validate_simulated(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_val_instance = MagicMock()
        mock_val_instance.validate.return_value = ValidationResult(
            passed=True, total_tests=1, passed_tests=1,
        )
        mock_val.return_value = mock_val_instance

        engine = RemediationEngine()
        result = engine.validate(self.plan, run_live=False)

        self.assertTrue(result.passed)
        self.assertEqual(result.total_tests, 1)
        mock_val_instance.validate.assert_called_once_with(
            test_tasks_count=1, applied_tasks_count=2, run_live=False,
        )

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_validate_live(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_val_instance = MagicMock()
        mock_val_instance.validate.return_value = ValidationResult(
            passed=False, total_tests=1, passed_tests=0,
        )
        mock_val.return_value = mock_val_instance

        engine = RemediationEngine()
        result = engine.validate(self.plan, run_live=True)

        self.assertFalse(result.passed)
        self.assertEqual(result.passed_tests, 0)


class TestRemediationEngineCreatePR(unittest.TestCase):
    """Test the create_pr method."""

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_create_pr_success(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_gh_instance = MagicMock()
        mock_gh_instance.create_pull_request.return_value = PRResult(
            success=True,
            pr_url="https://github.com/org/repo/pull/42",
            pr_number=42,
            branch_url="https://github.com/org/repo/tree/fix/INC-014",
        )
        mock_gh.return_value = mock_gh_instance

        plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[],
            branch_name="fix/INC-014",
            pr_title="test",
        )
        engine = RemediationEngine()
        result = engine.create_pr(plan)

        self.assertTrue(result.success)
        self.assertEqual(result.pr_number, 42)
        self.assertEqual(result.pr_url, "https://github.com/org/repo/pull/42")

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_create_pr_failure(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_gh_instance = MagicMock()
        mock_gh_instance.create_pull_request.return_value = PRResult(
            success=False,
            error="API rate limited",
        )
        mock_gh.return_value = mock_gh_instance

        plan = RemediationPlan(
            incident_id="INC-014",
            tasks=[],
            branch_name="fix/INC-014",
            pr_title="test",
        )
        engine = RemediationEngine()
        result = engine.create_pr(plan)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "API rate limited")


class TestRemediationEngineRun(unittest.TestCase):
    """Test the full run method."""

    def setUp(self):
        self.diagnosis = {
            'diagnosis': {
                'root_cause': 'Redis pool exhausted',
                'fix_steps': ['Set pool size to 25'],
            },
            'incident_id': 'INC-014',
            'incident_type': 'KNOWN',
        }

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_run_full_success(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        # Mock task generator
        mock_gen = MagicMock()
        mock_gen.generate.return_value = ([
            FixTask(id="fix-001", description="Set pool size",
                    change_type=ChangeType.CONFIG_EDIT,
                    file_path="config.conf"),
        ], "fix/INC-014-redis")
        mock_tk.return_value = mock_gen

        # Mock fixer with side_effect that updates task statuses
        def apply_all_side_effect(tasks):
            for t in tasks:
                t.status = FixStatus.APPLIED
            return (1, 0)
        mock_fixer_instance = MagicMock()
        mock_fixer_instance.apply_all.side_effect = apply_all_side_effect
        mock_fixer.return_value = mock_fixer_instance

        # Mock test generator
        mock_tg_instance = MagicMock()
        mock_tg_instance.generate.return_value = [
            FixTask(id="test-001", description="Test fix",
                    change_type=ChangeType.FILE_CREATE,
                    file_path="tests/test_fix.py",
                    status=FixStatus.APPLIED),
        ]
        mock_tg.return_value = mock_tg_instance

        # Mock validator
        mock_val_instance = MagicMock()
        mock_val_instance.validate.return_value = ValidationResult(
            passed=True, total_tests=1, passed_tests=1,
        )
        mock_val.return_value = mock_val_instance

        # Mock GitHub pusher
        mock_gh_instance = MagicMock()
        mock_gh_instance.create_pull_request.return_value = PRResult(
            success=True, pr_url="https://github.com/org/repo/pull/42",
        )
        mock_gh.return_value = mock_gh_instance

        engine = RemediationEngine()
        result = engine.run(self.diagnosis)

        self.assertIsNotNone(result.plan)
        self.assertEqual(result.applied_tasks, 2)  # 1 fix task + 1 test task
        self.assertEqual(result.failed_tasks, 0)
        self.assertTrue(result.validation.passed)
        self.assertTrue(result.pr.success)
        self.assertIsNone(result.error)

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_run_no_tasks_generated(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_gen = MagicMock()
        mock_gen.generate.return_value = ([], "")
        mock_tk.return_value = mock_gen

        engine = RemediationEngine()
        result = engine.run(self.diagnosis)

        self.assertIsNone(result.pr)
        self.assertIsNotNone(result.error)
        self.assertIn("No fix tasks", result.error)

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_run_exception_handling(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_gen = MagicMock()
        mock_gen.generate.side_effect = ValueError("Unexpected error")
        mock_tk.return_value = mock_gen

        engine = RemediationEngine()
        result = engine.run(self.diagnosis)

        self.assertIsNotNone(result.error)
        self.assertIn("Unexpected error", result.error)


class TestRemediationEngineGetLastPlan(unittest.TestCase):
    """Test get_last_plan and get_diff."""

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_get_last_plan_after_plan(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_gen = MagicMock()
        mock_gen.generate.return_value = ([], "fix/test")
        mock_tk.return_value = mock_gen

        engine = RemediationEngine()
        self.assertIsNone(engine.get_last_plan())

        engine.plan({'diagnosis': {'root_cause': 'test'}}, "")
        self.assertIsNotNone(engine.get_last_plan())

    @patch('src.remediation.engine.TaskGenerator')
    @patch('src.remediation.engine.Fixer')
    @patch('src.remediation.engine.TestGenerator')
    @patch('src.remediation.engine.Validator')
    @patch('src.remediation.engine.GitHubPusher')
    def test_get_diff(self, mock_gh, mock_val, mock_tg, mock_fixer, mock_tk):
        mock_fixer_instance = MagicMock()
        mock_fixer_instance.get_diff.return_value = "--- a/file\n+++ b/file\n+new line"
        mock_fixer.return_value = mock_fixer_instance

        engine = RemediationEngine()
        diff = engine.get_diff()
        self.assertEqual(diff, "--- a/file\n+++ b/file\n+new line")


if __name__ == '__main__':
    unittest.main()
