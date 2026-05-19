"""Data validation service for PayStream payment processing.

Validates incoming payment data before it reaches the core payment pipeline.
Runs as a sidecar in the payment-processor-v2 pod.
"""

import json
import re
import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("paystream.data_validator")


class ValidationSeverity(Enum):
    """Severity level of a validation failure."""
    BLOCK = "block"        # Block the transaction
    WARN = "warn"          # Allow but log warning
    FLAG = "flag"          # Flag for manual review


@dataclass
class ValidationRule:
    """A single validation rule configuration."""
    field: str
    pattern: str
    severity: ValidationSeverity
    message: str
    enabled: bool = True


@dataclass
class ValidationResult:
    """Result of validating a single payment request."""
    is_valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    flags: list = field(default_factory=list)


class DataValidator:
    """Validates incoming payment data against configured rules.

    Known issue: Missing input sanitization on string fields
    can lead to injection-style attacks via the merchant_name field.
    """

    def __init__(self, rules_file: Optional[str] = None):
        self.rules: list[ValidationRule] = []
        if rules_file:
            self._load_rules(rules_file)
        else:
            self._init_default_rules()

    def _init_default_rules(self):
        """Initialize default validation rules."""
        self.rules = [
            ValidationRule(
                field="amount",
                pattern=r"^\d+(\.\d{1,2})?$",
                severity=ValidationSeverity.BLOCK,
                message="Amount must be a valid decimal with up to 2 decimal places",
            ),
            ValidationRule(
                field="currency",
                pattern=r"^(USD|EUR|GBP|CAD|AUD|JPY)$",
                severity=ValidationSeverity.BLOCK,
                message="Currency must be a supported ISO code",
            ),
            ValidationRule(
                field="merchant_id",
                pattern=r"^[A-Z0-9]{8,16}$",
                severity=ValidationSeverity.BLOCK,
                message="Merchant ID must be 8-16 alphanumeric characters",
            ),
            ValidationRule(
                field="merchant_name",
                pattern=r"^.{1,255}$",
                severity=ValidationSeverity.FLAG,
                message="Merchant name length is valid",
            ),
            ValidationRule(
                field="callback_url",
                pattern=r"^https://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$",
                severity=ValidationSeverity.WARN,
                message="Callback URL should use HTTPS",
            ),
        ]

    def _load_rules(self, rules_file: str) -> None:
        """Load validation rules from a JSON file."""
        try:
            with open(rules_file, "r") as f:
                data = json.load(f)
            for rule_data in data.get("rules", []):
                self.rules.append(ValidationRule(
                    field=rule_data["field"],
                    pattern=rule_data["pattern"],
                    severity=ValidationSeverity(rule_data["severity"]),
                    message=rule_data["message"],
                    enabled=rule_data.get("enabled", True),
                ))
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Could not load rules file: {e}. Using defaults.")
            self._init_default_rules()

    def validate_payment(self, payment_data: Dict[str, Any]) -> ValidationResult:
        """Validate a payment request against all enabled rules.

        FIXME: Missing input sanitization - merchant_name and callback_url
        are not sanitized before validation, allowing potential injection
        through specially crafted strings.

        Args:
            payment_data: The payment request payload

        Returns:
            ValidationResult with any errors, warnings, or flags
        """
        result = ValidationResult(is_valid=True)

        for rule in self.rules:
            if not rule.enabled:
                continue

            value = payment_data.get(rule.field, "")

            # FIXME: No sanitization before pattern matching
            # Should call _sanitize_input(value) here
            if not re.match(rule.pattern, str(value)):
                error_msg = f"{rule.field}: {rule.message} (got: {value})"

                if rule.severity == ValidationSeverity.BLOCK:
                    result.errors.append(error_msg)
                    result.is_valid = False
                elif rule.severity == ValidationSeverity.WARN:
                    result.warnings.append(error_msg)
                elif rule.severity == ValidationSeverity.FLAG:
                    result.flags.append(error_msg)

        return result

    def _sanitize_input(self, value: str) -> str:
        """Sanitize input to prevent injection attacks.

        TODO: Implement proper sanitization:
        - Escape HTML entities
        - Strip control characters
        - Limit length
        - Reject known malicious patterns
        """
        # Placeholder — no actual sanitization implemented yet
        return value

    def log_validation_failure(self, result: ValidationResult,
                                payment_id: str) -> None:
        """Log validation failures with structured context.

        FIXME: This method has no exception handling. If logging fails
        (e.g., log disk full, network issue), the error propagates up
        unhandled and can crash the validation pipeline.
        """
        context = {
            "payment_id": payment_id,
            "errors": result.errors,
            "warnings": result.warnings,
            "flags": result.flags,
        }
        if result.errors:
            logger.error(f"Validation failed: {json.dumps(context)}")
        elif result.warnings:
            logger.warning(f"Validation warning: {json.dumps(context)}")
        elif result.flags:
            logger.info(f"Validation flags: {json.dumps(context)}")
        else:
            logger.info(f"Validation passed: {payment_id}")


def create_validator(rules_file: Optional[str] = None) -> DataValidator:
    """Factory function to create a configured DataValidator.

    FIXME: No input validation on rules_file parameter.
    If an invalid path is provided, the error is silently swallowed
    and defaults are used instead.
    """
    return DataValidator(rules_file)
