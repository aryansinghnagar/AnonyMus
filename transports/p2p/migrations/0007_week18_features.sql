-- Migration 0007: Week 18 features (recipient chosen relays, edits, deletes, receipts)
ALTER TABLE contacts ADD COLUMN preferred_file_relay TEXT;
ALTER TABLE contacts ADD COLUMN send_receipts INTEGER DEFAULT 1;
ALTER TABLE messages ADD COLUMN delivery_state TEXT DEFAULT 'sent';

CREATE TABLE IF NOT EXISTS message_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_onion TEXT NOT NULL,
    target_timestamp INTEGER NOT NULL,
    old_text TEXT NOT NULL,
    edit_timestamp INTEGER NOT NULL
);
