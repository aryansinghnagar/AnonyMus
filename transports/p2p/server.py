"""
Server Module for AnonyMus (P2P Decentralized Architecture).

Implements the local node interface and public Tor peer-to-peer message endpoints.
Local routes (/api/*, /, /chat) are secured to localhost only.
Public P2P routes (/p2p/*) process incoming requests routed through the Tor onion service.
"""

import json
import os
import re
import sys
import threading
import time
import uuid

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO

import transports.p2p.database as database
import transports.p2p.tor_manager as tor_manager

# Regex for validating peer Tor hidden service addresses
ONION_RE = re.compile(r"^[a-z2-7]{16,56}\.onion$")


def validate_onion(addr):
    """
    Validates and normalizes Tor Onion addresses.

    Args:
        addr (str): Raw string containing the onion address.

    Returns:
        str: Sanitized lowercase address, or None if validation fails.
    """
    addr = (addr or "").strip().lower()
    if not ONION_RE.match(addr):
        return None
    return addr


def validate_nickname(nickname: str) -> str:
    """
    Validates and cleans user nickname. Enforces length and character class constraints.
    """
    if not nickname:
        raise ValueError("Nickname cannot be empty.")
    nickname = nickname.strip()
    if len(nickname) < 1 or len(nickname) > 50:
        raise ValueError("Nickname must be between 1 and 50 characters.")
    if not re.match(r"^[a-zA-Z0-9._\- @()]+$", nickname):
        raise ValueError("Nickname contains invalid characters.")
    return nickname


BASE64_RE = re.compile(r"^[A-Za-z0-9+/=-_]+$")


def is_valid_base64_like(val: str, max_len: int = 100000) -> bool:
    if not isinstance(val, str):
        return False
    if len(val) > max_len:
        return False
    return bool(BASE64_RE.match(val))


# Load configurations from environment variables
load_dotenv()

# Resolve correct template and static paths
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(APP_ROOT, "web", "templates")
STATIC_DIR = os.path.join(APP_ROOT, "web", "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

from core.gunicorn_check import assert_single_worker

assert_single_worker()

if (
    os.environ.get("ANONYMUS_ENV", "").lower() == "production"
    and os.environ.get("FLASK_DEBUG", "").lower() == "true"
):
    raise RuntimeError(
        "Security Violation: FLASK_DEBUG=true is active while ANONYMUS_ENV=production. Refusing to boot."
    )

from concurrent.futures import ThreadPoolExecutor
from functools import wraps


class QueueFull(Exception):
    pass


class BoundedThreadPoolExecutor(ThreadPoolExecutor):
    def __init__(self, max_workers=20, max_queue_size=100):
        super().__init__(max_workers=max_workers)
        self.max_queue_size = max_queue_size

    def submit(self, fn, *args, **kwargs):
        if self._work_queue.qsize() >= self.max_queue_size:
            raise QueueFull("Thread pool queue is full.")
        return super().submit(fn, *args, **kwargs)


def validate_json_schema(required_fields):
    """
    Decorator to validate JSON request bodies.
    required_fields is a dict mapping field_name to expected python type.
    """

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 400
            data = request.get_json(silent=True)
            if data is None:
                return jsonify({"error": "Invalid or missing JSON payload"}), 400
            for field, expected_type in required_fields.items():
                if field not in data:
                    return jsonify({"error": f"Missing required field: {field}"}), 400
                if expected_type == int:
                    try:
                        int(data[field])
                    except (ValueError, TypeError):
                        return jsonify(
                            {"error": f"Field {field} must be an integer"}
                        ), 400
                elif not isinstance(data[field], expected_type):
                    return jsonify(
                        {
                            "error": f"Field {field} has invalid type (expected {expected_type.__name__})"
                        }
                    ), 400
            return f(*args, **kwargs)

        return wrapper

    return decorator


@app.errorhandler(QueueFull)
def handle_queue_full(e):
    app.logger.warning("ThreadPoolExecutor queue limit reached! Applying backpressure.")
    response = jsonify({"error": "Service busy. Thread pool queue full."})
    response.headers["Retry-After"] = "10"
    return response, 503


@app.errorhandler(Exception)
def handle_unexpected_exception(e):
    app.logger.exception("Unhandled exception encountered: %s", e)
    return jsonify({"error": "An unexpected error occurred"}), 500


from core.logging import setup_logging

setup_logging(app)


@app.context_processor
def inject_mode():
    return dict(mode="p2p")


@app.before_request
def handle_options_preflight():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response


@app.after_request
def add_cors_headers(response):
    if request.path.startswith("/file/") or request.path.startswith("/p2p/file/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# Enforce secure session key setup
_PLACEHOLDER_SECRETS = {
    "your-secure-random-key-here",
    "diagnostics_ephemeral_control_key_2026",
    "changeme",
    "",
}
secret_key = os.environ.get("FLASK_SECRET_KEY")
debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
if not secret_key or secret_key in _PLACEHOLDER_SECRETS:
    if not debug_mode:
        raise RuntimeError(
            "A secure FLASK_SECRET_KEY environment variable is required in production mode!"
        )
    app.logger.warning("=" * 80)
    app.logger.warning(
        "WARNING: FLASK_SECRET_KEY environment variable is missing or insecure!"
    )
    app.logger.warning(
        "Using ephemeral key. Sessions will NOT persist across restarts!"
    )
    app.logger.warning("=" * 80)
    secret_key = os.urandom(32).hex()
app.secret_key = secret_key

# Apply session cookie and payload constraints
from datetime import timedelta

app.config.update(
    SESSION_COOKIE_SECURE=False,  # Set to False because local browser connects via HTTP (localhost)
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,  # Enforce 1MB maximum payload size
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

# Initialize local controller rate limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)


def get_p2p_rate_limit_key():
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            onion = data.get("sender") or data.get("onion_address")
            if onion and isinstance(onion, str):
                return onion.strip().lower()
    except Exception:
        pass
    return get_remote_address()


# Server-side in-memory cache to store derived database keys
_DB_KEY_CACHE = {}
_DB_KEY_CACHE_LOCK = threading.Lock()


def cache_db_key(db_key_hex: str, lifetime_seconds=28800) -> str:
    db_key_id = uuid.uuid4().hex
    expiry = time.time() + lifetime_seconds
    with _DB_KEY_CACHE_LOCK:
        # Prune expired keys to limit memory usage
        now = time.time()
        expired = [k for k, v in _DB_KEY_CACHE.items() if v[1] < now]
        for k in expired:
            _DB_KEY_CACHE.pop(k, None)
        _DB_KEY_CACHE[db_key_id] = (db_key_hex, expiry)
    return db_key_id


def get_db_key_hex() -> str:
    db_key_id = session.get("db_key_id")
    if not db_key_id:
        return None
    with _DB_KEY_CACHE_LOCK:
        entry = _DB_KEY_CACHE.get(db_key_id)
        if entry:
            db_key_hex, expiry = entry
            if time.time() < expiry:
                return db_key_hex
            else:
                _DB_KEY_CACHE.pop(db_key_id, None)
    return None


from core.security_headers import setup_security_headers

setup_security_headers(app)


# Socket.IO local control interface setup (only allows connections from localhost)
p2p_port = int(os.environ.get("PORT", 5000))
p2p_origins = [
    f"http://127.0.0.1:{p2p_port}",
    f"http://localhost:{p2p_port}",
    f"http://[::1]:{p2p_port}",
]
socketio = SocketIO(app, cors_allowed_origins=p2p_origins, transports=["websocket"])

# Ensure P2P database tables exist
database.init_db()

# Outbound Tor SOCKS proxy config
SOCKS_PORT = 9050

# Thread pool executor for non-blocking asynchronous Tor requests with bounded queue size
executor = BoundedThreadPoolExecutor(max_workers=20, max_queue_size=100)


def message_expiry_sweeper():
    """Background thread that deletes expired messages and notifies UI."""
    while True:
        try:
            expired = database.get_expired_messages()
            if expired:
                deleted_count = database.delete_expired_messages()
                if deleted_count > 0:
                    for msg in expired:
                        socketio.emit(
                            "message_expired",
                            {
                                "id": msg["id"],
                                "peer_onion": msg["peer_onion"],
                                "timestamp": msg["timestamp"],
                            },
                        )
        except Exception:
            pass
        time.sleep(1)


# Launch background message expiry sweeper daemon thread
sweeper_thread = threading.Thread(target=message_expiry_sweeper, daemon=True)
sweeper_thread.start()


def send_onion_post(onion_address, endpoint, payload):
    """
    Sends an HTTP POST request to a remote Onion service through the Tor SOCKS proxy.

    Args:
        onion_address (str): Target .onion address.
        endpoint (str): Route endpoint (e.g., '/p2p/message').
        payload (dict): JSON data to transmit.

    Returns:
        dict: Decoded JSON response, or error dict on network failure.
    """
    proxies = {
        "http": f"socks5h://127.0.0.1:{SOCKS_PORT}",
        "https": f"socks5h://127.0.0.1:{SOCKS_PORT}",
    }
    url = f"http://{onion_address.strip().lower()}{endpoint}"
    try:
        response = requests.post(url, json=payload, proxies=proxies, timeout=20)
        return response.json()
    except Exception as e:
        print(f"Error connecting to onion {onion_address} via Tor: {e}")
        return {"error": "unreachable"}


def send_onion_get(onion_address, endpoint):
    """
    Sends an HTTP GET request to a remote Onion service through the Tor SOCKS proxy.
    Returns (bytes_content, status_code).
    """
    proxies = {
        "http": f"socks5h://127.0.0.1:{SOCKS_PORT}",
        "https": f"socks5h://127.0.0.1:{SOCKS_PORT}",
    }
    url = f"http://{onion_address.strip().lower()}{endpoint}"
    try:
        response = requests.get(url, proxies=proxies, timeout=30)
        return response.content, response.status_code
    except Exception as e:
        print(f"Error connecting to onion {onion_address} via Tor GET: {e}")
        return b"", 504


# ---------------------------------------------------------------------------
# XFTP Chunked Encrypted File Transfer In-Memory Store (10.E.1)
# ---------------------------------------------------------------------------
file_chunks = {}
file_chunks_lock = threading.Lock()


def start_chunk_cleanup_loop():
    def run_cleanup():
        while True:
            time.sleep(600)  # every 10 minutes
            now = time.time()
            with file_chunks_lock:
                expired = [k for k, v in file_chunks.items() if v["expires_at"] < now]
                for k in expired:
                    del file_chunks[k]

    t = threading.Thread(target=run_cleanup, daemon=True)
    t.start()


start_chunk_cleanup_loop()


# ---------------------------------------------------------------------------
# XFTP File Transfer Local API Routes
# ---------------------------------------------------------------------------


@app.route("/api/file/upload/<chunk_id>", methods=["POST"])
def api_file_upload(chunk_id):
    """Local user uploads an encrypted file chunk."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_data()
    if len(data) > 16500:  # limit to ~16KB
        return jsonify({"error": "Chunk size exceeds maximum limit"}), 400

    with file_chunks_lock:
        file_chunks[chunk_id] = {
            "data": data,
            "expires_at": time.time() + 86400,  # 24 hour TTL
        }
    return jsonify({"success": True})


@app.route("/api/file/download/<chunk_id>", methods=["GET"])
def api_file_download(chunk_id):
    """
    Local user downloads a chunk.
    If 'onion' query param is set, downloads the chunk over Tor from the peer.
    Otherwise, retrieves it from the local in-memory store.
    """
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    onion = request.args.get("onion")
    if onion:
        onion = validate_onion(onion)
        if not onion:
            return jsonify({"error": "Invalid peer onion address"}), 400

        # Proxy request to remote peer over Tor
        content, status = send_onion_get(onion, f"/p2p/file/download/{chunk_id}")
        if status != 200:
            return jsonify({"error": "Failed to download chunk from peer"}), status
        return content, 200, {"Content-Type": "application/octet-stream"}

    # Local download from memory
    with file_chunks_lock:
        chunk = file_chunks.pop(chunk_id, None)

    if chunk is None or chunk["expires_at"] < time.time():
        return jsonify({"error": "Chunk not found or expired"}), 404

    return chunk["data"], 200, {"Content-Type": "application/octet-stream"}


# ---------------------------------------------------------------------------
# XFTP File Transfer Public P2P Routes (accessed over Tor)
# ---------------------------------------------------------------------------


@app.route("/p2p/file/upload/<chunk_id>", methods=["POST"])
def p2p_file_upload(chunk_id):
    """Remote peer uploads a chunk to our temporary storage."""
    data = request.get_data()
    if len(data) > 16500:
        return jsonify({"error": "Chunk size exceeds maximum limit"}), 400

    with file_chunks_lock:
        file_chunks[chunk_id] = {
            "data": data,
            "expires_at": time.time() + 86400,  # 24 hour TTL
        }
    return jsonify({"success": True})


@app.route("/p2p/file/download/<chunk_id>", methods=["GET"])
def p2p_file_download(chunk_id):
    """Remote peer downloads a chunk from our temporary storage."""
    with file_chunks_lock:
        chunk = file_chunks.pop(chunk_id, None)

    if chunk is None or chunk["expires_at"] < time.time():
        return jsonify({"error": "Chunk not found or expired"}), 404

    return chunk["data"], 200, {"Content-Type": "application/octet-stream"}


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
    host = request.headers.get("Host", "").split(":")[0].strip().lower()
    path = request.path

    is_local_host = host in ("127.0.0.1", "localhost", "[::1]")
    is_p2p_route = path.startswith("/p2p/")

    if not is_local_host and not is_p2p_route:
        # Remote users over Tor attempting to access local control panel
        return "Forbidden: Local access only", 403


# ==========================================
# 1. HTTP UI ROUTES (Local only)
# ==========================================
@app.route("/", methods=["GET"])
def index():
    """Renders registration view on first boot, login screen on subsequent boots, or redirects to chat."""
    if not database.is_initialized():
        return render_template("login.html", register_only=True)
    if "username" in session:
        return redirect(url_for("chat"))
    return render_template("login.html")


@app.route("/chat", methods=["GET"])
def chat():
    """Renders chat dashboard view for authenticated users."""
    if "username" not in session:
        return redirect(url_for("index"))
    return render_template("chat.html")


@app.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
@validate_json_schema({"username": str, "password": str})
def register():
    """Handles local database initialization and master password registration."""
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    res = database.register_local_user(username, password)
    return jsonify(res)


@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
@validate_json_schema({"username": str, "password": str})
def login():
    """Authenticates local user and derives the database decryption key from password."""
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    res = database.login_local_user(username, password)
    if res.get("success"):
        session.clear()
        session.permanent = True
        session["username"] = username
        session["active_profile_id"] = "default"

        # Retrieve db_key_salt from database
        db_key_salt_hex = database.get_config("db_key_salt")
        if db_key_salt_hex:
            salt = bytes.fromhex(db_key_salt_hex)
            iterations = 600000
        else:
            # Fallback for legacy DBs
            salt = b"salt_for_db_key_anonymus"
            iterations = 10000

        # Derive secure database encryption key
        import hashlib

        db_key = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        session["db_key_id"] = cache_db_key(db_key.hex())
    return jsonify(res)


@app.route("/logout", methods=["POST"])
def logout():
    """Clears Flask session data."""
    db_key_id = session.get("db_key_id")
    if db_key_id:
        with _DB_KEY_CACHE_LOCK:
            _DB_KEY_CACHE.pop(db_key_id, None)
    session.clear()
    return jsonify({"success": True})


# ==========================================
# 2. LOCAL API ROUTES (Local only)
# ==========================================
@app.route("/api/my_info", methods=["GET"])
def my_info():
    """Retrieves local node onion address and local username."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(
        {
            "onion_address": database.get_config("my_onion_address"),
            "local_username": session["username"],
        }
    )


@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    """Retrieves list of contacts, decrypting secrets if authenticated."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    db_key = get_db_key_hex()
    profile_id = session.get("active_profile_id", "default")
    return jsonify(database.get_contacts(db_key=db_key, profile_id=profile_id))


@app.route("/api/contacts/add", methods=["POST"])
@validate_json_schema({"onion_address": str, "nickname": str, "my_public_key": str})
def add_contact():
    """Initiates an asynchronous handshake request with a remote P2P node over Tor."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    nickname = data.get("nickname", "").strip()
    try:
        nickname = validate_nickname(nickname)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    my_public_key = data.get("my_public_key")
    if not my_public_key or not is_valid_base64_like(my_public_key, max_len=5000):
        return jsonify({"error": "Invalid public key format or size."}), 400

    if not onion:
        return jsonify({"error": "Invalid onion address."}), 400

    import secrets

    display_name = secrets.token_hex(4)
    # Save contact locally as pending_outgoing (now storing per-contact onion)
    my_onion = database.get_config("my_onion_address")
    profile_id = session.get("active_profile_id", "default")
    database.add_contact(
        onion,
        nickname,
        status="pending_outgoing",
        my_onion_address=my_onion,
        display_name=display_name,
        profile_id=profile_id,
    )

    # Store public key in contacts config
    database.set_config(f"my_pubkey_for_{onion}", my_public_key)

    # Async handshake over Tor
    nickname_to_send = display_name

    def do_handshake():
        relay = database.get_config("preferred_file_relay")
        payload = {
            "onion_address": my_onion,
            "nickname": nickname_to_send,
            "public_key": my_public_key,
        }
        if relay:
            payload["preferred_file_relay"] = relay
        res = send_onion_post(onion, "/p2p/handshake", payload)
        if "error" in res:
            # Let UI know peer is currently offline
            socketio.emit(
                "contact_status_change", {"onion_address": onion, "status": "offline"}
            )

    executor.submit(do_handshake)

    return jsonify({"success": True})


@app.route("/api/contacts/accept", methods=["POST"])
@validate_json_schema(
    {"onion_address": str, "my_public_key": str, "shared_secret": str}
)
def accept_contact():
    """Accepts a pending incoming contact handshake request and notifies the peer."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    my_public_key = data.get("my_public_key")
    shared_secret = data.get("shared_secret")

    db_key = get_db_key_hex()
    contact = database.get_contact(onion, db_key=db_key)
    if not contact:
        return jsonify({"error": "Contact not found."}), 404

    # Save the derived secret locally
    database.update_contact_secret(
        onion, shared_secret, contact["peer_public_key"], db_key=db_key
    )

    # Notify peer over Tor that we accepted
    my_onion = database.get_config("my_onion_address")

    def do_accept():
        relay = database.get_config("preferred_file_relay")
        payload = {"onion_address": my_onion, "public_key": my_public_key}
        if relay:
            payload["preferred_file_relay"] = relay
        send_onion_post(onion, "/p2p/accept", payload)

    executor.submit(do_accept)

    return jsonify({"success": True})


@app.route("/api/contacts/save_secret", methods=["POST"])
@validate_json_schema(
    {"onion_address": str, "shared_secret": str, "peer_public_key": str}
)
def save_secret():
    """Saves derived shared cryptographic secret for an accepted contact."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    shared_secret = data.get("shared_secret")
    peer_public_key = data.get("peer_public_key")
    dr_state = data.get("dr_state")
    # PQ hybrid mode fields (optional, ignored if liboqs not active)
    peer_kem_public_key = data.get("peer_kem_public_key")
    my_kem_private_key = data.get("my_kem_private_key")

    db_key = get_db_key_hex()
    database.update_contact_secret(onion, shared_secret, peer_public_key, db_key=db_key)
    if dr_state:
        database.update_contact_dr_state(onion, dr_state)
    if peer_kem_public_key or my_kem_private_key:
        database.update_contact_kem_keys(
            onion,
            peer_kem_public_key=peer_kem_public_key,
            my_kem_private_key=my_kem_private_key,
        )
    return jsonify({"success": True})


@app.route("/api/contacts/delete", methods=["POST"])
@validate_json_schema({"onion_address": str})
def delete_contact():
    """Deletes a contact and cleans up associated chat history."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400
    database.delete_contact(onion)
    return jsonify({"success": True})


@app.route("/api/contacts/migrate", methods=["POST"])
@validate_json_schema({"old_address": str, "new_address": str})
def migrate_contact():
    """Migrates a contact's onion address to a new pairwise address."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    old_addr = data.get("old_address", "").strip().lower()
    new_addr = data.get("new_address", "").strip().lower()

    old_addr = validate_onion(old_addr)
    new_addr = validate_onion(new_addr)
    if not old_addr or not new_addr:
        return jsonify({"error": "Invalid onion address"}), 400

    contact = database.get_contact(old_addr)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404

    success = database.migrate_contact_address(old_addr, new_addr)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Failed to migrate contact address"}), 500


@app.route("/api/contacts/update_display_name", methods=["POST"])
@validate_json_schema({"onion_address": str, "display_name": str})
def update_display_name():
    """Allows user to override display name for a contact connection."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    display_name = data.get("display_name", "").strip()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400
    try:
        display_name = validate_nickname(display_name)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    database.update_contact_display_name(onion, display_name)
    return jsonify({"success": True})


@app.route("/api/contacts/update_dr_state", methods=["POST"])
@validate_json_schema({"onion_address": str, "dr_state": str})
def update_dr_state():
    """Persists serialized Double Ratchet state for a contact."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    dr_state = data.get("dr_state")
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    database.update_contact_dr_state(onion, dr_state)
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Notification Queue API (10.H.3)
# ---------------------------------------------------------------------------


@app.route("/api/notifications/register", methods=["POST"])
@validate_json_schema({"onion_address": str})
def notifications_register():
    """
    Registers a random notification token for a contact.
    The Android background service stores this token and uses it to poll
    for new messages without exposing any message content.

    Returns:
        {"token": "<base64-random-32-bytes>"}
    """
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    import base64 as _base64
    import secrets as _secrets

    token = (
        _base64.urlsafe_b64encode(_secrets.token_bytes(32)).decode("utf-8").rstrip("=")
    )
    database.set_notify_token(onion, token)
    return jsonify({"token": token})


@app.route("/api/notifications/poll", methods=["GET"])
def notifications_poll():
    """
    Polls for pending notification flags for a set of tokens.
    The Android service calls this every 30s to check whether any contact
    has sent a new message.

    Query param: tokens=<comma-separated list of tokens>

    Returns:
        {"has_new": {"<token>": true/false, ...}}

    IMPORTANT: No message content is ever included in this response.
    """
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    tokens_param = request.args.get("tokens", "")
    tokens = [t.strip() for t in tokens_param.split(",") if t.strip()]
    if not tokens:
        return jsonify({"has_new": {}})
    if len(tokens) > 200:
        return jsonify({"error": "Too many tokens (max 200)"}), 400

    pending = database.poll_notify_queue(tokens)
    result = {t: (t in pending) for t in tokens}
    return jsonify({"has_new": result})


@app.route("/api/notifications/clear", methods=["POST"])
@validate_json_schema({"tokens": list})
def notifications_clear():
    """
    Clears pending notification flags for the given tokens.
    Called after the client has successfully pulled messages from the main queue.

    Body: {"tokens": ["<token1>", "<token2>", ...]}
    """
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    tokens = data.get("tokens", [])
    if not isinstance(tokens, list) or not all(isinstance(t, str) for t in tokens):
        return jsonify({"error": "tokens must be a list of strings"}), 400
    if len(tokens) > 200:
        return jsonify({"error": "Too many tokens (max 200)"}), 400

    database.clear_notify_queue(tokens)
    return jsonify({"success": True})


@app.route("/api/contacts/generate_invite", methods=["POST"])
def generate_invite():
    """
    Generates a pairwise invite link for a new connection.

    Spawns a fresh hidden service via tor_manager and returns an invite payload
    embedding the new .onion address and a fresh session token. The invite link
    is created entirely in-memory and never transmitted to a server.
    """
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    import secrets

    token = secrets.token_urlsafe(12)
    service_name = f"inv_{token}"

    try:
        invite_onion = tor_manager.add_onion_service(service_name)
    except Exception as e:
        app.logger.error(f"Failed to spawn invite hidden service: {e}")
        # Fallback to main onion when Tor is not running (dev/test environment)
        invite_onion = database.get_config("my_onion_address") or "unavailable.onion"

    return jsonify(
        {"invite_onion": invite_onion, "service_name": service_name, "token": token}
    )


@app.route("/api/contacts/accept_invite", methods=["POST"])
@validate_json_schema({"invite_onion": str, "nickname": str, "my_public_key": str})
def accept_invite():
    """
    Accepts a pairwise invite by spawning a fresh hidden service for this contact
    and sending the handshake to the invite onion address.
    """
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    invite_onion = data.get("invite_onion", "").strip().lower()
    invite_onion = validate_onion(invite_onion)
    if not invite_onion:
        return jsonify({"error": "Invalid invite onion address"}), 400

    nickname = data.get("nickname", "").strip()
    try:
        nickname = validate_nickname(nickname)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    my_public_key = data.get("my_public_key", "")
    if not is_valid_base64_like(my_public_key, max_len=5000):
        return jsonify({"error": "Invalid public key"}), 400

    import secrets

    token = secrets.token_urlsafe(12)
    service_name = f"contact_{token}"

    try:
        my_contact_onion = tor_manager.add_onion_service(service_name)
    except Exception as e:
        app.logger.error(f"Failed to spawn contact hidden service for invite: {e}")
        my_contact_onion = (
            database.get_config("my_onion_address") or "unavailable.onion"
        )

    import secrets

    display_name = secrets.token_hex(4)
    # Add contact with the pairwise onion address
    profile_id = session.get("active_profile_id", "default")
    database.add_contact(
        invite_onion,
        nickname,
        status="pending_outgoing",
        my_onion_address=my_contact_onion,
        display_name=display_name,
        profile_id=profile_id,
    )
    database.set_config(f"my_pubkey_for_{invite_onion}", my_public_key)

    nickname_to_send = display_name

    def do_handshake():
        payload = {
            "onion_address": my_contact_onion,
            "nickname": nickname_to_send,
            "public_key": my_public_key,
        }
        res = send_onion_post(invite_onion, "/p2p/handshake", payload)
        if "error" in res:
            socketio.emit(
                "contact_status_change",
                {"onion_address": invite_onion, "status": "offline"},
            )

    executor.submit(do_handshake)
    return jsonify({"success": True, "my_onion": my_contact_onion})


@app.route("/api/messages", methods=["GET"])
def get_messages():
    """Retrieves chat history for a contact."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    onion = request.args.get("onion", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    limit = request.args.get("limit")
    offset = request.args.get("offset")
    try:
        if limit is not None:
            limit = int(limit)
        if offset is not None:
            offset = int(offset)
    except ValueError:
        return jsonify({"error": "Limit and offset must be integers"}), 400

    return jsonify(database.get_messages(onion, limit=limit, offset=offset))


@app.route("/api/groups", methods=["GET"])
def api_get_groups():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    profile_id = session.get("active_profile_id", "default")
    return jsonify(database.get_groups(profile_id=profile_id))


@app.route("/api/groups/<group_id>", methods=["GET"])
def api_get_group_details(group_id):
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    group = database.get_group(group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    members = database.get_group_members(group_id)
    return jsonify({"group": group, "members": members})


@app.route("/api/groups/create", methods=["POST"])
def api_create_group():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    founder_onion = data.get("founder_onion", "").strip().lower()
    group_id = data.get("group_id") or str(uuid.uuid4())
    is_channel = int(data.get("is_channel", 0))

    profile_id = session.get("active_profile_id", "default")
    database.create_group(
        group_id, name, founder_onion, profile_id=profile_id, is_channel=is_channel
    )

    # Add creator as founder member
    my_username = session["username"]
    database.add_group_member(group_id, founder_onion, my_username, role="founder")

    return jsonify({"success": True, "group_id": group_id})


@app.route("/api/groups/add_member", methods=["POST"])
@validate_json_schema(
    {"group_id": str, "member_onion": str, "nickname": str, "role": str}
)
def api_group_add_member():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    group_id = data.get("group_id")
    member_onion = data.get("member_onion")
    nickname = data.get("nickname")
    role = data.get("role", "member")

    database.add_group_member(group_id, member_onion, nickname, role=role)
    return jsonify({"success": True})


@app.route("/api/groups/remove_member", methods=["POST"])
@validate_json_schema({"group_id": str, "member_onion": str})
def api_group_remove_member():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    group_id = data.get("group_id")
    member_onion = data.get("member_onion")

    database.remove_group_member(group_id, member_onion)
    return jsonify({"success": True})


@app.route("/api/groups/save_message", methods=["POST"])
@validate_json_schema(
    {
        "group_id": str,
        "sender_onion": str,
        "sender_nickname": str,
        "message": str,
        "timestamp": int,
    }
)
def api_group_save_message():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    group_id = data.get("group_id")
    sender_onion = data.get("sender_onion")
    sender_nickname = data.get("sender_nickname")
    message = data.get("message")
    timestamp = data.get("timestamp")

    # Check if group is a channel
    group = database.get_group(group_id)
    if group and group.get("is_channel") == 1:
        if sender_onion.lower() != group["founder_onion"].lower():
            return jsonify(
                {"error": "Unauthorized: Only channel founder can post messages."}
            ), 403

    database.save_group_message(
        group_id, sender_onion, sender_nickname, message, timestamp=timestamp
    )

    # Notify browser UI that group message is saved
    socketio.emit(
        "group_message_saved",
        {
            "group_id": group_id,
            "sender_onion": sender_onion,
            "sender_nickname": sender_nickname,
            "message": message,
            "timestamp": timestamp,
        },
    )

    return jsonify({"success": True})


@app.route("/api/groups/report_message", methods=["POST"])
@validate_json_schema(
    {"message_hash": str, "reporter_onion": str, "reason": str, "signature": str}
)
def api_report_message():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    report_id = str(uuid.uuid4())
    message_hash = data.get("message_hash")
    reporter_onion = data.get("reporter_onion")
    reason = data.get("reason")
    signature = data.get("signature")

    database.save_abuse_report(
        report_id, message_hash, reporter_onion, reason, signature
    )
    return jsonify({"success": True, "report_id": report_id})


@app.route("/api/profile/supporter_badge", methods=["POST"])
@validate_json_schema({"onion_address": str, "signature": str})
def api_supporter_badge():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    onion_address = data.get("onion_address").strip().lower()
    signature = data.get("signature").strip()

    from core.crypto import verify_supporter_badge

    is_valid = verify_supporter_badge(onion_address, signature)
    if not is_valid:
        return jsonify({"error": "Invalid supporter signature."}), 400

    database.save_supporter_badge(onion_address, signature)
    return jsonify({"success": True})


@app.route("/api/profile/supporter_badge/status", methods=["GET"])
def api_supporter_badge_status():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    onion_address = request.args.get("onion_address", "").strip().lower()
    badge = database.get_supporter_badge(onion_address)
    if badge:
        return jsonify(
            {"is_supporter": True, "badge_signature": badge["badge_signature"]}
        )
    return jsonify({"is_supporter": False})


@app.route("/api/groups/<group_id>/messages", methods=["GET"])
def api_group_get_messages(group_id):
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(database.get_group_messages(group_id))


@app.route("/api/groups/invite", methods=["POST"])
@validate_json_schema({"group_id": str})
def api_group_generate_invite():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    group_id = data.get("group_id")

    token = str(uuid.uuid4())
    database.create_group_invite(token, group_id)
    return jsonify({"success": True, "token": token})


@app.route("/api/groups/use_invite", methods=["POST"])
@validate_json_schema({"token": str})
def api_group_use_invite():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    token = data.get("token")
    group_id = database.use_group_invite(token)
    if group_id:
        return jsonify({"success": True, "group_id": group_id})
    return jsonify({"error": "Invalid or expired invite token"}), 400


@app.route("/api/groups/vouch", methods=["POST"])
@validate_json_schema({"group_id": str, "vouching_member": str, "vouched_member": str})
def api_group_add_vouch():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    group_id = data.get("group_id")
    vouching_member = data.get("vouching_member")
    vouched_member = data.get("vouched_member")

    database.add_member_vouch(group_id, vouching_member, vouched_member)

    # Notify group UI
    socketio.emit(
        "group_vouch_added",
        {
            "group_id": group_id,
            "vouching_member": vouching_member,
            "vouched_member": vouched_member,
        },
    )
    return jsonify({"success": True})


@app.route("/api/groups/<group_id>/vouches", methods=["GET"])
def api_group_get_vouches(group_id):
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(database.get_member_vouches(group_id))


@app.route("/api/messages/send", methods=["POST"])
@validate_json_schema({"onion_address": str, "iv": str, "ciphertext": str, "seq": int})
def send_message():
    """Encrypts and pushes message to peer onion service over Tor."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    iv = data.get("iv")
    ciphertext = data.get("ciphertext")
    seq = int(data.get("seq"))

    db_key = get_db_key_hex()
    contact = database.get_contact(onion, db_key=db_key)
    if not contact or contact["status"] != "accepted":
        return jsonify({"error": "Contact not accepted or not found."}), 400

    timestamp = int(time.time() * 1000)

    disappearing_ttl = contact.get("disappearing_ttl")
    expires_at = None
    if disappearing_ttl and disappearing_ttl > 0:
        expires_at = timestamp + disappearing_ttl

    is_ephemeral = bool(data.get("ephemeral", False))

    # Save locally first (unless ephemeral)
    if not is_ephemeral:
        message_payload = {"iv": iv, "ciphertext": ciphertext, "seq": seq}
        database.save_message(
            onion, "me", json.dumps(message_payload), timestamp, expires_at=expires_at
        )

    # Send over Tor
    my_onion = database.get_config("my_onion_address")

    def transmit():
        payload = {
            "sender": my_onion,
            "iv": iv,
            "ciphertext": ciphertext,
            "seq": seq,
            "timestamp": timestamp,
            "ephemeral": is_ephemeral,
        }
        if expires_at is not None:
            payload["expires_at"] = expires_at
        res = send_onion_post(onion, "/p2p/message", payload)
        if "error" in res:
            # Let UI know it failed (peer offline) unless it is ephemeral
            if not is_ephemeral:
                socketio.emit(
                    "message_delivery_failed",
                    {"onion_address": onion, "timestamp": timestamp},
                )

    executor.submit(transmit)

    return jsonify({"success": True, "timestamp": timestamp, "expires_at": expires_at})


@app.route("/api/messages/send_batch", methods=["POST"])
def send_message_batch():
    """Encrypts and pushes a batch of messages to peer onion service over Tor."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    events = data.get("events", [])
    if not events:
        return jsonify({"success": True})

    db_key = get_db_key_hex()
    contact = database.get_contact(onion, db_key=db_key)
    if not contact or contact["status"] != "accepted":
        return jsonify({"error": "Contact not accepted or not found."}), 400

    timestamp = int(time.time() * 1000)
    disappearing_ttl = contact.get("disappearing_ttl")
    expires_at = None
    if disappearing_ttl and disappearing_ttl > 0:
        expires_at = timestamp + disappearing_ttl

    for event in events:
        is_ephemeral = bool(event.get("ephemeral", False))
        if not is_ephemeral:
            iv = event.get("iv")
            ciphertext = event.get("ciphertext")
            seq = int(event.get("seq"))
            event_payload = {"iv": iv, "ciphertext": ciphertext, "seq": seq}
            database.save_message(
                onion, "me", json.dumps(event_payload), timestamp, expires_at=expires_at
            )

    # Send over Tor
    my_onion = database.get_config("my_onion_address")

    def transmit():
        payload = {"sender": my_onion, "events": events, "timestamp": timestamp}
        if expires_at is not None:
            payload["expires_at"] = expires_at
        res = send_onion_post(onion, "/p2p/message/batch", payload)
        if "error" in res:
            for event in events:
                if not event.get("ephemeral"):
                    socketio.emit(
                        "message_delivery_failed",
                        {"onion_address": onion, "timestamp": timestamp},
                    )

    executor.submit(transmit)
    return jsonify({"success": True, "timestamp": timestamp, "expires_at": expires_at})


@app.route("/api/messages/set_ttl", methods=["POST"])
@validate_json_schema({"onion_address": str})
def set_message_ttl():
    """Sets the per-conversation disappearing message TTL."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    ttl_ms = data.get("ttl_ms")  # Can be None or int
    if ttl_ms is not None:
        try:
            ttl_ms = int(ttl_ms)
            if ttl_ms < 0:
                raise ValueError()
        except ValueError:
            return jsonify({"error": "TTL must be a non-negative integer or null"}), 400

    database.set_disappearing_ttl(onion, ttl_ms)
    return jsonify({"success": True})


@app.route("/api/messages/delete", methods=["POST"])
@validate_json_schema({"onion_address": str, "timestamp": int})
def delete_message():
    """Deletes a message locally and propagates the deletion request to the remote peer."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    timestamp = int(data.get("timestamp"))

    # 1. Delete locally
    database.delete_message_by_timestamp(onion, timestamp)

    # 2. Propagate to remote peer via Tor
    my_onion = database.get_config("my_onion_address")

    def propagate():
        payload = {"sender": my_onion, "timestamp": timestamp}
        send_onion_post(onion, "/p2p/delete", payload)

    executor.submit(propagate)
    return jsonify({"success": True})


@app.route("/api/settings/preferred_relay", methods=["GET", "POST"])
def api_preferred_relay():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "GET":
        val = database.get_config("preferred_file_relay") or ""
        return jsonify({"preferred_file_relay": val})
    else:
        # POST
        data = request.get_json() or {}
        val = data.get("preferred_file_relay", "").strip()
        if val and not val.startswith("http"):
            return jsonify(
                {"error": "Preferred file relay must be a valid HTTP/HTTPS URL"}
            ), 400
        database.set_config("preferred_file_relay", val)
        return jsonify({"success": True})


@app.route("/api/contacts/update_receipts", methods=["POST"])
@validate_json_schema({"onion_address": str, "send_receipts": bool})
def api_update_receipts():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400
    send_receipts = data.get("send_receipts")
    database.update_send_receipts(onion, send_receipts)
    return jsonify({"success": True})


@app.route("/api/messages/edits", methods=["GET"])
def api_message_edits():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    onion = request.args.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400
    ts_str = request.args.get("timestamp", "0")
    try:
        timestamp = int(ts_str)
    except ValueError:
        return jsonify({"error": "Invalid timestamp"}), 400
    edits = database.get_message_edits(onion, timestamp)
    return jsonify({"edits": edits})


@app.route("/api/messages/edit", methods=["POST"])
@validate_json_schema({"onion_address": str, "timestamp": int, "message": str})
def edit_message():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400
    timestamp = int(data.get("timestamp"))
    message = data.get("message", "").strip()
    database.update_message_text(onion, timestamp, message)
    return jsonify({"success": True})


@app.route("/api/messages/receipt", methods=["POST"])
@validate_json_schema({"onion_address": str, "timestamp": int, "state": str})
def api_message_receipt():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400
    timestamp = int(data.get("timestamp"))
    state = data.get("state", "").strip()
    database.update_message_delivery_state(onion, timestamp, state)
    return jsonify({"success": True})


@app.route("/api/reset-data", methods=["POST"])
@validate_json_schema({"confirm": str})
def handle_reset_data():
    """Wipes all local contacts, configuration, and messages databases."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if data.get("confirm") != "RESET":
        return jsonify({"error": "Confirmation phrase 'RESET' is required"}), 400

    database.reset_app_data()
    return jsonify({"success": True})


# ==========================================
# 3. PUBLIC TOR P2P ROUTES (Tor Network only)
# ==========================================
@app.route("/p2p/handshake", methods=["POST"])
@csrf.exempt
@limiter.limit("20 per minute", key_func=get_p2p_rate_limit_key)
@validate_json_schema({"onion_address": str, "nickname": str, "public_key": str})
def p2p_handshake():
    """Receives contact request handshakes from remote Tor peers."""
    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    nickname = data.get("nickname", "").strip()
    try:
        nickname = validate_nickname(nickname)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    public_key = data.get("public_key", "").strip()
    if not is_valid_base64_like(public_key, max_len=5000):
        return jsonify({"error": "Invalid public key"}), 400

    if not onion:
        return jsonify({"error": "Missing or invalid payload fields"}), 400

    # Validate Host header — must match one of our registered onion addresses
    host = request.headers.get("Host", "").strip().lower().split(":")[0]
    if host and host.endswith(".onion"):
        # Build set of all known per-contact onion addresses
        contacts = database.get_contacts()
        known_onions = {
            c["my_onion_address"] for c in contacts if c.get("my_onion_address")
        }
        main_onion = database.get_config("my_onion_address")
        if main_onion:
            known_onions.add(main_onion.strip().lower())
        if known_onions and host not in known_onions:
            app.logger.warning(
                f"Rejected handshake: Host {host} not in known onion set"
            )
            return jsonify({"error": "Not found"}), 404

    # Verify contact is not blocked
    existing = database.get_contact(onion)
    if existing and existing["status"] == "blocked":
        return jsonify({"error": "blocked"}), 403

    import secrets

    display_name = secrets.token_hex(4)
    # Store request locally as pending_incoming
    database.add_contact(
        onion, nickname, status="pending_incoming", display_name=display_name
    )
    database.update_contact_secret(onion, None, public_key)
    database.update_contact_status(onion, "pending_incoming")
    preferred_file_relay = data.get("preferred_file_relay", "").strip()
    if preferred_file_relay and preferred_file_relay.startswith("http"):
        database.update_preferred_relay(onion, preferred_file_relay)

    # Emit event to local browser UI
    socketio.emit(
        "incoming_contact_request",
        {"onion_address": onion, "nickname": nickname, "peer_public_key": public_key},
    )

    return jsonify({"status": "pending"})


@app.route("/p2p/accept", methods=["POST"])
@csrf.exempt
@limiter.limit("20 per minute", key_func=get_p2p_rate_limit_key)
@validate_json_schema({"onion_address": str, "public_key": str})
def p2p_accept():
    """Receives handshake acceptance confirmation from a remote peer."""
    data = request.get_json()
    onion = data.get("onion_address", "").strip().lower()
    onion = validate_onion(onion)
    if not onion:
        return jsonify({"error": "Invalid onion address"}), 400

    public_key = data.get("public_key", "").strip()
    if not is_valid_base64_like(public_key, max_len=5000):
        return jsonify({"error": "Invalid public key"}), 400

    contact = database.get_contact(onion)
    if not contact:
        return jsonify({"error": "No handshake record found."}), 404

    # Retrieve our own public key generated for this contact
    my_pubkey = database.get_config(f"my_pubkey_for_{onion}")

    preferred_file_relay = data.get("preferred_file_relay", "").strip()
    if preferred_file_relay and preferred_file_relay.startswith("http"):
        database.update_preferred_relay(onion, preferred_file_relay)

    # Emit event to browser to trigger DH secret derivation
    socketio.emit(
        "handshake_accepted",
        {
            "onion_address": onion,
            "peer_public_key": public_key,
            "my_public_key": my_pubkey,
        },
    )

    return jsonify({"status": "accepted"})


@app.route("/p2p/message/batch", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per minute", key_func=get_p2p_rate_limit_key)
def p2p_message_batch():
    """Receives incoming encrypted message batches from authorized remote peers."""
    data = request.get_json()
    sender = data.get("sender", "").strip().lower()
    sender = validate_onion(sender)
    if not sender:
        return jsonify({"error": "Invalid onion address"}), 400

    events = data.get("events", [])
    timestamp = int(data.get("timestamp", time.time() * 1000))

    contact = database.get_contact(sender)
    if not contact or contact["status"] != "accepted":
        return jsonify({"error": "Unauthorized contact."}), 403

    expires_at = data.get("expires_at")
    if expires_at is None and contact.get("disappearing_ttl"):
        expires_at = timestamp + contact["disappearing_ttl"]

    # Validate and save events
    for event in events:
        iv = event.get("iv")
        ciphertext = event.get("ciphertext")
        seq = int(event.get("seq"))
        is_ephemeral = bool(event.get("ephemeral", False))

        if not is_valid_base64_like(iv, max_len=100) or not is_valid_base64_like(
            ciphertext, max_len=100000
        ):
            continue

        last_seq = database.get_last_sequence_number(sender)
        if seq <= last_seq:
            continue

        if not is_ephemeral:
            message_payload = {"iv": iv, "ciphertext": ciphertext, "seq": seq}
            database.save_message(
                sender,
                sender,
                json.dumps(message_payload),
                timestamp,
                expires_at=expires_at,
            )

            # Notify queue: push a zero-content flag for Android background service
            notify_token = database.get_notify_token(sender)
            if notify_token:
                database.push_notify_queue(notify_token)

        # Push notification to active local browser UI
        socketio.emit(
            "incoming_message",
            {
                "sender": sender,
                "iv": iv,
                "ciphertext": ciphertext,
                "seq": seq,
                "timestamp": timestamp,
                "expires_at": expires_at,
                "ephemeral": is_ephemeral,
            },
        )

    return jsonify({"status": "delivered"})


@app.route("/p2p/message", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per minute", key_func=get_p2p_rate_limit_key)
@validate_json_schema(
    {"sender": str, "iv": str, "ciphertext": str, "seq": int, "timestamp": int}
)
def p2p_message():
    """Receives incoming encrypted messages from authorized remote peers."""
    data = request.get_json()
    sender = data.get("sender", "").strip().lower()
    sender = validate_onion(sender)
    if not sender:
        return jsonify({"error": "Invalid onion address"}), 400

    iv = data.get("iv")
    ciphertext = data.get("ciphertext")
    seq = int(data.get("seq"))
    timestamp = int(data.get("timestamp"))

    if not is_valid_base64_like(iv, max_len=100) or not is_valid_base64_like(
        ciphertext, max_len=100000
    ):
        return jsonify({"error": "Invalid cryptographic payload"}), 400

    contact = database.get_contact(sender)
    if not contact or contact["status"] != "accepted":
        return jsonify({"error": "Unauthorized contact."}), 403

    preferred_file_relay = data.get("preferred_file_relay", "").strip()
    if preferred_file_relay and preferred_file_relay.startswith("http"):
        database.update_preferred_relay(sender, preferred_file_relay)

    last_seq = database.get_last_sequence_number(sender)
    if seq <= last_seq:
        return jsonify({"error": "Sequence number must be strictly monotonic"}), 400

    expires_at = data.get("expires_at")
    if expires_at is None and contact.get("disappearing_ttl"):
        expires_at = timestamp + contact["disappearing_ttl"]

    is_ephemeral = bool(data.get("ephemeral", False))

    if not is_ephemeral:
        # Store encrypted payload locally
        message_payload = {"iv": iv, "ciphertext": ciphertext, "seq": seq}
        database.save_message(
            sender,
            sender,
            json.dumps(message_payload),
            timestamp,
            expires_at=expires_at,
        )

        # Notify queue: push a zero-content flag for the Android background service
        notify_token = database.get_notify_token(sender)
        if notify_token:
            database.push_notify_queue(notify_token)

    # Push notification to active local browser UI
    socketio.emit(
        "incoming_message",
        {
            "sender": sender,
            "iv": iv,
            "ciphertext": ciphertext,
            "seq": seq,
            "timestamp": timestamp,
            "expires_at": expires_at,
            "ephemeral": is_ephemeral,
        },
    )

    return jsonify({"status": "delivered"})


@app.route("/p2p/delete", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per minute", key_func=get_p2p_rate_limit_key)
@validate_json_schema({"sender": str, "timestamp": int})
def p2p_delete():
    """Receives and processes message deletion requests from remote peers."""
    data = request.get_json()
    sender = data.get("sender", "").strip().lower()
    sender = validate_onion(sender)
    if not sender:
        return jsonify({"error": "Invalid onion address"}), 400

    timestamp = int(data.get("timestamp"))

    contact = database.get_contact(sender)
    if not contact or contact["status"] != "accepted":
        return jsonify({"error": "Unauthorized contact."}), 403

    # Delete the message
    database.delete_message_by_timestamp(sender, timestamp)

    # Notify UI to remove message from DOM
    socketio.emit("message_deleted", {"onion_address": sender, "timestamp": timestamp})

    return jsonify({"status": "deleted"})


import bcrypt


@app.route("/api/profiles", methods=["GET"])
def api_get_profiles():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(database.get_profiles())


@app.route("/api/profiles/create", methods=["POST"])
def api_create_profile():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    display_name = data.get("display_name", "").strip()
    hidden = int(data.get("hidden", 0))
    passphrase = data.get("passphrase", "")

    if not display_name:
        return jsonify({"error": "Display name is required"}), 400

    profile_id = str(uuid.uuid4())
    passphrase_hash = None
    if hidden and passphrase:
        salt = bcrypt.gensalt()
        passphrase_hash = bcrypt.hashpw(passphrase.encode("utf-8"), salt).decode(
            "utf-8"
        )

    database.create_profile(profile_id, display_name, hidden, passphrase_hash)
    return jsonify({"success": True, "profile_id": profile_id})


@app.route("/api/profiles/unlock", methods=["POST"])
def api_unlock_profile():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    passphrase = data.get("passphrase", "")

    profile = database.verify_hidden_profile(passphrase)
    if profile:
        session["active_profile_id"] = profile["profile_id"]
        return jsonify({"success": True, "profile": profile})
    else:
        return jsonify({"error": "Invalid credentials"}), 401


@app.route("/api/profiles/switch", methods=["POST"])
def api_switch_profile():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    profile_id = data.get("profile_id", "default")

    profile = database.get_profile(profile_id)
    if profile and profile["hidden"] == 0:
        session["active_profile_id"] = profile_id
        return jsonify({"success": True, "profile_id": profile_id})
    return jsonify({"error": "Unauthorized or profile not found"}), 403


@app.route("/api/profiles/active", methods=["GET"])
def api_active_profile():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    profile_id = session.get("active_profile_id", "default")
    profile = database.get_profile(profile_id)
    if profile:
        return jsonify(
            {
                "profile_id": profile_id,
                "display_name": profile["display_name"],
                "hidden": profile["hidden"],
            }
        )
    return jsonify(
        {"profile_id": "default", "display_name": "Default Profile", "hidden": 0}
    )


active_pairing_broker = None
pairing_private_key = None


def get_local_ip():
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


@app.route("/api/sync/pair", methods=["POST"])
def api_sync_pair():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    global active_pairing_broker, pairing_private_key
    import base64

    from cryptography.hazmat.primitives.asymmetric import x25519

    if active_pairing_broker is not None:
        ip = get_local_ip()
        pub_bytes = pairing_private_key.public_key().public_bytes_raw()
        pub_b64 = base64.b64encode(pub_bytes).decode("utf-8")
        return jsonify({"success": True, "ip": ip, "port": 8999, "k": pub_b64})

    pairing_private_key = x25519.X25519PrivateKey.generate()
    pub_bytes = pairing_private_key.public_key().public_bytes_raw()
    pub_b64 = base64.b64encode(pub_bytes).decode("utf-8")
    ip = get_local_ip()
    port = 8999

    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class FlaskPairingHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == "/api/sync/pairing":
                content_length = int(self.headers["Content-Length"])
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode("utf-8"))
                    client_pub_b64 = payload.get("client_public_key")
                    ciphertext_b64 = payload.get("ciphertext")
                    iv_b64 = payload.get("iv")

                    peer_pub = x25519.X25519PublicKey.from_public_bytes(
                        base64.b64decode(client_pub_b64)
                    )
                    shared_key = pairing_private_key.exchange(peer_pub)

                    from cryptography.hazmat.primitives import hashes
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

                    aes_key = HKDF(
                        algorithm=hashes.SHA256(),
                        length=32,
                        salt=None,
                        info=b"AnonyMus-Device-Sync-Key",
                    ).derive(shared_key)

                    aesgcm = AESGCM(aes_key)
                    decrypted = aesgcm.decrypt(
                        base64.b64decode(iv_b64), base64.b64decode(ciphertext_b64), None
                    )

                    db_path = database.DB_FILE
                    if os.path.exists(db_path):
                        import shutil

                        shutil.copyfile(db_path, db_path + ".bak")

                    with open(db_path, "wb") as f:
                        f.write(decrypted)

                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"success": true}')
                except Exception as e:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(str(e).encode())
            else:
                self.send_response(404)
                self.end_headers()

    def run_server():
        global active_pairing_broker
        try:
            active_pairing_broker = HTTPServer((ip, port), FlaskPairingHandler)
            active_pairing_broker.serve_forever()
        except Exception:
            pass

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    return jsonify({"success": True, "ip": ip, "port": port, "k": pub_b64})


@app.route("/api/sync/push", methods=["POST"])
def api_sync_push():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    import base64

    from cryptography.hazmat.primitives.asymmetric import x25519

    data = request.get_json() or {}
    desktop_ip = data.get("ip")
    desktop_port = data.get("port")
    desktop_key_b64 = data.get("k")

    if not desktop_ip or not desktop_port or not desktop_key_b64:
        return jsonify({"error": "Missing pairing credentials"}), 400

    try:
        db_path = database.DB_FILE
        with open(db_path, "rb") as f:
            db_bytes = f.read()

        client_priv = x25519.X25519PrivateKey.generate()
        client_pub = client_priv.public_key()

        peer_pub = x25519.X25519PublicKey.from_public_bytes(
            base64.b64decode(desktop_key_b64)
        )
        shared_key = client_priv.exchange(peer_pub)

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"AnonyMus-Device-Sync-Key",
        ).derive(shared_key)

        iv = os.urandom(12)
        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(iv, db_bytes, None)

        import requests

        res = requests.post(
            f"http://{desktop_ip}:{desktop_port}/api/sync/pairing",
            json={
                "client_public_key": base64.b64encode(
                    client_pub.public_bytes_raw()
                ).decode("utf-8"),
                "iv": base64.b64encode(iv).decode("utf-8"),
                "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
            },
            timeout=15,
        )

        if res.status_code == 200:
            return jsonify(
                {"success": True, "message": "Database backup successfully fanned out!"}
            )
        else:
            return jsonify({"error": f"Broker returned error: {res.text}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_legacy_migration():
    """Checks for legacy contacts (from v0.9) and generates pairwise hidden services and display names for them."""
    try:
        contacts = database.get_contacts()
        main_onion = database.get_config("my_onion_address")
        for c in contacts:
            if not c.get("my_onion_address") or (
                main_onion
                and c["my_onion_address"].strip().lower() == main_onion.strip().lower()
            ):
                import secrets

                token = secrets.token_urlsafe(12)
                service_name = f"contact_{token}"
                try:
                    new_onion = tor_manager.add_onion_service(service_name)
                    database.update_contact_my_onion(c["onion_address"], new_onion)
                    app.logger.info(
                        f"Generated pairwise onion {new_onion} for legacy contact {c['nickname']}"
                    )
                except Exception as e:
                    app.logger.error(
                        f"Failed to generate pairwise onion for legacy contact {c['nickname']}: {e}"
                    )
            if not c.get("display_name"):
                import secrets

                display_name = secrets.token_hex(4)
                database.update_contact_display_name(c["onion_address"], display_name)
    except Exception as e:
        app.logger.error(f"Error running legacy migration: {e}")


# ==========================================
# STARTUP
# ==========================================
if __name__ == "__main__":
    # Launch Tor expert bundle and bind ports
    try:
        onion, socks, peer = tor_manager.launch_tor()
        SOCKS_PORT = socks
        database.set_config("my_onion_address", onion)
        run_legacy_migration()
    except Exception as e:
        print(f"FATAL: Embedded Tor failed to start: {e}")
        sys.exit(1)

    print(f"Flask running local control panel on http://127.0.0.1:{peer}")
    socketio.run(app, host="127.0.0.1", port=peer, debug=False)
