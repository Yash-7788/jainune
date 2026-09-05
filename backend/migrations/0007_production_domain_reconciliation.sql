-- =============================================================================
-- MIGRATION 0007: Production Domain Reconciliation & Safety Hardening
-- =============================================================================

BEGIN;

-- 1. Admin Users table (required by app/routers/admin.py)
CREATE TABLE IF NOT EXISTS admin_users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    role          VARCHAR(32) NOT NULL CHECK (role IN ('superadmin', 'moderator', 'support')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by    UUID REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_admin_users_user_id ON admin_users(user_id);

-- 2. User Blocks table (safety and harassment prevention)
CREATE TABLE IF NOT EXISTS user_blocks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blocker_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason        VARCHAR(64),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (blocker_id, blocked_id)
);

CREATE INDEX IF NOT EXISTS idx_user_blocks_blocker ON user_blocks(blocker_id);
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked ON user_blocks(blocked_id);

-- 3. Reconcile user_media columns
ALTER TABLE user_media ADD COLUMN IF NOT EXISTS is_processed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE user_media ADD COLUMN IF NOT EXISTS duration_seconds NUMERIC(5, 2);
ALTER TABLE user_media ADD COLUMN IF NOT EXISTS reviewed_by UUID REFERENCES users(id);
ALTER TABLE user_media ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

-- Backfill is_processed for existing approved media
UPDATE user_media SET is_processed = TRUE WHERE status = 'approved' AND is_processed = FALSE;

-- 4. Fail-safe compatibility VIEW for queries referencing "media"
CREATE OR REPLACE VIEW media AS SELECT * FROM user_media;

-- 5. Reconcile chats columns
ALTER TABLE chats ADD COLUMN IF NOT EXISTS is_ephemeral BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE chats ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- 6. Reconcile messages columns
ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_messages_unread ON messages(chat_id, sender_id) WHERE is_read = FALSE;

-- 7. Ensure users table has is_paused and super_connect_credits
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_paused BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS super_connect_credits INT NOT NULL DEFAULT 0;

COMMIT;
