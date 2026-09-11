-- =============================================================================
-- Out-of-transaction maintenance script for concurrent index creation / reindexing.
-- Run with psql or standalone connection outside of any transaction block.
-- Example: psql "$DATABASE_URL" -f reindex_concurrent.sql
-- =============================================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_location_geog
    ON users USING GIST ((location::geography));

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ubv_hnsw_cosine
    ON user_behavior_vectors
    USING hnsw (revealed_preference_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_active_gender_city
    ON users (gender, city, community_sect)
    WHERE account_status = 'active' AND is_paused = FALSE;

REINDEX INDEX CONCURRENTLY idx_users_location_geog;
REINDEX INDEX CONCURRENTLY idx_ubv_hnsw_cosine;
REINDEX INDEX CONCURRENTLY idx_users_active_gender_city;
