-- Migration 0012: Functional GiST index on location::geography
-- Accelerates true spherical ST_DWithin and ST_Distance queries in core_people_finder
-- Prevents full table scan when querying user radius in WGS84 geography coordinates.

CREATE INDEX IF NOT EXISTS idx_users_location_geog
    ON users USING GIST ((location::geography));
