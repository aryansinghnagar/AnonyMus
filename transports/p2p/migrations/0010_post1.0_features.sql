-- Migration 0010: Post-1.0 features (Channels, Abuse Reports, Supporter Badges)
-- Add is_channel to groups
ALTER TABLE groups ADD COLUMN is_channel INTEGER NOT NULL DEFAULT 0;

-- Create abuse_reports table
CREATE TABLE IF NOT EXISTS abuse_reports (
    report_id TEXT PRIMARY KEY,
    message_hash TEXT NOT NULL,
    reporter_onion TEXT NOT NULL,
    reason TEXT,
    signature TEXT NOT NULL,
    timestamp INTEGER NOT NULL
);

-- Create supporter_badges table
CREATE TABLE IF NOT EXISTS supporter_badges (
    onion_address TEXT PRIMARY KEY,
    badge_signature TEXT NOT NULL,
    signed_by_key TEXT NOT NULL,
    timestamp INTEGER NOT NULL
);
