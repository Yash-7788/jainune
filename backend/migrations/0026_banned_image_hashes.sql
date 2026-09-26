-- Migration: 0026 — banned_image_hashes table for perceptual hash deduplication
-- Purpose: Store dHash fingerprints of rejected photos for 0ms instant future rejection.
-- Avoids re-spending Cloudflare Neurons on re-uploaded banned content.

CREATE TABLE IF NOT EXISTS banned_image_hashes (
    dhash       TEXT        PRIMARY KEY,        -- 16-char hex dHash fingerprint
    reason      TEXT        NOT NULL,           -- nudity / csam / weapon / gore / contact / ad / celebrity / morph
    confidence  REAL        NOT NULL DEFAULT 0.95,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Internal moderation fingerprints must not be readable through the Data API.
ALTER TABLE banned_image_hashes ENABLE ROW LEVEL SECURITY;

-- GIN index for bulk LIKE/contains if needed later (no-op for exact match, covered by PK)
COMMENT ON TABLE banned_image_hashes IS
    'Perceptual hash fingerprints of AI-rejected photos. Checked in-memory (O(1)) pre-API.';
