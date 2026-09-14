DROP INDEX IF EXISTS idx_interactions_target_liked_cursor;
ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_status_check;
ALTER TABLE matches ADD CONSTRAINT matches_status_check CHECK (status IN ('active','unmatched','expired'));
