-- 0003_disappearing_messages.sql
-- Adds disappearing message support (10.D.1).
-- expires_at: Unix timestamp (ms) after which the message is auto-deleted.
--             NULL means the message never expires.
-- disappearing_ttl column on contacts: per-contact TTL in milliseconds (NULL = off).

ALTER TABLE messages ADD COLUMN expires_at INTEGER;

ALTER TABLE contacts ADD COLUMN disappearing_ttl INTEGER;

CREATE INDEX IF NOT EXISTS idx_messages_expires_at
ON messages (expires_at)
WHERE expires_at IS NOT NULL;
