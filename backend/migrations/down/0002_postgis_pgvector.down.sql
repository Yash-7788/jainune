-- =============================================================================
-- ROLLBACK MIGRATION 0002: PostGIS, pgvector, Snapping, and Matching Schema
-- =============================================================================

BEGIN;

DROP TRIGGER IF EXISTS trg_chats_updated_at ON chats;
DROP TRIGGER IF EXISTS trg_users_location_snap ON users;
DROP FUNCTION IF EXISTS snap_user_location();

DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS chats CASCADE;
DROP TABLE IF EXISTS matches CASCADE;
DROP TABLE IF EXISTS reports CASCADE;
DROP TABLE IF EXISTS blocks CASCADE;
DROP TABLE IF EXISTS likes CASCADE;
DROP TABLE IF EXISTS interactions CASCADE;

DROP INDEX IF EXISTS idx_users_active_gender;
DROP INDEX IF EXISTS idx_users_city_sect;
DROP INDEX IF EXISTS idx_users_geo;

ALTER TABLE users
    DROP COLUMN IF EXISTS is_paused,
    DROP COLUMN IF EXISTS bio,
    DROP COLUMN IF EXISTS height_cm,
    DROP COLUMN IF EXISTS company,
    DROP COLUMN IF EXISTS job_title,
    DROP COLUMN IF EXISTS looking_for,
    DROP COLUMN IF EXISTS compatibility_embedding,
    DROP COLUMN IF EXISTS location;

COMMIT;
