-- =============================================================================
-- MIGRATION 0002: PostGIS, pgvector, Location Snapping, and Matching Schema
-- =============================================================================
-- Run after 0001_initial_schema.sql
-- Requires PostgreSQL 15+ with PostGIS and pgvector extensions installed.
-- On Supabase: both are available via the Extensions UI.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid() supplement

-- ---------------------------------------------------------------------------
-- 2. Add geospatial and vector columns to users
--    (0001 may have created users without these if run standalone)
-- ---------------------------------------------------------------------------

-- Add PostGIS location column (not in 0001)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS location GEOMETRY(Point, 4326);

-- Add behavioral vector column (0001 has 'embedding'; add alias for BRRE)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS compatibility_embedding vector(128);

-- Add missing profile fields (0001 may have subsets; IF NOT EXISTS is safe)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS looking_for VARCHAR(32),
    ADD COLUMN IF NOT EXISTS job_title   VARCHAR(128),
    ADD COLUMN IF NOT EXISTS company     VARCHAR(128),
    ADD COLUMN IF NOT EXISTS height_cm   INT,
    ADD COLUMN IF NOT EXISTS bio         TEXT,
    ADD COLUMN IF NOT EXISTS is_paused   BOOLEAN NOT NULL DEFAULT FALSE;

-- ---------------------------------------------------------------------------
-- 3. GiST spatial index for PostGIS radius queries (ST_DWithin)
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_users_geo
    ON users USING GIST (location);

-- Composite B-Tree for fast cultural / city filter pre-gating
CREATE INDEX IF NOT EXISTS idx_users_city_sect
    ON users (city, community_sect, dietary_strictness)
    WHERE account_status = 'active';

-- Partial index: active users only, for feed query WHERE clause
CREATE INDEX IF NOT EXISTS idx_users_active_gender
    ON users (gender, account_status)
    WHERE account_status = 'active' AND is_paused = FALSE;

-- ---------------------------------------------------------------------------
-- 4. Geohash-6 Location Snap Trigger
--    Snaps raw GPS coordinates to a Geohash-6 centroid (~1.2 km x 0.6 km).
--    This prevents trilateration attacks: stored coordinate is the cell
--    centroid, not the user's exact position.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_snap_user_location_to_geohash6()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    geohash_str    TEXT;
    grid_centroid  GEOMETRY;
BEGIN
    IF NEW.location IS NULL THEN
        RETURN NEW;
    END IF;

    -- Only execute when location is inserted or actually changed
    IF (TG_OP = 'INSERT') OR (TG_OP = 'UPDATE' AND NOT ST_Equals(NEW.location, OLD.location)) THEN
        -- Encode to Geohash precision 6 (each cell ~1.2 km wide x 0.6 km tall)
        geohash_str   := ST_GeoHash(ST_Transform(NEW.location, 4326), 6);
        -- Derive the centroid of that bounding box
        grid_centroid := ST_Centroid(ST_GeomFromGeoHash(geohash_str));
        -- Overwrite raw GPS with snapped centroid; preserve SRID 4326
        NEW.location  := ST_SetSRID(grid_centroid, 4326);
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_snap_user_location ON users;

CREATE TRIGGER trg_snap_user_location
    BEFORE INSERT OR UPDATE OF location ON users
    FOR EACH ROW
    EXECUTE FUNCTION fn_snap_user_location_to_geohash6();

-- ---------------------------------------------------------------------------
-- 5. Updated-at helper function (0001 created set_updated_at; reuse it)
-- ---------------------------------------------------------------------------

-- Alias fn_set_updated_at -> set_updated_at for tables created in 0002
-- (The users trigger was already created in 0001; do not recreate it.)
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 6. User Media table (photos + voice snapshots)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_media (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    media_type    VARCHAR(16)  NOT NULL CHECK (media_type IN ('photo', 'voice')),
    s3_key        VARCHAR(512) NOT NULL,      -- quarantine-relative key
    cdn_url       VARCHAR(512),               -- populated after EXIF strip
    position      INT          NOT NULL CHECK (position BETWEEN 1 AND 6),
    -- NULL for photos; 7.0 for voice snapshots; variable for sparks
    duration_seconds NUMERIC(5, 2),
    is_processed  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, media_type, position)
);

CREATE INDEX IF NOT EXISTS idx_user_media_user ON user_media (user_id);

-- ---------------------------------------------------------------------------
-- 7. User Behavior Vectors table (BRRE telemetry + HNSW)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_behavior_vectors (
    user_id                 UUID         PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    -- 128-dimensional dynamic preference vector; updated via EMA gradient
    revealed_preference_vector  vector(128)  NOT NULL,
    -- Raw interaction counters for Thompson Sampling bandit
    total_likes_sent        INT          NOT NULL DEFAULT 0,
    total_passes_sent       INT          NOT NULL DEFAULT 0,
    total_likes_received    INT          NOT NULL DEFAULT 0,
    total_passes_received   INT          NOT NULL DEFAULT 0,
    -- Aggregated behavioral tendencies [0.0, 1.0]
    voice_affinity_ratio    NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
    prompt_depth_ratio      NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
    commenter_score         NUMERIC(4, 3) NOT NULL DEFAULT 0.300,
    -- Dignity floor: how many boosts used in lifetime
    dignity_boost_count     INT          NOT NULL DEFAULT 0,
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_ubv_updated_at ON user_behavior_vectors;

CREATE TRIGGER trg_ubv_updated_at
    BEFORE UPDATE ON user_behavior_vectors
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_matches_updated_at_pre ON matches;

-- HNSW index for sub-15ms cosine ANN search across 128-d vectors
-- ef_construction=128 and m=16 are production-calibrated for 200k profiles
CREATE INDEX IF NOT EXISTS idx_ubv_hnsw_cosine
    ON user_behavior_vectors
    USING hnsw (revealed_preference_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- ---------------------------------------------------------------------------
-- 8. Discovery Interactions table (likes / passes)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS interactions (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id         UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_id        UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    interaction_type VARCHAR(8)   NOT NULL CHECK (interaction_type IN ('like', 'pass')),
    -- Element the like was attached to
    content_type     VARCHAR(16)  CHECK (content_type IN ('photo', 'prompt', 'voice')),
    content_id       UUID,
    comment          VARCHAR(200),
    -- Consumed = the target has already seen / responded to this like
    is_consumed      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- One interaction per actor-target pair (upsertable)
    UNIQUE (actor_id, target_id)
);

CREATE INDEX IF NOT EXISTS idx_interactions_target
    ON interactions (target_id, interaction_type);

CREATE INDEX IF NOT EXISTS idx_interactions_actor
    ON interactions (actor_id);

-- ---------------------------------------------------------------------------
-- 9. Matches table with 72-hour momentum state machine
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS matches (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_a            UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_b            UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status            VARCHAR(24)  NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'momentum_locked', 'closed', 'expired')),
    -- 72-hour deadline from match creation; background worker evaluates this
    momentum_deadline TIMESTAMPTZ  NOT NULL DEFAULT (NOW() + INTERVAL '72 hours'),
    voice_notes_count INT          NOT NULL DEFAULT 0,
    match_source      VARCHAR(24)  NOT NULL DEFAULT 'orbit_feed'
                          CHECK (match_source IN ('orbit_feed', 'daily_compatible', 'the_wheel')),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Canonical ordering: user_a < user_b by UUID string to prevent duplicate pairs
    UNIQUE (user_a, user_b),
    CHECK (user_a < user_b)
);

DROP TRIGGER IF EXISTS trg_matches_updated_at ON matches;

CREATE TRIGGER trg_matches_updated_at
    BEFORE UPDATE ON matches
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_matches_users
    ON matches (user_a, user_b);

CREATE INDEX IF NOT EXISTS idx_matches_deadline
    ON matches (momentum_deadline)
    WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 10. Chats table (1:1, scoped to a match)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS chats (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id      UUID         NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    participant_a UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    participant_b UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_unmatched  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (match_id)
);

CREATE INDEX IF NOT EXISTS idx_chats_participant_a ON chats (participant_a);
CREATE INDEX IF NOT EXISTS idx_chats_participant_b ON chats (participant_b);

-- ---------------------------------------------------------------------------
-- 11. Messages table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS messages (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id      UUID         NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    sender_id    UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_type VARCHAR(24)  NOT NULL DEFAULT 'text'
                     CHECK (message_type IN ('text', 'voice', 'bounty', 'date_card', 'exit')),
    content      TEXT,
    media_url    VARCHAR(512),
    -- Client-generated idempotency key to prevent double-sends
    client_msg_id VARCHAR(64) UNIQUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_order
    ON messages (chat_id, created_at ASC);

-- ---------------------------------------------------------------------------
-- 12. Green Flags (positive peer badge system)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_green_flags (
    target_user_id UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge_key      VARCHAR(32) NOT NULL
                       CHECK (badge_key IN (
                           'punctual', 'respects_diet', 'real_photos',
                           'great_conversation', 'courteous'
                       )),
    award_count    INT         NOT NULL DEFAULT 1,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (target_user_id, badge_key)
);

-- ---------------------------------------------------------------------------
-- 13. Consent Records (DPDP Act 2023 compliance)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS consent_records (
    id                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type          VARCHAR(64)  NOT NULL,
    -- 'core_matchmaking', 'family_contact_gotra', 'relocation_intercity'
    granted               BOOLEAN      NOT NULL,
    consent_version       VARCHAR(16)  NOT NULL DEFAULT '1.0.0',
    ip_address            INET,
    user_agent            TEXT,
    recorded_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_consent_user ON consent_records (user_id);

-- ---------------------------------------------------------------------------
-- 14. Dilemma Duel daily questions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dilemma_questions (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    dilemma_date   DATE         NOT NULL UNIQUE,
    question       TEXT         NOT NULL,
    option_a       TEXT         NOT NULL,
    option_b       TEXT         NOT NULL,
    total_votes_a  INT          NOT NULL DEFAULT 0,
    total_votes_b  INT          NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dilemma_votes (
    user_id        UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dilemma_id     UUID         NOT NULL REFERENCES dilemma_questions(id),
    choice         CHAR(1)      NOT NULL CHECK (choice IN ('a', 'b')),
    voted_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, dilemma_id)
);

-- ---------------------------------------------------------------------------
-- 15. Statement timeout per session (defense against HNSW exhaustion attacks)
-- ---------------------------------------------------------------------------

ALTER ROLE authenticator SET statement_timeout = '2000ms';
ALTER ROLE anon         SET statement_timeout = '2000ms';

COMMIT;
