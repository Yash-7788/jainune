-- Migration 0025: FINDING-04 Chat message idempotency key and deduplication index
ALTER TABLE messages ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_chat_sender_idempotency
    ON messages (chat_id, sender_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
