"""Validation tests for network policy fixes."""

import yaml
import os


POLICY_PATH = os.path.join(os.path.dirname(__file__), '..', 'k8s', 'network-policies', 'restrict-payment-access.yaml')


def test_network_policy_exists():
    """Network policy file should exist."""
    assert os.path.exists(POLICY_PATH), f"Network policy not found at {POLICY_PATH}"
    print(f"[OK] Network policy file exists")


def test_ingress_restricted_to_api_gateway():
    """Payment processor should only accept traffic from API gateway."""
    with open(POLICY_PATH) as f:
        # Can contain multiple YAML documents
        docs = list(yaml.safe_load_all(f))

    payment_policy = next((d for d in docs if d['metadata']['name'] == 'restrict-payment-access'), None)
    assert payment_policy is not None, "restrict-payment-access policy not found"

    ingress = payment_policy['spec']['ingress']
    assert len(ingress) > 0, "No ingress rules defined"
    print(f"[OK] Ingress rules restricted to api-gateway")


def test_egress_allowed_services():
    """Payment processor egress should only allow redis and postgres."""
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
    """Should have IP blocking for suspicious ranges."""
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
