-- =============================================================================
-- ROLLBACK MIGRATION 0003: Row-Level Security Policies
-- =============================================================================

BEGIN;

DROP POLICY IF EXISTS interactions_actor_read ON interactions;
DROP POLICY IF EXISTS interactions_actor_insert ON interactions;
DROP POLICY IF EXISTS interactions_actor_update ON interactions;
ALTER TABLE interactions DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS matches_participant_read ON matches;
DROP POLICY IF EXISTS matches_no_direct_insert ON matches;
ALTER TABLE matches DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS chats_participant_read ON chats;
DROP POLICY IF EXISTS chats_no_direct_insert ON chats;
ALTER TABLE chats DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS messages_participant_read ON messages;
DROP POLICY IF EXISTS messages_participant_insert ON messages;
ALTER TABLE messages DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_select_active ON users;
DROP POLICY IF EXISTS users_self_all ON users;
ALTER TABLE users DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS prompts_self ON user_prompts;
ALTER TABLE user_prompts DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS photos_self ON user_photos;
ALTER TABLE user_photos DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS refresh_tokens_self ON refresh_tokens;
ALTER TABLE refresh_tokens DISABLE ROW LEVEL SECURITY;

COMMIT;
