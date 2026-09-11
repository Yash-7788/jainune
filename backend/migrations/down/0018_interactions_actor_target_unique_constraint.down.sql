-- Down migration 0018: drop interactions actor_id, target_id unique constraint
ALTER TABLE interactions DROP CONSTRAINT IF EXISTS uq_interactions_actor_target;
