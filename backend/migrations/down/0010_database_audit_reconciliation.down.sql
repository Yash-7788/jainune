-- =============================================================================
-- ROLLBACK MIGRATION 0010: Database Audit Reconciliation & Performance Indexing
-- =============================================================================

BEGIN;

ALTER TABLE user_media DROP CONSTRAINT IF EXISTS chk_voice_position_one;

DROP INDEX IF EXISTS idx_payment_intents_stale;
DROP INDEX IF EXISTS idx_dilemmas_active;
DROP INDEX IF EXISTS idx_matches_status_last_msg;
DROP INDEX IF EXISTS idx_interactions_target_action;

ALTER TABLE dilemma_votes
    DROP CONSTRAINT IF EXISTS fk_dilemma_votes_dilemma,
    DROP CONSTRAINT IF EXISTS chk_dilemma_votes_choice;

COMMIT;
