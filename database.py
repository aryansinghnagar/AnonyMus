import os
import sqlite3
import bcrypt
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DB_FILE = 'local_node.db'

# Pre-calculate dummy hash for timing attacks
DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode('utf-8')

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def encrypt_secret(plaintext_b64, db_key_hex):
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
    except Exception as e:
        return ciphertext_b64

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Config Table (stores local user settings: nickname, password hash, onion address, identity keys)
    c.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # 2. Contacts Table (stores contacts, their onion address, their public key, and handshake status)
    c.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            onion_address TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            shared_secret TEXT,
            peer_public_key TEXT,
            status TEXT NOT NULL DEFAULT 'pending_outgoing'
        )
    ''')
    
    # 3. Messages Table (stores chat history locally)
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer_onion TEXT NOT NULL,
            sender TEXT NOT NULL, -- 'me' or the peer's onion address
            message TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            FOREIGN KEY (peer_onion) REFERENCES contacts(onion_address) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

def is_initialized():
    """Checks if the local account has been registered."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM config WHERE key = ?', ('password_hash',))
    row = c.fetchone()
    conn.close()
    return row is not None

def register_local_user(username, password):
    """Creates the local database user credentials on first boot."""
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
    """Verifies the local login password to open the app control panel."""
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
    
    # Mitigate timing attack by executing bcrypt check even if username is wrong
    if username.lower() != stored_user:
        bcrypt.checkpw(password.encode('utf-8'), DUMMY_HASH.encode('utf-8'))
        return {"error": "Wrong credentials."}
        
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
        return {"error": "Wrong credentials."}
        
    return {"success": True}

def get_config(key, default=None):
    """Gets a configuration setting from the database."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT value FROM config WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_config(key, value):
    """Saves or updates a configuration setting."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()

# --- Contact Management ---

def add_contact(onion_address, nickname, status='pending_outgoing'):
    """Adds a new contact to the local database."""
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
    """Retrieves a contact from the database."""
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
    """Gets all contacts stored locally."""
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
    """Updates the status of a contact (e.g. accepted, blocked)."""
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE contacts SET status = ? WHERE onion_address = ?', (status, onion_address))
    conn.commit()
    conn.close()

def update_contact_secret(onion_address, shared_secret, peer_public_key, db_key=None):
    """Saves the E2EE keys negotiated with a contact."""
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
    """Deletes a contact and all associated chat logs."""
    onion_address = onion_address.strip().lower()
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM contacts WHERE onion_address = ?', (onion_address,))
    # SQLite foreign keys on delete cascade will delete messages automatically
    c.execute('DELETE FROM messages WHERE peer_onion = ?', (onion_address,))
    conn.commit()
    conn.close()

# --- Message History Management ---

def save_message(peer_onion, sender, message, timestamp):
    """Saves a message (plain text) to local chat history."""
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
    """Retrieves all chat messages for a specific contact."""
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
    """Wipes all contacts and chat logs, leaving only config intact."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM messages')
    c.execute('DELETE FROM contacts')
    conn.commit()
    conn.close()

def reset_app_data():
    """Wipes all traces of the node except the password config (nuke messages and contacts)."""
    nuke_database()
