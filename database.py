import os
import sqlite3
import bcrypt

DATABASE_URL = os.environ.get('DATABASE_URL')
DB_FILE = 'users.db'

# Pre-calculate dummy hash for timing attack mitigation
DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode('utf-8')

# Define integrity errors tuple dynamically
db_integrity_errors = (sqlite3.IntegrityError,)
if DATABASE_URL:
    try:
        import psycopg2
        db_integrity_errors = (sqlite3.IntegrityError, psycopg2.IntegrityError)
    except ImportError:
        pass

def get_connection():
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def user_exists(username):
    conn = get_connection()
    c = conn.cursor()
    placeholder = '%s' if DATABASE_URL else '?'
    c.execute(f'SELECT 1 FROM users WHERE username = {placeholder}', (username.lower(),))
    result = c.fetchone()
    conn.close()
    return result is not None

def register_user(username, password):
    if not username or not password:
        return {"error": "Missing fields."}
    
    username_lower = username.lower()
    if user_exists(username_lower):
        return {"error": "Username already taken."}
        
    pwd_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    conn = get_connection()
    c = conn.cursor()
    placeholder = '%s' if DATABASE_URL else '?'
    try:
        c.execute(f'INSERT INTO users (username, password_hash) VALUES ({placeholder}, {placeholder})',
                  (username_lower, pwd_hash))
        conn.commit()
        success = True
    except db_integrity_errors:
        success = False
        return {"error": "Failed to register (username already exists)."}
    except Exception as e:
        success = False
        print(f"Registration DB error: {e}")
    finally:
        conn.close()
        
    if success:
        return {"success": True}
    else:
        return {"error": "Failed to register."}

def login_user(username, password):
    if not username or not password:
        return {"error": "Missing fields."}

    username_lower = username.lower()
    conn = get_connection()
    c = conn.cursor()
    placeholder = '%s' if DATABASE_URL else '?'
    c.execute(f'SELECT password_hash FROM users WHERE username = {placeholder}', (username_lower,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        # Dummy check to prevent timing side-channel
        bcrypt.checkpw(password.encode('utf-8'), DUMMY_HASH.encode('utf-8'))
        return {"error": "Wrong credentials."}
        
    stored_hash = row[0]
    
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
        return {"error": "Wrong credentials."}
        
    return {"success": True}
