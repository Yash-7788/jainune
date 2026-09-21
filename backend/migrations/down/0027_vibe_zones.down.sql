-- Rollback 0027: Remove vibe_zones column
BEGIN;
ALTER TABLE users DROP COLUMN IF EXISTS vibe_zones;
COMMIT;
