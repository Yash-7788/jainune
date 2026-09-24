-- Keep the widened transaction identity column on rollback: verified Google
-- purchase tokens may exceed the former VARCHAR(128) limit.
SELECT 1;
