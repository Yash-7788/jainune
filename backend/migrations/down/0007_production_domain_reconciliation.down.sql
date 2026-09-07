-- =============================================================================
-- ROLLBACK MIGRATION 0007: Production Domain Reconciliation & Safety Hardening
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS media CASCADE;

DROP TABLE IF EXISTS user_blocks CASCADE;
DROP TABLE IF EXISTS admin_users CASCADE;

DROP INDEX IF EXISTS idx_messages_unread;

ALTER TABLE messages
    DROP COLUMN IF EXISTS read_at,
    DROP COLUMN IF EXISTS is_read;

ALTER TABLE chats
    DROP COLUMN IF EXISTS expires_at,
    DROP COLUMN IF EXISTS is_ephemeral;

ALTER TABLE user_media
    DROP COLUMN IF EXISTS reviewed_at,
    DROP COLUMN IF EXISTS reviewed_by,
    DROP COLUMN IF EXISTS duration_seconds,
    DROP COLUMN IF EXISTS is_processed;

COMMIT;
