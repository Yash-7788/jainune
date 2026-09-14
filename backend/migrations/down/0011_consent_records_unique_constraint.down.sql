ALTER TABLE consent_records DROP CONSTRAINT IF EXISTS consent_records_user_type_unique;
ALTER TABLE consent_records DROP COLUMN IF EXISTS updated_at;
