-- =============================================================================
-- ROLLBACK MIGRATION 0005: Chat Safety Moderation Fields
-- =============================================================================

BEGIN;

DROP INDEX IF EXISTS idx_messages_moderated;

ALTER TABLE messages
    DROP COLUMN IF EXISTS moderation_disclaimer,
    DROP COLUMN IF EXISTS moderation_type,
    DROP COLUMN IF EXISTS is_moderated;

COMMIT;
