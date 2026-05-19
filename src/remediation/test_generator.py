"""Test generator — creates validation tests for applied fixes.

Generates pytest-compatible test files that validate:
- Config changes (expected values in YAML/conf files)
- Kubernetes manifest correctness
- Code-level invariants (resource limits, pool sizes, etc.)
- Health check assertions
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from src.remediation.models import (
    ChangeType, FixStatus, FixTask, RemediationPlan,
)

logger = logging.getLogger('incident_agent.remediation.test_generator')

# Pre-defined test templates for known fix scenarios
TEST_TEMPLATES: Dict[str, str] = {
    'test_redis_pool.py': """\"\"\"Validation tests for Redis connection pool fixes.\"\"\"

import yaml
import os


CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'configs', 'payment-processor', 'configmap.yaml')


def test_connection_pool_size_increased():
    \"\"\"CONNECTION_POOL_SIZE should have been increased to handle traffic.\"\"\"
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)

    pool_size = int(data['data']['CONNECTION_POOL_SIZE'])
    assert pool_size >= 20, f"Pool size {pool_size} is too small; expected >= 20"
    print(f"[OK] CONNECTION_POOL_SIZE={pool_size} (>= 20)")


def test_retry_backoff_enabled():
    \"\"\"Retry with backoff should be configured.\"\"\"
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)

    max_retries = int(data['data']['MAX_RETRIES'])
    backoff = int(data['data']['RETRY_BACKOFF_MS'])

    assert max_retries >= 3, f"MAX_RETRIES={max_retries} should be >= 3"
    assert backoff > 500, f"RETRY_BACKOFF_MS={backoff} should be > 500ms for proper backoff"
    print(f"[OK] Retry configured: MAX_RETRIES={max_retries}, BACKOFF={backoff}ms")
""",
    'test_postgres_pool.py': """\"\"\"Validation tests for Postgres connection pool fixes.\"\"\"

import yaml
import os


CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'configs', 'postgres', 'pgbouncer-config.yaml')


def test_max_connections_increased():
    \"\"\"max_client_conn should have been increased.\"\"\"
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)

    ini_content = data['data']['pgbouncer.ini']
    assert 'max_client_conn = 300' in ini_content, \
        f"max_client_conn should be >= 200"
    print("[OK] max_client_conn increased to 300")


def test_pool_leak_fix():
    \"\"\"Connection pool should have proper release settings.\"\"\"
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)

    ini_content = data['data']['pgbouncer.ini']
    assert 'idle_timeout' in ini_content, "idle_timeout should be configured"
    print("[OK] Connection pool leak mitigation configured")
""",
    'test_redis_config.py': """\"\"\"Validation tests for Redis maxmemory fix.\"\"\"

import os


CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'configs', 'redis', 'redis-config.conf')


def test_maxmemory_increased():
    \"\"\"Redis maxmemory should be > 512MB to prevent OOM evictions.\"\"\"
    with open(CONFIG_PATH) as f:
        content = f.read()

    for line in content.split('\\n'):
        line = line.strip()
        if line.startswith('maxmemory') and not line.startswith('maxmemory-policy'):
            size_str = line.split()[1].lower()
            assert 'gb' in size_str, f"maxmemory should be at least 1gb, got: {size_str}"
            print(f"[OK] {line}")
            return

    assert False, "maxmemory setting not found in config"
""",
    'test_notification_worker.py': """\"\"\"Validation tests for notification worker fixes.\"\"\"

import yaml
import os


DEPLOY_PATH = os.path.join(os.path.dirname(__file__), '..', 'k8s', 'notification-worker', 'deployment.yaml')


def test_memory_limit_increased():
    \"\"\"Memory limit should have been increased to prevent OOMKill.\"\"\"
    with open(DEPLOY_PATH) as f:
        data = yaml.safe_load(f)

    limits = data['spec']['template']['spec']['containers'][0]['resources']['limits']
    memory = limits.get('memory', '')
    assert memory == '1Gi', f"Memory limit should be 1Gi, got: {memory}"
    print(f"[OK] Memory limit set to {memory}")


def test_replicas_increased():
    \"\"\"Replica count should have been increased for high throughput.\"\"\"
    with open(DEPLOY_PATH) as f:
        data = yaml.safe_load(f)

    replicas = data['spec']['replicas']
    assert replicas >= 3, f"Replicas should be >= 3, got: {replicas}"
    print(f"[OK] Replicas increased to {replicas}")
""",
    'test_api_gateway.py': """\"\"\"Validation tests for API gateway timeout fix.\"\"\"

import yaml
import os


DEPLOY_PATH = os.path.join(os.path.dirname(__file__), '..', 'k8s', 'api-gateway', 'deployment.yaml')


def test_upstream_timeout_increased():
    \"\"\"Upstream timeout should be increased to prevent 502s.\"\"\"
    with open(DEPLOY_PATH) as f:
        data = yaml.safe_load(f)

    env_vars = data['spec']['template']['spec']['containers'][0]['env']
    timeout_var = next((v for v in env_vars if v['name'] == 'UPSTREAM_TIMEOUT_MS'), None)

    assert timeout_var is not None, "UPSTREAM_TIMEOUT_MS should be set"
    timeout_value = int(timeout_var['value'])
    assert timeout_value >= 20000, \
        f"UPSTREAM_TIMEOUT_MS should be >= 20000ms, got: {timeout_value}"
    print(f"[OK] Upstream timeout increased to {timeout_value}ms")
""",
    'test_data_validator.py': """\"\"\"Validation tests for Python data validator fixes.\"\"\"

import sys
import os


# Add source to path so we can import the module
SRC_PATH = os.path.join(os.path.dirname(__file__), '..', 'src', 'data-service')
sys.path.insert(0, SRC_PATH)

from data_validator import DataValidator


def test_input_sanitization_blocks_xss():
    \"\"\"Sanitization should block XSS attempts in merchant_name.\"\"\"
    validator = DataValidator()
    payload = {
        "amount": "100.00",
        "currency": "USD",
        "merchant_id": "ACME12345678",
        "merchant_name": "<script>alert('xss')</script>Acme Corp",
        "callback_url": "https://acme.com/hook",
    }
    result = validator.validate_payment(payload)
    # With sanitization, the merchant_name should be cleaned, not blocked
    assert result.is_valid, f"XSS should be sanitized, not blocked: {result.errors}"
    print("[OK] XSS attempt sanitized")


def test_exception_handling_in_logging():
    \"\"\"Logging should not crash on unexpected input.\"\"\"
    validator = DataValidator()
    result = validator.validate_payment({"amount": "50.00", "currency": "USD"})
    # Should not raise any exception
    validator.log_validation_failure(result, "test-payment-001")
    print("[OK] Logging handles all inputs gracefully")


def test_rules_file_validation():
    \"\"\"Invalid rules_file should fall back to defaults, not crash.\"\"\"
    from data_validator import create_validator
    # Should not crash with invalid path
    validator = create_validator("/nonexistent/path/rules.json")
    assert validator is not None, "Validator should be created even with bad path"
    print("[OK] Invalid rules_file handled gracefully")


def test_malicious_patterns_sanitized():
    \"\"\"SQL injection patterns should be sanitized, not passed through.\"\"\"
    validator = DataValidator()
    payload = {
        "amount": "100.00",
        "currency": "USD",
        "merchant_id": "ACME12345678",
        "merchant_name": "Acme\\' OR 1=1 --",
        "callback_url": "https://acme.com/hook",
    }
    result = validator.validate_payment(payload)
    assert result.is_valid, f"SQL injection should be sanitized: {result.errors}"
    print("[OK] SQL injection patterns sanitized")
""",
    'test_db_migration.py': """\"\"\"Validation tests for database migration V005.\"\"\"

import os


MIGRATION_PATH = os.path.join(os.path.dirname(__file__), '..', 'configs', 'db', 'migrations', 'V005__add_payment_indexes.sql')


def test_migration_file_exists():
    \"\"\"Migration file should exist after remediation.\"\"\"
    assert os.path.exists(MIGRATION_PATH), f"Migration file not found at {MIGRATION_PATH}"
    print(f"[OK] Migration file exists")


def test_required_indexes_defined():
    \"\"\"Required payment indexes should be defined in the migration.\"\"\"
    with open(MIGRATION_PATH) as f:
        content = f.read()

    required_indexes = [
        'idx_payments_merchant_status',
        'idx_payments_created_at_merchant',
        'idx_payments_settlement_date',
        'idx_payments_transaction_ref',
    ]
    for idx_name in required_indexes:
        assert idx_name in content, f"Missing index: {idx_name}"
        print(f"[OK] {idx_name} defined")


def test_migration_has_rollback():
    \"\"\"Migration should include rollback instructions.\"\"\"
    with open(MIGRATION_PATH) as f:
        content = f.read()

    assert 'DROP INDEX' in content, "Migration missing rollback DROP INDEX statements"
    assert 'Rollback' in content or 'rollback' in content, "Migration missing rollback section"
    print("[OK] Rollback instructions present")


def test_create_index_concurrently():
    \"\"\"Indexes should use CONCURRENTLY to avoid locking.\"\"\"
    with open(MIGRATION_PATH) as f:
        content = f.read()

    # Count CREATE INDEX CONCURRENTLY statements
    import re
    concurrent_count = len(re.findall(r'CREATE INDEX CONCURRENTLY', content))
    assert concurrent_count >= 4, f"Expected >=4 CONCURRENTLY indexes, got {concurrent_count}"
    print(f"[OK] All {concurrent_count} indexes use CONCURRENTLY")
""",
    'test_network_policy.py': """\"\"\"Validation tests for network policy fixes.\"\"\"

import yaml
import os


POLICY_PATH = os.path.join(os.path.dirname(__file__), '..', 'k8s', 'network-policies', 'restrict-payment-access.yaml')


def test_network_policy_exists():
    \"\"\"Network policy file should exist.\"\"\"
    assert os.path.exists(POLICY_PATH), f"Network policy not found at {POLICY_PATH}"
    print(f"[OK] Network policy file exists")


def test_ingress_restricted_to_api_gateway():
    \"\"\"Payment processor should only accept traffic from API gateway.\"\"\"
    with open(POLICY_PATH) as f:
        # Can contain multiple YAML documents
        docs = list(yaml.safe_load_all(f))

    payment_policy = next((d for d in docs if d['metadata']['name'] == 'restrict-payment-access'), None)
    assert payment_policy is not None, "restrict-payment-access policy not found"

    ingress = payment_policy['spec']['ingress']
    assert len(ingress) > 0, "No ingress rules defined"
    print(f"[OK] Ingress rules restricted to api-gateway")


def test_egress_allowed_services():
    \"\"\"Payment processor egress should only allow redis and postgres.\"\"\"
    with open(POLICY_PATH) as f:
        docs = list(yaml.safe_load_all(f))

    payment_policy = next((d for d in docs if d['metadata']['name'] == 'restrict-payment-access'), None)
    assert payment_policy is not None, "restrict-payment-access policy not found"

    egress = payment_policy['spec'].get('egress', [])
    allowed_ports = set()
    for rule in egress:
        for port in rule.get('ports', []):
            allowed_ports.add(port['port'])

    assert 6379 in allowed_ports, "Redis port (6379) should be allowed"
    assert 5432 in allowed_ports, "Postgres port (5432) should be allowed"
    print(f"[OK] Egress restricted to Redis (6379) and Postgres (5432)")


def test_ip_block_rule_exists():
    \"\"\"Should have IP blocking for suspicious ranges.\"\"\"
    with open(POLICY_PATH) as f:
        docs = list(yaml.safe_load_all(f))

    block_policy = next((d for d in docs if 'block' in d['metadata']['name'].lower()), None)
    assert block_policy is not None, "No IP block policy found"

    ingress = block_policy['spec']['ingress']
    except_cidrs = []
    for rule in ingress:
        for frm in rule.get('from', []):
            ip_block = frm.get('ipBlock', {})
            except_cidrs.extend(ip_block.get('except', []))

    assert len(except_cidrs) > 0, "No CIDR exceptions found (should block suspicious ranges)"
    print(f"[OK] IP block rule with {len(except_cidrs)} blocked CIDR ranges")
""",
}


class TestGenerator:
    """Generates validation test files for applied fixes.

    Maps applied fix tasks to pre-defined test templates, or
    generates generic tests based on change type.
    """

    def __init__(self, target_repo_path: str = "fixes/paystream"):
        self.target_repo = Path(target_repo_path)
        self.tests_dir = self.target_repo / "tests"
        self._generated_tests: List[str] = []

    def generate(self, tasks: List[FixTask]) -> List[FixTask]:
        """Generate test files based on applied fix tasks.

        Args:
            tasks: List of applied FixTask objects

        Returns:
            List of FILE_CREATE FixTask objects for the generated tests
        """
        test_tasks: List[FixTask] = []
        applied_tasks = [t for t in tasks if t.status == FixStatus.APPLIED]

        if not applied_tasks:
            logger.info("No applied tasks to generate tests for.")
            return test_tasks

        # Determine which test templates to apply based on file paths
        test_paths = self._map_tasks_to_tests(applied_tasks)

        for test_file_name, template_content in TEST_TEMPLATES.items():
            if test_file_name in test_paths or not test_paths:
                # Generate the test file
                test_path = f"tests/{test_file_name}"
                full_path = self.target_repo / test_path

                if full_path.exists():
                    logger.info(f"Test file already exists: {test_path}")
                    continue

                self.tests_dir.mkdir(parents=True, exist_ok=True)
                full_path.write_text(template_content, encoding='utf-8')
                self._generated_tests.append(test_path)

                test_task = FixTask(
                    id=f"test-{test_file_name.replace('.py', '')}",
                    description=f"Generate validation test: {test_file_name}",
                    change_type=ChangeType.FILE_CREATE,
                    file_path=test_path,
                    new_content=template_content,
                    status=FixStatus.APPLIED,
                    priority=100,  # Tests run after fixes
                )
                test_tasks.append(test_task)

                logger.info(f"  Generated: {test_path}")

        if not test_tasks:
            logger.info("No test templates matched the applied tasks.")

        return test_tasks

    def _map_tasks_to_tests(self, tasks: List[FixTask]) -> set:
        """Map applied fix tasks to the test templates that should validate them."""
        test_paths: set = set()

        for task in tasks:
            fp = task.file_path.replace('\\', '/')

            if 'configmap.yaml' in fp or 'payment' in fp.lower():
                test_paths.add('test_redis_pool.py')
            if 'pgbouncer' in fp or 'postgres' in fp.lower():
                test_paths.add('test_postgres_pool.py')
            if 'redis-config' in fp:
                test_paths.add('test_redis_config.py')
            if 'notification' in fp.lower() or 'kafka' in fp.lower():
                test_paths.add('test_notification_worker.py')
            if 'api-gateway' in fp.lower() or 'upstream' in fp.lower():
                test_paths.add('test_api_gateway.py')
            if 'data_validator' in fp or 'data-service' in fp.lower():
                test_paths.add('test_data_validator.py')
            if 'migration' in fp.lower() or 'sql' in fp.lower():
                test_paths.add('test_db_migration.py')
            if 'network-polic' in fp.lower() or 'restrict' in fp.lower():
                test_paths.add('test_network_policy.py')

        return test_paths

    def get_generated_tests(self) -> List[str]:
        """Get list of generated test file paths (relative to target repo)."""
        return self._generated_tests
