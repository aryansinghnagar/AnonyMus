"""
Server Module for AnonyMus (Client-Server Relay Architecture).

Implements a zero-knowledge WebSocket relay server using Flask-SocketIO.
Coordinates secure message routing, queue ownership validation, session management,
rate limiting, self-signed SSL certificate generation, and mDNS local network service discovery.
"""

import eventlet
eventlet.monkey_patch()

import os
import datetime
import uuid
import socket
import time
import re
import threading
import logging
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, disconnect
from dotenv import load_dotenv

import transports.relay.database as database

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load configurations from environment file
load_dotenv()

# Resolve correct template and static paths
import os
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(APP_ROOT, "web", "templates")
STATIC_DIR = os.path.join(APP_ROOT, "web", "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

@app.context_processor
def inject_mode():
    return dict(mode="relay")

# Enforce secure session key setup
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

# Apply session cookie and payload constraints
app.config.update(
    SESSION_COOKIE_SECURE=not os.environ.get('DISABLE_SSL', 'False').lower() == 'true',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
    MAX_CONTENT_LENGTH=1 * 1024 * 1024  # Enforce 1MB maximum payload size
)

# Initialize HTTP endpoint rate limiter (uses Redis backend if configured)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.environ.get('REDIS_URL', 'memory://')
)


def get_local_ip():
    """
    Determines the local network IP address of the machine.
    
    Returns:
        str: IPv4 address string (defaults to '127.0.0.1' on error).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Route to a dummy public IP to resolve local interface binding
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


# Thread-safe global references for mDNS advertising
zeroconf_instance = None


def advertise_mdns(port):
    """
    Spawns a background thread to advertise the server via Multicast DNS (mDNS).
    
    Service registered: _anonymus._tcp.local.
    
    Args:
        port (int): The network port the server is binding to.
    """
    def run():
        global zeroconf_instance
        try:
            from zeroconf import Zeroconf, ServiceInfo
            zeroconf_instance = Zeroconf()
            local_ip = get_local_ip()
            info = ServiceInfo(
                "_anonymus._tcp.local.",
                f"AnonyMus Server._anonymus._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=port,
                properties={},
            )
            zeroconf_instance.register_service(info)
            print(f"mDNS Service advertised: _anonymus._tcp.local. on {local_ip}:{port}")
        except Exception as e:
            print(f"mDNS advertisement not active: {e}")
            
    t = threading.Thread(target=run, daemon=True)
    t.start()


def redact_sensitive(log_message):
    """
    Removes Base64 cryptographic keys and UUID strings from log output.
    
    Args:
        log_message (str): Original logging message string.
        
    Returns:
        str: Redacted message string.
    """
    if not isinstance(log_message, str):
        return log_message
    # Redact standard UUID structures
    log_message = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '[REDACTED-UUID]', log_message)
    # Redact Base64 ciphertext/key payloads
    log_message = re.sub(r'[A-Za-z0-9+/]{20,}={0,2}', '[REDACTED-B64]', log_message)
    return log_message


class RedactingFilter(logging.Filter):
    """Logging filter to invoke redaction on all processed logs."""
    def filter(self, record):
        if record.msg and isinstance(record.msg, str):
            record.msg = redact_sensitive(record.msg)
        return True


# Register filters to scrub system logs
app.logger.addFilter(RedactingFilter())
logging.getLogger().addFilter(RedactingFilter())


@app.after_request
def set_security_headers(response):
    """
    Flask hook to enforce browser security headers.
    
    Sets Strict-Transport-Security (HTTPS only), X-Content-Type-Options,
    X-Frame-Options, X-XSS-Protection, CSP rules, and disables route caching
    on sensitive dashboards.
    """
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '0'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    
    # Restrict loading of scripts/frames, allowing socket connection over WS/WSS
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
    
    # Disable caching on core views
    if request.path in ['/login', '/register', '/chat']:
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        
    return response


# Configure allowed Socket.IO CORS Origins dynamically
cors_origins_env = os.environ.get("CORS_ORIGINS")
if cors_origins_env:
    allowed_origins = cors_origins_env.split(",")
else:
    if debug_mode:
        allowed_origins = "*"
    else:
        local_ip = get_local_ip()
        allowed_origins = ["https://localhost", "https://127.0.0.1", f"https://{local_ip}"]

redis_url = os.environ.get('REDIS_URL')
socketio_kwargs = {
    "cors_allowed_origins": allowed_origins,
    "transports": ['websocket'],
    "engineio_logger": False,
    "ping_timeout": 60,
    "ping_interval": 25
}
if redis_url:
    socketio_kwargs["message_queue"] = redis_url

socketio = SocketIO(app, **socketio_kwargs)

if not redis_url and os.environ.get('WEB_CONCURRENCY', '1') != '1':
    app.logger.warning("Multi-worker mode without Redis detected. "
                       "Rate limiting and queue ownership will be per-worker. "
                       "Set REDIS_URL for consistent state.")

# Setup Redis Client connection pool if configuring multi-worker scaling
r_client = None
if redis_url:
    try:
        import redis
        r_client = redis.Redis.from_url(redis_url, decode_responses=True)
    except Exception as e:
        app.logger.warning(f"Could not initialize Redis client, falling back to memory: {e}")

# Ensure database tables exist
database.init_db()

# Queue state management maps & lock primitives (for single worker fallback)
queue_owners = {}
queue_creators = {}
queue_owners_lock = threading.Lock()


def add_queue_owner(queue_id, sid):
    """
    Binds a Socket connection ID (sid) as an authorized recipient for a message queue.
    
    Stores in Redis set if available, otherwise falls back to local in-memory tracking.
    
    Args:
        queue_id (str): UUID representation of queue.
        sid (str): WebSocket session ID.
    """
    if r_client:
        try:
            r_client.sadd(f"queue_owner:{queue_id}", sid)
            r_client.expire(f"queue_owner:{queue_id}", 86400)  # 24 hour TTL
            return
        except Exception:
            pass
    with queue_owners_lock:
        queue_owners.setdefault(queue_id, set()).add(sid)


def add_queue_creator(queue_id, sid):
    """
    Registers the primary creator/host socket connection for a message queue.
    
    Args:
        queue_id (str): UUID representation of queue.
        sid (str): WebSocket session ID.
    """
    if r_client:
        try:
            r_client.set(f"queue_creator:{queue_id}", sid, ex=86400)
            return
        except Exception:
            pass
    with queue_owners_lock:
        queue_creators[queue_id] = sid


def is_queue_owner(queue_id, sid):
    """
    Checks if a Socket connection ID is authorized to access the queue.
    
    Args:
        queue_id (str): Queue UUID.
        sid (str): WebSocket session ID.
        
    Returns:
        bool: True if authorized, False otherwise.
    """
    if r_client:
        try:
            return r_client.sismember(f"queue_owner:{queue_id}", sid)
        except Exception:
            pass
    with queue_owners_lock:
        return queue_id in queue_owners and sid in queue_owners[queue_id]


def is_recipient_online(queue_id):
    """
    Checks if the queue creator's socket is active and registered.
    
    Args:
        queue_id (str): Queue UUID.
        
    Returns:
        bool: True if online, False otherwise.
    """
    creator_sid = None
    if r_client:
        try:
            creator_sid = r_client.get(f"queue_creator:{queue_id}")
        except Exception:
            pass
    if not creator_sid:
        with queue_owners_lock:
            creator_sid = queue_creators.get(queue_id)
    if not creator_sid:
        return False
    with socket_connect_times_lock:
        return creator_sid in socket_connect_times


# In-memory WebSocket client rate limiter structures
socket_rate_limits = {}
socket_rate_limits_lock = threading.Lock()


def is_rate_limited(sid, limit=5, window=1):
    """
    Evaluates Socket.IO message frequency to detect flood attempts.
    
    Args:
        sid (str): Socket connection ID.
        limit (int): Max messages allowed within temporal window.
        window (int): Time interval in seconds.
        
    Returns:
        bool: True if rate limit breached, False otherwise.
    """
    now = time.time()
    with socket_rate_limits_lock:
        if sid not in socket_rate_limits:
            socket_rate_limits[sid] = []
        
        # Prune expired timestamps outside active window
        socket_rate_limits[sid] = [t for t in socket_rate_limits[sid] if now - t < window]
        
        is_limited = len(socket_rate_limits[sid]) >= limit
        if not is_limited:
            socket_rate_limits[sid].append(now)
            
        # Deallocate unused dictionary keys to optimize memory footprint
        if not socket_rate_limits[sid]:
            del socket_rate_limits[sid]
            
        return is_limited


# Connection time logging and session lifetime enforcement structures
socket_connect_times = {}
socket_connect_times_lock = threading.Lock()


def validate_session():
    """
    Validates active cookie session data and forces disconnection
    if connection exceeds 8 hours to refresh key states.
    
    Returns:
        bool: True if session remains valid, False if invalid/expired.
    """
    if 'username' not in session:
        return False
    
    with socket_connect_times_lock:
        connect_time = socket_connect_times.get(request.sid)
    if connect_time and (time.time() - connect_time > 8 * 3600):
        app.logger.warning(f"WebSocket session expired (8h limit) for SID={request.sid}")
        return False
    return True


def validate_username(username):
    """
    Validates username pattern and length.
    
    Args:
        username (str): Target username.
        
    Returns:
        str: Error message, or None if validation passes.
    """
    if not username:
        return "Username is required."
    if len(username) < 3 or len(username) > 50:
        return "Username must be between 3 and 50 characters."
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        return "Username can only contain letters, numbers, underscores, and hyphens."
    return None


def validate_password(password):
    """
    Enforces strong password composition boundaries.
    
    Requires minimum 8 characters, maximum 128 characters, and complexity containing
    characters from at least 3 categories (uppercase, lowercase, digits, special characters).
    
    Args:
        password (str): Target password.
        
    Returns:
        str: Error message, or None if validation passes.
    """
    if not password:
        return "Password is required."
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if len(password) > 128:
        return "Password must be at most 128 characters long."
    categories = 0
    if re.search(r'[A-Z]', password): categories += 1
    if re.search(r'[a-z]', password): categories += 1
    if re.search(r'[0-9]', password): categories += 1
    if re.search(r'[^A-Za-z0-9]', password): categories += 1
    if categories < 3:
        return "Password must contain characters from at least 3 of: uppercase, lowercase, digits, special characters."
    return None


# ==========================================
# 1. HTTP ROUTES
# ==========================================

@app.route('/', methods=['GET'])
def index():
    """Renders main entrance view or redirects to chat panel if authenticated."""
    if 'username' in session:
        return redirect(url_for('chat'))
    return render_template('login.html')


@app.route('/chat', methods=['GET'])
def chat():
    """Renders chat dashboard view for authenticated users."""
    if 'username' not in session:
        return redirect(url_for('index'))
    return render_template('chat.html')


@app.route('/health', methods=['GET'])
def health():
    """Basic health check probe for cluster metrics/monitoring."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }), 200


@app.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    """Handles secure user account registration."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
        
    username = data.get('username')
    password = data.get('password')
    
    user_err = validate_username(username)
    if user_err:
        return jsonify({"error": user_err}), 400

    pwd_err = validate_password(password)
    if pwd_err:
        return jsonify({"error": pwd_err}), 400
        
    res = database.register_user(username, password)
    return jsonify(res)


@app.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """Handles secure authentication, clearing session tokens to mitigate fixation attacks."""
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
    """Logs out user, clearing current server sessions."""
    session.clear()
    return jsonify({"success": True})


# ==========================================
# 2. WEBSOCKET HANDLERS
# ==========================================

@socketio.on('connect')
def handle_connect():
    """Validates HTTP session cookie state when initiating WS connection."""
    if 'username' not in session:
        return False
    with socket_connect_times_lock:
        socket_connect_times[request.sid] = time.time()
        
    truncated_sid = request.sid[:4] if request.sid else "None"
    app.logger.debug(f"Client connected. SID={truncated_sid}, User={session['username']}")
    
    with socket_rate_limits_lock:
        if request.sid not in socket_rate_limits:
            socket_rate_limits[request.sid] = []


@socketio.on('create_queue')
def handle_create_queue():
    """Generates a secure UUID and sets up an authorized message queue for client."""
    if not validate_session():
        emit('session_expired', {})
        disconnect()
        return

    if is_rate_limited(request.sid, limit=5, window=10):
        app.logger.warning(f"Rate limit exceeded for create_queue on SID={request.sid[:4]}")
        return

    queue_id = str(uuid.uuid4())
    add_queue_owner(queue_id, request.sid)
    add_queue_creator(queue_id, request.sid)
    join_room(queue_id)
    app.logger.debug(f"Queue room {queue_id} joined by SID={request.sid[:4]}")
    
    emit('queue_created', {'queue_id': queue_id})


@socketio.on('register_peer')
def handle_register_peer(data):
    """Permits an active peer to authorize exchange routing to client's queue room."""
    if not validate_session():
        emit('session_expired', {})
        disconnect()
        return

    my_queue = data.get('my_queue')
    peer_queue = data.get('peer_queue')
    if not my_queue or not peer_queue:
        return

    # Verify requesting client owns target queue before associating permissions
    if is_queue_owner(my_queue, request.sid):
        add_queue_owner(peer_queue, request.sid)
        app.logger.debug(f"Peer queue {peer_queue[:8]} registered for owner SID={request.sid[:4]}")


@socketio.on('push_queue')
def handle_push_queue(data):
    """Pushes secure E2EE payload to designated target queue."""
    if not validate_session():
        emit('session_expired', {})
        disconnect()
        return

    if is_rate_limited(request.sid, limit=10, window=1):
        app.logger.warning(f"Rate limit exceeded for push_queue on SID={request.sid[:4]}")
        return

    queue_id = data.get('queue_id')
    payload = data.get('payload')
    
    if not queue_id or not payload:
        return
        
    if len(payload) > 100 * 1024:
        app.logger.warning(f"Payload too large from SID={request.sid[:4]}")
        return

    # Enforce queue authorization
    if not is_queue_owner(queue_id, request.sid):
        app.logger.warning(f"Unauthorised push_queue attempt for queue_id={queue_id[:8]} from SID={request.sid[:4]}")
        return

    if not is_recipient_online(queue_id):
        emit('push_queue_error', {'queue_id': queue_id, 'error': 'recipient_offline'})
        return
    emit('queue_payload', {'queue_id': queue_id, 'payload': payload}, to=queue_id)


@socketio.on('disconnect')
def handle_disconnect():
    """Wipes active session timestamps, rate limit tables, and clean up queue mappings."""
    sid = request.sid
    with socket_connect_times_lock:
        socket_connect_times.pop(sid, None)
    with socket_rate_limits_lock:
        socket_rate_limits.pop(sid, None)
        
    # Clean up local queue mapping states
    with queue_owners_lock:
        empty_queues = []
        for q_id, sids in queue_owners.items():
            if sid in sids:
                sids.remove(sid)
            if not sids:
                empty_queues.append(q_id)
        for q_id in empty_queues:
            del queue_owners[q_id]
            
        expired_queues = [q for q, creator in queue_creators.items() if creator == sid]
        for q in expired_queues:
            del queue_creators[q]

    app.logger.debug(f"Client disconnected. SID={sid[:4]}")


# ==========================================
# 3. SSL EXECUTION
# ==========================================

def generate_self_signed_cert(cert_path, key_path):
    """
    Generates a secure self-signed P-256 SSL certificate and key pair
    and writes them to the specified PEM filepaths.
    
    Args:
        cert_path (str): Filepath to write the TLS certificate.
        key_path (str): Filepath to write the private key.
    """
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
    
    # Broadcast service via local multicast DNS
    advertise_mdns(port)
    
    if not debug_mode:
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.WARNING)
        app.logger.setLevel(logging.WARNING)
    
    # Secure server interface binding context
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