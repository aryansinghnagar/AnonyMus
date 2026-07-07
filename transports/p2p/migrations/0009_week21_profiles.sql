CREATE TABLE IF NOT EXISTS profiles (
    profile_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    hidden INTEGER NOT NULL DEFAULT 0,
    passphrase_hash TEXT
);

-- Insert a default profile
INSERT OR IGNORE INTO profiles (profile_id, display_name, hidden) VALUES ('default', 'Default Profile', 0);

-- Alter contacts and groups to add profile_id column
-- Wrap in try-catch/silent errors during migration to avoid crashing if already run
ALTER TABLE contacts ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE groups ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'default';
