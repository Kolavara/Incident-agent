"""Validation tests for API gateway timeout fix."""

import yaml
import os


DEPLOY_PATH = os.path.join(os.path.dirname(__file__), '..', 'k8s', 'api-gateway', 'deployment.yaml')


def test_upstream_timeout_increased():
    """Upstream timeout should be increased to prevent 502s."""
    with open(DEPLOY_PATH) as f:
        data = yaml.safe_load(f)

    env_vars = data['spec']['template']['spec']['containers'][0]['env']
    timeout_var = next((v for v in env_vars if v['name'] == 'UPSTREAM_TIMEOUT_MS'), None)

    assert timeout_var is not None, "UPSTREAM_TIMEOUT_MS should be set"
    timeout_value = int(timeout_var['value'])
    assert timeout_value >= 20000,         f"UPSTREAM_TIMEOUT_MS should be >= 20000ms, got: {timeout_value}"
    print(f"[OK] Upstream timeout increased to {timeout_value}ms")
