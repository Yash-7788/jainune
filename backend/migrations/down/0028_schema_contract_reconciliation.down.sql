-- Rollback Migration 0028: Schema contract reconciliation

BEGIN;

DROP TABLE IF EXISTS feed_queues CASCADE;
DROP TABLE IF EXISTS revoked_refresh_tokens CASCADE;
ALTER TABLE users DROP COLUMN IF EXISTS avatar_url;

COMMIT;
