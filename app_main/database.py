"""
Database Management Module for AnonyMus (Client-Server Architecture).

Provides connection pooling, table initialization, and authentication wrappers.
Supports dynamic switching between a local SQLite database (in Write-Ahead Log mode)
and a remote PostgreSQL server depending on environment configuration.
"""

import os
import sqlite3
import bcrypt

# Fetch database configuration from environment
DATABASE_URL = os.environ.get('DATABASE_URL')
DB_FILE = os.environ.get('DB_FILE', 'users.db')

# Pre-calculate dummy hash to mitigate timing side-channel attacks for non-existent users
DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode('utf-8')

# Dynamically resolve integrity error classes based on backend database package availability
db_integrity_errors = (sqlite3.IntegrityError,)
if DATABASE_URL:
    try:
        import psycopg2
        db_integrity_errors = (sqlite3.IntegrityError, psycopg2.IntegrityError)
    except ImportError:
        pass

# Threaded connection pool reference for PostgreSQL
_connection_pool = None


def get_connection():
    """
    Retrieves or establishes a database connection.
    
    If DATABASE_URL is set, obtains a connection from a ThreadedConnectionPool.
    Otherwise, returns a local SQLite connection configured with WAL (Write-Ahead Logging)
    and a busy timeout (5000ms) for concurrent access resilience.
    
    Returns:
        Connection: sqlite3 or psycopg2 connection object.
    """
    global _connection_pool
    if DATABASE_URL:
        import psycopg2
        from psycopg2 import pool
        if _connection_pool is None:
            # Initialize connection pool for multi-threaded environments
            _connection_pool = pool.ThreadedConnectionPool(
                minconn=2, maxconn=10, dsn=DATABASE_URL
            )
        return _connection_pool.getconn()
    else:
        # Configure SQLite for thread safety and concurrent operations
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')
        return conn


def release_connection(conn):
    """
    Releases a database connection.
    
    Returns connection back to the PostgreSQL pool if database is remote,
    or closes the SQLite connection if running locally.
    
    Args:
        conn (Connection): The database connection object to release.
    """
    global _connection_pool
    if DATABASE_URL and _connection_pool:
        _connection_pool.putconn(conn)
    else:
        conn.close()


def init_db():
    """
    Initializes database schema.
    
    Creates the 'users' table if it does not already exist, specifying
    username as the primary key and password_hash as a non-null string.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL
        )
    ''')
    conn.commit()
    release_connection(conn)


def user_exists(username):
    """
    Queries database to check if a specific user exists.
    
    Username matching is performed case-insensitively.
    
    Args:
        username (str): The username string.
        
    Returns:
        bool: True if the user exists, False otherwise.
    """
    conn = get_connection()
    c = conn.cursor()
    placeholder = '%s' if DATABASE_URL else '?'
    c.execute(f'SELECT 1 FROM users WHERE username = {placeholder}', (username.lower(),))
    result = c.fetchone()
    release_connection(conn)
    return result is not None


def register_user(username, password):
    """
    Registers a new user in the database.
    
    Checks for missing fields, checks if the username is already taken, hashes the password
    using bcrypt with a random salt, and inserts the record into the database.
    
    Args:
        username (str): The desired username.
        password (str): The raw user password.
        
    Returns:
        dict: Dict containing 'success': True or 'error': str description of failure.
    """
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
        release_connection(conn)
        
    if success:
        return {"success": True}
    else:
        return {"error": "Failed to register."}


def login_user(username, password):
    """
    Authenticates a user session against stored credentials.
    
    Fetches the password hash for the user. If the user does not exist,
    compares the password against a dummy hash to prevent timing attacks.
    Otherwise, verifies the password against the stored hash.
    
    Args:
        username (str): Username to check.
        password (str): Raw password.
        
    Returns:
        dict: Dict containing 'success': True or 'error': str credentials mismatch message.
    """
    if not username or not password:
        return {"error": "Missing fields."}

    username_lower = username.lower()
    conn = get_connection()
    c = conn.cursor()
    placeholder = '%s' if DATABASE_URL else '?'
    c.execute(f'SELECT password_hash FROM users WHERE username = {placeholder}', (username_lower,))
    row = c.fetchone()
    release_connection(conn)
    
    if not row:
        # Execute dummy hash validation to make processing time indistinguishable
        bcrypt.checkpw(password.encode('utf-8'), DUMMY_HASH.encode('utf-8'))
        return {"error": "Wrong credentials."}
        
    stored_hash = row[0]
    
    # Verify password match
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
        return {"error": "Wrong credentials."}
        
    return {"success": True}
