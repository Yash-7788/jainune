-- Migration 0018: interactions actor_id, target_id unique constraint (BUG-061)
-- Required for record_interaction_action upsert:
-- ON CONFLICT (actor_id, target_id) DO UPDATE ...
-- Ensures unique constraint exists regardless of schema migration history.

-- 1. Deduplicate any duplicate interactions if present, keeping most recent
DELETE FROM interactions i
WHERE i.id NOT IN (
    SELECT DISTINCT ON (actor_id, target_id) id
    FROM interactions
    ORDER BY actor_id, target_id, created_at DESC
);

-- 2. Add unique constraint idempotently
DO $$
BEGIN
    ALTER TABLE interactions
        ADD CONSTRAINT uq_interactions_actor_target UNIQUE (actor_id, target_id);
EXCEPTION
    WHEN duplicate_table OR duplicate_object THEN
        RAISE NOTICE 'Unique constraint on interactions(actor_id, target_id) already exists, skipping.';
END $$;

