import os
import datetime
from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from database import init_db, register_user, login_user

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Load environment variables from the .env file into os.environ
load_dotenv()

# State management dictionaries for WebSockets
active_users = {}
sid_to_username = {}
user_keys = {}

app = Flask(__name__)

# Initialize SocketIO with the Flask app (explicitly allow CORS for multi-device connections)
socketio = SocketIO(app, cors_allowed_origins="*")

# Securely retrieve the secret key from the .env file.
# We raise an error if it is missing to prevent the app from running insecurely.
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
if not app.secret_key:
    raise ValueError("No FLASK_SECRET_KEY found. Please check your .env file.")

# Initialize the database table when the server starts
init_db()

# ==========================================
# 1. HTTP ROUTES (Standard Web Traffic)
# ==========================================

@app.route('/', methods=['GET'])
def index():
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"error": "Username and password are required"}), 400

    username = data.get('username')
    password = data.get('password')
    
    result = register_user(username, password)
    
    if result.startswith("Success"):
        return jsonify({"success": True}), 201
    else:
        return jsonify({"error": result}), 409 

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"error": "Username and password are required"}), 400

    username = data.get('username')
    password = data.get('password')
    
    is_valid = login_user(username, password)
    
    if is_valid:
        session['username'] = username
        return jsonify({"success": True}), 200
    else:
        return jsonify({"error": "Wrong credentials"}), 401

@app.route('/chat', methods=['GET'])
def chat():
    if 'username' in session:
        return render_template('chat.html', username=session['username'])
    else:
        return redirect(url_for('index'))

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

# ==========================================
# 2. WEBSOCKET HANDLERS (Real-time Events)
# ==========================================

@socketio.on('connect')
def handle_connect():
    print(f"DEBUG: Socket.IO client connected. SID={request.sid}, IP={request.remote_addr}")

@socketio.on('authenticate')
def handle_authenticate(data):
    username = data.get('username')
    print(f"DEBUG: Authenticate request from SID={request.sid} for username='{username}'")
    if not username:
        print(f"DEBUG: Authentication rejected. Missing username.")
        return

    # Map username to socket_id, and vice-versa
    sid = request.sid
    active_users[username] = sid
    sid_to_username[sid] = username
    print(f"DEBUG: User '{username}' authenticated. Current online list: {list(active_users.keys())}")

    # Broadcast updated online user list to everyone
    emit('user_list_update', list(active_users.keys()), broadcast=True)
    print(f"DEBUG: Broadcasted user_list_update to everyone.")

@socketio.on('public_key')
def handle_public_key(data):
    username = sid_to_username.get(request.sid)
    public_key = data.get('public_key')
    print(f"DEBUG: Received public key from SID={request.sid} ('{username}')")
    
    if username and public_key:
        user_keys[username] = public_key
        print(f"DEBUG: Stored public key for user '{username}'")

@socketio.on('request_key')
def handle_request_key(data):
    target_username = data.get('username')
    print(f"DEBUG: SID={request.sid} ('{sid_to_username.get(request.sid)}') requested public key for '{target_username}'")
    
    # Look up the key and emit it strictly back to the requester
    if target_username in user_keys:
        key = user_keys[target_username]
        emit('public_key', {
            'username': target_username, 
            'public_key': key
        }, to=request.sid)
        print(f"DEBUG: Sent public key of '{target_username}' to SID={request.sid}")
    else:
        print(f"DEBUG: Public key for '{target_username}' not found in user_keys.")

@socketio.on('private_message')
def handle_private_message(data):
    target_username = data.get('to')
    iv = data.get('iv')
    ciphertext = data.get('ciphertext')
    sender_username = sid_to_username.get(request.sid)
    print(f"DEBUG: Private message from '{sender_username}' to '{target_username}' (SID={request.sid})")

    # Look up the target's socket ID
    target_sid = active_users.get(target_username)
    
    if target_sid:
        # Emit exactly what was received to the target socket ONLY.
        emit('private_message', {
            'from': sender_username,
            'iv': iv,
            'ciphertext': ciphertext
        }, to=target_sid)
        print(f"DEBUG: Routed message from '{sender_username}' to target SID={target_sid}")
    else:
        print(f"DEBUG: Routing failed. Target user '{target_username}' is offline or not found.")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    username = sid_to_username.get(sid)
    print(f"DEBUG: Socket.IO client disconnected. SID={sid}, username='{username}'")
    
    if username:
        # Clean up all mappings
        active_users.pop(username, None)
        user_keys.pop(username, None)
        sid_to_username.pop(sid, None)
        print(f"DEBUG: Cleaned up active_user mappings for '{username}'. Remaining: {list(active_users.keys())}")
        
        # Broadcast updated online list
        emit('user_list_update', list(active_users.keys()), broadcast=True)
        print(f"DEBUG: Broadcasted user_list_update after disconnection.")

# ==========================================
# 3. EXECUTION
# ==========================================

def generate_self_signed_cert(cert_path, key_path):
    print("Generating self-signed SSL certificates...")
    # Generate private key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Generate a self-signed certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Anonymouse"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    ).not_valid_after(
        # Valid for 1 year
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.DNSName("127.0.0.1"),
        ]),
        critical=False,
    ).sign(key, hashes.SHA256())
    
    # Save key
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        
    # Save cert
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"SSL certificate generated successfully:\n  Cert: {cert_path}\n  Key: {key_path}")

def ensure_ssl_certificates(cert_path, key_path):
    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
        print("SSL certificates (cert.pem/key.pem) not found.")
        generate_self_signed_cert(cert_path, key_path)

if __name__ == '__main__':
    # Fetch debug state from the .env file (defaulting to False for safety)
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Check for SSL certificates in the project root directory
    project_root = os.path.dirname(os.path.abspath(__file__))
    cert_path = os.path.join(project_root, 'cert.pem')
    key_path = os.path.join(project_root, 'key.pem')
    
    # Ensure certificates are present (auto-generates if not found)
    ensure_ssl_certificates(cert_path, key_path)
    
    print("Starting server strictly in HTTPS mode...")
    if socketio.server.eio.async_mode == 'threading':
        socketio.run(app, host='0.0.0.0', port=5000, debug=debug_mode, ssl_context=(cert_path, key_path), allow_unsafe_werkzeug=True)
    else:
        socketio.run(app, host='0.0.0.0', port=5000, debug=debug_mode, certfile=cert_path, keyfile=key_path)