"""
pairing_broker.py — Ephemeral Pairing Broker for AnonyMus Multi-Device Sync

Generates temporary X25519 DH keys, starts a local HTTP listener, performs
a key agreement handshake, and decrypts the incoming database backup from 
the mobile client to link the devices.
"""

import os
import sys
import json
import base64
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class PairingHandler(BaseHTTPRequestHandler):
    pairing_key = None
    db_file_out = "linked_node.db"

    def do_POST(self):
        if self.path == "/api/sync/pairing":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data.decode('utf-8'))

            # Read client's public key and ciphertext payload
            client_pub_b64 = payload.get("client_public_key")
            ciphertext_b64 = payload.get("ciphertext")
            iv_b64 = payload.get("iv")

            try:
                # 1. Derive shared secret using ECDH
                peer_pub = x25519.X25519PublicKey.from_public_bytes(base64.b64decode(client_pub_b64))
                shared_key = self.pairing_key.exchange(peer_pub)

                # 2. Run HKDF to get AES key
                aes_key = HKDF(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=None,
                    info=b"AnonyMus-Device-Sync-Key",
                ).derive(shared_key)

                # 3. Decrypt database backup
                aesgcm = AESGCM(aes_key)
                decrypted = aesgcm.decrypt(
                    base64.b64decode(iv_b64),
                    base64.b64decode(ciphertext_b64),
                    None
                )

                # 4. Save SQLite file locally
                with open(self.db_file_out, "wb") as f:
                    f.write(decrypted)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"success": true, "message": "Device linked and database synchronized!"}')
                print(f"[Pairing Broker] Successfully linked and synced DB to {self.db_file_out}")
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f'{{"success": false, "error": "{str(e)}"}}'.encode())
        else:
            self.send_response(404)
            self.end_headers()

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

def start_broker():
    # 1. Generate X25519 pairing key
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_bytes = public_key.public_bytes_raw()
    pub_b64 = base64.b64encode(pub_bytes).decode('utf-8')

    # 2. Get local network identity
    ip = get_local_ip()
    port = 8999

    # 3. Render pairing instructions / QR code payload
    pairing_payload = {
        "ip": ip,
        "port": port,
        "k": pub_b64
    }
    
    print("\n" + "="*80)
    print(" ANONYMUS EPHEMERAL PAIRING BROKER")
    print("="*80)
    print("Scan this payload via your primary Mobile Client to initiate sync:")
    print(f"\n{json.dumps(pairing_payload)}\n")
    print("="*80 + "\n")

    # 4. Bind and listen
    PairingHandler.pairing_key = private_key
    server = HTTPServer((ip, port), PairingHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping pairing broker.")
        server.server_close()

if __name__ == "__main__":
    start_broker()
