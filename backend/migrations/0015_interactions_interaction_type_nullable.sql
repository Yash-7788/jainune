-- 0015_interactions_interaction_type_nullable.sql
-- Drop NOT NULL constraint on legacy interaction_type column superseded by action_type.
-- Set DEFAULT 'like' for backward-compatible fallback.

ALTER TABLE interactions ALTER COLUMN interaction_type DROP NOT NULL;
ALTER TABLE interactions ALTER COLUMN interaction_type SET DEFAULT 'like';
