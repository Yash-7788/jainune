-- Migration 0021: Store subscriptions and authoritative billing status in users
-- Reconciles store subscription state, event idempotency, and DB-backed account hold

ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_status VARCHAR(32) NOT NULL DEFAULT 'active';

CREATE TABLE IF NOT EXISTS store_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    store VARCHAR(16) NOT NULL, -- 'apple' or 'google'
    original_transaction_id VARCHAR(128) NOT NULL,
    latest_transaction_id VARCHAR(128),
    sku VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    expires_at TIMESTAMPTZ,
    last_event_type VARCHAR(32),
    last_event_timestamp BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_store_sub_orig_txn UNIQUE (store, original_transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_store_sub_user ON store_subscriptions(user_id);
