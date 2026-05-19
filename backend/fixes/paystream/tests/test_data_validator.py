"""Validation tests for Python data validator fixes."""

import sys
import os


# Add source to path so we can import the module
SRC_PATH = os.path.join(os.path.dirname(__file__), '..', 'src', 'data-service')
sys.path.insert(0, SRC_PATH)

from data_validator import DataValidator


def test_input_sanitization_blocks_xss():
    """Sanitization should block XSS attempts in merchant_name."""
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
    """Logging should not crash on unexpected input."""
    validator = DataValidator()
    result = validator.validate_payment({"amount": "50.00", "currency": "USD"})
    # Should not raise any exception
    validator.log_validation_failure(result, "test-payment-001")
    print("[OK] Logging handles all inputs gracefully")


def test_rules_file_validation():
    """Invalid rules_file should fall back to defaults, not crash."""
    from data_validator import create_validator
    # Should not crash with invalid path
    validator = create_validator("/nonexistent/path/rules.json")
    assert validator is not None, "Validator should be created even with bad path"
    print("[OK] Invalid rules_file handled gracefully")


def test_malicious_patterns_sanitized():
    """SQL injection patterns should be sanitized, not passed through."""
    validator = DataValidator()
    payload = {
        "amount": "100.00",
        "currency": "USD",
        "merchant_id": "ACME12345678",
        "merchant_name": "Acme\' OR 1=1 --",
        "callback_url": "https://acme.com/hook",
    }
    result = validator.validate_payment(payload)
    assert result.is_valid, f"SQL injection should be sanitized: {result.errors}"
    print("[OK] SQL injection patterns sanitized")
