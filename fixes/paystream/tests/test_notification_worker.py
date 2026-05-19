"""Validation tests for notification worker fixes."""

import yaml
import os


DEPLOY_PATH = os.path.join(os.path.dirname(__file__), '..', 'k8s', 'notification-worker', 'deployment.yaml')


def test_memory_limit_increased():
    """Memory limit should have been increased to prevent OOMKill."""
    with open(DEPLOY_PATH) as f:
        data = yaml.safe_load(f)

    limits = data['spec']['template']['spec']['containers'][0]['resources']['limits']
    memory = limits.get('memory', '')
    assert memory == '1Gi', f"Memory limit should be 1Gi, got: {memory}"
    print(f"[OK] Memory limit set to {memory}")


def test_replicas_increased():
    """Replica count should have been increased for high throughput."""
    with open(DEPLOY_PATH) as f:
        data = yaml.safe_load(f)

    replicas = data['spec']['replicas']
    assert replicas >= 3, f"Replicas should be >= 3, got: {replicas}"
    print(f"[OK] Replicas increased to {replicas}")
