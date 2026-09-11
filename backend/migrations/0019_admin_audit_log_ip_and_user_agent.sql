-- Migration 0019: Add ip_address and user_agent to admin_audit_log for forensic auditability (BUG-093)
ALTER TABLE admin_audit_log
    ADD COLUMN IF NOT EXISTS ip_address INET,
    ADD COLUMN IF NOT EXISTS user_agent TEXT;
