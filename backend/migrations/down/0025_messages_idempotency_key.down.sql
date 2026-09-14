-- Down Migration 0025: Drop idempotency_key index and column
DROP INDEX IF EXISTS idx_messages_chat_sender_idempotency;
ALTER TABLE messages DROP COLUMN IF EXISTS idempotency_key;
