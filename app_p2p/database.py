"""
Database Management Module for AnonyMus (P2P Decentralized Architecture).

Coordinates local SQLite database connection configurations (WAL mode).
Stores local credentials (master password hash), remote contacts, E2EE keys,
and encrypted message logs. Includes AES-GCM encryption helper functions
to protect negotiated shared secrets on disk.
"""

import os
import sqlite3
import bcrypt
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Database file location for the local P2P node
DB_FILE = 'local_node.db'

# Pre-calculate dummy hash for timing attacks mitigation during credentials check
DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode('utf-8')


def get_connection():
    """
    Establishes a connection to the local SQLite database.
    
    Configures Write-Ahead Logging (WAL) and an active busy timeout (5000ms)
    to prevent locks across multi-threaded operations.
    
    Returns:
        Connection: sqlite3 database connection object.
    """
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def encrypt_secret(plaintext_b64, db_key_hex):
    """
    Encrypts a shared secret using AES-GCM.
    
    Args:
        plaintext_b64 (str): Base64 encoded secret string.
        db_key_hex (str): Hex encoded database key.
        
    Returns:
        str: Encrypted ciphertext encoded in Base64.
    """
    if not plaintext_b64 or not db_key_hex:
        return plaintext_b64
    try:
        key = bytes.fromhex(db_key_hex)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext_b64.encode('utf-8'), None)
        return base64.b64encode(nonce + ct).decode('utf-8')
    except Exception as e:
        print(f"Encryption error: {e}")
        return plaintext_b64


def decrypt_secret(ciphertext_b64, db_key_hex):
    """
    Decrypts a shared secret using AES-GCM.
    
    Args:
        ciphertext_b64 (str): Base64 encoded ciphertext string.
        db_key_hex (str): Hex encoded database key.
        
    Returns:
        str: Decrypted plaintext string.
    """
    if not ciphertext_b64 or not db_key_hex:
        return ciphertext_b64
    try:
        data = base64.b64decode(ciphertext_b64)
        if len(data) < 12:
            return ciphertext_b64
        nonce = data[:12]
        ct = data[12:]
        key = bytes.fromhex(db_key_hex)
        aesgcm = AESGCM(key)
        pt = aesgcm.decrypt(nonce, ct, None)
        return pt.decode('utf-8')
    except Exception:
        return ciphertext_b64


def init_db():
    """
    Initializes local SQLite schema.
    
    Creates config, contacts, and messages tables if they do not exist.
    """
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Config Table (stores local user credentials and node configuration)
    c.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # 2. Contacts Table (stores peer list, public keys, status, and encrypted shared secrets)
    c.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            onion_address TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            shared_secret TEXT,
            peer_public_key TEXT,
            status TEXT NOT NULL DEFAULT 'pending_outgoing'
        )
    ''')
    
    # 3. Messages Table (stores local chat log history, referencing contacts)
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer_onion TEXT NOT NULL,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            FOREIGN KEY (peer_onion) REFERENCES contacts(onion_address) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()


def is_initialized():
    """
    Checks if a local user profile password hash exists in the database.
    
    Returns:
        bool: True if profile is initialized, False otherwise.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM config WHERE key = ?', ('password_hash',))
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
        
    pwd_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO config (key, value) VALUES (?, ?)', ('local_username', username.lower()))
        c.execute('INSERT INTO config (key, value) VALUES (?, ?)', ('password_hash', pwd_hash))
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
    
    Args:
        username (str): Entered username.
        password (str): Entered master password.
        
    Returns:
        dict: Dict containing 'success': True or 'error': str credentials mismatch message.
    """
    if not is_initialized():
        return {"error": "App not initialized yet."}
        
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT value FROM config WHERE key = ?', ('password_hash',))
    row_hash = c.fetchone()
    c.execute('SELECT value FROM config WHERE key = ?', ('local_username',))
    row_user = c.fetchone()
    conn.close()
    
    if not row_hash or not row_user:
        return {"error": "Invalid configuration."}
        
    stored_hash = row_hash[0]
    stored_user = row_user[0]
    
    if username.lower() != stored_user:
        bcrypt.checkpw(password.encode('utf-8'), DUMMY_HASH.encode('utf-8'))
        return {"error": "Wrong credentials."}
        
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
        return {"error": "Wrong credentials."}
        
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
    c.execute('SELECT value FROM config WHERE key = ?', (key,))
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
    c.execute('INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()


def add_contact(onion_address, nickname, status='pending_outgoing'):
    """
    Adds a new contact to the local database list.
    
    Args:
        onion_address (str): Peer's Tor onion address.
        nickname (str): Local friendly nickname.
        status (str): Current handshake status state.
        
    Returns:
        bool: True if insertion succeeded, False otherwise.
    """
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR IGNORE INTO contacts (onion_address, nickname, status)
            VALUES (?, ?, ?)
        ''', (onion_address, nickname, status))
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
    
    Decrypted the shared secret key if a valid database key is provided.
    
    Args:
        onion_address (str): Target contact's onion address.
        db_key (str): Hex encoded database secret key.
        
    Returns:
        dict: Contact properties, or None if not found.
    """
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT onion_address, nickname, shared_secret, peer_public_key, status FROM contacts WHERE onion_address = ?', (onion_address,))
    row = c.fetchone()
    conn.close()
    if row:
        secret = row[2]
        if secret and db_key:
            secret = decrypt_secret(secret, db_key)
        return {
            'onion_address': row[0],
            'nickname': row[1],
            'shared_secret': secret,
            'peer_public_key': row[3],
            'status': row[4]
        }
    return None


def get_contacts(db_key=None):
    """
    Retrieves all contacts from the local list.
    
    Args:
        db_key (str): Hex encoded database secret key.
        
    Returns:
        list: List of dicts representing contacts.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT onion_address, nickname, shared_secret, peer_public_key, status FROM contacts')
    rows = c.fetchall()
    conn.close()
    
    contacts = []
    for row in rows:
        secret = row[2]
        if secret and db_key:
            secret = decrypt_secret(secret, db_key)
        contacts.append({
            'onion_address': row[0],
            'nickname': row[1],
            'shared_secret': secret,
            'peer_public_key': row[3],
            'status': row[4]
        })
    return contacts


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
    c.execute('UPDATE contacts SET status = ? WHERE onion_address = ?', (status, onion_address))
    conn.commit()
    conn.close()


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
    c.execute('''
        UPDATE contacts 
        SET shared_secret = ?, peer_public_key = ?, status = 'accepted'
        WHERE onion_address = ?
    ''', (encrypted_secret, peer_public_key, onion_address))
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
    c.execute('DELETE FROM contacts WHERE onion_address = ?', (onion_address,))
    c.execute('DELETE FROM messages WHERE peer_onion = ?', (onion_address,))
    conn.commit()
    conn.close()


def save_message(peer_onion, sender, message, timestamp):
    """
    Saves an encrypted message payload to the local chat history table.
    
    Args:
        peer_onion (str): Conversation contact's onion address.
        sender (str): Message sender identity ('me' or peer onion address).
        message (str): Encrypted payload JSON string.
        timestamp (int): Delivery timestamp milliseconds.
        
    Returns:
        bool: True if write succeeded, False otherwise.
    """
    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO messages (peer_onion, sender, message, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (peer_onion, sender, message, int(timestamp)))
        conn.commit()
        success = True
    except Exception as e:
        success = False
        print(f"Error saving message: {e}")
    finally:
        conn.close()
    return success


def get_messages(peer_onion):
    """
    Retrieves all messages exchanged with a specific contact in chronological order.
    
    Args:
        peer_onion (str): Contact's onion address.
        
    Returns:
        list: Chronological message structures list.
    """
    peer_onion = peer_onion.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT sender, message, timestamp FROM messages WHERE peer_onion = ? ORDER BY timestamp ASC', (peer_onion,))
    rows = c.fetchall()
    conn.close()
    
    messages = []
    for row in rows:
        messages.append({
            'sender': row[0],
            'message': row[1],
            'timestamp': row[2]
        })
    return messages


def nuke_database():
    """Wipes all conversation messages and contact records, leaving credentials intact."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM messages')
    c.execute('DELETE FROM contacts')
    conn.commit()
    conn.close()


def reset_app_data():
    """Resets local database node details except for credentials config."""
    nuke_database()
