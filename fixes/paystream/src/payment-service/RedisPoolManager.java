package com.paystream.redis;

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
 * Known issues:
 * - Pool exhaustion under high traffic (see INC-001, INC-011)
 * - No exponential backoff on connection retry
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
        this.poolConfig.setMinIdle(2);
        this.poolConfig.setMaxWait(Duration.ofMillis(timeoutMs));
        this.poolConfig.setTestOnBorrow(true);
        this.poolConfig.setTestOnReturn(true);
        this.poolConfig.setBlockWhenExhausted(true);

        String[] parts = redisEndpoint.split(":");
        String host = parts[0];
        int port = parts.length > 1 ? Integer.parseInt(parts[1]) : 6379;

        this.pool = new JedisPool(poolConfig, host, port, timeoutMs);
    }

    /**
     * Acquires a connection from the pool.
     * Currently uses simple retry — no exponential backoff.
     */
    public JedisConnection acquire() throws JedisConnectionException {
        try {
            return pool.getResource();
        } catch (JedisConnectionException e) {
            // Simple retry — should use exponential backoff
            for (int i = 0; i < 3; i++) {
                try {
                    Thread.sleep(100);
                    return pool.getResource();
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    break;
                } catch (JedisConnectionException retryEx) {
                    if (i == 2) {
                        throw retryEx;
                    }
                }
            }
            throw e;
        }
    }

    /**
     * Acquires a connection with a lock for payment locks.
     * 
     * WARNING: This method is called frequently during payment spikes
     * and can exhaust the pool under concurrent load.
     */
    public boolean acquireLock(String lockKey, int ttlSeconds) {
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
