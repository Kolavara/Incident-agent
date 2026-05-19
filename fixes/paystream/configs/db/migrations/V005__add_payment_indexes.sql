-- =============================================================================
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
