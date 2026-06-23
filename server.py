import eventlet
eventlet.monkey_patch()

import os
import datetime
import uuid
import socket
import time
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room
from dotenv import load_dotenv

import database

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load environment variables
load_dotenv()

app = Flask(__name__)
secret_key = os.environ.get('FLASK_SECRET_KEY')
debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
if not secret_key:
    if not debug_mode:
        raise RuntimeError("FLASK_SECRET_KEY environment variable is required in production mode!")
    app.logger.warning("=" * 80)
    app.logger.warning("WARNING: FLASK_SECRET_KEY environment variable is missing!")
    app.logger.warning("Using ephemeral key. Sessions will NOT persist across restarts/workers!")
    app.logger.warning("=" * 80)
    secret_key = os.urandom(32).hex()
app.secret_key = secret_key

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
    MAX_CONTENT_LENGTH=1 * 1024 * 1024  # 1MB limit for requests
)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.environ.get('REDIS_URL', 'memory://')
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
    
    # Stricter CSP: no 'unsafe-inline' for scripts, restrict connect-src
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.socket.io; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "connect-src 'self' wss: ws:;"
    )
    
    # Sensitive routes should not be cached
    if request.path in ['/login', '/register', '/chat']:
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        
    return response

# Initialize SocketIO
allowed_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
if "*" in allowed_origins:
    allowed_origins = "*"
redis_url = os.environ.get('REDIS_URL')
if redis_url:
    socketio = SocketIO(app, cors_allowed_origins=allowed_origins, message_queue=redis_url, transports=['websocket'])
else:
    socketio = SocketIO(app, cors_allowed_origins=allowed_origins, transports=['websocket'])

# Initialize DB for all workers
database.init_db()

# Rooms are used natively for Zero-Knowledge Queues routing, eliminating in-memory state.

import threading

# Rate limiting for sockets
socket_rate_limits = {}
socket_rate_limits_lock = threading.Lock()

def is_rate_limited(username, limit=5, window=1):
    now = time.time()
    with socket_rate_limits_lock:
        if username not in socket_rate_limits:
            socket_rate_limits[username] = []
        
        # Clean up old timestamps
        socket_rate_limits[username] = [t for t in socket_rate_limits[username] if now - t < window]
        
        is_limited = len(socket_rate_limits[username]) >= limit
        if not is_limited:
            socket_rate_limits[username].append(now)
            
        # Clean up empty dictionary keys to prevent memory leak
        if not socket_rate_limits[username]:
            del socket_rate_limits[username]
            
        return is_limited

# ==========================================
# 1. HTTP ROUTES
# ==========================================

@app.route('/', methods=['GET'])
def index():
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
    
    # Enforce lengths
    if username and len(username) > 50:
        return jsonify({"error": "Username too long"}), 400
    if password and len(password) > 128:
        return jsonify({"error": "Password too long"}), 400
        
    res = database.register_user(username, password)
    return jsonify(res)

@app.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
        
    username = data.get('username')
    password = data.get('password')
    
    res = database.login_user(username, password)
    if res.get('success'):
        # Session fixation protection: regenerate session ID
        session.clear()
        session['username'] = username
    return jsonify(res)

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

# ==========================================
# 2. WEBSOCKET HANDLERS
# ==========================================

@socketio.on('connect')
def handle_connect():
    if 'username' not in session:
        return False
    app.logger.debug(f"Client connected. SID={request.sid}, User={session['username']}")
    # Do not clear rate limits on reconnect, only initialize if not present
    with socket_rate_limits_lock:
        if request.sid not in socket_rate_limits:
            socket_rate_limits[request.sid] = []

@socketio.on('create_queue')
def handle_create_queue():
    username = session.get('username', request.sid)
    if is_rate_limited(username, limit=5, window=10):
        app.logger.warning(f"Rate limit exceeded for create_queue on User={username}")
        return

    queue_id = str(uuid.uuid4())
    join_room(queue_id)
    app.logger.debug(f"Queue room {queue_id} joined by SID={request.sid}")
    
    emit('queue_created', {'queue_id': queue_id})

@socketio.on('push_queue')
def handle_push_queue(data):
    username = session.get('username', request.sid)
    if is_rate_limited(username, limit=10, window=1):
        app.logger.warning(f"Rate limit exceeded for push_queue on User={username}")
        return

    queue_id = data.get('queue_id')
    payload = data.get('payload')
    
    if not queue_id or not payload:
        return
        
    if len(payload) > 100 * 1024:
        app.logger.warning(f"Payload too large from User={username}")
        return
        
    participants = socketio.server.manager.get_participants(request.namespace, queue_id)
    if not list(participants):
        emit('push_queue_error', {'queue_id': queue_id, 'error': 'recipient_offline'})
        return
    emit('queue_payload', {'queue_id': queue_id, 'payload': payload}, to=queue_id)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    # Clean up rate limit data associated with request.sid
    with socket_rate_limits_lock:
        socket_rate_limits.pop(sid, None)
    app.logger.debug(f"Client disconnected. SID={sid}")

# ==========================================
# 3. SSL EXECUTION
# ==========================================

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def generate_self_signed_cert(cert_path, key_path):
    print("Generating self-signed SSL certificates...")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Workspace"),
        x509.NameAttribute(NameOID.COMMON_NAME, "workspace.local"),
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
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.DNSName("workspace.local"),
            x509.IPAddress(socket.inet_aton('127.0.0.1')),
            x509.IPAddress(socket.inet_aton(get_local_ip())),
        ]),
        critical=False,
    ).sign(key, hashes.SHA256())
    
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("SSL certificate generated successfully")


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    disable_ssl = os.environ.get('DISABLE_SSL', 'False').lower() == 'true'
    
    import logging
    if not debug_mode:
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.WARNING)
        app.logger.setLevel(logging.WARNING)
    
    # Never bind 0.0.0.0 with debug mode enabled to prevent remote debugger access
    bind_host = '127.0.0.1' if debug_mode else '0.0.0.0'
    
    if disable_ssl:
        print(f"Starting Messages Server on HTTP port {port}...")
        socketio.run(app, host=bind_host, port=port, debug=debug_mode)
    else:
        project_root = os.path.dirname(os.path.abspath(__file__))
        cert_path = os.path.join(project_root, 'cert.pem')
        key_path = os.path.join(project_root, 'key.pem')
        
        if not (os.path.exists(cert_path) and os.path.exists(key_path)):
            generate_self_signed_cert(cert_path, key_path)
        
        print(f"Starting Messages Server securely on HTTPS port {port}...")
        
        if socketio.server.eio.async_mode == 'threading':
            socketio.run(app, host=bind_host, port=port, debug=debug_mode, ssl_context=(cert_path, key_path), allow_unsafe_werkzeug=debug_mode)
        else:
            socketio.run(app, host=bind_host, port=port, debug=debug_mode, certfile=cert_path, keyfile=key_path)