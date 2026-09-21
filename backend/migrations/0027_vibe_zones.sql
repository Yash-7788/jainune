-- Migration 0027: Add vibe_zones column to users table
-- Supports the "Vibe Zones" feature in EditProfileScreen

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS vibe_zones TEXT[] NOT NULL DEFAULT '{}';

COMMIT;
