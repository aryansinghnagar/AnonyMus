"""
Python Client SDK for AnonyMus (P2P Architecture).
Allows third-party scripting, headless bots, and headless client operations.
Provides clean API for authentication, contacts, history, and real-time messaging.
"""

import base64
import json
import re
import threading

import requests
import socketio
from cryptography.hazmat.primitives.asymmetric import ec

from core import protocol


class AnonyMusClient:
    def __init__(self, base_url="http://127.0.0.1:5001"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.sio = socketio.Client()
        self.is_logged_in = False
        self.username = None
        self.my_onion = None

        # Handshake cryptographic keys (ephemeral/session lifetime)
        self.private_key, self.public_key = protocol.generate_key_pair()
        self.public_key_b64 = protocol.export_public_key(self.public_key)

        # Track session states per active contact
        self.chain_keys = {}  # onion -> {"send_chain_key": bytes, "recv_chain_key": bytes}
        self.session_ids = {}  # onion -> safety_number (str)
        self.message_callbacks = []

        self._setup_socket_handlers()

    def _setup_socket_handlers(self):
        @self.sio.on("incoming_message")
        def on_incoming_message(data):
            sender = data.get("sender")
            iv = data.get("iv")
            ciphertext = data.get("ciphertext")
            seq = int(data.get("seq"))
            timestamp = int(data.get("timestamp"))

            # Decrypt message locally if we have the session keys
            text = self.decrypt_incoming(sender, iv, ciphertext, seq)
            if text is not None:
                for cb in self.message_callbacks:
                    try:
                        cb(sender, text, timestamp)
                    except Exception as e:
                        print(f"[SDK] Callback error: {e}")

        @self.sio.on("handshake_accepted")
        def on_handshake_accepted(data):
            onion_address = data.get("onion_address")
            peer_public_key_b64 = data.get("peer_public_key")
            my_pub_key_b64 = data.get("my_public_key")

            # Derive shared secret and save it
            peer_pubkey = protocol.import_public_key(peer_public_key_b64)
            shared_secret = (
                self.private_key.exchange(ec.ECDH(), peer_pubkey)
                if hasattr(self.private_key, "exchange")
                else None
            )
            if not shared_secret:
                # Fallback to cryptography direct exchange
                shared_secret = self.private_key.exchange(ec.ECDH(), peer_pubkey)

            shared_secret_b64 = base64.b64encode(shared_secret).decode("utf-8")

            # Save derived shared secret back to server database
            self.save_shared_secret(
                onion_address, shared_secret_b64, peer_public_key_b64
            )
            # Sync keys
            self.sync_contacts()

    def register(self, username, password) -> dict:
        """Registers a new local master profile password."""
        try:
            r = self.session.get(f"{self.base_url}/")
            csrf_token = self._extract_csrf(r.text)
            headers = {"X-CSRFToken": csrf_token} if csrf_token else {}

            res = self.session.post(
                f"{self.base_url}/register",
                json={"username": username, "password": password},
                headers=headers,
            )
            return res.json()
        except Exception as e:
            return {"error": str(e)}

    def login(self, username, password) -> bool:
        """Authenticates with the local panel and syncs state."""
        try:
            r = self.session.get(f"{self.base_url}/")
            csrf_token = self._extract_csrf(r.text)
            headers = {"X-CSRFToken": csrf_token} if csrf_token else {}

            res = self.session.post(
                f"{self.base_url}/login",
                json={"username": username, "password": password},
                headers=headers,
            )
            if res.status_code == 200 and res.json().get("success"):
                self.is_logged_in = True
                self.username = username
                self._fetch_my_info()
                self.sync_contacts()
                return True
        except Exception as e:
            print(f"[SDK] Login connection failed: {e}")
        return False

    def _extract_csrf(self, html: str) -> str:
        match = re.search(r'meta name="csrf-token" content="([^"]+)"', html)
        return match.group(1) if match else None

    def _fetch_my_info(self):
        try:
            res = self.session.get(f"{self.base_url}/api/my_info")
            if res.status_code == 200:
                data = res.json()
                self.my_onion = data.get("onion_address")
                self.username = data.get("local_username")
        except Exception as e:
            print(f"[SDK] Error fetching info: {e}")

    def sync_contacts(self):
        """Syncs in-memory cryptographic chain keys for all accepted contacts."""
        if not self.is_logged_in:
            return
        try:
            res = self.session.get(f"{self.base_url}/api/contacts")
            if res.status_code == 200:
                contacts = res.json()
                for c in contacts:
                    if c.get("status") == "accepted" and c.get("shared_secret"):
                        self.init_contact_session(c)
        except Exception as e:
            print(f"[SDK] Error syncing contacts: {e}")

    def init_contact_session(self, contact):
        """Derives sending and receiving ratchets from shared secret for a contact."""
        onion = contact.get("onion_address")
        shared_secret_b64 = contact.get("shared_secret")
        peer_pub_b64 = contact.get("peer_public_key")
        my_pub_b64 = contact.get("my_public_key") or self.public_key_b64

        shared_secret_bytes = base64.b64decode(shared_secret_b64)

        salt = b"\x00" * 32
        label_client = b"AnonyMus-Client-To-Server-Key"
        label_server = b"AnonyMus-Server-To-Client-Key"

        client_chain = protocol.hkdf_derive(shared_secret_bytes, label_client, salt)
        server_chain = protocol.hkdf_derive(shared_secret_bytes, label_server, salt)

        is_alice = my_pub_b64 < peer_pub_b64

        self.chain_keys[onion] = {
            "send_chain_key": client_chain if is_alice else server_chain,
            "recv_chain_key": server_chain if is_alice else client_chain,
        }
        self.session_ids[onion] = protocol.compute_safety_number(
            my_pub_b64, peer_pub_b64
        )

    def add_contact(self, onion_address, nickname) -> bool:
        """Initiates handshake invite to a P2P onion address."""
        if not self.is_logged_in:
            return False
        try:
            r = self.session.get(f"{self.base_url}/")
            csrf_token = self._extract_csrf(r.text)
            headers = {"X-CSRFToken": csrf_token} if csrf_token else {}

            res = self.session.post(
                f"{self.base_url}/api/contacts/add",
                json={
                    "onion_address": onion_address,
                    "nickname": nickname,
                    "my_public_key": self.public_key_b64,
                },
                headers=headers,
            )
            return res.status_code == 200 and res.json().get("success")
        except Exception as e:
            print(f"[SDK] Error adding contact: {e}")
            return False

    def accept_contact(self, onion_address) -> bool:
        """Accepts a pending incoming contact handshake request."""
        if not self.is_logged_in:
            return False
        try:
            # Find contact peer_public_key
            res_c = self.session.get(f"{self.base_url}/api/contacts")
            contacts = res_c.json()
            contact = next(
                (c for c in contacts if c.get("onion_address") == onion_address), None
            )
            if not contact or not contact.get("peer_public_key"):
                return False

            peer_pub_key_b64 = contact["peer_public_key"]
            peer_pubkey = protocol.import_public_key(peer_pub_key_b64)

            from cryptography.hazmat.primitives.asymmetric import ec as crypto_ec

            shared_secret = self.private_key.exchange(crypto_ec.ECDH(), peer_pubkey)
            shared_secret_b64 = base64.b64encode(shared_secret).decode("utf-8")

            r = self.session.get(f"{self.base_url}/")
            csrf_token = self._extract_csrf(r.text)
            headers = {"X-CSRFToken": csrf_token} if csrf_token else {}

            res = self.session.post(
                f"{self.base_url}/api/contacts/accept",
                json={
                    "onion_address": onion_address,
                    "my_public_key": self.public_key_b64,
                    "shared_secret": shared_secret_b64,
                },
                headers=headers,
            )
            if res.status_code == 200 and res.json().get("success"):
                self.sync_contacts()
                return True
        except Exception as e:
            print(f"[SDK] Error accepting contact: {e}")
        return False

    def save_shared_secret(
        self, onion_address, shared_secret_b64, peer_pub_key_b64
    ) -> bool:
        try:
            r = self.session.get(f"{self.base_url}/")
            csrf_token = self._extract_csrf(r.text)
            headers = {"X-CSRFToken": csrf_token} if csrf_token else {}

            res = self.session.post(
                f"{self.base_url}/api/contacts/save_secret",
                json={
                    "onion_address": onion_address,
                    "shared_secret": shared_secret_b64,
                    "peer_public_key": peer_pub_key_b64,
                },
                headers=headers,
            )
            return res.status_code == 200 and res.json().get("success")
        except Exception as e:
            print(f"[SDK] Error saving shared secret: {e}")
            return False

    def send_message(self, onion_address, text) -> bool:
        """Derives next send message key, encrypts message, and posts to server."""
        if not self.is_logged_in:
            return False
        if onion_address not in self.chain_keys:
            print(f"[SDK] No active ratcheting session found for {onion_address}")
            return False

        try:
            # 1. Fetch current sequence number from message history length
            hist = self.get_messages(onion_address)
            # Find sender messages count to determine next sequence number
            seq = len(hist)

            # 2. Ratchet send key
            keys = self.chain_keys[onion_address]
            ratchet_step = protocol.derive_chain_keys(keys["send_chain_key"])
            self.chain_keys[onion_address]["send_chain_key"] = ratchet_step[
                "next_chain_key"
            ]
            message_key = ratchet_step["message_key"]

            # 3. Encrypt payload
            session_id = self.session_ids[onion_address]
            payload = protocol.encrypt_message(message_key, text, "me", seq, session_id)

            r = self.session.get(f"{self.base_url}/")
            csrf_token = self._extract_csrf(r.text)
            headers = {"X-CSRFToken": csrf_token} if csrf_token else {}

            res = self.session.post(
                f"{self.base_url}/api/messages/send",
                json={
                    "onion_address": onion_address,
                    "iv": payload["iv"],
                    "ciphertext": payload["ciphertext"],
                    "seq": seq,
                },
                headers=headers,
            )
            return res.status_code == 200 and res.json().get("success")
        except Exception as e:
            print(f"[SDK] Error sending message: {e}")
            return False

    def get_messages(self, onion_address, limit=100, offset=0) -> list:
        """Retrieves and decrypts message logs for a contact."""
        if not self.is_logged_in:
            return []
        try:
            res = self.session.get(
                f"{self.base_url}/api/messages",
                params={"onion": onion_address, "limit": limit, "offset": offset},
            )
            if res.status_code == 200:
                raw_messages = res.json()
                decrypted_messages = []

                for m in raw_messages:
                    sender = m.get("sender")
                    payload_str = m.get("message")
                    timestamp = m.get("timestamp")

                    try:
                        payload = json.loads(payload_str)
                        iv = payload.get("iv")
                        ciphertext = payload.get("ciphertext")
                        seq = int(payload.get("seq", 0))

                        # Decrypt
                        if sender == "me":
                            # Use sending key path logic or decrypt with send ratchet
                            # Since we can just derive keys sequentially based on sequence number:
                            text = self.decrypt_historical(
                                onion_address, iv, ciphertext, seq, "me"
                            )
                        else:
                            text = self.decrypt_historical(
                                onion_address, iv, ciphertext, seq, "peer"
                            )

                        decrypted_messages.append(
                            {
                                "sender": sender,
                                "text": text,
                                "timestamp": timestamp,
                                "seq": seq,
                            }
                        )
                    except Exception:
                        decrypted_messages.append(
                            {
                                "sender": sender,
                                "text": "[Decryption Failure]",
                                "timestamp": timestamp,
                                "seq": 0,
                            }
                        )
                return decrypted_messages
        except Exception as e:
            print(f"[SDK] Error fetching messages: {e}")
        return []

    def decrypt_incoming(self, sender_onion, iv, ciphertext, seq) -> str:
        """Decrypts a real-time incoming message and ratchets the recv chain key."""
        if sender_onion not in self.chain_keys:
            return None
        try:
            keys = self.chain_keys[sender_onion]
            # Step the recv ratchet sequentially to message key
            ratchet_step = protocol.derive_chain_keys(keys["recv_chain_key"])
            self.chain_keys[sender_onion]["recv_chain_key"] = ratchet_step[
                "next_chain_key"
            ]

            session_id = self.session_ids[sender_onion]
            return protocol.decrypt_message(
                ratchet_step["message_key"], iv, ciphertext, "peer", seq, session_id
            )
        except Exception as e:
            print(f"[SDK] Incoming decryption error: {e}")
            return None

    def decrypt_historical(self, onion_address, iv, ciphertext, seq, role) -> str:
        """Derives a message key dynamically for a given sequence index without shifting the active ratchet."""
        if onion_address not in self.chain_keys:
            return "[No Session Keys]"
        try:
            # Clone root key to step to seq index without modifying self.chain_keys
            active_keys = self.chain_keys[onion_address]
            root_key = (
                active_keys["send_chain_key"]
                if role == "me"
                else active_keys["recv_chain_key"]
            )

            # Since the ratchet is symmetric, we can walk from base root to seq index
            # Wait, in AnonyMus, does the root chain key ratchet forward on every message?
            # Yes! Each step of derive_chain_keys returns next_chain_key, which is used for the next message.
            # So the message key at index `seq` is derived after `seq + 1` ratcheting steps from the initial root!
            # Let's verify: yes, because Alice/Bob start with a baseline root chain key.
            # Message 0: derived from root_key info="AnonyMus-ChainKey", then next_chain_key.
            # So we step seq+1 times!
            temp_key = root_key
            for _ in range(seq + 1):
                step = protocol.derive_chain_keys(temp_key)
                message_key = step["message_key"]
                temp_key = step["next_chain_key"]

            session_id = self.session_ids[onion_address]
            # When we decrypt our own sent messages, we are role "me". When decrypting peer messages, role is "peer".
            # Wait, who is the sender in construct_aad?
            # In encryptMessage (chat.js): role is "me" if encrypting, and "peer" if decrypting incoming.
            # In decryptMessage: role is "peer" if decrypting incoming, and "me" if decrypting our own.
            # This matches exactly!
            return protocol.decrypt_message(
                message_key, iv, ciphertext, role, seq, session_id
            )
        except Exception as e:
            return f"[Decryption Error: {e}]"

    def on_message(self, callback):
        """Registers a callback function: callback(sender, text, timestamp)."""
        self.message_callbacks.append(callback)

    def start_listening(self):
        """Establishes Socket.IO connection to listen for incoming messages in a background thread."""
        if not self.is_logged_in:
            print("[SDK] Must log in before listening for sockets.")
            return

        def run():
            try:
                # Pass session cookies to Socket.IO connection
                cookies_str = "; ".join(
                    [f"{k}={v}" for k, v in self.session.cookies.items()]
                )
                self.sio.connect(
                    self.base_url,
                    headers={"Cookie": cookies_str},
                    transports=["websocket"],
                )
                self.sio.wait()
            except Exception as e:
                print(f"[SDK] Socket connection error: {e}")

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def disconnect(self):
        """Cleanly disconnects WebSocket client."""
        if self.sio.connected:
            self.sio.disconnect()
