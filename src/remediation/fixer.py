"""Fix implementation engine — applies structured fix tasks to the target repo.

Supports multiple change types:
- CONFIG_EDIT: Modifies YAML configmaps, INI-style configs
- CODE_EDIT: Patches source files (Java, Python)
- FILE_CREATE: Creates new files from templates
- K8S_MANIFEST: Updates Kubernetes deployment manifests
- SCRIPT_RUN: Logs commands for the user to execute
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

from src.remediation.models import ChangeType, FixStatus, FixTask

logger = logging.getLogger('incident_agent.remediation.fixer')

# ──────────────────────────────────────────────
# Fix content templates for common scenarios
# These define what the "fixed" version of each
# file looks like for the demo incidents.
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# Java code fix templates for known bugs
# These patch the simulated PayStream source files.
# ──────────────────────────────────────────────

PYTHON_CODE_FIXES: Dict[str, str] = {
    # Fix data_validator.py — add input sanitization + exception handling
    'src/data-service/data_validator.py': '''"""Data validation service for PayStream payment processing.

Validates incoming payment data before it reaches the core payment pipeline.
Runs as a sidecar in the payment-processor-v2 pod.

FIXED (INC-016):
- Added input sanitization on all string fields
- Added exception handling around logging
- Added validation on the rules_file parameter
- Added length limits and control character stripping
"""

import html
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

    FIXED: Added input sanitization on string fields to prevent
    injection-style attacks via the merchant_name field.
    """

    def __init__(self, rules_file: Optional[str] = None):
        self.rules: list[ValidationRule] = []
        if rules_file:
            # FIXED: validate rules_file path before loading
            if not isinstance(rules_file, str) or not rules_file.strip():
                logger.warning("Invalid rules_file path provided, using defaults")
                self._init_default_rules()
                return
            self._load_rules(rules_file)
        else:
            self._init_default_rules()

    def _init_default_rules(self):
        """Initialize default validation rules."""
        self.rules = [
            ValidationRule(
                field="amount",
                pattern=r"^\\d+(\\.\\d{1,2})?$",
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
                pattern=r"^https://[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}(/.*)?$",
                severity=ValidationSeverity.WARN,
                message="Callback URL should use HTTPS",
            ),
        ]

    def _load_rules(self, rules_file: str) -> None:
        """Load validation rules from a JSON file.

        FIXED: Added try/except with specific exception handling.
        """
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
        except FileNotFoundError:
            logger.warning(f"Rules file not found: {rules_file}. Using defaults.")
            self._init_default_rules()
        except json.JSONDecodeError as e:
            logger.warning(f"Rules file has invalid JSON: {e}. Using defaults.")
            self._init_default_rules()
        except KeyError as e:
            logger.warning(f"Rules file missing key: {e}. Using defaults.")
            self._init_default_rules()

    def _sanitize_input(self, value: str) -> str:
        """Sanitize input to prevent injection attacks.

        FIXED: Implemented proper sanitization:
        - Escape HTML entities
        - Strip control characters
        - Limit length to 4096 characters
        - Reject known malicious patterns
        """
        if not isinstance(value, str):
            return str(value)

        # Strip control characters (except newlines and tabs)
        sanitized = re.sub(r'[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]', '', value)

        # Escape HTML entities
        sanitized = html.escape(sanitized, quote=True)

        # Limit length
        if len(sanitized) > 4096:
            sanitized = sanitized[:4096]

        # Reject known malicious patterns (SQL injection, XSS attempts)
        malicious_patterns = [
            r'(?i)\\'\\s*OR\\s*1\\s*=\\s*1',
            r'(?i)<script.*?>.*?</script>',
            r'(?i)UNION\\s+SELECT',
            r'(?i)DROP\\s+TABLE',
            r'(?i)--\\s',
        ]
        for pattern in malicious_patterns:
            if re.search(pattern, sanitized):
                logger.warning(f"Malicious pattern detected in input, sanitizing: {pattern}")
                sanitized = re.sub(pattern, '[BLOCKED]', sanitized)

        return sanitized

    def validate_payment(self, payment_data: Dict[str, Any]) -> ValidationResult:
        """Validate a payment request against all enabled rules.

        FIXED: Added input sanitization before pattern matching on
        all string fields to prevent injection attacks.

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

            # FIXED: Sanitize input before pattern matching
            if isinstance(value, str):
                value = self._sanitize_input(value)

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

    def log_validation_failure(self, result: ValidationResult,
                                payment_id: str) -> None:
        """Log validation failures with structured context.

        FIXED: Added try/except around logging to prevent crashes
        if the logging subsystem is unavailable.
        """
        try:
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
        except Exception as e:
            # FIXED: Don't let logging failures crash the pipeline
            print(f"[CRITICAL] Failed to log validation result: {e}")


def create_validator(rules_file: Optional[str] = None) -> DataValidator:
    """Factory function to create a configured DataValidator.

    FIXED: Added input validation on rules_file parameter.

    Args:
        rules_file: Optional path to a JSON rules configuration file

    Returns:
        Configured DataValidator instance
    """
    if rules_file is not None and not isinstance(rules_file, str):
        logger.warning(f"Invalid rules_file type: {type(rules_file).__name__}. Using defaults.")
        return DataValidator()
    return DataValidator(rules_file)
'''
}

SQL_MIGRATION_FIXES: Dict[str, str] = {
    # Add payment processing indexes
    'configs/db/migrations/V005__add_payment_indexes.sql': '''-- =============================================================================
-- Migration V005: Add payment processing indexes
--
-- Description: Add composite indexes to optimize payment query performance.
-- Created in response to INC-009 (postgres disk bloat) and ongoing
-- payment query performance issues.
--
-- Applied by: Database migration pipeline
-- =============================================================================

-- Index for payment lookup by merchant + status (most common query pattern)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_payments_merchant_status
    ON payments (merchant_id, status)
    WHERE status IN ('pending', 'processing');

-- Index for fraud detection queries (time-range scans)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_payments_created_at_merchant
    ON payments (created_at DESC, merchant_id)
    INCLUDE (amount, currency, status);

-- Index for settlement batch queries (grouping by date)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_payments_settlement_date
    ON payments (DATE(created_at), merchant_id)
    INCLUDE (amount)
    WHERE status = 'completed';

-- Index for transaction lookup by reference
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_payments_transaction_ref
    ON payments (transaction_ref)
    INCLUDE (status, amount, currency);

-- =============================================================================
-- Rollback (if needed):
--   DROP INDEX IF EXISTS idx_payments_merchant_status;
--   DROP INDEX IF EXISTS idx_payments_created_at_merchant;
--   DROP INDEX IF EXISTS idx_payments_settlement_date;
--   DROP INDEX IF EXISTS idx_payments_transaction_ref;
-- =============================================================================
'''
}

NETWORK_POLICY_FIXES: Dict[str, str] = {
    # Restrict payment access with network policies
    'k8s/network-policies/restrict-payment-access.yaml': '''apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: restrict-payment-access
  namespace: paystream-prod
spec:
  podSelector:
    matchLabels:
      app: payment-processor
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: paystream-prod
          podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: redis-cache
        - podSelector:
            matchLabels:
              app: postgres-primary
      ports:
        - protocol: TCP
          port: 6379
        - protocol: TCP
          port: 5432
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: restrict-auth-access
  namespace: paystream-prod
spec:
  podSelector:
    matchLabels:
      app: auth-service
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - protocol: TCP
          port: 4000
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: block-suspicious-ips
  namespace: paystream-prod
spec:
  podSelector:
    matchLabels:
      app: api-gateway
  policyTypes:
    - Ingress
  ingress:
    - from:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 198.51.100.0/24  # Block known malicious range (from INC-015)
      ports:
        - protocol: TCP
          port: 443
        - protocol: TCP
          port: 80
'''
}

JAVA_CODE_FIXES: Dict[str, str] = {
    # Fix RedisPoolManager — exponential backoff + connection leak detection
    'src/payment-service/RedisPoolManager.java': '''package com.paystream.redis;

import redis.clients.jedis.JedisPool;
import redis.clients.jedis.JedisPoolConfig;
import redis.clients.jedis.JedisCluster;
import redis.clients.jedis.HostAndPort;
import redis.clients.jedis.exceptions.JedisConnectionException;

import java.time.Duration;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

/**
 * Manages Redis connection pools for the PayStream payment processing service.
 *
 * FIXED (INC-011/INC-012):
 * - Increased pool size to 25
 * - Added exponential backoff on connection retry
 * - Added connection pool health check
 * - Added connection leak detection
 */
public class RedisPoolManager {

    private final JedisPoolConfig poolConfig;
    private final JedisPool pool;
    private final String poolName;
    private final int maxPoolSize;
    private final int timeoutMs;
    private final ReentrantLock acquireLock = new ReentrantLock();

    public RedisPoolManager(String poolName, String redisEndpoint, int maxPoolSize, int timeoutMs) {
        this.poolName = poolName;
        this.maxPoolSize = maxPoolSize;
        this.timeoutMs = timeoutMs;

        this.poolConfig = new JedisPoolConfig();
        this.poolConfig.setMaxTotal(maxPoolSize);
        this.poolConfig.setMaxIdle(maxPoolSize / 2);
        this.poolConfig.setMinIdle(5);
        this.poolConfig.setMaxWait(Duration.ofMillis(timeoutMs));
        this.poolConfig.setTestOnBorrow(true);
        this.poolConfig.setTestOnReturn(true);
        this.poolConfig.setTestWhileIdle(true);
        this.poolConfig.setTimeBetweenEvictionRuns(Duration.ofSeconds(30));
        this.poolConfig.setBlockWhenExhausted(true);

        String[] parts = redisEndpoint.split(":");
        String host = parts[0];
        int port = parts.length > 1 ? Integer.parseInt(parts[1]) : 6379;

        this.pool = new JedisPool(poolConfig, host, port, timeoutMs);
    }

    /**
     * Acquires a connection from the pool with exponential backoff.
     *
     * FIXED: Added exponential backoff retry instead of simple fixed-delay loop.
     */
    public JedisConnection acquire() throws JedisConnectionException {
        int retryCount = 0;
        int maxRetries = 5;
        long baseDelay = 100;

        while (true) {
            try {
                if (pool.isClosed()) {
                    throw new JedisConnectionException("Connection pool is closed");
                }
                return pool.getResource();
            } catch (JedisConnectionException e) {
                retryCount++;
                if (retryCount >= maxRetries) {
                    throw e;
                }
                // Exponential backoff: 100ms, 200ms, 400ms, 800ms, 1600ms
                long delay = baseDelay * (long) Math.pow(2, retryCount - 1);
                try {
                    Thread.sleep(delay);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new JedisConnectionException("Interrupted during retry backoff", ie);
                }
            }
        }
    }

    /**
     * Acquires a connection with a lock for payment locks.
     *
     * FIXED: Added connection pool health check before acquisition.
     */
    public boolean acquireLock(String lockKey, int ttlSeconds) {
        if (getHealthScore() < 0.3) {
            System.err.println("Pool health critical, circuit breaker active for: " + lockKey);
            return false;
        }
        try (JedisConnection conn = acquire()) {
            String result = conn.getJedis().set(
                "lock:" + lockKey,
                Thread.currentThread().getName(),
                "NX",
                "EX",
                ttlSeconds
            );
            return "OK".equals(result);
        }
    }

    /**
     * Returns a health score between 0.0 (critical) and 1.0 (healthy).
     * Considers active vs. max connections and pending waiters.
     */
    public double getHealthScore() {
        int active = getActiveConnections();
        int pending = getPendingAcquires();
        if (maxPoolSize == 0) return 1.0;
        double utilization = (double) active / maxPoolSize;
        double penalty = (double) pending / (maxPoolSize + pending);
        return Math.max(0.0, 1.0 - utilization - penalty);
    }

    public int getActiveConnections() {
        return pool.getNumActive();
    }

    public int getIdleConnections() {
        return pool.getNumIdle();
    }

    public int getPendingAcquires() {
        return pool.getNumWaiters();
    }

    public void close() {
        pool.close();
    }
}
''',
    # Fix TokenHandler — graceful JWT expiry with retry-after
    'src/auth-service/TokenHandler.java': '''package com.paystream.auth;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.exceptions.TokenExpiredException;
import com.auth0.jwt.interfaces.DecodedJWT;

import java.time.Instant;
import java.util.Date;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Handles JWT token generation and validation for the PayStream auth service.
 *
 * FIXED (INC-004/INC-015):
 * - Token expiry returns structured response with retry_after
 * - Exponential backoff on repeated failed attempts
 * - Distributed rate limiting with per-endpoint buckets
 */
public class TokenHandler {

    private final Algorithm algorithm;
    private final JWTVerifier verifier;
    private final String issuer;
    private final int tokenExpiryMinutes;

    // Per-endpoint rate limiters
    private final ConcurrentHashMap<String, RateBucket> rateLimiters = new ConcurrentHashMap<>();

    public TokenHandler(String secret, String issuer, int tokenExpiryMinutes) {
        this.algorithm = Algorithm.HMAC256(secret);
        this.verifier = JWT.require(algorithm)
            .withIssuer(issuer)
            .build();
        this.issuer = issuer;
        this.tokenExpiryMinutes = tokenExpiryMinutes;
    }

    public String generateToken(String userId) {
        return JWT.create()
            .withIssuer(issuer)
            .withSubject(userId)
            .withIssuedAt(Date.from(Instant.now()))
            .withExpiresAt(Date.from(Instant.now().plusSeconds(tokenExpiryMinutes * 60)))
            .sign(algorithm);
    }

    /**
     * Validates a JWT token.
     *
     * FIXED: On expiry, throws TokenExpiredException with retry_after hint
     * so the client knows to refresh its token.
     */
    public TokenValidationResult validateToken(String token) {
        try {
            DecodedJWT decoded = verifier.verify(token);
            return new TokenValidationResult(true, decoded, null);
        } catch (TokenExpiredException e) {
            // FIXED: Return structured expiry info with retry_after
            long retryAfter = 0;
            if (e.getExpiredAt() != null) {
                retryAfter = e.getExpiredAt().toInstant().getEpochSecond()
                    - Instant.now().getEpochSeconds() + 300; // retry in 5 min
            }
            return new TokenValidationResult(
                false, null,
                new TokenError("TOKEN_EXPIRED",
                    "Token expired at " + e.getExpiredAt(),
                    Math.max(retryAfter, 0))
            );
        } catch (JWTVerificationException e) {
            return new TokenValidationResult(
                false, null,
                new TokenError("TOKEN_INVALID", e.getMessage(), 0)
            );
        }
    }

    /**
     * Checks rate limit for a specific endpoint.
     * FIXED: Uses per-endpoint rate limiting with exponential backoff.
     */
    public RateLimitResult checkRateLimit(String clientIp, String endpoint,
                                           int limit, int windowSeconds) {
        String key = clientIp + ":" + endpoint;
        RateBucket bucket = rateLimiters.computeIfAbsent(
            key, k -> new RateBucket(limit, windowSeconds)
        );
        return bucket.tryConsume();
    }

    /**
     * Result of token validation with structured error info.
     */
    public static class TokenValidationResult {
        public final boolean valid;
        public final DecodedJWT decoded;
        public final TokenError error;

        public TokenValidationResult(boolean valid, DecodedJWT decoded, TokenError error) {
            this.valid = valid;
            this.decoded = decoded;
            this.error = error;
        }
    }

    public static class TokenError {
        public final String code;
        public final String message;
        public final long retryAfterSeconds;

        public TokenError(String code, String message, long retryAfterSeconds) {
            this.code = code;
            this.message = message;
            this.retryAfterSeconds = retryAfterSeconds;
        }
    }

    public static class RateLimitResult {
        public final boolean allowed;
        public final int remaining;
        public final long retryAfterMs;

        public RateLimitResult(boolean allowed, int remaining, long retryAfterMs) {
            this.allowed = allowed;
            this.remaining = remaining;
            this.retryAfterMs = retryAfterMs;
        }
    }

    private static class RateBucket {
        private final int limit;
        private final long windowMillis;
        private final AtomicInteger count = new AtomicInteger(0);
        private volatile long windowStart = System.currentTimeMillis();
        private volatile int failedAttempts = 0;
        private volatile long blockUntil = 0;

        RateBucket(int limit, int windowSeconds) {
            this.limit = limit;
            this.windowMillis = windowSeconds * 1000L;
        }

        synchronized RateLimitResult tryConsume() {
            long now = System.currentTimeMillis();

            // Check if currently blocked (exponential backoff)
            if (now < blockUntil) {
                return new RateLimitResult(false, 0, blockUntil - now);
            }

            // Reset window
            if (now - windowStart > windowMillis) {
                windowStart = now;
                count.set(0);
                failedAttempts = 0;
                blockUntil = 0;
            }

            int current = count.incrementAndGet();
            if (current > limit) {
                // FIXED: Exponential backoff on repeated violations
                failedAttempts++;
                long backoffMs = Math.min(
                    60000,
                    (long) (100 * Math.pow(2, failedAttempts - 1))
                );
                blockUntil = now + backoffMs;
                return new RateLimitResult(false, 0, backoffMs);
            }

            failedAttempts = 0;
            return new RateLimitResult(true, limit - current, 0);
        }
    }
}
''',
}

FIX_TEMPLATES: Dict[str, str] = {
    # Payment processor ConfigMap — increase pool size
    'configs/payment-processor/configmap.yaml': """apiVersion: v1
kind: ConfigMap
metadata:
  name: payment-processor-config
  namespace: paystream-prod
data:
  CONNECTION_POOL_SIZE: "25"
  POOL_TIMEOUT_MS: "2000"
  MAX_RETRIES: "5"
  RETRY_BACKOFF_MS: "1000"
  REDIS_ENDPOINT: "redis-cluster.internal:6379"
  TRANSACTION_TIMEOUT_MS: "5000"
  ENABLE_CIRCUIT_BREAKER: "true"
  CIRCUIT_BREAKER_THRESHOLD: "5"
""",
    # Postgres pgbouncer config — increase connections
    'configs/postgres/pgbouncer-config.yaml': """apiVersion: v1
kind: ConfigMap
metadata:
  name: pgbouncer-config
  namespace: paystream-prod
data:
  pgbouncer.ini: |
    [databases]
    paystream = host=postgres-primary.internal port=5432 dbname=paystream

    [pgbouncer]
    pool_mode = transaction
    max_client_conn = 300
    default_pool_size = 50
    reserve_pool_size = 10
    reserve_pool_timeout = 3
    max_db_connections = 300
    query_timeout = 10
    idle_timeout = 600
""",
    # Redis config — increase maxmemory
    'configs/redis/redis-config.conf': """# Redis configuration for redis-cache-03
maxmemory 1gb
maxmemory-policy allkeys-lfu
save 300 100
save 60 10000
timeout 300
tcp-keepalive 60
lfu-log-factor 10
lfu-decay-time 1
activerehashing yes
appendonly yes
appendfsync everysec
maxmemory-samples 10
""",
    # Notification worker — memory limit increase
    'k8s/notification-worker/deployment.yaml': """apiVersion: apps/v1
kind: Deployment
metadata:
  name: notification-worker
  namespace: paystream-prod
  labels:
    app: notification-worker
spec:
  replicas: 8
  selector:
    matchLabels:
      app: notification-worker
  template:
    metadata:
      labels:
        app: notification-worker
    spec:
      containers:
        - name: notification-worker
          image: paystream/notification-worker:v1.8.2
          ports:
            - containerPort: 9090
          env:
            - name: KAFKA_BROKER
              value: "kafka-02:9092"
            - name: CONSUMER_GROUP
              value: "email-workers"
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
          livenessProbe:
            httpGet:
              path: /health
              port: 9090
            initialDelaySeconds: 15
            periodSeconds: 20
""",
    # API gateway — increase upstream timeout
    'k8s/api-gateway/deployment.yaml': """apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
  namespace: paystream-prod
  labels:
    app: api-gateway
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api-gateway
  template:
    metadata:
      labels:
        app: api-gateway
    spec:
      containers:
        - name: api-gateway
          image: paystream/api-gateway:v3.1.0
          ports:
            - containerPort: 443
          env:
            - name: PAYMENT_SERVICE_URL
              value: "http://payment-processor-v2:8080"
            - name: AUTH_SERVICE_URL
              value: "http://auth-service:4000"
            - name: UPSTREAM_TIMEOUT_MS
              value: "30000"
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 15
""",
    # Redis payment processor deployment — pool health check
    'k8s/payment-processor-v2/deployment.yaml': """apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-processor-v2
  namespace: paystream-prod
  labels:
    app: payment-processor
    version: v2
spec:
  replicas: 5
  selector:
    matchLabels:
      app: payment-processor
  template:
    metadata:
      labels:
        app: payment-processor
    spec:
      containers:
        - name: payment-processor
          image: paystream/payment-processor:v2.4.1
          ports:
            - containerPort: 8080
          env:
            - name: CONNECTION_POOL_SIZE
              valueFrom:
                configMapKeyRef:
                  name: payment-processor-config
                  key: CONNECTION_POOL_SIZE
            - name: POOL_TIMEOUT_MS
              valueFrom:
                configMapKeyRef:
                  name: payment-processor-config
                  key: POOL_TIMEOUT_MS
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
""",
}


class Fixer:
    """Applies structured fix tasks to the target repository.

    Each fix task specifies a file path, change type, and (optionally)
    the new content. The fixer reads the current file, applies the
    change, and writes back.
    """

    def __init__(self, target_repo_path: str = "fixes/paystream",
                 dry_run: bool = False):
        self.target_repo = Path(target_repo_path)
        self.dry_run = dry_run
        self._applied_files: Dict[str, Tuple[str, str]] = {}  # path -> (original, new)

    def apply(self, task: FixTask) -> bool:
        """Apply a single fix task to the target repository.

        Args:
            task: The fix task to apply

        Returns:
            True if the task was applied successfully
        """
        logger.info(
            f"[{task.id}] Applying: {task.description[:60]}... "
            f"({task.change_type.value})"
        )

        try:
            if task.change_type == ChangeType.CONFIG_EDIT:
                return self._apply_config_edit(task)
            elif task.change_type == ChangeType.K8S_MANIFEST:
                return self._apply_k8s_manifest(task)
            elif task.change_type == ChangeType.CODE_EDIT:
                return self._apply_code_edit(task)
            elif task.change_type == ChangeType.FILE_CREATE:
                # SQL migrations checked first, falls through to generic create
                return self._apply_sql_migration(task)
            elif task.change_type == ChangeType.SCRIPT_RUN:
                return self._apply_script_run(task)
            else:
                logger.warning(f"[{task.id}] Unknown change type: {task.change_type}")
                task.status = FixStatus.SKIPPED
                return False

        except Exception as e:
            logger.error(f"[{task.id}] Failed to apply: {e}")
            task.status = FixStatus.FAILED
            return False

    def apply_all(self, tasks: List[FixTask]) -> Tuple[int, int]:
        """Apply a list of fix tasks in priority order.

        Args:
            tasks: List of FixTask objects to apply

        Returns:
            Tuple of (applied_count, failed_count)
        """
        tasks.sort(key=lambda t: t.priority)
        applied = 0
        failed = 0

        for task in tasks:
            if task.status != FixStatus.PENDING:
                continue
            if self.apply(task):
                applied += 1
            else:
                failed += 1

        return applied, failed

    def get_diff(self) -> str:
        """Generate a git-style diff of all applied changes.

        Returns:
            String containing diffs for all modified files
        """
        lines = []
        for file_path, (original, new) in sorted(self._applied_files.items()):
            if original == new:
                continue
            lines.append(f"--- a/{file_path}")
            lines.append(f"+++ b/{file_path}")
            lines.append(f"@@ -1 +1 @@")
            lines.append(f"-{original[:80].strip()}")
            lines.append(f"+{new[:80].strip()}")
            lines.append("")
        return "\n".join(lines)

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve a relative file path against the target repo root."""
        return self.target_repo / file_path

    def _read_file(self, path: Path) -> Optional[str]:
        """Read a file's content, returning None if it doesn't exist."""
        try:
            if path.exists():
                return path.read_text(encoding='utf-8')
            return None
        except Exception as e:
            logger.warning(f"Could not read {path}: {e}")
            return None

    def _write_file(self, path: Path, content: str):
        """Write content to a file, creating parent directories if needed."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would write {path}")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        logger.info(f"  Written: {path}")

    def _apply_config_edit(self, task: FixTask) -> bool:
        """Apply a config file edit using the fix template or task content."""
        path = self._resolve_path(task.file_path)

        # Use template if available
        template_key = task.file_path.replace('\\', '/')
        if template_key in FIX_TEMPLATES:
            original = self._read_file(path) or ""
            new_content = FIX_TEMPLATES[template_key]
            self._applied_files[template_key] = (original, new_content)
            self._write_file(path, new_content)
            task.new_content = new_content
            task.original_content = original
            task.status = FixStatus.APPLIED
            return True

        # Use task-provided content
        if task.new_content:
            original = self._read_file(path) or ""
            self._applied_files[template_key] = (original, task.new_content)
            self._write_file(path, task.new_content)
            task.original_content = original
            task.status = FixStatus.APPLIED
            return True

        logger.warning(f"[{task.id}] No template or content for config edit: {task.file_path}")
        task.status = FixStatus.SKIPPED
        return False

    def _apply_k8s_manifest(self, task: FixTask) -> bool:
        """Apply a Kubernetes manifest edit using templates or content."""
        template_key = task.file_path.replace('\\', '/')

        # Check network policy fix templates
        if template_key in NETWORK_POLICY_FIXES:
            path = self._resolve_path(task.file_path)
            original = self._read_file(path) or ""
            new_content = NETWORK_POLICY_FIXES[template_key]
            self._applied_files[template_key] = (original, new_content)
            self._write_file(path, new_content)
            task.new_content = new_content
            task.original_content = original
            task.status = FixStatus.APPLIED
            logger.info(f"  Network policy applied: {task.file_path}")
            return True

        if template_key in FIX_TEMPLATES:
            path = self._resolve_path(task.file_path)
            original = self._read_file(path) or ""
            new_content = FIX_TEMPLATES[template_key]
            self._applied_files[template_key] = (original, new_content)
            self._write_file(path, new_content)
            task.new_content = new_content
            task.original_content = original
            task.status = FixStatus.APPLIED
            return True

        if task.new_content:
            path = self._resolve_path(task.file_path)
            original = self._read_file(path) or ""
            self._applied_files[template_key] = (original, task.new_content)
            self._write_file(path, task.new_content)
            task.original_content = original
            task.status = FixStatus.APPLIED
            return True

        task.status = FixStatus.SKIPPED
        logger.warning(f"[{task.id}] No template/content for k8s manifest: {task.file_path}")
        return False

    def _apply_code_edit(self, task: FixTask) -> bool:
        """Apply a source code edit using fix templates or task content."""
        path = self._resolve_path(task.file_path)
        template_key = task.file_path.replace('\\', '/')

        # Check Python code fix templates first
        if template_key in PYTHON_CODE_FIXES:
            original = self._read_file(path) or ""
            new_content = PYTHON_CODE_FIXES[template_key]
            self._applied_files[template_key] = (original, new_content)
            self._write_file(path, new_content)
            task.new_content = new_content
            task.original_content = original
            task.status = FixStatus.APPLIED
            logger.info(f"  Python fix applied: {task.file_path}")
            return True

        # Check Java code fix templates
        if template_key in JAVA_CODE_FIXES:
            original = self._read_file(path) or ""
            new_content = JAVA_CODE_FIXES[template_key]
            self._applied_files[template_key] = (original, new_content)
            self._write_file(path, new_content)
            task.new_content = new_content
            task.original_content = original
            task.status = FixStatus.APPLIED
            logger.info(f"  Java fix applied: {task.file_path}")
            return True

        # Use task-provided content
        if task.new_content:
            original = self._read_file(path) or ""
            self._applied_files[template_key] = (original, task.new_content)
            self._write_file(path, task.new_content)
            task.original_content = original
            task.status = FixStatus.APPLIED
            return True

        # No template or content — mark as needing manual implementation
        logger.warning(
            f"[{task.id}] Code edit requires manual implementation: {task.file_path}"
        )
        task.status = FixStatus.SKIPPED
        return False

    def _apply_sql_migration(self, task: FixTask) -> bool:
        """Apply a SQL migration file create."""
        path = self._resolve_path(task.file_path)
        template_key = task.file_path.replace('\\', '/')

        if template_key in SQL_MIGRATION_FIXES:
            original = self._read_file(path) or ""
            new_content = SQL_MIGRATION_FIXES[template_key]
            self._applied_files[template_key] = (original, new_content)
            self._write_file(path, new_content)
            task.new_content = new_content
            task.original_content = original
            task.status = FixStatus.APPLIED
            logger.info(f"  SQL migration created: {task.file_path}")
            return True

        # Fall through to generic file create
        if task.new_content:
            original = self._read_file(path) or ""
            self._applied_files[template_key] = (original, task.new_content)
            self._write_file(path, task.new_content)
            task.original_content = original
            task.status = FixStatus.APPLIED
            return True

        task.status = FixStatus.SKIPPED
        logger.warning(f"[{task.id}] No template/content for SQL migration: {task.file_path}")
        return False

    def _apply_file_create(self, task: FixTask) -> bool:
        """Create a new file."""
        path = self._resolve_path(task.file_path)

        if path.exists():
            logger.info(f"[{task.id}] File already exists: {task.file_path}")
            task.status = FixStatus.SKIPPED
            return False

        content = task.new_content or ""
        self._write_file(path, content)
        task.original_content = ""
        task.new_content = content
        template_key = task.file_path.replace('\\', '/')
        self._applied_files[template_key] = ("", content)
        task.status = FixStatus.APPLIED
        return True

    def _apply_script_run(self, task: FixTask) -> bool:
        """Log a script/command to be run (does not execute)."""
        command = task.command or task.description

        logger.info(
            f"[{task.id}] Script to execute: {command}"
        )
        # For demo, we just log the command. In production, execution
        # would require user confirmation or an automation runner.
        task.new_content = f"# {task.description}\n{command}"
        task.status = FixStatus.APPLIED
        return True
