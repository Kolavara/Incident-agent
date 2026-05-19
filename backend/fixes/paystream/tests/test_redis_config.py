"""Validation tests for Redis maxmemory fix."""

import os


CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'configs', 'redis', 'redis-config.conf')


def test_maxmemory_increased():
    """Redis maxmemory should be > 512MB to prevent OOM evictions."""
    with open(CONFIG_PATH) as f:
        content = f.read()

    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('maxmemory') and not line.startswith('maxmemory-policy'):
            size_str = line.split()[1].lower()
            assert 'gb' in size_str, f"maxmemory should be at least 1gb, got: {size_str}"
            print(f"[OK] {line}")
            return

    assert False, "maxmemory setting not found in config"
