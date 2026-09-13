-- Migration 0024: N-14 matches status constraint + N-27 pagination index
ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_status_check;
ALTER TABLE matches ADD CONSTRAINT matches_status_check CHECK (status IN ('active','unmatched','expired','matched'));
CREATE INDEX IF NOT EXISTS idx_interactions_target_liked_cursor ON interactions (target_id, created_at DESC) WHERE action_type IN ('like','super_connect');
