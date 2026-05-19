"""Unit tests for the Fixer remediation module.

Tests the application of config edits, k8s manifest changes,
code edits, SQL migrations, file creation, and script logging.
"""

import sys
import os
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.remediation.fixer import (
    Fixer, FIX_TEMPLATES, JAVA_CODE_FIXES, PYTHON_CODE_FIXES,
    SQL_MIGRATION_FIXES, NETWORK_POLICY_FIXES,
)
from src.remediation.models import ChangeType, FixStatus, FixTask


class TestFIXTEMPLATES(unittest.TestCase):
    """Test the FIX_TEMPLATES dictionary."""

    def test_all_templates_have_content(self):
        """Every template should have non-empty content."""
        for key, content in FIX_TEMPLATES.items():
            with self.subTest(template=key):
                self.assertIsInstance(content, str)
                self.assertGreater(len(content.strip()), 0)

    def test_all_template_keys_are_relative_paths(self):
        """Template keys should be file paths."""
        for key in FIX_TEMPLATES:
            self.assertIn('.', key, f"Template key '{key}' doesn't look like a file path")


class TestPYTHONCODEFIXES(unittest.TestCase):
    """Test Python code fix templates."""

    def test_has_data_validator_key(self):
        self.assertIn('src/data-service/data_validator.py', PYTHON_CODE_FIXES)

    def test_content_contains_class_definition(self):
        content = PYTHON_CODE_FIXES['src/data-service/data_validator.py']
        self.assertIn('class DataValidator', content)

    def test_content_contains_fix_comments(self):
        content = PYTHON_CODE_FIXES['src/data-service/data_validator.py']
        self.assertIn('FIXED', content)


class TestSQLMIGRATIONFIXES(unittest.TestCase):
    """Test SQL migration templates."""

    def test_has_migration_key(self):
        self.assertIn('configs/db/migrations/V005__add_payment_indexes.sql',
                      SQL_MIGRATION_FIXES)

    def test_content_contains_sql_keywords(self):
        content = list(SQL_MIGRATION_FIXES.values())[0]
        self.assertIn('CREATE INDEX', content)
        self.assertIn('CONCURRENTLY', content)

    def test_content_has_rollback(self):
        content = list(SQL_MIGRATION_FIXES.values())[0]
        self.assertIn('Rollback', content)


class TestNETWORKPOLICYFIXES(unittest.TestCase):
    """Test network policy templates."""

    def test_has_restrict_payment_key(self):
        self.assertIn('k8s/network-policies/restrict-payment-access.yaml',
                      NETWORK_POLICY_FIXES)

    def test_content_is_valid_yaml_structure(self):
        content = list(NETWORK_POLICY_FIXES.values())[0]
        self.assertIn('kind: NetworkPolicy', content)
        self.assertIn('apiVersion: networking.k8s.io/v1', content)

    def test_policy_types_are_correct(self):
        content = list(NETWORK_POLICY_FIXES.values())[0]
        self.assertIn('Ingress', content)
        self.assertIn('Egress', content)


class TestFixerInit(unittest.TestCase):
    """Test Fixer initialization."""

    def test_default_path(self):
        fixer = Fixer()
        self.assertEqual(fixer.target_repo, Path('fixes/paystream'))
        self.assertFalse(fixer.dry_run)

    def test_custom_path(self):
        fixer = Fixer(target_repo_path='/tmp/test-repo', dry_run=True)
        self.assertEqual(fixer.target_repo, Path('/tmp/test-repo'))
        self.assertTrue(fixer.dry_run)

    def test_applied_files_initially_empty(self):
        fixer = Fixer()
        self.assertEqual(len(fixer._applied_files), 0)


class TestFixerApply(unittest.TestCase):
    """Test the main apply method routing to sub-methods."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixer = Fixer(target_repo_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_config_edit_without_template_fails(self):
        """Config edit without template or content should be skipped."""
        task = FixTask(
            id="test-001", description="Edit config",
            change_type=ChangeType.CONFIG_EDIT, file_path="nonexistent.yaml",
        )
        result = self.fixer.apply(task)
        self.assertFalse(result)
        self.assertEqual(task.status, FixStatus.SKIPPED)

    def test_config_edit_with_content(self):
        """Config edit with task content should write the file."""
        file_path = "test-config.yaml"
        full_path = Path(self.temp_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text("original: content", encoding='utf-8')

        task = FixTask(
            id="test-002", description="Edit config",
            change_type=ChangeType.CONFIG_EDIT, file_path=file_path,
            new_content="updated: content",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        self.assertEqual(task.status, FixStatus.APPLIED)
        self.assertEqual(full_path.read_text(encoding='utf-8'), "updated: content")

    def test_k8s_manifest_with_content(self):
        """K8s manifest with task content should write the file."""
        file_path = "test-deploy.yaml"
        full_path = Path(self.temp_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text("original", encoding='utf-8')

        task = FixTask(
            id="test-003", description="Update k8s",
            change_type=ChangeType.K8S_MANIFEST, file_path=file_path,
            new_content="updated: manifest",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        self.assertEqual(task.status, FixStatus.APPLIED)

    def test_code_edit_without_template_fails(self):
        """Code edit without template or content should be skipped."""
        task = FixTask(
            id="test-004", description="Edit code",
            change_type=ChangeType.CODE_EDIT, file_path="src/unknown.py",
        )
        result = self.fixer.apply(task)
        self.assertFalse(result)
        self.assertEqual(task.status, FixStatus.SKIPPED)

    def test_code_edit_with_task_content(self):
        """Code edit with task content should write file."""
        file_path = "src/test.py"
        full_path = Path(self.temp_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text("# original", encoding='utf-8')

        task = FixTask(
            id="test-005", description="Edit code",
            change_type=ChangeType.CODE_EDIT, file_path=file_path,
            new_content="# updated",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        self.assertEqual(task.status, FixStatus.APPLIED)

    def test_script_run_always_succeeds(self):
        """Script run tasks should always succeed (they just log)."""
        task = FixTask(
            id="test-006", description="Run kubectl",
            change_type=ChangeType.SCRIPT_RUN, file_path="",
            command="kubectl scale deployment/test --replicas=3",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        self.assertEqual(task.status, FixStatus.APPLIED)

    def test_unknown_change_type_skipped(self):
        """Unknown change types should be skipped."""
        # Create a mock change type that has .value but isn't handled in if/elif
        class UnknownChangeType:
            value = "unknown_type"

        task = FixTask(
            id="test-007", description="Unknown",
            change_type=UnknownChangeType(), file_path="",
        )
        result = self.fixer.apply(task)
        self.assertFalse(result)

    def test_file_create_generic(self):
        """Generic file create should write new file."""
        file_path = "new-file.txt"
        full_path = Path(self.temp_dir) / file_path

        task = FixTask(
            id="test-008", description="Create file",
            change_type=ChangeType.FILE_CREATE, file_path=file_path,
            new_content="hello world",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        self.assertEqual(task.status, FixStatus.APPLIED)
        self.assertTrue(full_path.exists())
        self.assertEqual(full_path.read_text(encoding='utf-8'), "hello world")

    def test_file_create_overwrites_existing_with_content(self):
        """FILE_CREATE with new_content overwrites existing file."""
        file_path = "existing.txt"
        full_path = Path(self.temp_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text("existing", encoding='utf-8')

        task = FixTask(
            id="test-009", description="Create duplicate",
            change_type=ChangeType.FILE_CREATE, file_path=file_path,
            new_content="new content",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        self.assertEqual(task.status, FixStatus.APPLIED)
        self.assertEqual(full_path.read_text(encoding='utf-8'), "new content")


class TestFixerApplyWithTemplates(unittest.TestCase):
    """Test fixer with actual template content (in temp dir)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixer = Fixer(target_repo_path=self.temp_dir)

        # Create directory structure needed by templates
        for template_key in FIX_TEMPLATES:
            full_path = Path(self.temp_dir) / template_key
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(f"original {template_key}", encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_configmap_template_applied(self):
        """ConfigMap template should be applied successfully."""
        task = FixTask(
            id="test-010", description="Update ConfigMap",
            change_type=ChangeType.CONFIG_EDIT,
            file_path="configs/payment-processor/configmap.yaml",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        path = Path(self.temp_dir) / "configs/payment-processor/configmap.yaml"
        content = path.read_text(encoding='utf-8')
        self.assertIn('CONNECTION_POOL_SIZE: "25"', content)

    def test_redis_config_template_applied(self):
        """Redis config template should be applied."""
        task = FixTask(
            id="test-011", description="Update Redis",
            change_type=ChangeType.CONFIG_EDIT,
            file_path="configs/redis/redis-config.conf",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        path = Path(self.temp_dir) / "configs/redis/redis-config.conf"
        content = path.read_text(encoding='utf-8')
        self.assertIn('maxmemory 1gb', content)

    def test_pgbouncer_template_applied(self):
        """Postgres pgbouncer template should be applied."""
        task = FixTask(
            id="test-012", description="Update Postgres pool",
            change_type=ChangeType.CONFIG_EDIT,
            file_path="configs/postgres/pgbouncer-config.yaml",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        path = Path(self.temp_dir) / "configs/postgres/pgbouncer-config.yaml"
        content = path.read_text(encoding='utf-8')
        self.assertIn('max_client_conn = 300', content)

    def test_k8s_template_applied(self):
        """K8s manifest template should be applied."""
        task = FixTask(
            id="test-013", description="Update deployment",
            change_type=ChangeType.K8S_MANIFEST,
            file_path="k8s/notification-worker/deployment.yaml",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        path = Path(self.temp_dir) / "k8s/notification-worker/deployment.yaml"
        content = path.read_text(encoding='utf-8')
        self.assertIn('memory: "1Gi"', content)
        self.assertIn('replicas: 8', content)


class TestFixerTracksChanges(unittest.TestCase):
    """Test that fixer tracks original and new content."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixer = Fixer(target_repo_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_applied_files_tracks_original_and_new(self):
        """Fixer should track before/after content for each changed file."""
        file_path = "test-track.yaml"
        full_path = Path(self.temp_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        original = "original: content\n"
        full_path.write_text(original, encoding='utf-8')

        task = FixTask(
            id="test-014", description="Track changes",
            change_type=ChangeType.CONFIG_EDIT, file_path=file_path,
            new_content="updated: content\n",
        )
        self.fixer.apply(task)

        tracked = self.fixer._applied_files[file_path]
        self.assertEqual(tracked[0], original)
        self.assertEqual(tracked[1], "updated: content\n")

    def test_get_diff_contains_changes(self):
        """get_diff should return a diff string with file paths."""
        file_path = "test-diff.yaml"
        full_path = Path(self.temp_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text("original\n", encoding='utf-8')

        task = FixTask(
            id="test-015", description="Diff test",
            change_type=ChangeType.CONFIG_EDIT, file_path=file_path,
            new_content="updated\n",
        )
        self.fixer.apply(task)
        diff = self.fixer.get_diff()
        self.assertIn('--- a/', diff)
        self.assertIn('+++ b/', diff)
        self.assertIn(file_path, diff)

    def test_get_diff_empty_if_no_changes(self):
        """get_diff should return empty string if no files changed."""
        diff = self.fixer.get_diff()
        self.assertEqual(diff, "")


class TestFixerApplyAll(unittest.TestCase):
    """Test the apply_all method."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixer = Fixer(target_repo_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_apply_all_counts_correctly(self):
        """apply_all should return (applied, failed) counts."""
        # Script run always succeeds
        t1 = FixTask(
            id="t1", description="Script 1",
            change_type=ChangeType.SCRIPT_RUN, file_path="",
            command="echo hello",
        )
        # Config edit without template or content fails (skipped)
        t2 = FixTask(
            id="t2", description="Bad config",
            change_type=ChangeType.CONFIG_EDIT, file_path="nonexistent.yaml",
        )

        applied, failed = self.fixer.apply_all([t1, t2])
        self.assertEqual(applied, 1)
        self.assertEqual(failed, 1)

    def test_apply_all_skips_non_pending_tasks(self):
        """apply_all should skip tasks that are not in PENDING status."""
        t1 = FixTask(
            id="t1", description="Script",
            change_type=ChangeType.SCRIPT_RUN, file_path="",
            command="echo hi", status=FixStatus.FAILED,
        )
        applied, failed = self.fixer.apply_all([t1])
        self.assertEqual(applied, 0)
        self.assertEqual(failed, 0)

    def test_apply_all_sorts_by_priority(self):
        """apply_all should execute tasks in priority order."""
        results = []

        class TrackingFixer(Fixer):
            def apply(self, task):
                results.append(task.id)
                return True

        fixer = TrackingFixer(target_repo_path=self.temp_dir)

        t3 = FixTask(id="t3", description="Third", change_type=ChangeType.SCRIPT_RUN,
                     file_path="", command="echo 3", priority=3)
        t1 = FixTask(id="t1", description="First", change_type=ChangeType.SCRIPT_RUN,
                     file_path="", command="echo 1", priority=1)
        t2 = FixTask(id="t2", description="Second", change_type=ChangeType.SCRIPT_RUN,
                     file_path="", command="echo 2", priority=2)

        fixer.apply_all([t3, t1, t2])
        self.assertEqual(results, ["t1", "t2", "t3"])


class TestFixerDryRun(unittest.TestCase):
    """Test dry-run mode."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixer = Fixer(target_repo_path=self.temp_dir, dry_run=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_dry_run_does_not_write_file(self):
        """In dry run mode, files should NOT be written."""
        file_path = "test-dry.txt"
        full_path = Path(self.temp_dir) / file_path

        task = FixTask(
            id="test-dry", description="Dry run test",
            change_type=ChangeType.FILE_CREATE, file_path=file_path,
            new_content="should not be written",
        )
        self.fixer.apply(task)
        self.assertFalse(full_path.exists())

    def test_dry_run_still_tracks_content(self):
        """In dry run mode, content should still be tracked in _applied_files."""
        file_path = "configs/redis/redis-config.conf"
        full_path = Path(self.temp_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text("original", encoding='utf-8')

        task = FixTask(
            id="test-dry2", description="Dry run config",
            change_type=ChangeType.CONFIG_EDIT, file_path=file_path,
            new_content="updated",
        )
        self.fixer.apply(task)
        # File should still have original content
        self.assertEqual(full_path.read_text(encoding='utf-8'), "original")
        # But tracked in _applied_files
        self.assertIn(file_path, self.fixer._applied_files)


class TestFixerCodeEditTemplates(unittest.TestCase):
    """Test code edit templates (Python, Java)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixer = Fixer(target_repo_path=self.temp_dir)

        # Create Java source file
        java_path = Path(self.temp_dir) / "src/payment-service/RedisPoolManager.java"
        java_path.parent.mkdir(parents=True, exist_ok=True)
        java_path.write_text("package com.paystream.redis;\n// original\n",
                             encoding='utf-8')

        # Create Python source file
        py_path = Path(self.temp_dir) / "src/data-service/data_validator.py"
        py_path.parent.mkdir(parents=True, exist_ok=True)
        py_path.write_text("# original data validator\n", encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_python_code_fix_applied(self):
        """Python code edit template should be applied."""
        task = FixTask(
            id="test-py", description="Fix Python",
            change_type=ChangeType.CODE_EDIT,
            file_path="src/data-service/data_validator.py",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        content = (Path(self.temp_dir) / "src/data-service/data_validator.py").read_text()
        self.assertIn('class DataValidator', content)
        self.assertIn('FIXED', content)

    def test_java_code_fix_applied(self):
        """Java code edit template should be applied."""
        task = FixTask(
            id="test-java", description="Fix Redis pool",
            change_type=ChangeType.CODE_EDIT,
            file_path="src/payment-service/RedisPoolManager.java",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        content = (Path(self.temp_dir) / "src/payment-service/RedisPoolManager.java").read_text()
        self.assertIn('class RedisPoolManager', content)
        self.assertIn('FIXED', content)


class TestFixerNetworkPolicyTemplates(unittest.TestCase):
    """Test network policy templates."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixer = Fixer(target_repo_path=self.temp_dir)

        nw_path = Path(self.temp_dir) / "k8s/network-policies/restrict-payment-access.yaml"
        nw_path.parent.mkdir(parents=True, exist_ok=True)
        nw_path.write_text("# original network policy\n", encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_network_policy_template_applied(self):
        """Network policy template should be applied."""
        task = FixTask(
            id="test-nw", description="Fix network policy",
            change_type=ChangeType.K8S_MANIFEST,
            file_path="k8s/network-policies/restrict-payment-access.yaml",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        content = (Path(self.temp_dir) / "k8s/network-policies/restrict-payment-access.yaml").read_text()
        self.assertIn('kind: NetworkPolicy', content)
        self.assertIn('block-suspicious-ips', content)


class TestFixerSQLMigrationTemplates(unittest.TestCase):
    """Test SQL migration templates."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixer = Fixer(target_repo_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_sql_migration_template_applied(self):
        """SQL migration template should create the file."""
        task = FixTask(
            id="test-sql", description="Add migration",
            change_type=ChangeType.FILE_CREATE,
            file_path="configs/db/migrations/V005__add_payment_indexes.sql",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        path = Path(self.temp_dir) / "configs/db/migrations/V005__add_payment_indexes.sql"
        self.assertTrue(path.exists())
        content = path.read_text(encoding='utf-8')
        self.assertIn('CREATE INDEX', content)
        self.assertIn('CONCURRENTLY', content)


class TestFixerEdgeCases(unittest.TestCase):
    """Test edge cases for the Fixer."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixer = Fixer(target_repo_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_apply_with_nonexistent_file_edit(self):
        """Editing a nonexistent file should work (creates it)."""
        task = FixTask(
            id="test-edge-1", description="Edit nonexistent",
            change_type=ChangeType.CONFIG_EDIT,
            file_path="some/deep/path/config.yaml",
            new_content="content\n",
        )
        result = self.fixer.apply(task)
        self.assertTrue(result)
        path = Path(self.temp_dir) / "some/deep/path/config.yaml"
        self.assertTrue(path.exists())

    def test_task_status_on_exception(self):
        """Task should be marked FAILED if an exception occurs during apply."""

        class BrokenFixer(Fixer):
            def _apply_config_edit(self, task):
                raise RuntimeError("Unexpected error")

        fixer = BrokenFixer(target_repo_path=self.temp_dir)
        task = FixTask(
            id="test-exc", description="Broken",
            change_type=ChangeType.CONFIG_EDIT, file_path="test.yaml",
            new_content="content",
        )
        result = fixer.apply(task)
        self.assertFalse(result)
        self.assertEqual(task.status, FixStatus.FAILED)

    def test_apply_empty_tasks_list(self):
        """apply_all with empty list should return (0, 0)."""
        applied, failed = self.fixer.apply_all([])
        self.assertEqual(applied, 0)
        self.assertEqual(failed, 0)


if __name__ == '__main__':
    unittest.main()
