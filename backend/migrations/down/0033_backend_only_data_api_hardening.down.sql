-- Keep backend-only Data API restrictions during rollback. Regranting direct
-- access would expose token hashes, private profile data, and migration state.
SELECT 1;
