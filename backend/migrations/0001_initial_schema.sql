-- Migration: 0001_initial_schema.sql
-- Creates core user, refresh_token, and prompt tables.
-- Run AFTER enabling pgvector and postgis extensions.

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number          VARCHAR(16) UNIQUE NOT NULL,
    first_name            VARCHAR(64),
    date_of_birth         DATE,
    gender                VARCHAR(24),
    show_me               VARCHAR(24),                           -- 'men', 'women', 'everyone'

    -- Jain cultural attributes
    dietary_strictness    VARCHAR(32),                           -- 'pure_jain', 'vaishnav', 'ovo_veg', 'vegan'
    eats_root_vegetables  BOOLEAN DEFAULT FALSE,
    eats_onion_garlic     BOOLEAN DEFAULT FALSE,
    paryushan_mode        BOOLEAN DEFAULT FALSE,                 -- strict Paryushan observer flag
    community_sect        VARCHAR(32),                           -- 'digambar', 'shwetambar_deravasi', etc.
    mother_tongue         VARCHAR(32),                           -- 'gujarati', 'marwari', 'hindi', etc.

    -- Location (PostGIS point snapped to Geohash-6 centroid via trigger)
    city                  VARCHAR(64),
    state                 VARCHAR(64),
    max_distance_km       INT DEFAULT 25,
    open_to_relocation    BOOLEAN DEFAULT FALSE,

    -- Education / Profession
    education             VARCHAR(128),
    profession            VARCHAR(128),
    employer              VARCHAR(128),
    annual_income_range   VARCHAR(32),

    -- Account state
    account_status        VARCHAR(24) NOT NULL DEFAULT 'active', -- 'active', 'banned', 'deleted'
    onboarding_completed  BOOLEAN DEFAULT FALSE,
    onboarding_step       INT DEFAULT 0,
    is_photo_verified     BOOLEAN DEFAULT FALSE,
    subscription_tier     VARCHAR(24) NOT NULL DEFAULT 'free',   -- 'free', 'jainune_plus'

    -- Algo state
    impressions_last_48h  INT DEFAULT 0,
    embedding             vector(128),                           -- pgvector 128-d behavioral embedding

    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone_number);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(account_status);

-- ── Refresh Tokens ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS refresh_tokens (
    user_id     UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64) NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── User Prompts ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_prompts (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID REFERENCES users(id) ON DELETE CASCADE,
    prompt_key            VARCHAR(64) NOT NULL,
    response_text         VARCHAR(200),
    audio_s3_url          VARCHAR(512),
    audio_duration_seconds NUMERIC(4, 2),
    position              INT NOT NULL,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompts_user ON user_prompts(user_id);

-- ── User Photos ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_photos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    s3_key      VARCHAR(512) NOT NULL,
    cdn_url     VARCHAR(512),
    position    INT NOT NULL,
    is_primary  BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_photos_user ON user_photos(user_id, position);

-- ── updated_at trigger ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
