"""Validation tests for Postgres connection pool fixes."""

import yaml
import os


CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'configs', 'postgres', 'pgbouncer-config.yaml')


def test_max_connections_increased():
    """max_client_conn should have been increased."""
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)

    ini_content = data['data']['pgbouncer.ini']
    assert 'max_client_conn = 300' in ini_content,         f"max_client_conn should be >= 200"
    print("[OK] max_client_conn increased to 300")


def test_pool_leak_fix():
    """Connection pool should have proper release settings."""
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)

    ini_content = data['data']['pgbouncer.ini']
    assert 'idle_timeout' in ini_content, "idle_timeout should be configured"
    print("[OK] Connection pool leak mitigation configured")
