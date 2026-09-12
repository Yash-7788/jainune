-- Migration 0020: Canonical message types reconciliation
-- Reconciles messages.message_type CHECK constraint with backend Pydantic schema and mobile client

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_message_type_check;
ALTER TABLE messages ADD CONSTRAINT messages_message_type_check
    CHECK (message_type IN ('text', 'photo', 'voice', 'gif', 'dilemma_invite', 'bounty', 'date_card', 'exit'));
