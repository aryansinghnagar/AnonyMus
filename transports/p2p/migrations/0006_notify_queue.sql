-- Migration 0006: Notification Queue (10.H.3)
-- Adds a zero-content notification flag queue.
-- The notify_queue_token is a random 32-byte value (base64) shared only between
-- the device and its own server. NO message content ever enters this table.

ALTER TABLE contacts ADD COLUMN notify_queue_token TEXT; -- base64-encoded 32-byte random token

CREATE TABLE IF NOT EXISTS notify_queue (
    token      TEXT    NOT NULL,
    arrived_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_notify_queue_token ON notify_queue (token);
