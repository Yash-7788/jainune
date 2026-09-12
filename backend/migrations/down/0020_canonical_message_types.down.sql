-- Down Migration 0020: Revert canonical message types reconciliation

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_message_type_check;
ALTER TABLE messages ADD CONSTRAINT messages_message_type_check
    CHECK (message_type IN ('text', 'voice', 'bounty', 'date_card', 'exit'));
