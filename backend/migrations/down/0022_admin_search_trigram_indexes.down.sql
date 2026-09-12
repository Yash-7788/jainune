-- Migration 0022 Down: Admin Search Trigram Indexes

DROP INDEX IF EXISTS idx_users_phone_number_trgm;
DROP INDEX IF EXISTS idx_users_first_name_trgm;
