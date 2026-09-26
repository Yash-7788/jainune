-- Restore the JWT-backed Supabase auth.uid() contract. The migration runner
-- previously replaced this function with a NULL-returning local placeholder.
DO $$
BEGIN
    -- Hosted Supabase owns auth.uid() as supabase_auth_admin and already
    -- supplies the JWT-backed contract. Only repair an app-owned helper.
    IF (SELECT pg_get_userbyid(proowner)
        FROM pg_proc WHERE oid = to_regprocedure('auth.uid()')) = current_user THEN
        EXECUTE $function$
            CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
            LANGUAGE sql STABLE
            AS $body$
                SELECT COALESCE(
                    NULLIF(current_setting('request.jwt.claim.sub', true), ''),
                    NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
                )::uuid
            $body$
        $function$;
    END IF;
END
$$;

-- RLS controls rows, not columns. Keep the intended authenticated CDN/media
-- metadata read while withholding the private quarantine storage key.
REVOKE SELECT ON TABLE public.user_media FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE SELECT ON TABLE public.user_media FROM anon';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE 'REVOKE SELECT ON TABLE public.user_media FROM authenticated';
        EXECUTE 'GRANT SELECT (id, user_id, media_type, cdn_url, position, duration_seconds, is_processed, created_at) ON TABLE public.user_media TO authenticated';
    END IF;
END
$$;
