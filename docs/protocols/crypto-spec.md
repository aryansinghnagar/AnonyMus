# System Features & Cryptographic Specification

This document details the functional features and cryptographic specifications implemented in the unified AnonyMus application. It covers both the **Centralized Relay** architecture and the **Decentralized P2P** (Tor onion) architecture.

---

## 1. Shared Cryptographic Security Model

Both modes of operation share the same core cryptographic DNA to ensure end-to-end encryption (E2EE) and metadata resistance.

### A. Key Exchange & Session Setup
- **Key Generation**: Clients generate ephemeral Elliptic Curve Diffie-Hellman (ECDH) keypairs using the **NIST P-256 (secp256r1)** curve.
- **Handshake Protocol**: Session initiation is conducted out-of-band (via QR code or secure onion exchange URL). The clients exchange public identity keys.
- **Shared Secret Derivation**: A master shared secret is generated via P-256 ECDH and immediately run through **HKDF-SHA256** to derive initial encryption, decryption, and authentication keys.

### B. Message Forward Secrecy (HKDF Ratchet)
To protect past messages in the event of a key compromise, a symmetric key ratchet is executed:
- **Chain Key Ratchet**: For every message sent or received, the active chain key is advanced through an **HKDF-SHA256** step to derive a new message key and the next chain key.
- **Ephemeral Message Keys**: Every message is encrypted with a unique, single-use symmetric key. Once used, the key is overwritten with zeros (zero-filled) in local RAM.

### C. Authenticated Encryption
- **Symmetric Cipher**: Payload encryption utilizes **AES-256-GCM** with a random 12-byte initialization vector (IV) generated via cryptographically secure random number generators (CSPRNG).
- **Associated Data Binding (AAD)**: Ciphertext integrity is bound to the conversation context by injecting the sorted cryptographic fingerprints of the participants (Safety Number) and the protocol version as Associated Data during the encryption and decryption steps.

---

## 2. Centralized Relay Mode Features

When operating in centralized relay mode, the system uses a server-client layout optimized for metadata resistance and speed.

- **Stateless Message Queues**: Messages are routed to ephemeral memory queues identified by UUIDs. The server retains messages in-memory only until they are successfully fetched by the recipient, minimizing the storage footprint.
- **Queue Access Authorization**: WebSocket clients must authenticate using session tokens. The server enforces queue-level authorization checks to ensure a user can only pull messages from their designated queue.
- **Write-Ahead Logging (WAL)**: The SQLite authentication database utilizes WAL mode and an active busy timeout (5000ms) to ensure thread-safety and prevent database locks under high load.
- **Local Area mDNS Discovery**: The server advertises its socket port over multicast DNS using the service type `_anonymus._tcp.local.`. Scanning Android clients parse mDNS pointers to locate active server relays without requiring manual IP entry.

---

## 3. Decentralized P2P Mode Features

When operating in peer-to-peer mode, the application runs as a local server node integrated with Tor, bypassing the need for a centralized relay server.

- **Embedded Tor Expert Bundle**: Auto-downloads, integrity-verifies, and orchestrates a local Tor daemon. Outbound traffic is routed through local SOCKS5 proxy (`127.0.0.1:9050`), ensuring peers never see another peer's actual IP address.
- **Tor Onion Hidden Services**: Exposes the local node Flask endpoint over Tor (`.onion` address), enabling connection traversal across firewalls and NATs.
- **Localhost-Bound Security Boundary**: Restricts Flask API access. Only endpoints starting with `/p2p/` are accessible via the external Tor network. The general chat interface and administrative control paths are strictly bound to `localhost`/`127.0.0.1` to prevent unauthorized remote control.
- **AES-256-GCM Local Database Encryption**: Peer keys, contact lists, and message history are stored in a local SQLite database (`local_node.db`) encrypted at rest using AES-256-GCM. The key is derived from the master password using PBKDF2-HMAC-SHA256 (10,000 iterations).
- **Contact Directory Model**: Stores peer nicknames, onion addresses, public keys, and negotiated shared secrets in the encrypted local database.
- **Camouflage Launcher GUI**: Tkinter GUI is disguised as "Windows Network Diagnostics & Adapter Utility" with dynamic port binding to evade static-port detection.
- **Secure-Wiping Uninstaller**: Built with Inno Setup, the uninstaller secure-wipes and erases local databases, logs, Tor configurations, and downloaded Tor binaries upon removal.

---

## 4. Unified WSGI Dispatcher & Mode Selector

The application integrates both architectures into a single process:
- **Unified Dispatcher**: Runs a WSGI middleware wrapping both the Relay Flask server and the P2P Flask server.
- **Runtime Mode Swapping**: Supports hot-swapping modes without restarting the web interface. Changing modes triggers a handoff procedure, copying session parameters, stopping the active transport, and starting the target transport.
- **Log Sanitation**: A unified logging filter automatically redacts Base64 key material, authorization headers, and UUIDs to prevent leaks in logs across both modes.

---

## 5. Client Protections & Hardening

### Web Client
- **Chunked Base64 Conversion**: Encodes and transfers large message payloads using chunked `toBase64` conversion to avoid browser call-stack overflows.
- **Disappearing Messages**: Message lifetime is negotiated client-to-client via encrypted control frames. Client-side timers delete the message from the DOM and overwrite memory upon expiration.

### Android Client
- **Google Tink Engine**: Cryptographic primitives are managed via Google's Tink library, isolating key material from standard application space.
- **Biometric Authentication**: Access to the app dashboard is locked behind biometric fingerprint scanning (with device PIN fallback) utilizing Android `BiometricPrompt`.
- **Anti-Screenshot Flag**: Enforces `WindowManager.LayoutParams.FLAG_SECURE` to block screenshots, screen sharing, and remote recording.
- **Cert Pinning (TOFU)**: Implements Trust-on-First-Use cert pinning. The client pins the server's TLS certificate fingerprint on first connection and flags any modifications.
