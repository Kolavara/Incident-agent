"""Unit tests for the TaskGenerator remediation module.

Tests the rule-based pattern matching, LLM fallback generation,
generic task creation, and file inference logic.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.remediation.task_generator import TaskGenerator, FIX_PATTERNS
from src.remediation.models import ChangeType, FixTask


class TestFIX_PATTERNS(unittest.TestCase):
    """Test structure and completeness of FIX_PATTERNS."""

    def test_all_patterns_have_required_fields(self):
        """Every pattern definition must have 'patterns', 'change_type'."""
        for i, p in enumerate(FIX_PATTERNS):
            with self.subTest(pattern_idx=i):
                self.assertIn('patterns', p, f"Pattern {i} missing 'patterns'")
                self.assertIn('change_type', p, f"Pattern {i} missing 'change_type'")
                self.assertIsInstance(p['patterns'], list)
                self.assertGreater(len(p['patterns']), 0,
                                   f"Pattern {i} has empty patterns list")
                self.assertIsInstance(p['change_type'], ChangeType)

    def test_all_file_paths_are_strings(self):
        """If a pattern has file_path, it must be a non-empty string."""
        for i, p in enumerate(FIX_PATTERNS):
            if 'file_path' in p:
                with self.subTest(pattern_idx=i):
                    self.assertIsInstance(p['file_path'], str)
                    self.assertGreater(len(p['file_path']), 0)

    def test_all_change_types_are_valid(self):
        """Every change_type must be a valid ChangeType enum."""
        valid_types = set(ChangeType)
        for i, p in enumerate(FIX_PATTERNS):
            with self.subTest(pattern_idx=i):
                self.assertIn(p['change_type'], valid_types)

    def test_patterns_have_reasonable_coverage(self):
        """Patterns should cover all major fix categories."""
        # Verify we have patterns for each change type
        covered_types = set(p['change_type'] for p in FIX_PATTERNS)
        self.assertIn(ChangeType.CONFIG_EDIT, covered_types)
        self.assertIn(ChangeType.K8S_MANIFEST, covered_types)
        self.assertIn(ChangeType.CODE_EDIT, covered_types)
        self.assertIn(ChangeType.FILE_CREATE, covered_types)
        self.assertIn(ChangeType.SCRIPT_RUN, covered_types)

    def test_certbot_pattern_is_script_run(self):
        """SSL/certbot fix steps should map to SCRIPT_RUN."""
        cert_patterns = [p for p in FIX_PATTERNS
                         if any('cert' in pat.lower() for pat in p['patterns'])]
        for p in cert_patterns:
            self.assertEqual(p['change_type'], ChangeType.SCRIPT_RUN)
            self.assertIn('command', p)
            self.assertTrue('certbot' in p['command'] or 'renew' in p['command'])

    def test_network_policy_patterns_are_k8s(self):
        """Network policy related patterns should use K8S_MANIFEST."""
        net_pol_patterns = [p for p in FIX_PATTERNS
                            if 'network-polic' in p.get('file_path', '').lower()]
        for p in net_pol_patterns:
            self.assertEqual(p['change_type'], ChangeType.K8S_MANIFEST)

    def test_sql_migration_patterns_are_file_create(self):
        """Database migration patterns should use FILE_CREATE."""
        migration_patterns = [p for p in FIX_PATTERNS
                              if 'migration' in p.get('file_path', '').lower()]
        for p in migration_patterns:
            self.assertEqual(p['change_type'], ChangeType.FILE_CREATE)

    def test_python_patterns_are_code_edit(self):
        """Python code fix patterns should use CODE_EDIT."""
        py_patterns = [p for p in FIX_PATTERNS
                       if 'data_validator' in p.get('file_path', '').lower()]
        for p in py_patterns:
            self.assertEqual(p['change_type'], ChangeType.CODE_EDIT)


class TestTaskGeneratorInit(unittest.TestCase):
    """Test TaskGenerator initialization."""

    def test_default_path(self):
        gen = TaskGenerator()
        self.assertEqual(gen.target_repo, Path('fixes/paystream'))

    def test_custom_path(self):
        gen = TaskGenerator(target_repo_path='/tmp/test-repo')
        self.assertEqual(gen.target_repo, Path('/tmp/test-repo'))

    def test_without_llm_client(self):
        gen = TaskGenerator()
        self.assertIsNone(gen._llm_client)


class TestTaskGeneratorMatchPatterns(unittest.TestCase):
    """Test the _match_patterns method with various fix steps."""

    def setUp(self):
        self.gen = TaskGenerator()

    def test_match_connection_pool_size(self):
        """Fix step mentioning pool size should match config edit."""
        tasks = self.gen._match_patterns(
            ["Set CONNECTION_POOL_SIZE=25 in ConfigMap"], "INC-001")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].change_type, ChangeType.CONFIG_EDIT)
        self.assertIn('configmap.yaml', tasks[0].file_path)

    def test_match_redis_maxmemory(self):
        """Fix step mentioning maxmemory increase should match redis config."""
        tasks = self.gen._match_patterns(
            ["Increase maxmemory limit to 1gb"], "INC-002")
        self.assertEqual(len(tasks), 1)
        self.assertIn('redis-config', tasks[0].file_path)

    def test_match_postgres_connection(self):
        """Fix step mentioning Postgres connections should match pgbouncer."""
        tasks = self.gen._match_patterns(
            ["Reduce Postgres max_connections connection leak"], "INC-003")
        self.assertEqual(len(tasks), 1)
        self.assertIn('pgbouncer', tasks[0].file_path)

    def test_match_dns_resolution(self):
        """Fix step about DNS should match SCRIPT_RUN."""
        tasks = self.gen._match_patterns(
            ["Increase CoreDNS replicas for DNS resolution"], "INC-004")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].change_type, ChangeType.SCRIPT_RUN)
        self.assertIn('coredns', tasks[0].command.lower())

    def test_match_ssl_certificate(self):
        """Fix step about SSL should match SCRIPT_RUN with certbot."""
        tasks = self.gen._match_patterns(
            ["Renew SSL certificate for api.paystream.io"], "INC-005")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].change_type, ChangeType.SCRIPT_RUN)

    def test_match_notification_worker_oom(self):
        """Fix step about OOM in worker should match deployment."""
        tasks = self.gen._match_patterns(
            ["Increase memory limit for notification-worker to prevent OOMKill"], "INC-006")
        self.assertEqual(len(tasks), 1)
        self.assertIn('notification-worker', tasks[0].file_path)

    def test_match_api_gateway_timeout(self):
        """Fix step about API gateway timeout should match deployment."""
        tasks = self.gen._match_patterns(
            ["Increase upstream timeout for API gateway"], "INC-007")
        self.assertEqual(len(tasks), 1)
        self.assertIn('api-gateway', tasks[0].file_path)

    def test_match_kafka_consumer_lag(self):
        """Fix step about Kafka lag should match notification-worker replicas."""
        tasks = self.gen._match_patterns(
            ["Scale consumer replicas to reduce Kafka lag"], "INC-008")
        self.assertEqual(len(tasks), 1)
        self.assertIn('notification-worker', tasks[0].file_path)

    def test_match_jwt_token(self):
        """Fix step about JWT should match TokenHandler.java."""
        tasks = self.gen._match_patterns(
            ["Add auto-refresh for JWT tokens"], "INC-009")
        self.assertEqual(len(tasks), 1)
        self.assertIn('TokenHandler.java', tasks[0].file_path)

    def test_match_circuit_breaker(self):
        """Fix step about circuit breaker should match configmap."""
        tasks = self.gen._match_patterns(
            ["Adjust circuit breaker threshold for traffic"], "INC-010")
        self.assertEqual(len(tasks), 1)
        self.assertIn('configmap.yaml', tasks[0].file_path)

    def test_match_ttl_cache_policy(self):
        """Fix step about TTL/expiration policy should match redis config."""
        tasks = self.gen._match_patterns(
            ["Add expiration policy for cache keys"], "INC-011")
        self.assertEqual(len(tasks), 1)
        self.assertIn('redis-config', tasks[0].file_path)

    def test_match_python_code_fix(self):
        """Fix step about Python error handling should match data_validator."""
        tasks = self.gen._match_patterns(
            ["Fix Python error handling in data validator"], "INC-012")
        self.assertEqual(len(tasks), 1)
        self.assertIn('data_validator.py', tasks[0].file_path)
        self.assertEqual(tasks[0].change_type, ChangeType.CODE_EDIT)

    def test_match_sql_migration(self):
        """Fix step about DB migration should match migration file."""
        tasks = self.gen._match_patterns(
            ["Create database migration to add payment indexes"], "INC-013")
        self.assertEqual(len(tasks), 1)
        self.assertIn('migration', tasks[0].file_path.lower())
        self.assertEqual(tasks[0].change_type, ChangeType.FILE_CREATE)

    def test_match_network_policy(self):
        """Fix step about network policy should match network policy file."""
        tasks = self.gen._match_patterns(
            ["Configure network policy to restrict payment access"], "INC-014")
        self.assertEqual(len(tasks), 1)
        self.assertIn('network-polic', tasks[0].file_path.lower())
        self.assertEqual(tasks[0].change_type, ChangeType.K8S_MANIFEST)

    def test_match_connection_leak(self):
        """Fix step about connection leak should match RedisPoolManager."""
        tasks = self.gen._match_patterns(
            ["Fix connection pool leak in payment service"], "INC-015")
        self.assertEqual(len(tasks), 1)
        self.assertIn('RedisPoolManager.java', tasks[0].file_path)

    def test_no_match_returns_empty(self):
        """Completely unknown fix step should return no matches."""
        tasks = self.gen._match_patterns(
            ["Completely unrelated task about installing nginx on bare metal"], "INC-016")
        self.assertEqual(len(tasks), 0)

    def test_multiple_steps_multiple_matches(self):
        """Multiple fix steps that map to different files should produce multiple tasks."""
        steps = [
            "Set CONNECTION_POOL_SIZE=25 in ConfigMap",
            "Renew SSL certificate for api.paystream.io",
        ]
        tasks = self.gen._match_patterns(steps, "INC-017")
        self.assertEqual(len(tasks), 2)
        # Different change types for different steps
        self.assertEqual(tasks[0].change_type, ChangeType.CONFIG_EDIT)
        self.assertIn('configmap.yaml', tasks[0].file_path)
        self.assertEqual(tasks[1].change_type, ChangeType.SCRIPT_RUN)
        self.assertIn('certbot', tasks[1].command)
        # Should have correct IDs
        self.assertEqual(tasks[0].id, "INC-017-task-01")
        self.assertEqual(tasks[1].id, "INC-017-task-02")

    def test_deduplicates_same_file_path(self):
        """Two steps matching same file should only produce one task."""
        steps = [
            "Set CONNECTION_POOL_SIZE=25 in ConfigMap",
            "Update ConfigMap with pool timeout",
        ]
        tasks = self.gen._match_patterns(steps, "INC-018")
        # Both match configmap.yaml, so only one task should be created
        self.assertEqual(len(tasks), 1)

    def test_task_has_correct_description(self):
        """Task description should match the fix step text."""
        step = "Increase maxmemory limit to 2gb in Redis config"
        tasks = self.gen._match_patterns([step], "INC-019")
        self.assertEqual(tasks[0].description, step)

    def test_task_priority_matches_step_order(self):
        """Tasks should have priorities matching step indices."""
        steps = [
            "Set CONNECTION_POOL_SIZE=25 in ConfigMap",
            "Fix connection pool leak in payment service",
        ]
        tasks = self.gen._match_patterns(steps, "INC-020")
        for task in tasks:
            self.assertEqual(task.priority, int(task.id.split('-')[-1]))


class TestTaskGeneratorGenerate(unittest.TestCase):
    """Test the full generate method."""

    def setUp(self):
        self.gen = TaskGenerator()
        # Mock LLM client creation to avoid hanging on API calls
        self._llm_patch = patch.object(
            TaskGenerator, '_get_or_create_llm_client', return_value=None
        )
        self._llm_patch.start()

    def tearDown(self):
        self._llm_patch.stop()

    def test_generate_with_no_fix_steps(self):
        """Empty fix steps should return empty list."""
        result = self.gen.generate({
            'diagnosis': {'fix_steps': []},
            'incident_id': 'INC-001',
            'incident_type': 'KNOWN',
        })
        tasks, branch = result
        self.assertEqual(len(tasks), 0)

    def test_generate_with_missing_diagnosis_key(self):
        """Missing 'diagnosis' key should be handled gracefully."""
        result = self.gen.generate({
            'incident_id': 'INC-001',
        })
        tasks, branch = result
        self.assertEqual(len(tasks), 0)

    def test_generate_returns_branch_name(self):
        """Generate should return a branch name derived from root cause."""
        steps = ["Set CONNECTION_POOL_SIZE=25 in ConfigMap"]
        result = self.gen.generate({
            'diagnosis': {
                'fix_steps': steps,
                'root_cause': 'Redis connection pool exhausted',
            },
            'incident_id': 'INC-001',
            'incident_type': 'KNOWN',
        })
        tasks, branch = result
        self.assertGreater(len(tasks), 0)
        self.assertIn('INC-001', branch)
        self.assertIn('redis', branch.lower())

    def test_generate_fallback_to_generic(self):
        """Unknown fix steps should fall back to generic tasks."""
        result = self.gen.generate({
            'diagnosis': {
                'fix_steps': ['Install and configure monit for process monitoring'],
            },
            'incident_id': 'INC-099',
            'incident_type': 'NOVEL',
        })
        tasks, branch = result
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].change_type, ChangeType.CONFIG_EDIT)

    def test_generate_mixed_matched_and_unmatched(self):
        """A mix of matched and unmatched steps should produce tasks for both."""
        steps = [
            "Set CONNECTION_POOL_SIZE=25 in ConfigMap",
            "Also install and configure monit for process monitoring",
        ]
        result = self.gen.generate({
            'diagnosis': {
                'fix_steps': steps,
                'root_cause': 'Connection pool exhausted',
            },
            'incident_id': 'INC-021',
            'incident_type': 'PARTIAL',
        })
        tasks, branch = result
        # Should have at least 1 (the matched step)
        self.assertGreaterEqual(len(tasks), 1)

    def test_generate_assigns_priorities(self):
        """Tasks should have sequential priorities."""
        steps = [
            "Set CONNECTION_POOL_SIZE=25 in ConfigMap",
            "Fix JWT token refresh",
            "Increase CoreDNS replicas",
        ]
        result = self.gen.generate({
            'diagnosis': {
                'fix_steps': steps,
                'root_cause': 'Multi-service issue',
            },
            'incident_id': 'INC-022',
            'incident_type': 'KNOWN',
        })
        tasks, branch = result
        for i, task in enumerate(tasks):
            self.assertEqual(task.priority, i + 1)


class TestTaskGeneratorInferFilePath(unittest.TestCase):
    """Test the _infer_file_path method."""

    def setUp(self):
        self.gen = TaskGenerator()

    def test_infer_redis(self):
        path = self.gen._infer_file_path("Fix Redis connection pool")
        self.assertIn('configmap.yaml', path)

    def test_infer_postgres(self):
        path = self.gen._infer_file_path("Postgres database max connections")
        self.assertIn('pgbouncer', path)

    def test_infer_oom(self):
        path = self.gen._infer_file_path("OOM in notification worker")
        self.assertIn('notification-worker', path)

    def test_infer_gateway(self):
        path = self.gen._infer_file_path("API gateway upstream timeout")
        self.assertIn('api-gateway', path)

    def test_infer_dns(self):
        path = self.gen._infer_file_path("DNS resolution failure in CoreDNS")
        self.assertIn('coredns', path)

    def test_infer_kafka(self):
        path = self.gen._infer_file_path("Kafka consumer lag notification")
        self.assertIn('notification-worker', path)

    def test_infer_certificate(self):
        path = self.gen._infer_file_path("SSL certificate renewal")
        self.assertIn('cert', path)

    def test_infer_jwt(self):
        path = self.gen._infer_file_path("JWT token auth refresh")
        self.assertIn('TokenHandler', path)

    def test_infer_no_match_returns_empty(self):
        path = self.gen._infer_file_path("Something completely random")
        self.assertEqual(path, '')


class TestTaskGeneratorCreateGenericTasks(unittest.TestCase):
    """Test fallback generic task creation."""

    def setUp(self):
        self.gen = TaskGenerator()

    def test_creates_correct_number_of_tasks(self):
        tasks = self.gen._create_generic_tasks(
            ["Fix step 1", "Fix step 2", "Fix step 3"], "INC-100")
        self.assertEqual(len(tasks), 3)

    def test_generic_tasks_are_config_edit(self):
        tasks = self.gen._create_generic_tasks(["Fix stuff"], "INC-101")
        self.assertEqual(tasks[0].change_type, ChangeType.CONFIG_EDIT)

    def test_generic_tasks_have_descriptions(self):
        description = "Install and configure rate limiting"
        tasks = self.gen._create_generic_tasks([description], "INC-102")
        self.assertEqual(tasks[0].description, description)


class TestTaskGeneratorLLMFallback(unittest.TestCase):
    """Test LLM-based task generation fallback (mocked)."""

    def setUp(self):
        self.gen = TaskGenerator()

    @patch('src.remediation.task_generator.ModelRouter')
    def test_llm_fallback_returns_empty_when_no_client(self, mock_router):
        """When LLM client cannot be created, LLM fallback returns empty list."""
        mock_router.side_effect = Exception("No API keys")
        result = self.gen._generate_with_llm(
            ["Fix unknown issue"], {}, "", "INC-200", "fix/INC-200-unknown"
        )
        self.assertEqual(len(result), 0)

    @patch('src.remediation.task_generator.ModelRouter')
    def test_llm_client_created_lazily(self, mock_router):
        """LLM client should be created on first use."""
        mock_client = MagicMock()
        mock_router_instance = MagicMock()
        mock_router_instance.route.return_value = (mock_client, "model", "cheap")
        mock_router.return_value = mock_router_instance

        client = self.gen._get_or_create_llm_client()
        self.assertIsNotNone(client)
        self.assertIsNotNone(self.gen._llm_client)

    def test_describe_repo_structure_without_path(self):
        """When repo doesn't exist, should return placeholder."""
        gen = TaskGenerator(target_repo_path="/nonexistent/path")
        result = gen._describe_repo_structure()
        self.assertIn("not yet created", result)


class TestTaskGeneratorEdgeCases(unittest.TestCase):
    """Test edge cases for TaskGenerator."""

    def setUp(self):
        self.gen = TaskGenerator()

    def test_empty_fix_steps_list(self):
        """An empty list of fix steps should return empty tasks."""
        tasks = self.gen._match_patterns([], "INC-300")
        self.assertEqual(len(tasks), 0)

    def test_case_insensitive_matching(self):
        """Pattern matching should be case-insensitive."""
        tasks_lower = self.gen._match_patterns(
            ["increase connection pool size"], "INC-301")
        tasks_upper = self.gen._match_patterns(
            ["INCREASE CONNECTION POOL SIZE"], "INC-301")
        tasks_mixed = self.gen._match_patterns(
            ["IncreAse ConneCTION Pool Size"], "INC-301")

        self.assertEqual(len(tasks_lower), 1)
        self.assertEqual(len(tasks_upper), 1)
        self.assertEqual(len(tasks_mixed), 1)
        self.assertEqual(tasks_lower[0].file_path, tasks_upper[0].file_path)

    def test_whitespace_in_fix_steps(self):
        """Fix steps with leading/trailing whitespace should still match."""
        tasks = self.gen._match_patterns(
            ["   Set CONNECTION_POOL_SIZE=25 in ConfigMap   "], "INC-302")
        self.assertEqual(len(tasks), 1)

    def test_different_incident_ids(self):
        """Different incident IDs should produce different task IDs."""
        tasks_a = self.gen._match_patterns(
            ["Set CONNECTION_POOL_SIZE=25 in ConfigMap"], "INC-A")
        tasks_b = self.gen._match_patterns(
            ["Set CONNECTION_POOL_SIZE=25 in ConfigMap"], "INC-B")
        self.assertNotEqual(tasks_a[0].id, tasks_b[0].id)
        self.assertIn('INC-A', tasks_a[0].id)
        self.assertIn('INC-B', tasks_b[0].id)


if __name__ == '__main__':
    unittest.main()
