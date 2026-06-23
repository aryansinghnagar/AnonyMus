import os
import sys
import uuid
import time
import requests
import threading
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_socketio import SocketIO, emit
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

import database
import tor_manager

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize secret key
secret_key = os.environ.get('FLASK_SECRET_KEY')
debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
if not secret_key:
    if not debug_mode:
        raise RuntimeError("FLASK_SECRET_KEY environment variable is required in production mode!")
    app.logger.warning("=" * 80)
    app.logger.warning("WARNING: FLASK_SECRET_KEY environment variable is missing!")
    app.logger.warning("Using ephemeral key. Sessions will NOT persist across restarts!")
    app.logger.warning("=" * 80)
    secret_key = os.urandom(32).hex()
app.secret_key = secret_key

app.config.update(
    SESSION_COOKIE_SECURE=False,  # Set to False because local browser connects via HTTP (localhost)
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
    MAX_CONTENT_LENGTH=1 * 1024 * 1024  # 1MB limit
)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Security Headers
@app.after_request
def set_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '0'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.socket.io; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "connect-src 'self' ws: wss:;"
    )
    
    if request.path in ['/login', '/register', '/chat']:
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        
    return response

# SocketIO setup (only allows connections from localhost)
socketio = SocketIO(app, cors_allowed_origins="*", transports=['websocket'])

# Initialize Local DB
database.init_db()

# Outbound Tor SOCKS proxy config
SOCKS_PORT = 9050

# Helper to send requests over Tor
def send_onion_post(onion_address, endpoint, payload):
    proxies = {
        'http': f'socks5h://127.0.0.1:{SOCKS_PORT}',
        'https': f'socks5h://127.0.0.1:{SOCKS_PORT}'
    }
    url = f"http://{onion_address.strip().lower()}{endpoint}"
    try:
        response = requests.post(url, json=payload, proxies=proxies, timeout=20)
        return response.json()
    except Exception as e:
        print(f"Error connecting to onion {onion_address} via Tor: {e}")
        return {"error": "unreachable"}

# ==========================================
# SECURITY FILTER (Before Request Hook)
# ==========================================
@app.before_request
def restrict_access():
    """
    Enforces the security boundary between the local control panel and the public Tor network.
    Local UI endpoints and APIs must ONLY be accessed from localhost.
    P2P endpoints (/p2p/*) can be accessed via Tor (which carries the .onion Host header).
    """
    host = request.headers.get('Host', '').lower()
    path = request.path
    
    is_local_host = '127.0.0.1' in host or 'localhost' in host
    is_p2p_route = path.startswith('/p2p/')
    
    if not is_local_host and not is_p2p_route:
        # Remote users over Tor attempting to access local control panel
        return "Forbidden: Local access only", 403

# ==========================================
# 1. HTTP UI ROUTES (Local only)
# ==========================================
@app.route('/', methods=['GET'])
def index():
    if not database.is_initialized():
        return render_template('login.html', register_only=True)
    if 'username' in session:
        return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/chat', methods=['GET'])
def chat():
    if 'username' not in session:
        return redirect(url_for('index'))
    return render_template('chat.html')

@app.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
    username = data.get('username')
    password = data.get('password')
    
    res = database.register_local_user(username, password)
    return jsonify(res)

@app.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
    username = data.get('username')
    password = data.get('password')
    
    res = database.login_local_user(username, password)
    if res.get('success'):
        session.clear()
        session['username'] = username
    return jsonify(res)

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

# ==========================================
# 2. LOCAL API ROUTES (Local only)
# ==========================================
@app.route('/api/my_info', methods=['GET'])
def my_info():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "onion_address": database.get_config('my_onion_address'),
        "local_username": session['username']
    })

@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(database.get_contacts())

@app.route('/api/contacts/add', methods=['POST'])
def add_contact():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json()
    onion = data.get('onion_address', '').strip().lower()
    nickname = data.get('nickname', '').strip()
    my_public_key = data.get('my_public_key')
    
    if not onion.endswith('.onion') or not nickname or not my_public_key:
        return jsonify({"error": "Invalid onion address or nickname."}), 400
        
    # Save contact locally as pending_outgoing
    database.add_contact(onion, nickname, status='pending_outgoing')
    
    # Store public key in contacts config
    database.set_config(f"my_pubkey_for_{onion}", my_public_key)
    
    # Async handshake over Tor
    my_onion = database.get_config('my_onion_address')
    
    def do_handshake():
        payload = {
            "onion_address": my_onion,
            "nickname": session.get('username', 'Anonymous'),
            "public_key": my_public_key
        }
        res = send_onion_post(onion, "/p2p/handshake", payload)
        if "error" in res:
            # Let UI know peer is currently offline
            socketio.emit('contact_status_change', {"onion_address": onion, "status": "offline"})
            
    threading.Thread(target=do_handshake, daemon=True).start()
    
    return jsonify({"success": True})

@app.route('/api/contacts/accept', methods=['POST'])
def accept_contact():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json()
    onion = data.get('onion_address', '').strip().lower()
    my_public_key = data.get('my_public_key')
    shared_secret = data.get('shared_secret')
    
    contact = database.get_contact(onion)
    if not contact:
        return jsonify({"error": "Contact not found."}), 404
        
    # Save the derived secret locally
    database.update_contact_secret(onion, shared_secret, contact['peer_public_key'])
    
    # Notify peer over Tor that we accepted
    my_onion = database.get_config('my_onion_address')
    
    def do_accept():
        payload = {
            "onion_address": my_onion,
            "public_key": my_public_key
        }
        send_onion_post(onion, "/p2p/accept", payload)
        
    threading.Thread(target=do_accept, daemon=True).start()
    
    return jsonify({"success": True})

@app.route('/api/contacts/save_secret', methods=['POST'])
def save_secret():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json()
    onion = data.get('onion_address', '').strip().lower()
    shared_secret = data.get('shared_secret')
    peer_public_key = data.get('peer_public_key')
    
    database.update_contact_secret(onion, shared_secret, peer_public_key)
    return jsonify({"success": True})

@app.route('/api/contacts/delete', methods=['POST'])
def delete_contact():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    onion = data.get('onion_address', '').strip().lower()
    database.delete_contact(onion)
    return jsonify({"success": True})

@app.route('/api/messages', methods=['GET'])
def get_messages():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    onion = request.args.get('onion', '').strip().lower()
    return jsonify(database.get_messages(onion))

@app.route('/api/messages/send', methods=['POST'])
def send_message():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json()
    onion = data.get('onion_address', '').strip().lower()
    iv = data.get('iv')
    ciphertext = data.get('ciphertext')
    seq = data.get('seq')
    
    contact = database.get_contact(onion)
    if not contact or contact['status'] != 'accepted':
        return jsonify({"error": "Contact not accepted or not found."}), 400
        
    timestamp = int(time.time() * 1000)
    
    # Save locally first
    message_payload = {"iv": iv, "ciphertext": ciphertext, "seq": seq}
    import json
    database.save_message(onion, 'me', json.dumps(message_payload), timestamp)
    
    # Send over Tor
    my_onion = database.get_config('my_onion_address')
    
    def transmit():
        payload = {
            "sender": my_onion,
            "iv": iv,
            "ciphertext": ciphertext,
            "seq": seq,
            "timestamp": timestamp
        }
        res = send_onion_post(onion, "/p2p/message", payload)
        if "error" in res:
            # Let UI know it failed (peer offline)
            socketio.emit('message_delivery_failed', {"onion_address": onion, "timestamp": timestamp})
            
    threading.Thread(target=transmit, daemon=True).start()
    
    return jsonify({"success": True, "timestamp": timestamp})

@app.route('/api/obliviate', methods=['POST'])
def handle_obliviate():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    database.obliviate()
    return jsonify({"success": True})

# ==========================================
# 3. PUBLIC TOR P2P ROUTES (Tor Network only)
# ==========================================
@app.route('/p2p/handshake', methods=['POST'])
@limiter.limit("20 per minute")
def p2p_handshake():
    """Receives contact requests from remote Tor peers."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid payload"}), 400
        
    onion = data.get('onion_address', '').strip().lower()
    nickname = data.get('nickname', '').strip()
    public_key = data.get('public_key', '').strip()
    
    if not onion or not nickname or not public_key:
        return jsonify({"error": "Missing payload fields"}), 400
        
    # Check if already blocked or accepted
    existing = database.get_contact(onion)
    if existing and existing['status'] == 'blocked':
        return jsonify({"error": "blocked"}), 403
        
    # Store request locally as pending_incoming
    database.add_contact(onion, nickname, status='pending_incoming')
    # Save their public key
    database.update_contact_secret(onion, None, public_key)
    database.update_contact_status(onion, 'pending_incoming')
    
    # Emit event to local browser UI
    socketio.emit('incoming_contact_request', {
        "onion_address": onion,
        "nickname": nickname,
        "peer_public_key": public_key
    })
    
    return jsonify({"status": "pending"})

@app.route('/p2p/accept', methods=['POST'])
@limiter.limit("20 per minute")
def p2p_accept():
    """Receives handshake acceptance from a peer."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid payload"}), 400
        
    onion = data.get('onion_address', '').strip().lower()
    public_key = data.get('public_key', '').strip()
    
    contact = database.get_contact(onion)
    if not contact:
        return jsonify({"error": "No handshake record found."}), 404
        
    # Retrieve our own public key we generated for this contact
    my_pubkey = database.get_config(f"my_pubkey_for_{onion}")
    
    # Emit event to Alice's browser so her browser can derive the secret
    socketio.emit('handshake_accepted', {
        "onion_address": onion,
        "peer_public_key": public_key,
        "my_public_key": my_pubkey
    })
    
    return jsonify({"status": "accepted"})

@app.route('/p2p/message', methods=['POST'])
@limiter.limit("30 per minute")
def p2p_message():
    """Receives encrypted messages from accepted remote peers."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid payload"}), 400
        
    sender = data.get('sender', '').strip().lower()
    iv = data.get('iv')
    ciphertext = data.get('ciphertext')
    seq = data.get('seq')
    timestamp = data.get('timestamp')
    
    contact = database.get_contact(sender)
    if not contact or contact['status'] != 'accepted':
        return jsonify({"error": "Unauthorized contact."}), 403
        
    # Store message locally (encrypted)
    import json
    message_payload = {"iv": iv, "ciphertext": ciphertext, "seq": seq}
    database.save_message(sender, sender, json.dumps(message_payload), timestamp)
    
    # Push to local browser UI
    socketio.emit('incoming_message', {
        "sender": sender,
        "iv": iv,
        "ciphertext": ciphertext,
        "seq": seq,
        "timestamp": timestamp
    })
    
    return jsonify({"status": "delivered"})

# ==========================================
# STARTUP
# ==========================================
if __name__ == '__main__':
    # Start Tor in background thread to allow Flask to boot or boot Tor first
    try:
        onion, socks, peer = tor_manager.launch_tor()
        SOCKS_PORT = socks
        database.set_config('my_onion_address', onion)
    except Exception as e:
        print(f"FATAL: Embedded Tor failed to start: {e}")
        sys.exit(1)
        
    print(f"Flask running local control panel on http://127.0.0.1:{peer}")
    socketio.run(app, host='127.0.0.1', port=peer, debug=False)