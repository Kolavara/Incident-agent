"""Validation tests for Redis connection pool fixes."""

import yaml
import os


CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'configs', 'payment-processor', 'configmap.yaml')


def test_connection_pool_size_increased():
    """CONNECTION_POOL_SIZE should have been increased to handle traffic."""
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)

    pool_size = int(data['data']['CONNECTION_POOL_SIZE'])
    assert pool_size >= 20, f"Pool size {pool_size} is too small; expected >= 20"
    print(f"[OK] CONNECTION_POOL_SIZE={pool_size} (>= 20)")


def test_retry_backoff_enabled():
    """Retry with backoff should be configured."""
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)

    max_retries = int(data['data']['MAX_RETRIES'])
    backoff = int(data['data']['RETRY_BACKOFF_MS'])

    assert max_retries >= 3, f"MAX_RETRIES={max_retries} should be >= 3"
    assert backoff > 500, f"RETRY_BACKOFF_MS={backoff} should be > 500ms for proper backoff"
    print(f"[OK] Retry configured: MAX_RETRIES={max_retries}, BACKOFF={backoff}ms")
