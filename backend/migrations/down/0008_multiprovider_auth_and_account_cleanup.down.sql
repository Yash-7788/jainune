-- =============================================================================
-- ROLLBACK MIGRATION 0008: Multi-Provider Authentication & Account Cleanup
-- =============================================================================

BEGIN;

DROP INDEX IF EXISTS idx_users_last_active;
DROP INDEX IF EXISTS idx_users_apple_id;
DROP INDEX IF EXISTS idx_users_google_id;
DROP INDEX IF EXISTS idx_users_email;

ALTER TABLE users
    DROP COLUMN IF EXISTS last_active_at,
    DROP COLUMN IF EXISTS is_email_verified,
    DROP COLUMN IF EXISTS auth_provider,
    DROP COLUMN IF EXISTS apple_id,
    DROP COLUMN IF EXISTS google_id,
    DROP COLUMN IF EXISTS email;

COMMIT;
