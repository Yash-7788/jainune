-- 0013_financial_records_retention.sql
-- RBI Master Directions & DPDP Act 2023 Compliance:
-- Retain financial transaction records for 7 years even upon user account erasure.

CREATE TABLE IF NOT EXISTS financial_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_user_id UUID,
    transaction_type VARCHAR(32) NOT NULL, -- 'subscription_intent', 'arcade_purchase'
    reference_id VARCHAR(64) UNIQUE NOT NULL, -- razorpay_payment_id or razorpay_order_id
    razorpay_order_id VARCHAR(64),
    razorpay_payment_id VARCHAR(64),
    plan_id VARCHAR(64),
    amount_inr NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'INR',
    status VARCHAR(24) NOT NULL,
    captured_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retention_until TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 years')
);

CREATE INDEX IF NOT EXISTS idx_financial_audit_user ON financial_audit_logs (original_user_id);
CREATE INDEX IF NOT EXISTS idx_financial_audit_ref ON financial_audit_logs (reference_id);
CREATE INDEX IF NOT EXISTS idx_financial_audit_retention ON financial_audit_logs (retention_until);

-- Make user_id nullable in payment_intents and arcade_transactions to prevent cascade destruction of audit logs
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'payment_intents_user_id_fkey'
    ) THEN
        ALTER TABLE payment_intents ALTER COLUMN user_id DROP NOT NULL;
        ALTER TABLE payment_intents DROP CONSTRAINT payment_intents_user_id_fkey;
        ALTER TABLE payment_intents ADD CONSTRAINT payment_intents_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'arcade_transactions_user_id_fkey'
    ) THEN
        ALTER TABLE arcade_transactions ALTER COLUMN user_id DROP NOT NULL;
        ALTER TABLE arcade_transactions DROP CONSTRAINT arcade_transactions_user_id_fkey;
        ALTER TABLE arcade_transactions ADD CONSTRAINT arcade_transactions_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;
