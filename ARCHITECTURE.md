# AnonyMus System Architecture & Technical Specification

## 1. High-Level System Architecture

AnonyMus operates as a decentralized, post-quantum hybrid communication network engineered to eliminate metadata leakage, single points of failure, and side-channel exposure.

```mermaid
graph TD
    Client[Web Client / Tauri Desktop / Mobile] -->|ASGI HTTP/WS| Node[FastAPI v3 Async Node]
    Node -->|Async SOCKS5 Proxy & Stem Control| TorManager[TorManager / Tor Control Port 9051]
    TorManager -->|Tor Network (v3 Onion)| PeerTor[Peer Tor Onion Service]
    PeerTor -->|Inbound SOCKS/HTTP| PeerNode[Peer FastAPI Async Node]

    Node -->|FFI PyO3 / CFFI| RustCore[Rust Cryptographic Core: anonymus_core]
    Node -->|SQLAlchemy Async / SQLCipher| SQLite[(Encrypted SQLite Database: anonymus.db)]
    Node -->|Background Worker| PrekeyPool[Prekey Pool Replenishment Worker]
```

---

## 2. Core Subsystems & Router Topology

The backend runs an asynchronous FastAPI v3 ASGI engine structured into isolated routers:

| Router Path | Module | Core Functionality |
|---|---|---|
| `/v3/auth` | `transports/p2p/routers/auth.py` | Local session authentication, profile unlocking, and duress PIN wipe triggers. |
| `/v3/messages` | `transports/p2p/routers/messages.py` | Double Ratchet message ingestion, sealed-sender routing, out-of-order queueing. |
| `/v3/keys` | `transports/p2p/routers/keys.py` | Prekey bundle publishing, consumption, and automatic replenishment. |
| `/v3/files` | `transports/p2p/routers/files.py` | Encrypted XFTP chunk upload/download with Ed25519 signature verification. |
| `/v3/sync` | `transports/p2p/routers/sync.py` | LAN multi-device synchronization broker with 256-bit token mutual auth. |
| `/v3/node` | `transports/p2p/routers/node.py` | Node status, onion address introspection, and hardware capability tier detection. |

---

## 3. Cryptographic Layer & Protocols

AnonyMus implements a fail-closed, post-quantum hybrid cryptographic suite:

### A. Post-Quantum Hybrid Key Encapsulation (PQXDH)
- **Classical Primitive**: Curve25519 (X25519, RFC 7748) Diffie-Hellman.
- **Quantum-Resistant Primitive**: NIST FIPS 203 **ML-KEM-768** (Kyber768) key encapsulation via `core/pq_kem.py`.
- **Hybrid Key Derivation**:
  $$\text{SharedSecret} = \text{HKDF-SHA256}(\text{X25519\_Secret} \parallel \text{ML-KEM-768\_Secret}, \text{salt}, \text{info})$$
- **Prekey Pool Replenishment**: The background worker (`core/prekey_pool.py`) continuously maintains a minimum threshold of signed prekeys and one-time post-quantum prekey bundles in the database.

### B. Double Ratchet & Authenticated Decryption
- **Ratchet Engine**: Symmetric key ratchet steps per message combined with DH ratchet steps per round-trip exchange.
- **Payload Cipher**: AES-256-GCM / ChaCha20-Poly1305 with random 12-byte IVs.
- **Strict AAD Binding (`ANO-SEC-017`)**: Authenticated Associated Data strictly binds the protocol version (`v2`), sequence number, and session ID. Legacy v1 fallback is eliminated to prevent downgrade attacks.
- **Uniform Padding**: All plaintext payloads are padded to 2 KB uniform block boundaries with randomized jitter (`core/rust/src/protocol/padding.rs`) to prevent traffic-analysis side channels.

### C. Provably Unbiased Safety Numbers (`ANO-CODE-009`)
- Safety numbers are formatted as 12 groups of 5-digit decimal numbers.
- **Rejection Sampling**: Key fingerprints are hashed with SHA-256 hash chains into 32-bit windows with strict rejection sampling ($\text{val} < 4,294,900,000$) to guarantee zero modulo bias across the $[0, 99999]$ codespace.

### D. Sealed-Sender Verification (`ANO-SEC-013`)
- Outer envelopes encrypt the sender identity (`sender_onion`).
- In strict mode (`ANONYMUS_SEALED_SENDER_STRICT=1`), incoming sealed payloads are verified against the recipient's verified contact directory prior to processing.

---

## 4. Tor Onion Transport & Daemon Management

- **TorManager & Stem Control**: `transports/p2p/tor_manager.py` connects to the local Tor Control Port (`127.0.0.1:9051`) via `stem.control.Controller`.
- **Ephemeral v3 Hidden Services**: Ephemeral onion services (`ED25519-V3`) are created dynamically in memory without persisting private keys to disk.
- **Non-Blocking Egress**: Outbound HTTP requests to peer onion services traverse the Tor SOCKS5 pool (`127.0.0.1:9050`) using asynchronous `httpx` clients.

---

## 5. Storage Security & Anti-Forensics

- **SQLCipher Engine**: In production, the database engine enforces `sqlite+sqlcipher://` with mandatory `DB_KEY` validation (`ANO-SEC-008`).
- **Memory-Hard Key Derivation**: Master passphrases derive encryption keys via **Argon2id** (`t=3, m=65536, p=4`) with a unique 16-byte random salt (`ANO-SEC-002`), falling back to 600,000-iteration PBKDF2-HMAC-SHA256 if `argon2-cffi` is unavailable.
- **Duress Panic Shredding (`obliviate`)**: Entering a duress PIN zeroizes database pages on disk with cryptographic random bytes (`os.urandom`) and unlinks key stores instantly.

---

## 6. Multi-Device LAN Synchronization Protocol (`ANO-SEC-001`)

- **Transport**: Local HTTP broker on port `8999`.
- **Authentication**: High-entropy 256-bit random base32 pairing token with fresh per-pairing 16-byte HKDF salts.
- **Brute-Force Protection**: Per-IP rate limiting (5 failed attempts per 60s, 30-minute cooldown after 10 failures).
- **Replay Protection**: Monotonic sliding-window FIFO deque tracking transaction nonces with bounded memory overhead.

---

## 7. Bounded Encrypted File Transfer (XFTP)

- **Chunking**: Media files are partitioned into 10 MB encrypted chunks.
- **Signature Verification (`ANO-SEC-004`)**: Chunk uploads require an Ed25519 signature over `(chunk_id || timestamp)` verified against the uploader's onion address public key.
- **Quota & Lifecycle**: Bounded 500 MB disk quota with automatic 15-minute TTL eviction.
