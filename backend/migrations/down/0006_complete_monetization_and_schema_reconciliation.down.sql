-- =============================================================================
-- ROLLBACK MIGRATION 0006: Monetization, Arcade Ledger, Schema Reconciliation
-- =============================================================================

BEGIN;

DROP TABLE IF EXISTS daily_proposals CASCADE;
DROP TABLE IF EXISTS telemetry_hourly CASCADE;
DROP TABLE IF EXISTS telemetry_events CASCADE;
DROP TABLE IF EXISTS dilemmas CASCADE;
DROP TABLE IF EXISTS dignity_badges CASCADE;
DROP TABLE IF EXISTS admin_audit_log CASCADE;
DROP TABLE IF EXISTS reports CASCADE;
DROP TABLE IF EXISTS arcade_transactions CASCADE;
DROP TABLE IF EXISTS user_arcade_wallet CASCADE;
DROP TABLE IF EXISTS payment_intents CASCADE;

ALTER TABLE interactions
    DROP COLUMN IF EXISTS reacted_prompt_id,
    DROP COLUMN IF EXISTS action_type;

ALTER TABLE chats
    DROP COLUMN IF EXISTS participant_2_id,
    DROP COLUMN IF EXISTS participant_1_id;

ALTER TABLE matches
    DROP COLUMN IF EXISTS expired_at,
    DROP COLUMN IF EXISTS last_message_at,
    DROP COLUMN IF EXISTS expiry_warned,
    DROP COLUMN IF EXISTS chat_id,
    DROP COLUMN IF EXISTS match_type,
    DROP COLUMN IF EXISTS user_b_id,
    DROP COLUMN IF EXISTS user_a_id,
    DROP COLUMN IF EXISTS user_id_2,
    DROP COLUMN IF EXISTS user_id_1;

ALTER TABLE user_media
    DROP COLUMN IF EXISTS s3_purged,
    DROP COLUMN IF EXISTS rejection_reason,
    DROP COLUMN IF EXISTS status;

DROP INDEX IF EXISTS idx_users_sub_valid;
DROP INDEX IF EXISTS idx_users_fcm;

ALTER TABLE users
    DROP COLUMN IF EXISTS fcm_token,
    DROP COLUMN IF EXISTS deleted_at,
    DROP COLUMN IF EXISTS suspend_until,
    DROP COLUMN IF EXISTS super_connect_credits,
    DROP COLUMN IF EXISTS trust_score,
    DROP COLUMN IF EXISTS subscription_valid_until;

COMMIT;
