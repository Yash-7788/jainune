-- =============================================================================
-- MIGRATION 0004: Location Waitlist and Operational Zones
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS location_waitlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(16),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    city_hint VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_location_waitlist_created
    ON location_waitlist (created_at DESC);

-- Add operational location zone to users table if not exists
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS location_zone VARCHAR(64);

COMMIT;
