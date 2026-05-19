"""Unit tests for the TestGenerator remediation module.

Tests mapping of applied fix tasks to test templates, test file generation,
and handling of edge cases like no applied tasks or existing test files.
"""

import sys
import os
import unittest
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.remediation.test_generator import TestGenerator, TEST_TEMPLATES
from src.remediation.models import ChangeType, FixStatus, FixTask


class TestTEST_TEMPLATES(unittest.TestCase):
    """Test the TEST_TEMPLATES dictionary."""

    def test_all_templates_have_content(self):
        """Every test template should have non-empty Python code."""
        for key, content in TEST_TEMPLATES.items():
            with self.subTest(template=key):
                self.assertIsInstance(content, str)
                self.assertGreater(len(content.strip()), 0)
                self.assertTrue(content.startswith('"""') or content.startswith('\"\"\"') or
                                content.startswith("'''"),
                                f"Template {key} doesn't start with docstring")

    def test_all_templates_are_python_files(self):
        """All template keys should end with .py."""
        for key in TEST_TEMPLATES:
            self.assertTrue(key.endswith('.py'),
                            f"Template key '{key}' should end with .py")

    def test_all_templates_have_test_functions(self):
        """Each template should define at least one test_ function."""
        for key, content in TEST_TEMPLATES.items():
            with self.subTest(template=key):
                self.assertIn('def test_', content,
                              f"Template {key} has no test functions")

    def test_redis_pool_tests_exist(self):
        self.assertIn('test_redis_pool.py', TEST_TEMPLATES)

    def test_postgres_pool_tests_exist(self):
        self.assertIn('test_postgres_pool.py', TEST_TEMPLATES)

    def test_redis_config_tests_exist(self):
        self.assertIn('test_redis_config.py', TEST_TEMPLATES)

    def test_notification_worker_tests_exist(self):
        self.assertIn('test_notification_worker.py', TEST_TEMPLATES)

    def test_api_gateway_tests_exist(self):
        self.assertIn('test_api_gateway.py', TEST_TEMPLATES)

    def test_data_validator_tests_exist(self):
        self.assertIn('test_data_validator.py', TEST_TEMPLATES)

    def test_db_migration_tests_exist(self):
        self.assertIn('test_db_migration.py', TEST_TEMPLATES)

    def test_network_policy_tests_exist(self):
        self.assertIn('test_network_policy.py', TEST_TEMPLATES)

    def test_each_template_has_assertions(self):
        """Every test template should have at least one assert."""
        for key, content in TEST_TEMPLATES.items():
            with self.subTest(template=key):
                self.assertIn('assert', content,
                              f"Template {key} has no assertions")


class TestTestGeneratorInit(unittest.TestCase):
    """Test TestGenerator initialization."""

    def test_default_path(self):
        gen = TestGenerator()
        self.assertEqual(gen.target_repo, Path('fixes/paystream'))

    def test_tests_dir_is_under_target(self):
        gen = TestGenerator(target_repo_path='/tmp/test-repo')
        self.assertEqual(gen.tests_dir, Path('/tmp/test-repo/tests'))

    def test_generated_tests_initially_empty(self):
        gen = TestGenerator()
        self.assertEqual(len(gen._generated_tests), 0)


class TestTestGeneratorMapTasksToTests(unittest.TestCase):
    """Test the _map_tasks_to_tests method for all path patterns."""

    def setUp(self):
        self.gen = TestGenerator()

    def test_configmap_maps_to_redis_pool_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                         file_path="configs/payment-processor/configmap.yaml",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_redis_pool.py', result)

    def test_pgbouncer_maps_to_postgres_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                         file_path="configs/postgres/pgbouncer-config.yaml",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_postgres_pool.py', result)

    def test_redis_config_maps_to_redis_config_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                         file_path="configs/redis/redis-config.conf",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_redis_config.py', result)

    def test_notification_worker_maps_to_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.K8S_MANIFEST,
                         file_path="k8s/notification-worker/deployment.yaml",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_notification_worker.py', result)

    def test_kafka_maps_to_notification_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.K8S_MANIFEST,
                         file_path="k8s/notification-worker/deployment.yaml",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_notification_worker.py', result)

    def test_api_gateway_maps_to_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.K8S_MANIFEST,
                         file_path="k8s/api-gateway/deployment.yaml",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_api_gateway.py', result)

    def test_data_validator_maps_to_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.CODE_EDIT,
                         file_path="src/data-service/data_validator.py",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_data_validator.py', result)

    def test_data_service_maps_to_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.CODE_EDIT,
                         file_path="src/data-service/something.py",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_data_validator.py', result)

    def test_migration_maps_to_db_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.FILE_CREATE,
                         file_path="configs/db/migrations/V005__add_payment_indexes.sql",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_db_migration.py', result)

    def test_sql_file_maps_to_db_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.FILE_CREATE,
                         file_path="scripts/db/init.sql",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_db_migration.py', result)

    def test_network_policy_maps_to_network_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.K8S_MANIFEST,
                         file_path="k8s/network-policies/restrict-payment-access.yaml",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_network_policy.py', result)

    def test_restrict_file_maps_to_network_test(self):
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.K8S_MANIFEST,
                         file_path="k8s/network-policies/restrict-traffic.yaml",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_network_policy.py', result)

    def test_multiple_tasks_map_multiple_tests(self):
        """Multiple tasks touching different files should map to multiple tests."""
        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs/payment-processor/configmap.yaml",
                    status=FixStatus.APPLIED),
            FixTask(id="t2", description="", change_type=ChangeType.K8S_MANIFEST,
                    file_path="k8s/api-gateway/deployment.yaml",
                    status=FixStatus.APPLIED),
            FixTask(id="t3", description="", change_type=ChangeType.FILE_CREATE,
                    file_path="configs/db/migrations/V005__add_payment_indexes.sql",
                    status=FixStatus.APPLIED),
        ]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_redis_pool.py', result)
        self.assertIn('test_api_gateway.py', result)
        self.assertIn('test_db_migration.py', result)

    def test_unrecognized_path_returns_empty(self):
        """Tasks with unrecognized file paths should not match any test."""
        tasks = [FixTask(id="t1", description="", change_type=ChangeType.SCRIPT_RUN,
                         file_path="some/unknown/path.sh",
                         status=FixStatus.APPLIED)]
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertEqual(len(result), 0)


class TestTestGeneratorGenerate(unittest.TestCase):
    """Test the generate method that creates test files."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.gen = TestGenerator(target_repo_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_generate_creates_test_file(self):
        """Generate should create a test file in the tests directory."""
        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs/payment-processor/configmap.yaml",
                    status=FixStatus.APPLIED),
        ]
        test_tasks = self.gen.generate(tasks)
        self.assertGreater(len(test_tasks), 0)

        test_path = Path(self.temp_dir) / "tests/test_redis_pool.py"
        self.assertTrue(test_path.exists())
        content = test_path.read_text(encoding='utf-8')
        self.assertIn('def test_', content)

    def test_generate_returns_fix_tasks(self):
        """Generate should return FixTask objects with FILE_CREATE type."""
        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs/payment-processor/configmap.yaml",
                    status=FixStatus.APPLIED),
        ]
        test_tasks = self.gen.generate(tasks)
        for tt in test_tasks:
            self.assertIsInstance(tt, FixTask)
            self.assertEqual(tt.change_type, ChangeType.FILE_CREATE)
            self.assertIn('tests/', tt.file_path)
            self.assertEqual(tt.status, FixStatus.APPLIED)

    def test_generate_skips_existing_test_files(self):
        """Generate should not overwrite existing test files."""
        test_path = Path(self.temp_dir) / "tests/test_redis_pool.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text("# already exists\n", encoding='utf-8')

        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs/payment-processor/configmap.yaml",
                    status=FixStatus.APPLIED),
        ]
        test_tasks = self.gen.generate(tasks)
        # Should still be empty because the file already exists
        content = test_path.read_text(encoding='utf-8')
        self.assertEqual(content, "# already exists\n")

    def test_generate_no_applied_tasks(self):
        """Generate with no applied tasks should return empty list."""
        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configmap.yaml", status=FixStatus.PENDING),
            FixTask(id="t2", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="other.yaml", status=FixStatus.FAILED),
        ]
        test_tasks = self.gen.generate(tasks)
        self.assertEqual(len(test_tasks), 0)

    def test_generate_multiple_test_files(self):
        """Multiple matching tasks should create multiple test files."""
        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs/payment-processor/configmap.yaml",
                    status=FixStatus.APPLIED),
            FixTask(id="t2", description="", change_type=ChangeType.K8S_MANIFEST,
                    file_path="k8s/api-gateway/deployment.yaml",
                    status=FixStatus.APPLIED),
        ]
        test_tasks = self.gen.generate(tasks)
        self.assertGreaterEqual(len(test_tasks), 1)

        test_dir = Path(self.temp_dir) / "tests"
        py_files = list(test_dir.glob("test_*.py"))
        self.assertGreaterEqual(len(py_files), 1)

    def test_generated_tests_list(self):
        """get_generated_tests should return list of generated test paths."""
        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs/payment-processor/configmap.yaml",
                    status=FixStatus.APPLIED),
        ]
        self.gen.generate(tasks)
        gen_tests = self.gen.get_generated_tests()
        self.assertGreater(len(gen_tests), 0)
        for p in gen_tests:
            self.assertTrue(p.endswith('.py'))

    def test_create_tests_dir_if_not_exists(self):
        """Generate should create the tests directory if it doesn't exist."""
        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs/payment-processor/configmap.yaml",
                    status=FixStatus.APPLIED),
        ]
        self.gen.generate(tasks)
        test_dir = Path(self.temp_dir) / "tests"
        self.assertTrue(test_dir.exists())
        self.assertTrue(test_dir.is_dir())


class TestTestGeneratorEdgeCases(unittest.TestCase):
    """Test edge cases for the TestGenerator."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.gen = TestGenerator(target_repo_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_empty_tasks_list(self):
        """Empty tasks list should produce no test tasks."""
        test_tasks = self.gen.generate([])
        self.assertEqual(len(test_tasks), 0)

    def test_tasks_returned_have_correct_priority(self):
        """Generated test tasks should have priority 100."""
        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs/payment-processor/configmap.yaml",
                    status=FixStatus.APPLIED),
        ]
        test_tasks = self.gen.generate(tasks)
        for tt in test_tasks:
            self.assertEqual(tt.priority, 100)

    def test_backslash_paths_handled(self):
        """Windows-style backslash paths should be normalized."""
        tasks = [
            FixTask(id="t1", description="", change_type=ChangeType.CONFIG_EDIT,
                    file_path="configs\\payment-processor\\configmap.yaml",
                    status=FixStatus.APPLIED),
        ]
        # The _map_tasks_to_tests replaces backslashes with forward slashes
        result = self.gen._map_tasks_to_tests(tasks)
        self.assertIn('test_redis_pool.py', result)

    def test_generated_tests_list_empty_before_generate(self):
        """get_generated_tests should return empty list before any generate call."""
        gen_tests = self.gen.get_generated_tests()
        self.assertEqual(len(gen_tests), 0)


if __name__ == '__main__':
    unittest.main()
