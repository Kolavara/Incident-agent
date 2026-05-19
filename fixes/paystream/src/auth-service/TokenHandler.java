package com.paystream.auth;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.DecodedJWT;

import java.time.Instant;
import java.util.Date;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Handles JWT token generation and validation for the PayStream auth service.
 *
 * Known issues:
 * - Token expiry not handled gracefully (INC-004)
 * - No exponential backoff on repeated failed attempts
 * - Rate limiting is basic (per-IP only, no distributed rate limiting)
 */
public class TokenHandler {

    private final Algorithm algorithm;
    private final JWTVerifier verifier;
    private final String issuer;
    private final int tokenExpiryMinutes;

    // Simple in-memory rate limiter
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
     * BUG: When a token is expired, this returns false without
     * providing any guidance on refresh. The client has no way
     * to know it should refresh its token.
     */
    public DecodedJWT validateToken(String token) throws JWTVerificationException {
        return verifier.verify(token);
    }

    /**
     * Checks rate limit for a given client IP.
     * Does not distinguish between different endpoints.
     */
    public boolean isRateLimited(String clientIp, int limit, int windowSeconds) {
        RateBucket bucket = rateLimiters.computeIfAbsent(
            clientIp, k -> new RateBucket(limit, windowSeconds)
        );
        return !bucket.tryConsume();
    }

    private static class RateBucket {
        private final int limit;
        private final long windowMillis;
        private final AtomicInteger count = new AtomicInteger(0);
        private volatile long windowStart = System.currentTimeMillis();

        RateBucket(int limit, int windowSeconds) {
            this.limit = limit;
            this.windowMillis = windowSeconds * 1000L;
        }

        boolean tryConsume() {
            long now = System.currentTimeMillis();
            if (now - windowStart > windowMillis) {
                synchronized (this) {
                    if (now - windowStart > windowMillis) {
                        windowStart = now;
                        count.set(0);
                    }
                }
            }
            return count.incrementAndGet() <= limit;
        }
    }
}
