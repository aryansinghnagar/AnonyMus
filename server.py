import os
import sys

import eventlet
import eventlet.wsgi
from flask import Flask, jsonify, request

# Ensure path includes root directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.transport_registry import registry
from transports.p2p.adapter import P2PTransport
from transports.relay.adapter import RelayTransport

# Create dispatcher app
dispatcher_app = Flask(__name__)

_PLACEHOLDER_SECRETS = {
    "your-secure-random-key-here",
    "diagnostics_ephemeral_control_key_2026",
    "changeme",
    "",
}
if os.environ.get("FLASK_SECRET_KEY", "") in _PLACEHOLDER_SECRETS:
    raise RuntimeError(
        "Refusing to start: FLASK_SECRET_KEY is missing, empty, or a known placeholder. "
        "Please configure a secure unique key in your environment."
    )

from core.gunicorn_check import assert_single_worker

assert_single_worker()


def is_authorized_admin():
    # 1. Allow if from localhost
    remote_ip = request.remote_addr
    if remote_ip in ("127.0.0.1", "::1", "localhost"):
        return True
    # 2. Allow if matching admin secret
    admin_secret = os.environ.get("ANONYMUS_ADMIN_SECRET")
    if admin_secret and request.headers.get("X-Admin-Secret") == admin_secret:
        return True
    return False


@dispatcher_app.route("/api/mode", methods=["GET", "POST"])
def handle_mode():
    if not is_authorized_admin():
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    if request.method == "POST":
        data = request.get_json() or {}
        new_mode = data.get("mode")
        if new_mode not in ("relay", "p2p"):
            return jsonify({"success": False, "error": "Invalid mode"}), 400

        port = int(os.environ.get("PORT", 5000))
        config = {
            "PORT": port,
            "ANONYMUS_MDNS": os.environ.get("ANONYMUS_MDNS", "false"),
            "SOCKS_PORT": int(os.environ.get("SOCKS_PORT", 9050)),
        }

        success = registry.switch_mode(new_mode, config)
        if success:
            wsgi_dispatcher.current_mode = new_mode
            return jsonify({"success": True, "mode": new_mode})
        else:
            return jsonify({"success": False, "error": "Mode switch failed"}), 500

    return jsonify(
        {
            "success": True,
            "mode": registry.get_active_mode(),
            "active_transport": registry.get_active_transport().describe(),
        }
    )


@dispatcher_app.route("/api/health", methods=["GET"])
def handle_health():
    active_t = registry.get_active_transport()
    return jsonify(
        {
            "success": True,
            "mode": registry.get_active_mode(),
            "health": active_t.health(),
        }
    )


# Register both transports
relay_transport = RelayTransport()
p2p_transport = P2PTransport()
registry.register("relay", relay_transport)
registry.register("p2p", p2p_transport)

# Import the Flask apps from both transports
from transports.p2p.server import socketio as p2p_sio
from transports.relay.server import socketio as relay_sio


class UnifiedWSGIDispatcher:
    def __init__(self, dispatcher_app, relay_wsgi, p2p_wsgi):
        self.dispatcher_app = dispatcher_app
        self.relay_wsgi = relay_wsgi
        self.p2p_wsgi = p2p_wsgi
        self.current_mode = registry.get_active_mode()

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path.startswith("/api/mode") or path.startswith("/api/health"):
            return self.dispatcher_app(environ, start_response)

        # Route to active transport WSGI
        if self.current_mode == "relay":
            return self.relay_wsgi(environ, start_response)
        else:
            return self.p2p_wsgi(environ, start_response)


wsgi_dispatcher = UnifiedWSGIDispatcher(
    dispatcher_app, relay_sio.sockio_mw, p2p_sio.sockio_mw
)

# Re-expose app and socketio for external wsgi wrappers like gunicorn in docker
app = wsgi_dispatcher
socketio = relay_sio  # fallback object for WSGI servers requiring socketio hook

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    from core.logging import setup_logging

    setup_logging(dispatcher_app)

    mode = registry.get_active_mode()
    port = int(os.environ.get("PORT", 5000))
    config = {
        "PORT": port,
        "ANONYMUS_MDNS": os.environ.get("ANONYMUS_MDNS", "false"),
        "SOCKS_PORT": int(os.environ.get("SOCKS_PORT", 9050)),
    }

    print(f"Booting AnonyMus in active mode: {mode}")
    registry.get_active_transport().start(config)

    bind_ip = "127.0.0.1" if mode == "p2p" else "0.0.0.0"
    listener = eventlet.listen((bind_ip, port))
    print(f"WSGI dispatcher listening on {bind_ip}:{port}")
    eventlet.wsgi.server(listener, wsgi_dispatcher)
