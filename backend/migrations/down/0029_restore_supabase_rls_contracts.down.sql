-- Intentionally preserve the corrected auth.uid() implementation and the
-- private user_media column boundary during rollback. Reintroducing the old
-- NULL helper or broad table SELECT would break authentication or expose keys.
SELECT 1;
