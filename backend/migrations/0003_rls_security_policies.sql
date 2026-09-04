-- =============================================================================
-- MIGRATION 0003: Row-Level Security Policies
-- =============================================================================
-- Run after 0002_postgis_pgvector.sql
-- Enforces database-layer multi-tenant isolation. Even a missing WHERE clause
-- in application code cannot leak cross-user data when RLS is active.
--
-- Supabase auth.uid() returns the UUID of the currently authenticated user
-- via the JWT claims set by the Supabase auth gateway. For direct asyncpg
-- connections from FastAPI, RLS is bypassed by the service_role key;
-- the application-layer ownership checks in each router are the primary gate.
-- RLS is a defense-in-depth fallback for any query that reaches Postgres
-- through the Supabase REST or Realtime layers.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Interactions
-- ---------------------------------------------------------------------------

ALTER TABLE interactions ENABLE ROW LEVEL SECURITY;

-- Actor can read their own sent interactions
CREATE POLICY interactions_actor_read ON interactions
    FOR SELECT
    USING (auth.uid() = actor_id);

-- Actor can insert only as themselves
CREATE POLICY interactions_actor_insert ON interactions
    FOR INSERT
    WITH CHECK (auth.uid() = actor_id);

-- Actor can update only their own records (e.g. retract a like - future feature)
CREATE POLICY interactions_actor_update ON interactions
    FOR UPDATE
    USING (auth.uid() = actor_id);

-- ---------------------------------------------------------------------------
-- 2. Matches
-- ---------------------------------------------------------------------------

ALTER TABLE matches ENABLE ROW LEVEL SECURITY;

-- Only users who are part of the match can view it
CREATE POLICY matches_participant_read ON matches
    FOR SELECT
    USING (auth.uid() = user_a OR auth.uid() = user_b);

-- Matches are created only via the application service role; no direct insert
-- from clients. Block all direct inserts.
CREATE POLICY matches_no_direct_insert ON matches
    FOR INSERT
    WITH CHECK (FALSE);

-- ---------------------------------------------------------------------------
-- 3. Chats
-- ---------------------------------------------------------------------------

ALTER TABLE chats ENABLE ROW LEVEL SECURITY;

CREATE POLICY chats_participant_read ON chats
    FOR SELECT
    USING (auth.uid() = participant_a OR auth.uid() = participant_b);

CREATE POLICY chats_no_direct_insert ON chats
    FOR INSERT
    WITH CHECK (FALSE);

-- ---------------------------------------------------------------------------
-- 4. Messages
-- ---------------------------------------------------------------------------

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- Only participants of the parent chat may read messages
CREATE POLICY messages_participant_read ON messages
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM chats c
            WHERE c.id = messages.chat_id
              AND (c.participant_a = auth.uid() OR c.participant_b = auth.uid())
        )
    );

-- Sender must be the authenticated user AND the chat must still be active
CREATE POLICY messages_sender_insert ON messages
    FOR INSERT
    WITH CHECK (
        sender_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM chats c
            JOIN matches m ON m.id = c.match_id
            WHERE c.id = messages.chat_id
              AND (c.participant_a = auth.uid() OR c.participant_b = auth.uid())
              AND c.is_unmatched = FALSE
              AND m.status != 'expired'
        )
    );

-- ---------------------------------------------------------------------------
-- 5. User Behavior Vectors
-- ---------------------------------------------------------------------------

ALTER TABLE user_behavior_vectors ENABLE ROW LEVEL SECURITY;

-- Users can read only their own behavioral vectors
CREATE POLICY ubv_self_read ON user_behavior_vectors
    FOR SELECT
    USING (auth.uid() = user_id);

-- No direct writes; vectors are updated only by the background telemetry worker
-- via service_role connection (bypasses RLS).
CREATE POLICY ubv_no_direct_write ON user_behavior_vectors
    FOR INSERT
    WITH CHECK (FALSE);

-- ---------------------------------------------------------------------------
-- 6. User Media
-- ---------------------------------------------------------------------------

ALTER TABLE user_media ENABLE ROW LEVEL SECURITY;

-- Public CDN URLs are served via CloudFront; read is unrestricted by RLS.
-- However, s3_key (the quarantine path) must be private.
-- Allow any authenticated user to read CDN URLs (needed for feed rendering).
CREATE POLICY user_media_authenticated_read ON user_media
    FOR SELECT
    USING (auth.uid() IS NOT NULL);

-- Only owner can initiate a media record (the media router creates the row)
CREATE POLICY user_media_owner_insert ON user_media
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Only owner can delete their own media
CREATE POLICY user_media_owner_delete ON user_media
    FOR DELETE
    USING (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 7. Consent Records
-- ---------------------------------------------------------------------------

ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY consent_self_read ON consent_records
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY consent_self_insert ON consent_records
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 8. Dilemma Votes
-- ---------------------------------------------------------------------------

ALTER TABLE dilemma_votes ENABLE ROW LEVEL SECURITY;

-- Read all votes (aggregated counts shown in UI)
CREATE POLICY dilemma_votes_read ON dilemma_votes
    FOR SELECT
    USING (auth.uid() IS NOT NULL);

-- Can only vote as yourself
CREATE POLICY dilemma_votes_insert ON dilemma_votes
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 9. Users table: restrict cross-user raw data access
--    Private columns (location geometry, compatibility_embedding) must never
--    be returned to another user's Supabase session.
-- ---------------------------------------------------------------------------

ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Public read: limited fields - the feed API assembles public profiles
-- separately via service_role; this policy is for direct Supabase queries.
-- Authenticated users can see other profiles (public data only via view).
CREATE POLICY users_public_read ON users
    FOR SELECT
    USING (
        account_status = 'active'
        AND is_paused = FALSE
        AND auth.uid() IS NOT NULL
    );

-- Full own profile read
CREATE POLICY users_self_read ON users
    FOR SELECT
    USING (auth.uid() = id);

-- Own profile update only
CREATE POLICY users_self_update ON users
    FOR UPDATE
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- ---------------------------------------------------------------------------
-- 10. Create a public profile view that explicitly excludes private columns.
--     Feed-level queries use service_role and do projection in SQL; this view
--     is an additional safety net for any PostgREST access.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW public_profiles AS
    SELECT
        id,
        first_name,
        city,
        state,
        gender,
        date_of_birth,
        dietary_strictness,
        eats_root_vegetables,
        eats_onion_garlic,
        community_sect,
        paryushan_mode,
        job_title,
        education,
        height_cm,
        bio,
        open_to_relocation,
        subscription_tier,
        impressions_last_48h,
        is_photo_verified,
        account_status,
        created_at
        -- location (geometry), compatibility_embedding (vector), and
        -- phone_number are intentionally omitted
    FROM users;

COMMIT;
