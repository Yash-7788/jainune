-- =============================================================================
-- ROLLBACK MIGRATION 0026: Banned Image Hashes Table
-- =============================================================================

BEGIN;

DROP TABLE IF EXISTS banned_image_hashes;

COMMIT;
