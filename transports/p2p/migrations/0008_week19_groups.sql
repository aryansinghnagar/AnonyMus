CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    founder_onion TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id TEXT NOT NULL,
    member_onion TEXT NOT NULL,
    nickname TEXT NOT NULL,
    invited_by TEXT,
    role TEXT NOT NULL DEFAULT 'member', -- founder, admin, member
    joined_at INTEGER NOT NULL,
    PRIMARY KEY (group_id, member_onion),
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS group_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,
    sender_onion TEXT NOT NULL,
    sender_nickname TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS group_invites (
    invite_token TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    used_at INTEGER,
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS member_vouches (
    group_id TEXT NOT NULL,
    vouching_member TEXT NOT NULL,
    vouched_member TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    PRIMARY KEY (group_id, vouching_member, vouched_member),
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);
