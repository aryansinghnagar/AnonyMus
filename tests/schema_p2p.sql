CREATE TABLE schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE contacts (
    onion_address TEXT PRIMARY KEY,
    nickname TEXT NOT NULL,
    shared_secret TEXT,
    peer_public_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending_outgoing',
    my_onion_address TEXT,
    disappearing_ttl INTEGER,
    display_name TEXT,
    dr_state TEXT,
    peer_kem_public_key TEXT,
    my_kem_private_key TEXT,
    notify_queue_token TEXT,
    preferred_file_relay TEXT,
    send_receipts INTEGER DEFAULT 1,
    profile_id TEXT NOT NULL DEFAULT 'default'
);
CREATE TABLE notify_queue (
    token      TEXT    NOT NULL,
    arrived_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_notify_queue_token ON notify_queue (token);
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_onion TEXT NOT NULL,
    sender TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    expires_at INTEGER,
    delivery_state TEXT DEFAULT 'sent',
    FOREIGN KEY (peer_onion) REFERENCES contacts(onion_address) ON DELETE CASCADE
);
CREATE INDEX idx_messages_peer_timestamp ON messages (peer_onion, timestamp);
CREATE INDEX idx_messages_expires_at ON messages (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE message_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_onion TEXT NOT NULL,
    target_timestamp INTEGER NOT NULL,
    old_text TEXT NOT NULL,
    edit_timestamp INTEGER NOT NULL
);

CREATE TABLE groups (
    group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    founder_onion TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    profile_id TEXT NOT NULL DEFAULT 'default'
);

CREATE TABLE group_members (
    group_id TEXT NOT NULL,
    member_onion TEXT NOT NULL,
    nickname TEXT NOT NULL,
    invited_by TEXT,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at INTEGER NOT NULL,
    PRIMARY KEY (group_id, member_onion),
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

CREATE TABLE group_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,
    sender_onion TEXT NOT NULL,
    sender_nickname TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

CREATE TABLE group_invites (
    invite_token TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    used_at INTEGER,
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

CREATE TABLE member_vouches (
    group_id TEXT NOT NULL,
    vouching_member TEXT NOT NULL,
    vouched_member TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    PRIMARY KEY (group_id, vouching_member, vouched_member),
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

CREATE TABLE profiles (
    profile_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    hidden INTEGER NOT NULL DEFAULT 0,
    passphrase_hash TEXT
);
