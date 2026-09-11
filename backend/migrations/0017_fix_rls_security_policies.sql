-- =============================================================================
-- MIGRATION 0017: Reconciled Row-Level Security Policies (BUG-009)
-- =============================================================================
-- Drops and recreates matches, chats, and messages policies using COALESCE
-- to support both legacy (user_a, participant_a) and reconciled (user_id_1, participant_1_id)
-- column names across all PostgreSQL deployment states.
-- =============================================================================

BEGIN;

-- Matches: drop and recreate participant read
DROP POLICY IF EXISTS matches_participant_read ON matches;
CREATE POLICY matches_participant_read ON matches
    FOR SELECT
    USING (auth.uid() = COALESCE(user_id_1, user_a) OR auth.uid() = COALESCE(user_id_2, user_b));

-- Chats: drop and recreate participant read
DROP POLICY IF EXISTS chats_participant_read ON chats;
CREATE POLICY chats_participant_read ON chats
    FOR SELECT
    USING (auth.uid() = COALESCE(participant_1_id, participant_a) OR auth.uid() = COALESCE(participant_2_id, participant_b));

-- Messages: drop and recreate participant read and sender insert
DROP POLICY IF EXISTS messages_participant_read ON messages;
CREATE POLICY messages_participant_read ON messages
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM chats c
            WHERE c.id = messages.chat_id
              AND (COALESCE(c.participant_1_id, c.participant_a) = auth.uid() OR COALESCE(c.participant_2_id, c.participant_b) = auth.uid())
        )
    );

DROP POLICY IF EXISTS messages_sender_insert ON messages;
CREATE POLICY messages_sender_insert ON messages
    FOR INSERT
    WITH CHECK (
        sender_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM chats c
            JOIN matches m ON m.id = c.match_id
            WHERE c.id = messages.chat_id
              AND (COALESCE(c.participant_1_id, c.participant_a) = auth.uid() OR COALESCE(c.participant_2_id, c.participant_b) = auth.uid())
              AND c.is_unmatched = FALSE
              AND m.status != 'expired'
        )
    );

COMMIT;
