-- Migration 0009: Add performance indexes on chats, matches, and active users
-- Fixes full table scans on GET /v1/chats, feed matching, and user lookups.

-- Index chats participants for fast thread list queries
CREATE INDEX IF NOT EXISTS idx_chats_p1 ON chats(participant_1_id);
CREATE INDEX IF NOT EXISTS idx_chats_p2 ON chats(participant_2_id);

-- Index matches participants for fast match lookups
CREATE INDEX IF NOT EXISTS idx_matches_u1 ON matches(user_id_1);
CREATE INDEX IF NOT EXISTS idx_matches_u2 ON matches(user_id_2);
CREATE INDEX IF NOT EXISTS idx_matches_ua ON matches(user_a_id);
CREATE INDEX IF NOT EXISTS idx_matches_ub ON matches(user_b_id);

-- Index active users for fast non-sequential sampling
CREATE INDEX IF NOT EXISTS idx_users_account_status_id ON users(account_status, id);
