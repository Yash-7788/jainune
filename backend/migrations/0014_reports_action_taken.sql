-- 0014_reports_action_taken.sql
-- Add action_taken column to reports table for confirmed report tracking and audit trail

ALTER TABLE reports ADD COLUMN IF NOT EXISTS action_taken VARCHAR(32) DEFAULT 'no_action';

CREATE INDEX IF NOT EXISTS idx_reports_confirmed ON reports (reported_id, resolved, action_taken);
