"""
Server Module for AnonyMus (Client-Server Relay Architecture).

Implements a zero-knowledge WebSocket relay server using Flask-SocketIO.
Coordinates secure message routing, queue ownership validation, session management,
rate limiting, self-signed SSL certificate generation, and mDNS local network service discovery.
"""

import eventlet

eventlet.monkey_patch()

import datetime
import logging
import json
import os
import re
import socket
import threading
import time
import uuid

# database decommissioned
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO, emit, join_room

# Load configurations from environment file
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

from core.logging import setup_logging

setup_logging(app)


@app.context_processor
def inject_mode():
    return dict(mode="relay")


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
        "Using ephemeral key. Sessions will NOT persist across restarts/workers!"
    )
    app.logger.warning("=" * 80)
    secret_key = os.urandom(32).hex()
app.secret_key = secret_key

# Apply session cookie and payload constraints
from datetime import timedelta

app.config.update(
    SESSION_COOKIE_SECURE=os.environ.get("DISABLE_SSL", "False").lower() != "true",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,  # Enforce 1MB maximum payload size
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

# Initialize HTTP endpoint rate limiter (uses Redis backend if configured)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.environ.get("REDIS_URL", "memory://"),
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
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
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
            from zeroconf import ServiceInfo, Zeroconf

            zeroconf_instance = Zeroconf()
            local_ip = get_local_ip()
            info = ServiceInfo(
                "_anonymus._tcp.local.",
                "AnonyMus Server._anonymus._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=port,
                properties={},
            )
            zeroconf_instance.register_service(info)
            print(
                f"mDNS Service advertised: _anonymus._tcp.local. on {local_ip}:{port}"
            )
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
    log_message = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "[REDACTED-UUID]",
        log_message,
    )
    # Redact Base64 ciphertext/key payloads
    log_message = re.sub(r"[A-Za-z0-9+/]{20,}={0,2}", "[REDACTED-B64]", log_message)
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


from core.security_headers import setup_security_headers

setup_security_headers(app)


# Configure allowed Socket.IO CORS Origins dynamically
cors_origins_env = os.environ.get("CORS_ORIGINS")
if cors_origins_env:
    allowed_origins = [
        orig.strip() for orig in cors_origins_env.split(",") if orig.strip()
    ]
else:
    if debug_mode and os.environ.get("ANONYMUS_ENV", "").lower() != "production":
        allowed_origins = "*"
    else:
        local_ip = get_local_ip()
        allowed_origins = [
            "https://localhost",
            "https://127.0.0.1",
            f"https://{local_ip}",
        ]

redis_url = os.environ.get("REDIS_URL")
socketio_kwargs = {
    "cors_allowed_origins": allowed_origins,
    "transports": ["websocket"],
    "engineio_logger": False,
    "ping_timeout": 60,
    "ping_interval": 25,
}
if redis_url:
    socketio_kwargs["message_queue"] = redis_url

socketio = SocketIO(app, **socketio_kwargs)

if not redis_url and os.environ.get("WEB_CONCURRENCY", "1") != "1":
    app.logger.warning(
        "Multi-worker mode without Redis detected. "
        "Rate limiting and queue ownership will be per-worker. "
        "Set REDIS_URL for consistent state."
    )

# Setup Redis Client connection pool if configuring multi-worker scaling
r_client = None
if redis_url:
    try:
        import redis

        r_client = redis.Redis.from_url(redis_url, decode_responses=True)
    except Exception as e:
        app.logger.warning(
            f"Could not initialize Redis client, falling back to memory: {e}"
        )

# Database init decommissioned (blind relay mode)

# Queue state management maps & lock primitives (for single worker fallback)
queue_owners = {}
queue_creators = {}
queue_owners_lock = threading.Lock()

# Offline store-and-forward buffer (queue_id -> list of payloads)
# Messages are buffered here when the recipient is offline and flushed on reconnect.
# Redis list `offline_queue:<queue_id>` is used when r_client is configured.
offline_queue = {}
offline_queue_lock = threading.Lock()
MAX_OFFLINE_QUEUE = 500  # max buffered messages per queue
OFFLINE_QUEUE_TTL = 86400  # 24 hours TTL in Redis


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
            if creator_sid:
                return r_client.sismember("online_sids", creator_sid)
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


def enqueue_offline(queue_id: str, payload: str):
    """
    Stores an undeliverable message payload in the offline buffer.

    Uses a Redis list when available, otherwise an in-memory dict.
    Enforces a per-queue cap of MAX_OFFLINE_QUEUE messages to bound memory usage.
    """
    if r_client:
        try:
            key = f"offline_queue:{queue_id}"
            r_client.rpush(key, payload)
            r_client.ltrim(key, -MAX_OFFLINE_QUEUE, -1)  # keep latest N
            r_client.expire(key, OFFLINE_QUEUE_TTL)
            return
        except Exception as e:
            app.logger.warning(f"Redis enqueue_offline failed: {e}")
    with offline_queue_lock:
        if queue_id not in offline_queue:
            offline_queue[queue_id] = []
        offline_queue[queue_id].append(payload)
        # Trim to cap
        if len(offline_queue[queue_id]) > MAX_OFFLINE_QUEUE:
            offline_queue[queue_id] = offline_queue[queue_id][-MAX_OFFLINE_QUEUE:]


def flush_offline_queue(queue_id: str, sid: str):
    """
    Delivers all buffered offline messages to the now-online recipient.

    Drains the Redis list (or in-memory buffer) and emits each payload as a
    `queue_payload` event to the recipient's socket, then deletes the buffer.
    """
    payloads = []
    if r_client:
        try:
            key = f"offline_queue:{queue_id}"
            payloads = r_client.lrange(key, 0, -1)
            r_client.delete(key)
        except Exception as e:
            app.logger.warning(f"Redis flush_offline_queue failed: {e}")
    if not payloads:
        with offline_queue_lock:
            payloads = offline_queue.pop(queue_id, [])

    for payload in payloads:
        socketio.emit(
            "queue_payload", {"queue_id": queue_id, "payload": payload}, to=sid
        )

    if payloads:
        app.logger.debug(
            f"Flushed {len(payloads)} offline message(s) to SID={sid[:4]} for queue={queue_id[:8]}"
        )


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
        socket_rate_limits[sid] = [
            t for t in socket_rate_limits[sid] if now - t < window
        ]

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


# Session/User validation logic decommissioned for zero-identifier queue mode


# ==========================================
# 1. HTTP ROUTES
# ==========================================


@app.route("/", methods=["GET"])
def index():
    """Renders chat panel directly (no authentication)."""
    return render_template("chat.html")


@app.route("/chat", methods=["GET"])
def chat():
    """Redirects to index since chat is at root now."""
    return redirect(url_for("index"))


@app.route("/health", methods=["GET"])
def health():
    """Basic health check probe for cluster metrics/monitoring."""
    return jsonify(
        {"status": "ok", "timestamp": datetime.datetime.utcnow().isoformat()}
    ), 200


# ==========================================
# 2. WEBSOCKET HANDLERS
# ==========================================


@socketio.on("connect")
def handle_connect():
    """Allows anonymous client connections."""
    with socket_connect_times_lock:
        socket_connect_times[request.sid] = time.time()

    if r_client:
        try:
            r_client.sadd("online_sids", request.sid)
        except Exception as e:
            app.logger.warning(f"Failed to record socket online in Redis: {e}")

    truncated_sid = request.sid[:4] if request.sid else "None"
    app.logger.debug(f"Client connected. SID={truncated_sid}")

    with socket_rate_limits_lock:
        if request.sid not in socket_rate_limits:
            socket_rate_limits[request.sid] = []


@socketio.on("create_queue")
def handle_create_queue():
    """Generates a secure UUID and sets up an authorized message queue for client."""
    if is_rate_limited(request.sid, limit=5, window=10):
        app.logger.warning(
            f"Rate limit exceeded for create_queue on SID={request.sid[:4]}"
        )
        return

    queue_id = str(uuid.uuid4())
    add_queue_owner(queue_id, request.sid)
    add_queue_creator(queue_id, request.sid)
    join_room(queue_id)
    app.logger.debug(f"Queue room {queue_id} joined by SID={request.sid[:4]}")

    emit("queue_created", {"queue_id": queue_id})

    # Flush any messages that arrived while this client was offline (10.C.1)
    flush_offline_queue(queue_id, request.sid)


@socketio.on("rejoin_queue")
def handle_rejoin_queue(data):
    """
    Reclaims ownership of a previously held queue after a reconnect.

    The client persists its queue_id locally and sends it back on reconnect.
    The relay re-registers the client as owner/creator and flushes any buffered
    offline messages (10.C.1 delete-on-delivery store-and-forward).

    Args:
        data (dict): Must contain 'queue_id' (str) — the previously issued UUID.
    """
    if is_rate_limited(request.sid, limit=5, window=10):
        app.logger.warning(
            f"Rate limit exceeded for rejoin_queue on SID={request.sid[:4]}"
        )
        return

    queue_id = data.get("queue_id", "").strip()
    if not queue_id:
        return

    add_queue_owner(queue_id, request.sid)
    add_queue_creator(queue_id, request.sid)
    join_room(queue_id)
    app.logger.debug(f"Queue room {queue_id} rejoined by SID={request.sid[:4]}")

    emit("queue_rejoined", {"queue_id": queue_id})

    # Flush any messages buffered while offline (10.C.1)
    flush_offline_queue(queue_id, request.sid)


@socketio.on("register_peer")
def handle_register_peer(data):
    """Permits an active peer to authorize exchange routing to client's queue room."""
    my_queue = data.get("my_queue")
    peer_queue = data.get("peer_queue")
    if not my_queue or not peer_queue:
        return

    # Verify requesting client owns target queue before associating permissions
    if is_queue_owner(my_queue, request.sid):
        add_queue_owner(peer_queue, request.sid)
        app.logger.debug(
            f"Peer queue {peer_queue[:8]} registered for owner SID={request.sid[:4]}"
        )


@socketio.on("push_queue")
def handle_push_queue(data):
    """Pushes secure E2EE payload to designated target queue."""
    if is_rate_limited(request.sid, limit=10, window=1):
        app.logger.warning(
            f"Rate limit exceeded for push_queue on SID={request.sid[:4]}"
        )
        return

    queue_id = data.get("queue_id")
    payload = data.get("payload")

    if not queue_id or not payload:
        return

    if len(payload) > 100 * 1024:
        app.logger.warning(f"Payload too large from SID={request.sid[:4]}")
        return

    # Enforce queue authorization
    if not is_queue_owner(queue_id, request.sid):
        app.logger.warning(
            f"Unauthorised push_queue attempt for queue_id={queue_id[:8]} from SID={request.sid[:4]}"
        )
        return

    is_ephemeral = False
    try:
        parsed = json.loads(payload)
        is_ephemeral = bool(parsed.get("ephemeral", False))
    except Exception:
        pass

    if not is_recipient_online(queue_id):
        if is_ephemeral:
            # Drop ephemeral messages when offline
            return
        # Recipient offline — buffer for delivery on reconnect (10.C.1)
        enqueue_offline(queue_id, payload)
        emit(
            "push_queue_error",
            {"queue_id": queue_id, "error": "recipient_offline_queued"},
        )
        return
    emit("queue_payload", {"queue_id": queue_id, "payload": payload}, to=queue_id)


@socketio.on("disconnect")
def handle_disconnect():
    """Wipes active session timestamps, rate limit tables, and clean up queue mappings."""
    sid = request.sid
    with socket_connect_times_lock:
        socket_connect_times.pop(sid, None)
    with socket_rate_limits_lock:
        socket_rate_limits.pop(sid, None)

    if r_client:
        try:
            r_client.srem("online_sids", sid)
        except Exception as e:
            app.logger.warning(f"Failed to remove socket online from Redis: {e}")

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


# ---------------------------------------------------------------------------
# XFTP Chunked Encrypted File Transfer In-Memory/Redis Store (10.E.1)
# ---------------------------------------------------------------------------
relay_file_chunks = {}
relay_file_chunks_lock = threading.Lock()


def upload_chunk(chunk_id, data):
    if r_client:
        try:
            r_client.set(f"file_chunk:{chunk_id}", data, ex=86400)  # 24h TTL
            return True
        except Exception as e:
            app.logger.warning(f"Redis chunk upload failed: {e}")

    with relay_file_chunks_lock:
        relay_file_chunks[chunk_id] = {"data": data, "expires_at": time.time() + 86400}
    return True


def download_chunk(chunk_id):
    if r_client:
        try:
            # Retrieve binary content directly
            data = r_client.get(f"file_chunk:{chunk_id}")
            if data:
                r_client.delete(f"file_chunk:{chunk_id}")  # delete-on-download
                return data
        except Exception as e:
            app.logger.warning(f"Redis chunk download failed: {e}")

    with relay_file_chunks_lock:
        chunk = relay_file_chunks.pop(chunk_id, None)
        if chunk and chunk["expires_at"] >= time.time():
            return chunk["data"]
    return None


def start_relay_chunk_cleanup_loop():
    def run_cleanup():
        while True:
            time.sleep(600)
            now = time.time()
            with relay_file_chunks_lock:
                expired = [
                    k for k, v in relay_file_chunks.items() if v["expires_at"] < now
                ]
                for k in expired:
                    del relay_file_chunks[k]

    t = threading.Thread(target=run_cleanup, daemon=True)
    t.start()


start_relay_chunk_cleanup_loop()


# ---------------------------------------------------------------------------
# XFTP File Transfer Relay Routes
# ---------------------------------------------------------------------------


@app.route("/file/upload/<chunk_id>", methods=["POST"])
def relay_file_upload(chunk_id):
    """Uploads an encrypted file chunk to the relay."""
    data = request.get_data()
    if len(data) > 16500:
        return jsonify({"error": "Chunk size exceeds maximum limit"}), 400

    upload_chunk(chunk_id, data)
    return jsonify({"success": True})


@app.route("/file/download/<chunk_id>", methods=["GET"])
def relay_file_download(chunk_id):
    """Downloads and deletes a file chunk from the relay."""
    data = download_chunk(chunk_id)
    if data is None:
        return jsonify({"error": "Chunk not found or expired"}), 404

    return data, 200, {"Content-Type": "application/octet-stream"}


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

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Workspace"),
            x509.NameAttribute(NameOID.COMMON_NAME, "workspace.local"),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(
            datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
        )
        .not_valid_after(
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365)
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName("workspace.local"),
                    x509.IPAddress(socket.inet_aton("127.0.0.1")),
                    x509.IPAddress(socket.inet_aton(get_local_ip())),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # Write key_path securely (0600)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = 0o600
    with open(os.open(key_path, flags, mode), "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    # Write cert_path securely (0600)
    with open(os.open(cert_path, flags, mode), "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("SSL certificate generated successfully")


@app.errorhandler(Exception)
def handle_unexpected_exception(e):
    app.logger.exception("Unhandled exception encountered: %s", e)
    return jsonify({"error": "An unexpected error occurred"}), 500


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    disable_ssl = os.environ.get("DISABLE_SSL", "False").lower() == "true"

    # Broadcast service via local multicast DNS only if ANONYMUS_MDNS is explicitly set to true
    if os.environ.get("ANONYMUS_MDNS", "false").lower() == "true":
        advertise_mdns(port)

    if not debug_mode:
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.WARNING)
        app.logger.setLevel(logging.WARNING)

    # Secure server interface binding context
    bind_host = "127.0.0.1" if debug_mode else "0.0.0.0"

    if disable_ssl:
        print(f"Starting Messages Server on HTTP port {port}...")
        socketio.run(app, host=bind_host, port=port, debug=debug_mode)
    else:
        project_root = os.path.dirname(os.path.abspath(__file__))
        cert_path = os.path.join(project_root, "cert.pem")
        key_path = os.path.join(project_root, "key.pem")

        if not (os.path.exists(cert_path) and os.path.exists(key_path)):
            generate_self_signed_cert(cert_path, key_path)

        print(f"Starting Messages Server securely on HTTPS port {port}...")

        if socketio.server.eio.async_mode == "threading":
            socketio.run(
                app,
                host=bind_host,
                port=port,
                debug=debug_mode,
                ssl_context=(cert_path, key_path),
                allow_unsafe_werkzeug=debug_mode,
            )
        else:
            socketio.run(
                app,
                host=bind_host,
                port=port,
                debug=debug_mode,
                certfile=cert_path,
                keyfile=key_path,
            )
