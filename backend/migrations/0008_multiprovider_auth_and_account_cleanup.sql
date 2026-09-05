-- =============================================================================
-- MIGRATION 0008: Multi-Provider Authentication, Inactivity & Memory Freeing
-- =============================================================================

BEGIN;

-- 1. Make phone_number nullable to support Google, Apple, and Email signups
ALTER TABLE users ALTER COLUMN phone_number DROP NOT NULL;

-- 2. Add email, OAuth IDs, and provider tracking
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(128) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS apple_id VARCHAR(128) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(32) NOT NULL DEFAULT 'phone';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 3. Indexes for fast auth lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_users_apple_id ON users(apple_id);
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active_at);

-- 4. Ensure administrative foreign keys set NULL on user deletion
ALTER TABLE user_media DROP CONSTRAINT IF EXISTS fk_user_media_reviewed_by;
ALTER TABLE user_media ADD CONSTRAINT fk_user_media_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE admin_users DROP CONSTRAINT IF EXISTS fk_admin_users_created_by;
ALTER TABLE admin_users ADD CONSTRAINT fk_admin_users_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;

COMMIT;
