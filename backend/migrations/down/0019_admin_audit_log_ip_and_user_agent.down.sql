-- Rollback Migration 0019
ALTER TABLE admin_audit_log
    DROP COLUMN IF EXISTS ip_address,
    DROP COLUMN IF EXISTS user_agent;
