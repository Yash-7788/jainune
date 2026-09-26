-- Migration 0028: Schema contract reconciliation for runtime resilient tables and avatar_url
-- Adds revoked_refresh_tokens, feed_queues, and users.avatar_url

BEGIN;

-- 1. Add avatar_url column to users table (written by moderation and media services)
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512);

-- 2. Resilient token revocation table (queried on token refresh and session replacement)
CREATE TABLE IF NOT EXISTS revoked_refresh_tokens (
    token_hash VARCHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    revocation_type VARCHAR(32) NOT NULL,
    payload TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE revoked_refresh_tokens ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_user ON revoked_refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_refresh_tokens(expires_at);

-- 3. Resilient feed queues table (checkpointed by daily matching worker, fallback for feed)
CREATE TABLE IF NOT EXISTS feed_queues (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    candidate_ids UUID[] NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE feed_queues ENABLE ROW LEVEL SECURITY;

COMMIT;
