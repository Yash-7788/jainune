-- =============================================================================
-- MIGRATION 0016: Zero-Downtime Concurrent Spatial & Vector Maintenance
-- =============================================================================
-- In production PostgreSQL, index rebuilds take exclusive write locks (ACCESS EXCLUSIVE)
-- unless CONCURRENTLY is specified.
-- Note: In PostgreSQL, CREATE INDEX CONCURRENTLY and REINDEX INDEX CONCURRENTLY
-- must run as standalone commands outside of an explicit transaction block (BEGIN/COMMIT).
-- =============================================================================

-- 1. Concurrent PostGIS Geography GIST Index
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_location_geog
    ON users USING GIST ((location::geography));

-- 2. Concurrent pgvector HNSW Cosine Index
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ubv_hnsw_cosine
    ON user_behavior_vectors
    USING hnsw (revealed_preference_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- 3. Concurrent Composite Cultural & Activity B-Tree
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_active_gender_city
    ON users (gender, city, community_sect)
    WHERE account_status = 'active' AND is_paused = FALSE;
