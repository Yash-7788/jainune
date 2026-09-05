-- =============================================================================
-- MIGRATION 0006: Complete Monetization, Arcade Ledger, and Schema Reconciliation
-- =============================================================================

BEGIN;

-- 1. Users table additions
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS subscription_valid_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS trust_score NUMERIC(5, 2) NOT NULL DEFAULT 50.00,
    ADD COLUMN IF NOT EXISTS super_connect_credits INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS suspend_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS fcm_token VARCHAR(256);

CREATE INDEX IF NOT EXISTS idx_users_sub_valid ON users (subscription_valid_until)
    WHERE subscription_tier != 'free';
CREATE INDEX IF NOT EXISTS idx_users_fcm ON users (fcm_token)
    WHERE fcm_token IS NOT NULL AND fcm_token != '';

-- 2. Payment intents table (Razorpay orders & webhook idempotency)
CREATE TABLE IF NOT EXISTS payment_intents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    razorpay_order_id VARCHAR(64) UNIQUE NOT NULL,
    razorpay_payment_id VARCHAR(64) UNIQUE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id VARCHAR(64) NOT NULL,
    amount INT NOT NULL, -- in paise
    currency VARCHAR(8) NOT NULL DEFAULT 'INR',
    status VARCHAR(24) NOT NULL DEFAULT 'created', -- 'created', 'captured', 'refunded', 'failed'
    captured_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_intents_user ON payment_intents (user_id);
CREATE INDEX IF NOT EXISTS idx_payment_intents_order ON payment_intents (razorpay_order_id);

-- 3. Serendipity Arcade Wallet & Transactions
CREATE TABLE IF NOT EXISTS user_arcade_wallet (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    available_spins INT NOT NULL DEFAULT 0,
    available_dice_rolls INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arcade_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action_type VARCHAR(32) NOT NULL, -- 'wheel_spin', 'dice_roll', 'arcade_3_pack', 'spend_spin', 'spend_roll'
    amount_inr NUMERIC(6,2) NOT NULL DEFAULT 0.00,
    spins_delta INT NOT NULL DEFAULT 0,
    dice_rolls_delta INT NOT NULL DEFAULT 0,
    razorpay_order_id VARCHAR(64),
    razorpay_payment_id VARCHAR(64),
    status VARCHAR(24) NOT NULL DEFAULT 'captured', -- 'captured', 'spent', 'refunded'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arcade_tx_user ON arcade_transactions (user_id);

-- 4. User Media status & lifecycle columns
ALTER TABLE user_media
    ADD COLUMN IF NOT EXISTS status VARCHAR(24) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
    ADD COLUMN IF NOT EXISTS s3_purged BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_user_media_purge ON user_media (status, s3_purged, created_at);

-- 5. Reconcile Matches table
ALTER TABLE matches
    DROP CONSTRAINT IF EXISTS matches_status_check;

ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS user_id_1 UUID REFERENCES users(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS user_id_2 UUID REFERENCES users(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS user_a_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS user_b_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS match_type VARCHAR(32) NOT NULL DEFAULT 'mutual_like',
    ADD COLUMN IF NOT EXISTS chat_id UUID,
    ADD COLUMN IF NOT EXISTS expiry_warned BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS expired_at TIMESTAMPTZ;

-- Backfill user aliases
UPDATE matches
   SET user_id_1 = user_a,
       user_id_2 = user_b,
       user_a_id = user_a,
       user_b_id = user_b
 WHERE user_id_1 IS NULL AND user_a IS NOT NULL;

-- 6. Reconcile Chats table
ALTER TABLE chats
    ADD COLUMN IF NOT EXISTS participant_1_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS participant_2_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

UPDATE chats
   SET participant_1_id = participant_a,
       participant_2_id = participant_b
 WHERE participant_1_id IS NULL AND participant_a IS NOT NULL;

-- 7. Reconcile Interactions table
ALTER TABLE interactions
    DROP CONSTRAINT IF EXISTS interactions_interaction_type_check;

ALTER TABLE interactions
    ADD COLUMN IF NOT EXISTS action_type VARCHAR(24),
    ADD COLUMN IF NOT EXISTS reacted_prompt_id UUID;

UPDATE interactions
   SET action_type = interaction_type
 WHERE action_type IS NULL AND interaction_type IS NOT NULL;

-- 8. Dignity Engine Reports & Audit Logs
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reported_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason VARCHAR(64) NOT NULL,
    detail TEXT,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_reported ON reports (reported_id, resolved);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports (created_at DESC);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(64) NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_user ON admin_audit_log (target_user_id);

CREATE TABLE IF NOT EXISTS dignity_badges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (from_user_id, to_user_id, badge)
);

CREATE INDEX IF NOT EXISTS idx_dignity_badges_to ON dignity_badges (to_user_id);

-- 9. Dilemmas Table for Community Arcade
CREATE TABLE IF NOT EXISTS dilemmas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_text TEXT NOT NULL,
    option_a VARCHAR(150) NOT NULL,
    option_b VARCHAR(150) NOT NULL,
    tags TEXT[] DEFAULT ARRAY[]::TEXT[],
    total_votes_a INT NOT NULL DEFAULT 0,
    total_votes_b INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. Telemetry Events & Hourly Aggregation
CREATE TABLE IF NOT EXISTS telemetry_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(64) NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    target_id UUID REFERENCES users(id) ON DELETE SET NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    meta JSONB DEFAULT '{}'::JSONB
);

CREATE INDEX IF NOT EXISTS idx_telemetry_occurred ON telemetry_events (occurred_at DESC);

CREATE TABLE IF NOT EXISTS telemetry_hourly (
    hour_bucket TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (hour_bucket, event_type)
);

-- 11. Daily Proposals (Gale-Shapley Stable Marriage)
CREATE TABLE IF NOT EXISTS daily_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_a_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_b_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score NUMERIC(6, 3) NOT NULL,
    proposed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_a_id, user_b_id)
);

CREATE INDEX IF NOT EXISTS idx_daily_proposals_pair ON daily_proposals (user_a_id, user_b_id);

COMMIT;
