"""
Database Management Module for AnonyMus (P2P Decentralized Architecture).

Coordinates local SQLite database connection configurations (WAL mode).
Stores local credentials (master password hash), remote contacts, E2EE keys,
and encrypted message logs. Includes AES-GCM encryption helper functions
to protect negotiated shared secrets on disk.
"""

import os
import sqlite3
import time

import bcrypt

# Database file location for the local P2P node
DB_FILE = os.environ.get("DB_FILE", "local_node.db")

# Pre-calculate dummy hash for timing attacks mitigation during credentials check
DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode("utf-8")


import queue
import threading

_pool = None
_pool_lock = threading.Lock()
_all_pools = []


class BoundedSQLitePool:
    def __init__(self, db_file, max_connections=5):
        self.db_file = db_file
        self.max_connections = max_connections
        self.queue = queue.Queue(maxsize=max_connections)
        self.created = 0
        self.lock = threading.Lock()
        self.active_conns = set()
        global _all_pools
        _all_pools.append(self)

    def get(self):
        try:
            conn = self.queue.get_nowait()
            return conn
        except queue.Empty:
            with self.lock:
                if self.created < self.max_connections:
                    conn = sqlite3.connect(self.db_file, check_same_thread=False)
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA busy_timeout=5000")
                    conn.execute("PRAGMA foreign_keys = ON")
                    self.created += 1
                    self.active_conns.add(conn)
                    return conn
            conn = self.queue.get(timeout=10)
            return conn

    def put(self, conn):
        try:
            self.queue.put_nowait(conn)
        except queue.Full:
            conn.close()
            with self.lock:
                self.created -= 1
                self.active_conns.discard(conn)


class PooledConnection:
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._released = False

    def close(self):
        if not self._released:
            self._released = True
            self._pool.put(self._conn)

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._conn.__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_connection():
    """
    Retrieves a connection from the SQLite connection pool.
    Returns a PooledConnection wrapper that returns the connection back to the pool on close.
    """
    global _pool
    if _pool is None or _pool.db_file != DB_FILE:
        with _pool_lock:
            if _pool is None or _pool.db_file != DB_FILE:
                if _pool is not None:
                    # Close connections in the old pool
                    for conn in list(_pool.active_conns):
                        try:
                            conn.close()
                        except Exception:
                            pass
                _pool = BoundedSQLitePool(DB_FILE)

    conn = _pool.get()
    return PooledConnection(conn, _pool)


def close_pool():
    """
    Closes all active database connections in all connection pools and resets.
    Useful for releasing file locks in test teardown/setup on Windows.
    """
    global _pool, _all_pools
    for p in list(_all_pools):
        for conn in list(p.active_conns):
            try:
                conn.close()
            except Exception:
                pass
        p.active_conns.clear()
        while not p.queue.empty():
            try:
                p.queue.get_nowait()
            except Exception:
                pass
    _all_pools.clear()
    _pool = None


from core.crypto import decrypt_secret, encrypt_secret


def init_db():
    """
    Initializes local SQLite schema by running migrations.
    """
    from core.migrations import run_migrations

    conn = get_connection()
    migrations_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()


def is_initialized():
    """
    Checks if a local user profile password hash exists in the database.

    Returns:
        bool: True if profile is initialized, False otherwise.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT 1 FROM config WHERE key = ?", ("password_hash",))
    row = c.fetchone()
    conn.close()
    return row is not None


def register_local_user(username, password):
    """
    Initializes local credentials on the first run of the node.

    Hashes password using bcrypt and registers it along with the local username.

    Args:
        username (str): Local username.
        password (str): Local master password.

    Returns:
        dict: Dict containing 'success': True or 'error': str description of failure.
    """
    if is_initialized():
        return {"error": "Local database is already initialized."}
    if not username or len(username) < 3 or len(username) > 50:
        return {"error": "Username must be between 3 and 50 characters."}
    if len(password) < 8:
        return {"error": "Password must be at least 8 characters."}

    import secrets

    db_key_salt = secrets.token_hex(16)
    pwd_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)",
            ("local_username", username.lower()),
        )
        c.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)", ("password_hash", pwd_hash)
        )
        c.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)",
            ("db_key_salt", db_key_salt),
        )
        conn.commit()
        success = True
    except Exception as e:
        success = False
        print(f"Error registering local user: {e}")
    finally:
        conn.close()

    if success:
        return {"success": True}
    else:
        return {"error": "Failed to initialize local account."}


def login_local_user(username, password):
    """
    Validates local login credentials to open the control dashboard.

    Employs bcrypt check for dummy hash to mitigate timing side-channel attacks.
    Implements per-account lockout with exponential backoff.

    Args:
        username (str): Entered username.
        password (str): Entered master password.

    Returns:
        dict: Dict containing 'success': True or 'error': str credentials mismatch message.
    """
    if not is_initialized():
        return {"error": "App not initialized yet."}

    # Check lockout status first
    lockout_until_str = get_config("lockout_until")
    if lockout_until_str:
        try:
            lockout_until = float(lockout_until_str)
            remaining = lockout_until - time.time()
            if remaining > 0:
                # Dummy check to keep timings uniform
                bcrypt.checkpw(password.encode("utf-8"), DUMMY_HASH.encode("utf-8"))
                return {
                    "error": f"Account is locked. Try again in {int(remaining) + 1} seconds."
                }
        except ValueError:
            pass

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key = ?", ("password_hash",))
    row_hash = c.fetchone()
    c.execute("SELECT value FROM config WHERE key = ?", ("local_username",))
    row_user = c.fetchone()
    conn.close()

    if not row_hash or not row_user:
        return {"error": "Invalid configuration."}

    stored_hash = row_hash[0]
    stored_user = row_user[0]

    def register_failed_attempt():
        attempts_str = get_config("failed_login_attempts", "0")
        try:
            attempts = int(attempts_str) + 1
        except ValueError:
            attempts = 1
        set_config("failed_login_attempts", str(attempts))

        lock_duration = 0
        if attempts >= 20:
            lock_duration = 1800  # 30 minutes
        elif attempts >= 10:
            lock_duration = 300  # 5 minutes
        elif attempts >= 5:
            lock_duration = 60  # 1 minute

        if lock_duration > 0:
            set_config("lockout_until", str(time.time() + lock_duration))

    if username.lower() != stored_user:
        bcrypt.checkpw(password.encode("utf-8"), DUMMY_HASH.encode("utf-8"))
        register_failed_attempt()
        return {"error": "Wrong credentials."}

    if not bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
        register_failed_attempt()
        return {"error": "Wrong credentials."}

    # Success: reset failed attempts & lockout
    set_config("failed_login_attempts", "0")
    set_config("lockout_until", "")
    return {"success": True}


def get_config(key, default=None):
    """
    Retrieves a configuration value by key.

    Args:
        key (str): Config key name.
        default (any): Value to return if key is missing.

    Returns:
        str: Stored configuration value, or default value.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_config(key, value):
    """
    Saves or updates a configuration value.

    Args:
        key (str): Config key name.
        value (any): Value to write.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value))
    )
    conn.commit()
    conn.close()


def add_contact(
    onion_address,
    nickname,
    status="pending_outgoing",
    my_onion_address=None,
    display_name=None,
    dr_state=None,
    peer_kem_public_key=None,
    my_kem_private_key=None,
    profile_id="default",
):
    """
    Adds a new contact to the local database list.
    """
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT OR IGNORE INTO contacts (onion_address, nickname, status, my_onion_address, display_name, dr_state, peer_kem_public_key, my_kem_private_key, profile_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                onion_address,
                nickname,
                status,
                my_onion_address,
                display_name,
                dr_state,
                peer_kem_public_key,
                my_kem_private_key,
                profile_id,
            ),
        )
        conn.commit()
        success = True
    except Exception as e:
        success = False
        print(f"Error adding contact: {e}")
    finally:
        conn.close()
    return success


def get_contact(onion_address, db_key=None):
    """
    Queries details for a specific contact.
    """
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT onion_address, nickname, shared_secret, peer_public_key, status, my_onion_address, disappearing_ttl, display_name, dr_state, peer_kem_public_key, my_kem_private_key, preferred_file_relay, send_receipts FROM contacts WHERE onion_address = ?",
        (onion_address,),
    )
    row = c.fetchone()
    conn.close()
    if row:
        secret = row[2]
        if secret and db_key:
            secret = decrypt_secret(secret, db_key)
        return {
            "onion_address": row[0],
            "nickname": row[1],
            "shared_secret": secret,
            "peer_public_key": row[3],
            "status": row[4],
            "my_onion_address": row[5],
            "disappearing_ttl": row[6],
            "display_name": row[7],
            "dr_state": row[8],
            "peer_kem_public_key": row[9],
            "my_kem_private_key": row[10],
            "preferred_file_relay": row[11],
            "send_receipts": row[12] if len(row) > 12 else 1,
        }
    return None


def get_contacts(db_key=None, profile_id="default"):
    """
    Retrieves all contacts from the local list.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT onion_address, nickname, shared_secret, peer_public_key, status, my_onion_address, disappearing_ttl, display_name, dr_state, peer_kem_public_key, my_kem_private_key, preferred_file_relay, send_receipts FROM contacts WHERE profile_id = ?",
        (profile_id,),
    )
    rows = c.fetchall()

    c.execute("SELECT key, value FROM config WHERE key LIKE 'my_pubkey_for_%'")
    config_rows = c.fetchall()
    my_keys = {row[0].replace("my_pubkey_for_", ""): row[1] for row in config_rows}

    conn.close()

    contacts = []
    for row in rows:
        onion = row[0]
        secret = row[2]
        if secret and db_key:
            secret = decrypt_secret(secret, db_key)
        contacts.append(
            {
                "onion_address": onion,
                "nickname": row[1],
                "shared_secret": secret,
                "peer_public_key": row[3],
                "status": row[4],
                "my_public_key": my_keys.get(onion),
                "my_onion_address": row[5],
                "disappearing_ttl": row[6],
                "display_name": row[7],
                "dr_state": row[8],
                "peer_kem_public_key": row[9],
                "my_kem_private_key": row[10],
                "preferred_file_relay": row[11],
                "send_receipts": row[12] if len(row) > 12 else 1,
            }
        )
    return contacts


def update_contact_dr_state(onion_address, dr_state):
    """Updates serialized Double Ratchet session state for a contact."""
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE contacts SET dr_state = ? WHERE onion_address = ?",
        (dr_state, onion_address),
    )
    conn.commit()
    conn.close()


def update_contact_kem_keys(
    onion_address, peer_kem_public_key=None, my_kem_private_key=None
):
    """Stores ML-KEM-768 key material for a contact (used by PQ hybrid mode)."""
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    if peer_kem_public_key is not None:
        c.execute(
            "UPDATE contacts SET peer_kem_public_key = ? WHERE onion_address = ?",
            (peer_kem_public_key, onion_address),
        )
    if my_kem_private_key is not None:
        c.execute(
            "UPDATE contacts SET my_kem_private_key = ? WHERE onion_address = ?",
            (my_kem_private_key, onion_address),
        )
    conn.commit()
    conn.close()


def update_contact_display_name(onion_address, display_name):
    """Updates user display name overridden for a contact."""
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE contacts SET display_name = ? WHERE onion_address = ?",
        (display_name, onion_address),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Notification Queue (10.H.3)
# ---------------------------------------------------------------------------


def get_notify_token(onion_address: str) -> str | None:
    """Returns the notification queue token for a contact, or None if not registered."""
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT notify_queue_token FROM contacts WHERE onion_address = ?",
        (onion_address,),
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def set_notify_token(onion_address: str, token: str) -> None:
    """Stores a random notification queue token for a contact."""
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE contacts SET notify_queue_token = ? WHERE onion_address = ?",
        (token, onion_address),
    )
    conn.commit()
    conn.close()


def push_notify_queue(token: str) -> None:
    """
    Inserts a notification flag for the given token.
    Called when a new P2P message arrives for a contact that has a registered token.
    IMPORTANT: no message content is ever stored here.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO notify_queue (token) VALUES (?)", (token,))
    conn.commit()
    conn.close()


def poll_notify_queue(tokens: list[str]) -> set[str]:
    """
    Returns the subset of the given tokens that have pending notification flags.
    The Android service calls this every 30s to check for new messages.
    """
    if not tokens:
        return set()
    conn = get_connection()
    c = conn.cursor()
    placeholders = ",".join("?" * len(tokens))
    c.execute(
        f"SELECT DISTINCT token FROM notify_queue WHERE token IN ({placeholders})",
        tokens,
    )
    rows = c.fetchall()
    conn.close()
    return {row[0] for row in rows}


def clear_notify_queue(tokens: list[str]) -> None:
    """
    Clears notification flags for the given tokens.
    Called after the client has successfully pulled messages from the main queue.
    """
    if not tokens:
        return
    conn = get_connection()
    c = conn.cursor()
    placeholders = ",".join("?" * len(tokens))
    c.execute(f"DELETE FROM notify_queue WHERE token IN ({placeholders})", tokens)
    conn.commit()
    conn.close()


def update_contact_status(onion_address, status):
    """
    Updates the connection status for a contact.

    Args:
        onion_address (str): Contact's onion address.
        status (str): New status flag.
    """
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE contacts SET status = ? WHERE onion_address = ?",
        (status, onion_address),
    )
    conn.commit()
    conn.close()


def update_contact_my_onion(onion_address, my_onion_address):
    """
    Updates the local pairwise hidden service address used for a contact.
    """
    onion_address = onion_address.strip().lower()
    my_onion_address = my_onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE contacts SET my_onion_address = ? WHERE onion_address = ?",
        (my_onion_address, onion_address),
    )
    updated = c.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def update_contact_secret(onion_address, shared_secret, peer_public_key, db_key=None):
    """
    Saves derived E2EE key material negotiated with a contact.

    Saves the shared secret (GCM encrypted) and the peer's public key.

    Args:
        onion_address (str): Contact's onion address.
        shared_secret (str): Derived raw key bits.
        peer_public_key (str): Peer DH public key.
        db_key (str): Hex database secret key.
    """
    onion_address = onion_address.strip().lower()
    encrypted_secret = shared_secret
    if shared_secret and db_key:
        encrypted_secret = encrypt_secret(shared_secret, db_key)
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        UPDATE contacts
        SET shared_secret = ?, peer_public_key = ?, status = 'accepted'
        WHERE onion_address = ?
    """,
        (encrypted_secret, peer_public_key, onion_address),
    )
    conn.commit()
    conn.close()


def delete_contact(onion_address):
    """
    Deletes a contact, clearing their handshake records and chat history.

    Args:
        onion_address (str): Contact's onion address.
    """
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM contacts WHERE onion_address = ?", (onion_address,))
    c.execute("DELETE FROM messages WHERE peer_onion = ?", (onion_address,))
    conn.commit()
    conn.close()


def save_message(peer_onion, sender, message, timestamp, expires_at=None):
    """
    Saves an encrypted message payload to the local chat history table.

    Args:
        peer_onion (str): Conversation contact's onion address.
        sender (str): Message sender identity ('me' or peer onion address).
        message (str): Encrypted payload JSON string.
        timestamp (int): Delivery timestamp in milliseconds.
        expires_at (int|None): Unix timestamp (ms) after which the message should
                               be auto-deleted. None means it never expires.

    Returns:
        int|None: Row ID of the inserted message, or None on failure.
    """
    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    row_id = None
    try:
        # If expires_at is not set, check if contact has a disappearing_ttl set
        if expires_at is None:
            c.execute(
                "SELECT disappearing_ttl FROM contacts WHERE onion_address = ?",
                (peer_onion,),
            )
            contact_row = c.fetchone()
            if contact_row and contact_row[0] and contact_row[0] > 0:
                expires_at = int(timestamp) + contact_row[0]

        c.execute(
            """
            INSERT INTO messages (peer_onion, sender, message, timestamp, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (peer_onion, sender, message, int(timestamp), expires_at),
        )
        conn.commit()
        row_id = c.lastrowid
    except Exception as e:
        print(f"Error saving message: {e}")
    finally:
        conn.close()
    return row_id


def get_messages(peer_onion, limit=None, offset=None):
    """
    Retrieves messages exchanged with a specific contact in chronological order.
    Supports optional limit and offset pagination.
    Returns id and expires_at for each message so the client can schedule
    local deletion for disappearing messages (10.D.1).
    """
    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()

    query = "SELECT id, sender, message, timestamp, expires_at, delivery_state FROM messages WHERE peer_onion = ? ORDER BY timestamp ASC"
    params = [peer_onion]

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
        if offset is not None:
            query += " OFFSET ?"
            params.append(offset)

    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()

    messages = []
    for row in rows:
        messages.append(
            {
                "id": row[0],
                "sender": row[1],
                "message": row[2],
                "timestamp": row[3],
                "expires_at": row[4],
                "delivery_state": row[5] if len(row) > 5 else "sent",
            }
        )
    return messages


def delete_message_by_id(message_id: int) -> bool:
    """
    Deletes a single message by its primary key.

    Used by the disappearing messages scheduler (local expiry) and the
    x.msg.delete P2P event handler (sender-initiated remote deletion).

    Args:
        message_id (int): The message row ID.

    Returns:
        bool: True if a row was deleted, False otherwise.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def delete_expired_messages() -> int:
    """
    Deletes all messages whose expires_at timestamp has passed.

    Called periodically by the background sweeper thread in server.py.

    Returns:
        int: Number of messages deleted.
    """
    import time as _time

    now_ms = int(_time.time() * 1000)
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM messages WHERE expires_at IS NOT NULL AND expires_at <= ?",
        (now_ms,),
    )
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted


def set_disappearing_ttl(onion_address: str, ttl_ms: int | None) -> bool:
    """
    Sets the per-contact disappearing message TTL.

    Args:
        onion_address (str): Contact onion address.
        ttl_ms (int|None): TTL in milliseconds, or None to disable.

    Returns:
        bool: True if update succeeded.
    """
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE contacts SET disappearing_ttl = ? WHERE onion_address = ?",
        (ttl_ms, onion_address),
    )
    updated = c.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def delete_message_by_timestamp(peer_onion: str, timestamp: int) -> bool:
    """
    Deletes messages matching a specific conversation and timestamp.

    Used to propagate deletion to the peer (10.D.1 / 10.D.5).
    """
    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM messages WHERE peer_onion = ? AND timestamp = ?",
        (peer_onion, int(timestamp)),
    )
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_expired_messages():
    """
    Retrieves all messages that have expired based on expires_at.

    Returns:
        list: List of dicts with id, peer_onion, timestamp.
    """
    import time as _time

    now_ms = int(_time.time() * 1000)
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, peer_onion, timestamp FROM messages WHERE expires_at IS NOT NULL AND expires_at <= ?",
        (now_ms,),
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "peer_onion": r[1], "timestamp": r[2]} for r in rows]


def nuke_database():
    """Wipes all conversation messages and contact records, leaving credentials intact."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM messages")
    c.execute("DELETE FROM contacts")
    conn.commit()
    conn.close()


def reset_app_data():
    """Resets local database node details except for credentials config."""
    nuke_database()


def migrate_contact_address(old_address: str, new_address: str) -> bool:
    """
    Migrates a contact's onion address to a new pairwise address (v0.9 -> v0.10).

    Updates contacts, messages, and config tables.
    """
    old_address = old_address.strip().lower()
    new_address = new_address.strip().lower()
    if old_address == new_address:
        return True

    conn = get_connection()
    c = conn.cursor()
    try:
        # Disable foreign keys temporarily to allow primary key updates
        c.execute("PRAGMA foreign_keys = OFF")

        # 1. Update contacts table
        c.execute(
            "UPDATE contacts SET onion_address = ? WHERE onion_address = ?",
            (new_address, old_address),
        )

        # 2. Update messages table
        c.execute(
            "UPDATE messages SET peer_onion = ? WHERE peer_onion = ?",
            (new_address, old_address),
        )

        # 3. Update config keys (e.g., my_pubkey_for_{old} -> my_pubkey_for_{new})
        c.execute(
            "SELECT value FROM config WHERE key = ?", (f"my_pubkey_for_{old_address}",)
        )
        row = c.fetchone()
        if row:
            c.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (f"my_pubkey_for_{new_address}", row[0]),
            )
            c.execute(
                "DELETE FROM config WHERE key = ?", (f"my_pubkey_for_{old_address}",)
            )

        c.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        success = True
    except Exception as e:
        conn.rollback()
        print(f"Error migrating contact address in DB: {e}")
        success = False
    finally:
        conn.close()
    return success


def get_last_sequence_number(peer_onion):
    """
    Retrieves the sequence number of the last message received from or sent to a contact.
    """
    import json

    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT message FROM messages WHERE peer_onion = ? ORDER BY timestamp DESC LIMIT 1",
        (peer_onion,),
    )
    row = c.fetchone()
    conn.close()
    if row:
        try:
            payload = json.loads(row[0])
            return int(payload.get("seq", 0))
        except Exception:
            pass
    return 0


def update_preferred_relay(onion, url):
    onion = onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE contacts SET preferred_file_relay = ? WHERE onion_address = ?",
        (url, onion),
    )
    conn.commit()
    conn.close()


def get_preferred_relay(onion):
    onion = onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT preferred_file_relay FROM contacts WHERE onion_address = ?", (onion,)
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def update_send_receipts(onion, enabled):
    onion = onion.strip().lower()
    val = 1 if enabled else 0
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE contacts SET send_receipts = ? WHERE onion_address = ?", (val, onion)
    )
    conn.commit()
    conn.close()


def get_send_receipts(onion):
    onion = onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT send_receipts FROM contacts WHERE onion_address = ?", (onion,))
    row = c.fetchone()
    conn.close()
    return (row[0] if (row and row[0] is not None) else 1) == 1


def update_message_delivery_state(peer_onion, timestamp, state):
    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        UPDATE messages
        SET delivery_state = ?
        WHERE peer_onion = ? AND timestamp = ? AND sender = 'You'
    """,
        (state, peer_onion, int(timestamp)),
    )
    updated = c.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def add_message_edit(peer_onion, target_timestamp, old_text):
    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO message_edits (peer_onion, target_timestamp, old_text, edit_timestamp)
        VALUES (?, ?, ?, ?)
    """,
        (peer_onion, int(target_timestamp), old_text, int(time.time() * 1000)),
    )
    conn.commit()
    conn.close()


def get_message_edits(peer_onion, target_timestamp):
    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT old_text, edit_timestamp
        FROM message_edits
        WHERE peer_onion = ? AND target_timestamp = ?
        ORDER BY edit_timestamp ASC
    """,
        (peer_onion, int(target_timestamp)),
    )
    rows = c.fetchall()
    conn.close()
    return [{"old_text": row[0], "edit_timestamp": row[1]} for row in rows]


def update_message_text(peer_onion, timestamp, new_text):
    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT message FROM messages WHERE peer_onion = ? AND timestamp = ?",
        (peer_onion, int(timestamp)),
    )
    row = c.fetchone()
    if row:
        old_text = row[0]
        # Insert into edit history
        add_message_edit(peer_onion, timestamp, old_text)
        # Update message
        c.execute(
            "UPDATE messages SET message = ? WHERE peer_onion = ? AND timestamp = ?",
            (new_text, peer_onion, int(timestamp)),
        )
        conn.commit()
    conn.close()


def create_group(group_id, name, founder_onion, profile_id="default", is_channel=0):
    founder_onion = founder_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR IGNORE INTO groups (group_id, name, founder_onion, created_at, profile_id, is_channel)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            group_id,
            name,
            founder_onion,
            int(time.time() * 1000),
            profile_id,
            is_channel,
        ),
    )
    conn.commit()
    conn.close()


def get_groups(profile_id="default"):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT group_id, name, founder_onion, created_at, is_channel FROM groups WHERE profile_id = ?",
        (profile_id,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "group_id": r[0],
            "name": r[1],
            "founder_onion": r[2],
            "created_at": r[3],
            "is_channel": r[4],
        }
        for r in rows
    ]


def get_group(group_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT group_id, name, founder_onion, created_at, is_channel FROM groups WHERE group_id = ?",
        (group_id,),
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "group_id": row[0],
            "name": row[1],
            "founder_onion": row[2],
            "created_at": row[3],
            "is_channel": row[4],
        }
    return None


def save_abuse_report(report_id, message_hash, reporter_onion, reason, signature):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO abuse_reports (report_id, message_hash, reporter_onion, reason, signature, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            report_id,
            message_hash,
            reporter_onion,
            reason,
            signature,
            int(time.time() * 1000),
        ),
    )
    conn.commit()
    conn.close()


def get_abuse_reports():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT report_id, message_hash, reporter_onion, reason, signature, timestamp FROM abuse_reports"
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "report_id": r[0],
            "message_hash": r[1],
            "reporter_onion": r[2],
            "reason": r[3],
            "signature": r[4],
            "timestamp": r[5],
        }
        for r in rows
    ]


from core.crypto import DEVELOPER_PUBLIC_KEY_B64


def save_supporter_badge(onion_address, signature):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO supporter_badges (onion_address, badge_signature, signed_by_key, timestamp)
        VALUES (?, ?, ?, ?)
    """,
        (onion_address, signature, DEVELOPER_PUBLIC_KEY_B64, int(time.time() * 1000)),
    )
    conn.commit()
    conn.close()


def get_supporter_badge(onion_address):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT badge_signature, signed_by_key, timestamp FROM supporter_badges WHERE onion_address = ?",
        (onion_address,),
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {"badge_signature": row[0], "signed_by_key": row[1], "timestamp": row[2]}
    return None


def add_group_member(group_id, member_onion, nickname, invited_by=None, role="member"):
    member_onion = member_onion.strip().lower()
    if invited_by:
        invited_by = invited_by.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO group_members (group_id, member_onion, nickname, invited_by, role, joined_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (group_id, member_onion, nickname, invited_by, role, int(time.time() * 1000)),
    )
    conn.commit()
    conn.close()


def remove_group_member(group_id, member_onion):
    member_onion = member_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM group_members WHERE group_id = ? AND member_onion = ?",
        (group_id, member_onion),
    )
    conn.commit()
    conn.close()


def get_group_members(group_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT member_onion, nickname, invited_by, role, joined_at
        FROM group_members
        WHERE group_id = ?
    """,
        (group_id,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "member_onion": r[0],
            "nickname": r[1],
            "invited_by": r[2],
            "role": r[3],
            "joined_at": r[4],
        }
        for r in rows
    ]


def save_group_message(
    group_id, sender_onion, sender_nickname, message, timestamp=None
):
    sender_onion = sender_onion.strip().lower()
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO group_messages (group_id, sender_onion, sender_nickname, message, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """,
        (group_id, sender_onion, sender_nickname, message, int(timestamp)),
    )
    conn.commit()
    conn.close()


def get_group_messages(group_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, sender_onion, sender_nickname, message, timestamp
        FROM group_messages
        WHERE group_id = ?
        ORDER BY timestamp ASC
    """,
        (group_id,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "sender_onion": r[1],
            "sender_nickname": r[2],
            "message": r[3],
            "timestamp": r[4],
        }
        for r in rows
    ]


def create_group_invite(invite_token, group_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO group_invites (invite_token, group_id, created_at)
        VALUES (?, ?, ?)
    """,
        (invite_token, group_id, int(time.time() * 1000)),
    )
    conn.commit()
    conn.close()


def use_group_invite(invite_token):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT group_id, used_at FROM group_invites WHERE invite_token = ?",
        (invite_token,),
    )
    row = c.fetchone()
    if row:
        group_id, used_at = row[0], row[1]
        if used_at is None:
            c.execute(
                "UPDATE group_invites SET used_at = ? WHERE invite_token = ?",
                (int(time.time() * 1000), invite_token),
            )
            conn.commit()
            conn.close()
            return group_id
    conn.close()
    return None


def add_member_vouch(group_id, vouching_member, vouched_member):
    vouching_member = vouching_member.strip().lower()
    vouched_member = vouched_member.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO member_vouches (group_id, vouching_member, vouched_member, timestamp)
        VALUES (?, ?, ?, ?)
    """,
        (group_id, vouching_member, vouched_member, int(time.time() * 1000)),
    )
    conn.commit()
    conn.close()


def get_member_vouches(group_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT vouching_member, vouched_member, timestamp
        FROM member_vouches
        WHERE group_id = ?
    """,
        (group_id,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"vouching_member": r[0], "vouched_member": r[1], "timestamp": r[2]}
        for r in rows
    ]


import bcrypt


def create_profile(profile_id, display_name, hidden=0, passphrase_hash=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO profiles (profile_id, display_name, hidden, passphrase_hash)
        VALUES (?, ?, ?, ?)
    """,
        (profile_id, display_name, hidden, passphrase_hash),
    )
    conn.commit()
    conn.close()


def get_profiles():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT profile_id, display_name, hidden FROM profiles WHERE hidden = 0")
    rows = c.fetchall()
    conn.close()
    return [{"profile_id": r[0], "display_name": r[1], "hidden": r[2]} for r in rows]


def get_profile(profile_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT profile_id, display_name, hidden, passphrase_hash FROM profiles WHERE profile_id = ?",
        (profile_id,),
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "profile_id": row[0],
            "display_name": row[1],
            "hidden": row[2],
            "passphrase_hash": row[3],
        }
    return None


def verify_hidden_profile(passphrase):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT profile_id, display_name, passphrase_hash FROM profiles WHERE hidden = 1"
    )
    rows = c.fetchall()
    conn.close()

    for r in rows:
        prof_id, name, p_hash = r
        if p_hash:
            try:
                if bcrypt.checkpw(passphrase.encode("utf-8"), p_hash.encode("utf-8")):
                    return {"profile_id": prof_id, "display_name": name, "hidden": 1}
            except Exception:
                pass
    return None


# Module wrapper to intercept DB_FILE changes and release the connection pool
import sys


class DatabaseModuleWrapper:
    def __init__(self, module):
        self.__dict__["_module"] = module

    def __getattr__(self, name):
        return getattr(self._module, name)

    def __setattr__(self, name, value):
        if name == "DB_FILE":
            close_pool()
        setattr(self._module, name, value)


sys.modules[__name__] = DatabaseModuleWrapper(sys.modules[__name__])
