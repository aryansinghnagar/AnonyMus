import os
import sqlite3
import bcrypt

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "users.db")
 
def init_db():
    # Check if the file exists
    if not os.path.exists(DB_PATH):
        print("Database not found. Creating a new one...")

    # Opening the connection automatically creates the file
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Set up your initial table structure
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()

def user_exists(username: str) -> bool:
    # Ensure the database and table exist before trying to query
    init_db() 
    
    # Open a new connection for this specific transaction
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Use 'SELECT 1' for efficiency and '?' to prevent SQL injection
    cursor.execute("""
        SELECT 1 
        FROM users 
        WHERE username = ? 
        LIMIT 1;
    """, (username,))
    
    # fetchone() returns a tuple (e.g., (1,)) if a row is found, or None if not
    result = cursor.fetchone()
    
    # Close the connection to free up the database lock
    conn.close()
    
    # Return True if result is not None, False otherwise
    return result is not None

def register_user(username: str, password: str) -> str:
    # Call `user_exists()` — if already taken, return an error string.
    if user_exists(username):
        return "Error: Username is already taken."
        
    # Hash the password. 
    # bcrypt requires bytes, so we encode the password. We decode the result back 
    # to a utf-8 string so it can be stored cleanly in SQLite's TEXT column.
    hashed_bytes = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    password_hash = hashed_bytes.decode('utf-8')
    
    # 3. Insert `username` and the hash into the database.
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO users (username, password_hash)
        VALUES (?, ?)
    """, (username, password_hash))
    
    conn.commit()
    conn.close()
    
    # 4. Return a success string.
    return "Success: User registered."

def login_user(username: str, password: str) -> bool:  
    # Ensure the database exists in case login is called before register
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Look up the stored hash for the given username. 
    cursor.execute("""
        SELECT password_hash 
        FROM users 
        WHERE username = ?
    """, (username,))
    
    result = cursor.fetchone()
    conn.close()
    
    # If not found, return False.
    if result is None:
        return False
        
    stored_hash = result[0]
    
    # 2. Check the password
    # bcrypt.checkpw requires both the password and the stored hash to be bytes.
    is_valid = bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    
    # 3. Return True or False.
    return is_valid