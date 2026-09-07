-- =============================================================================
-- ROLLBACK MIGRATION 0001: Initial Schema Rollback
-- =============================================================================

BEGIN;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
DROP FUNCTION IF EXISTS set_updated_at();

DROP TABLE IF EXISTS user_photos CASCADE;
DROP TABLE IF EXISTS user_prompts CASCADE;
DROP TABLE IF EXISTS refresh_tokens CASCADE;
DROP TABLE IF EXISTS users CASCADE;

COMMIT;
