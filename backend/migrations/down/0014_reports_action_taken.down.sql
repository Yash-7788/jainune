DROP INDEX IF EXISTS idx_reports_confirmed;
ALTER TABLE reports DROP COLUMN IF EXISTS action_taken;
