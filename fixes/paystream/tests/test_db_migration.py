"""Validation tests for database migration V005."""

import os


MIGRATION_PATH = os.path.join(os.path.dirname(__file__), '..', 'configs', 'db', 'migrations', 'V005__add_payment_indexes.sql')


def test_migration_file_exists():
    """Migration file should exist after remediation."""
    assert os.path.exists(MIGRATION_PATH), f"Migration file not found at {MIGRATION_PATH}"
    print(f"[OK] Migration file exists")


def test_required_indexes_defined():
    """Required payment indexes should be defined in the migration."""
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
    """Migration should include rollback instructions."""
    with open(MIGRATION_PATH) as f:
        content = f.read()

    assert 'DROP INDEX' in content, "Migration missing rollback DROP INDEX statements"
    assert 'Rollback' in content or 'rollback' in content, "Migration missing rollback section"
    print("[OK] Rollback instructions present")


def test_create_index_concurrently():
    """Indexes should use CONCURRENTLY to avoid locking."""
    with open(MIGRATION_PATH) as f:
        content = f.read()

    # Count CREATE INDEX CONCURRENTLY statements
    import re
    concurrent_count = len(re.findall(r'CREATE INDEX CONCURRENTLY', content))
    assert concurrent_count >= 4, f"Expected >=4 CONCURRENTLY indexes, got {concurrent_count}"
    print(f"[OK] All {concurrent_count} indexes use CONCURRENTLY")
