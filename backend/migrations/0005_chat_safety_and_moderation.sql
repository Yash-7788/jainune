-- =============================================================================
-- MIGRATION 0005: Chat Safety Moderation Fields
-- =============================================================================

BEGIN;

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS is_moderated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS moderation_type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS moderation_disclaimer TEXT;

CREATE INDEX IF NOT EXISTS idx_messages_moderated
    ON messages (chat_id, is_moderated)
    WHERE is_moderated = TRUE;

COMMIT;
