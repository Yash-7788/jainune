-- Migration 0011: consent_records unique constraint + updated_at column
-- Required for the step-21 consent upsert (ON CONFLICT (user_id, consent_type) DO UPDATE).
-- Without this unique constraint the ON CONFLICT target is undefined and Postgres raises an error.

-- 1. Add updated_at column (referenced in the DO UPDATE SET clause)
ALTER TABLE consent_records
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 2. Deduplicate any existing rows before adding the constraint.
--    Keep the most-recent record per (user_id, consent_type) pair.
DELETE FROM consent_records cr
WHERE cr.id NOT IN (
    SELECT DISTINCT ON (user_id, consent_type) id
    FROM consent_records
    ORDER BY user_id, consent_type, recorded_at DESC
);

-- 3. Add the unique constraint so ON CONFLICT (user_id, consent_type) resolves correctly.
ALTER TABLE consent_records
    ADD CONSTRAINT consent_records_user_type_unique UNIQUE (user_id, consent_type);
