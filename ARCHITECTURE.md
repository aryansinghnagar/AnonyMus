# AnonyMus System Architecture & Technical Specification

## 1. High-Level System Architecture

AnonyMus operates as a decentralized, post-quantum hybrid communication network designed to eliminate metadata leakage and single points of failure.

```mermaid
graph TD
    Client[Web Client / Tauri Desktop] -->|ASGI HTTP/WS| Node[FastAPI v3 Async Node]
    Node -->|Async SOCKS5 Proxy| TorDaemon[Local Tor Daemon / Onion Service]
    TorDaemon -->|Tor Network (v3 Onion)| PeerTor[Peer Tor Onion Service]
    PeerTor -->|Inbound SOCKS/HTTP| PeerNode[Peer FastAPI Async Node]

    Node -->|FFI PyO3 / CFFI| RustCore[Rust Cryptographic Core: anonymus_core]
    Node -->|SQLAlchemy Async| SQLite[(Encrypted SQLite Database)]
```

---

## 2. Cryptographic Layer

AnonyMus combines classical and quantum-resistant primitives:

### Key Exchange & Post-Quantum Hybrid KEM
- **Classical**: Curve25519 (X25519) Diffie-Hellman.
- **Post-Quantum**: NIST FIPS 203 **ML-KEM-768** (Kyber768) key encapsulation via `core/pq_kem.py`.
- **Hybrid Combination**: `Shared_Secret = HKDF-SHA256(X25519_Secret || ML-KEM-768_Secret)`.

### Message Transport Encryption
- **Double Ratchet**: Symmetric ratchet step per message, Diffie-Hellman ratchet step per round-trip exchange.
- **Payload Cipher**: AES-256-GCM or ChaCha20-Poly1305 with unique 12-byte IVs.
- **Forward Secrecy & Break-in Recovery**: Old message keys are erased immediately after decryption; compromised keys self-heal after one round-trip.

### Key Derivation & Database Security
- **Argon2id**: Memory-hard key derivation from user passphrase (`t=3, m=65536, p=4`).
- **Storage**: AES-256-GCM encrypted SQLite database (`anonymus.db`).

---

## 3. Asynchronous Transport & Concurrency Model

- **FastAPI v3 (ASGI)**: Fully asynchronous event loop powered by `asyncio` and `uvicorn`.
- **Non-Blocking Tor Transmission**: Outbound P2P payloads and handshakes are dispatched asynchronously via `httpx.AsyncClient` through the local Tor SOCKS5 pool (`127.0.0.1:9050`).
- **Thread Pool Delegation**: Heavy cryptographic hashing operations (`bcrypt`, `Argon2id`) run inside `asyncio.to_thread` workers to ensure the ASGI event loop remains completely unblocked.

---

## 4. Multi-Device Synchronization Protocol

- **Transport**: Local Area Network (LAN) HTTP pairing broker (`0.0.0.0:8999`).
- **Mutual Authentication**: Short Authentication String (SAS) 6-digit numeric PIN verified on both sender and receiver devices.
- **Deduplication**: Monotonic sliding-window FIFO deque tracking sequence IDs (`core/sync.py`) to prevent replay attacks without unbounded memory consumption.

---

## 5. Bounded Encrypted File Transfer (XFTP)

- **Chunking**: Media is split into 10 MB encrypted chunks.
- **Storage Management**: Temporary disk cache (`/data/xftp_chunks/` or OS temp directory) constrained by a 500 MB total quota and a 15-minute TTL background cleaner.
- **Protection**: Strict regex validation on `chunk_id` (`^[a-zA-Z0-9_-]+$`) to prevent path traversal attacks.
