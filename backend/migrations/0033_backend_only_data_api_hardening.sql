-- Jainune clients use the backend API, not direct Supabase table access.
-- Keep sensitive legacy tables and the migration ledger unavailable to
-- Supabase's anon/authenticated Data API roles while preserving the backend's
-- privileged Postgres connection.

ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_green_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_prompts ENABLE ROW LEVEL SECURITY;
ALTER TABLE dilemma_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;

-- The older users_public_read policy grants rows to any signed-in caller; it
-- cannot hide phone numbers and FCM tokens without column restrictions.
-- All user/profile reads and writes already pass through the backend API.
ALTER VIEW public_profiles SET (security_invoker = true);
REVOKE ALL ON TABLE users, refresh_tokens, user_green_flags, user_photos,
    user_prompts, dilemma_questions, schema_migrations, public_profiles FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL ON TABLE users, refresh_tokens, user_green_flags, '
                || 'user_photos, user_prompts, dilemma_questions, '
                || 'schema_migrations, public_profiles FROM %I', api_role
            );
        END IF;
    END LOOP;
END
$$;
