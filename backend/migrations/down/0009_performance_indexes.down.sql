-- =============================================================================
-- ROLLBACK MIGRATION 0009: Add performance indexes on chats, matches, active users
-- =============================================================================

BEGIN;

DROP INDEX IF EXISTS idx_users_account_status_id;
DROP INDEX IF EXISTS idx_matches_ub;
DROP INDEX IF EXISTS idx_matches_ua;
DROP INDEX IF EXISTS idx_matches_u2;
DROP INDEX IF EXISTS idx_matches_u1;
DROP INDEX IF EXISTS idx_chats_p2;
DROP INDEX IF EXISTS idx_chats_p1;

COMMIT;
