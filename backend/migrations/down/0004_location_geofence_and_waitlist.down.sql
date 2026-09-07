-- =============================================================================
-- ROLLBACK MIGRATION 0004: Location Waitlist and Operational Zones
-- =============================================================================

BEGIN;

DROP INDEX IF EXISTS idx_location_waitlist_created;
DROP TABLE IF EXISTS location_waitlist CASCADE;

ALTER TABLE users
    DROP COLUMN IF EXISTS location_zone;

COMMIT;
