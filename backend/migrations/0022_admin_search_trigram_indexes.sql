-- Migration 0022: Admin Search Trigram Indexes
-- Optimizes substring/prefix search on users(first_name) and users(phone_number) (SECOND-031)

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_users_first_name_trgm
    ON users USING gin (first_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_users_phone_number_trgm
    ON users USING gin (phone_number gin_trgm_ops);
