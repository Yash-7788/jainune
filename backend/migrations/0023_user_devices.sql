-- Migration 0023: User devices table for multi-device push notification support
CREATE TABLE IF NOT EXISTS user_devices (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(256) NOT NULL,
    device_id VARCHAR(128),
    platform VARCHAR(32) DEFAULT 'unknown',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, token)
);

CREATE INDEX IF NOT EXISTS idx_user_devices_token ON user_devices(token);
CREATE INDEX IF NOT EXISTS idx_user_devices_user_id ON user_devices(user_id);

-- Backfill existing tokens from users table
INSERT INTO user_devices (user_id, token, created_at, updated_at)
SELECT id, fcm_token, NOW(), NOW()
FROM users
WHERE fcm_token IS NOT NULL AND fcm_token != ''
ON CONFLICT (user_id, token) DO NOTHING;
