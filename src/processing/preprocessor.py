"""Error log preprocessing module.

Cleans and normalizes raw error logs into structured dicts.
Strips timestamps, normalizes whitespace, and extracts key fields.
"""

import re
from typing import Dict, Optional


class LogPreprocessor:
    """Preprocesses raw error logs into clean, structured data."""

    TIMESTAMP_PATTERNS = [
        r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?',
        r'[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4}',
        r'\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2}',
        r'\d{10}(?:\.\d+)?',  # Unix timestamps
    ]

    SERVICE_PATTERNS = {
        'payment': r'(?:payment|payroll|payout|billing|invoice)',
        'auth': r'(?:auth|login|token|jwt|password)',
        'redis': r'(?:redis|cache|session)',
        'postgres': r'(?:postgres|postgresql|psql|database|db)',
        'api': r'(?:api[-\s]?gateway|nginx|haproxy|traefik)',
        'notification': r'(?:notification|notify|email|sms|push)',
        'ml': r'(?:ml[-\s]?model|inference|fraud[-\s]?detection|prediction)',
        'kubernetes': r'(?:kube|pod|container|oomkill|crashloop)',
        'dns': r'(?:dns|resolve|nameserver)',
        'queue': r'(?:queue|kafka|rabbitmq|message[-\s]?broker|consumer)',
    }

    ERROR_TYPE_PATTERNS = {
        'connection_pool_exhausted': r'(?:connection pool exhausted|max pool|pool timeout)',
        'max_connections': r'(?:max connections|too many connections|connection limit)',
        'oom_killed': r'(?:OOMKill|out of memory|memory limit|oom)',
        'timeout': r'(?:timeout|timed out|time out|deadline exceeded|504|502)',
        'ssl_error': r'(?:SSL|TLS|certificate expired|certificate error)',
        'disk_full': r'(?:disk space|no space left|disk utilization|97%|98%|99%)',
        'jwt_error': r'(?:JWT|token invalid|token expired|token validation)',
        'dns_error': r'(?:DNS|name resolution|could not resolve|NXDOMAIN)',
        'queue_lag': r'(?:consumer lag|queue depth|backlog|message lag)',
        'inference_timeout': r'(?:inference timeout|model timeout|prediction timeout)',
    }

    # Error codes to look for
    ERROR_CODE_PATTERN = re.compile(r'(?:ERROR|ERR|error|err)\s*[:#]?\s*([A-Z]\d{3,6}|[A-Z_]+\d*)', re.IGNORECASE)

    def clean_log(self, raw_log: str) -> str:
        """Clean and normalize a raw error log string."""
        if not raw_log or not raw_log.strip():
            raise ValueError("Empty or too-short input log")

        # Strip timestamps
        cleaned = raw_log
        for pattern in self.TIMESTAMP_PATTERNS:
            cleaned = re.sub(pattern, '', cleaned)

        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Remove leading/trailing special chars
        cleaned = re.sub(r'^[^\w\[{]+\s*', '', cleaned)
        cleaned = re.sub(r'\s*[^\w\]}]+$', '', cleaned)

        return cleaned

    def extract_fields(self, raw_log: str) -> Dict[str, Optional[str]]:
        """Extract structured fields from a raw error log."""
        fields: Dict[str, Optional[str]] = {
            'service': self._extract_service(raw_log),
            'error_type': self._extract_error_type(raw_log),
            'error_code': self._extract_error_code(raw_log),
            'host': self._extract_host(raw_log),
        }
        return fields

    def preprocess(self, raw_log: str) -> Dict[str, any]:
        """Full preprocessing: clean log and extract structured fields."""
        cleaned = self.clean_log(raw_log)
        fields = self.extract_fields(raw_log)

        return {
            'cleaned_log': cleaned,
            'service': fields.get('service'),
            'error_type': fields.get('error_type'),
            'error_code': fields.get('error_code'),
            'host': fields.get('host'),
        }

    def _extract_service(self, log: str) -> Optional[str]:
        """Try to identify the service from the log text."""
        log_lower = log.lower()
        for service, pattern in self.SERVICE_PATTERNS.items():
            if re.search(pattern, log_lower):
                return service
        return None

    def _extract_error_type(self, log: str) -> Optional[str]:
        """Try to classify the error type from the log text."""
        log_lower = log.lower()
        for error_type, pattern in self.ERROR_TYPE_PATTERNS.items():
            if re.search(pattern, log_lower):
                return error_type
        return None

    def _extract_error_code(self, log: str) -> Optional[str]:
        """Extract any error code from the log."""
        match = self.ERROR_CODE_PATTERN.search(log)
        if match:
            return match.group(1)
        return None

    def _extract_host(self, log: str) -> Optional[str]:
        """Try to extract hostname or IP from the log."""
        # Match hostnames
        host_match = re.search(r'(?:host|hostname|node|server)[=:]\s*([\w.-]+)', log, re.IGNORECASE)
        if host_match:
            return host_match.group(1)

        # Match IP addresses
        ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', log)
        if ip_match:
            return ip_match.group(0)

        return None

    def validate_input(self, raw_log: str) -> bool:
        """Validate that the input is sufficient for processing."""
        if not raw_log or not raw_log.strip():
            return False
        if len(raw_log.strip()) < 20:
            return False
        return True
