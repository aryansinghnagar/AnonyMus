import os
import sys
import eventlet
import eventlet.wsgi
from flask import Flask, jsonify, request

# Ensure path includes root directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.transport_registry import registry
from transports.relay.adapter import RelayTransport
from transports.p2p.adapter import P2PTransport

# Create dispatcher app
dispatcher_app = Flask(__name__)

@dispatcher_app.route('/api/mode', methods=['GET', 'POST'])
def handle_mode():
    if request.method == 'POST':
        data = request.get_json() or {}
        new_mode = data.get('mode')
        if new_mode not in ('relay', 'p2p'):
            return jsonify({"success": False, "error": "Invalid mode"}), 400
        
        port = int(os.environ.get("PORT", 5000))
        config = {
            "PORT": port,
            "ANONYMUS_MDNS": os.environ.get("ANONYMUS_MDNS", "false")
        }
        
        success = registry.switch_mode(new_mode, config)
        if success:
            wsgi_dispatcher.current_mode = new_mode
            return jsonify({"success": True, "mode": new_mode})
        else:
            return jsonify({"success": False, "error": "Mode switch failed"}), 500
            
    return jsonify({
        "success": True,
        "mode": registry.get_active_mode(),
        "active_transport": registry.get_active_transport().describe()
    })

@dispatcher_app.route('/api/health', methods=['GET'])
def handle_health():
    active_t = registry.get_active_transport()
    return jsonify({
        "success": True,
        "mode": registry.get_active_mode(),
        "health": active_t.health()
    })

# Register both transports
relay_transport = RelayTransport()
p2p_transport = P2PTransport()
registry.register("relay", relay_transport)
registry.register("p2p", p2p_transport)

# Import the Flask apps from both transports
from transports.relay.server import app as relay_app, socketio as relay_sio
from transports.p2p.server import app as p2p_app, socketio as p2p_sio

class UnifiedWSGIDispatcher:
    def __init__(self, dispatcher_app, relay_wsgi, p2p_wsgi):
        self.dispatcher_app = dispatcher_app
        self.relay_wsgi = relay_wsgi
        self.p2p_wsgi = p2p_wsgi
        self.current_mode = registry.get_active_mode()

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path.startswith('/api/mode') or path.startswith('/api/health'):
            return self.dispatcher_app(environ, start_response)
        
        # Route to active transport WSGI
        if self.current_mode == "relay":
            return self.relay_wsgi(environ, start_response)
        else:
            return self.p2p_wsgi(environ, start_response)

wsgi_dispatcher = UnifiedWSGIDispatcher(dispatcher_app, relay_sio.wsgi_app, p2p_sio.wsgi_app)

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
        "ANONYMUS_MDNS": os.environ.get("ANONYMUS_MDNS", "false")
    }
    
    print(f"Booting AnonyMus in active mode: {mode}")
    registry.get_active_transport().start(config)
    
    bind_ip = "127.0.0.1" if mode == "p2p" else "0.0.0.0"
    listener = eventlet.listen((bind_ip, port))
    print(f"WSGI dispatcher listening on {bind_ip}:{port}")
    eventlet.wsgi.server(listener, wsgi_dispatcher)
