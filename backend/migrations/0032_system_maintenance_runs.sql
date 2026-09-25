-- Tracks atomic execution state of scheduled maintenance tasks
CREATE TABLE IF NOT EXISTS system_maintenance_runs (
    task_name VARCHAR(64) PRIMARY KEY,
    last_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_date_ist DATE NOT NULL,
    locked_until TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01'::timestamptz
);
ALTER TABLE system_maintenance_runs ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE ALL ON TABLE system_maintenance_runs FROM anon';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE 'REVOKE ALL ON TABLE system_maintenance_runs FROM authenticated';
    END IF;
END
$$;
