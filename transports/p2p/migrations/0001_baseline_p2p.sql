CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    onion_address TEXT PRIMARY KEY,
    nickname TEXT NOT NULL,
    shared_secret TEXT,
    peer_public_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending_outgoing'
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_onion TEXT NOT NULL,
    sender TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (peer_onion) REFERENCES contacts(onion_address) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_peer_timestamp
ON messages (peer_onion, timestamp);
