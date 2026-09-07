-- =============================================================================
-- MIGRATION 0010: Database Audit Reconciliation & Performance Indexing
-- =============================================================================

BEGIN;

-- 1. Reconcile dilemma_votes foreign key and choice constraint
ALTER TABLE dilemma_votes
    DROP CONSTRAINT IF EXISTS dilemma_votes_dilemma_id_fkey,
    DROP CONSTRAINT IF EXISTS dilemma_votes_choice_check;

ALTER TABLE dilemma_votes
    ADD CONSTRAINT fk_dilemma_votes_dilemma
        FOREIGN KEY (dilemma_id) REFERENCES dilemmas(id) ON DELETE CASCADE,
    ADD CONSTRAINT chk_dilemma_votes_choice
        CHECK (choice IN ('A', 'B', 'a', 'b'));

-- 2. Composite performance indexes
CREATE INDEX IF NOT EXISTS idx_interactions_target_action
    ON interactions (target_id, action_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_matches_status_last_msg
    ON matches (status, last_message_at);

CREATE INDEX IF NOT EXISTS idx_dilemmas_active
    ON dilemmas (is_active, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payment_intents_stale
    ON payment_intents (status, created_at)
    WHERE status = 'created';

-- 3. Voice-note schema constraint: single voice note per user (position must be 1)
ALTER TABLE user_media
    DROP CONSTRAINT IF EXISTS chk_voice_position_one;

ALTER TABLE user_media
    ADD CONSTRAINT chk_voice_position_one
        CHECK (media_type != 'voice' OR position = 1);

COMMIT;
