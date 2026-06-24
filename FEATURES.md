# System Features & Cryptographic Specification

This document details the functional features and cryptographic specifications implemented in the centralized client-server version of the AnonyMus application.

---

## 1. Cryptographic Security Model

AnonyMus implements a zero-knowledge E2EE model. The server acts as an untrusted message relay, incapable of reading chat payload data, session negotiation packets, or client key material.

### A. Key Exchange & Session Setup
- **Key Generation**: Clients generate ephemeral Elliptic Curve Diffie-Hellman (ECDH) keypairs using the **NIST P-256 (secp256r1)** curve.
- **Handshake Protocol**: Session initiation is conducted out-of-band (via QR code or secure URL). The clients exchange public identity keys.
- **Shared Secret Derivation**: A master shared secret is generated via P-256 ECDH and immediately run through **HKDF-SHA256** to derive initial encryption, decryption, and authentication keys.

### B. Message Forward Secrecy (HKDF Ratchet)
To protect past messages in the event of a key compromise, a symmetric key ratchet is executed:
- **Chain Key Ratchet**: For every message sent or received, the active chain key is advanced through an **HKDF-SHA256** step to derive a new message key and the next chain key.
- **Ephemeral Message Keys**: Every message is encrypted with a unique, single-use symmetric key. Once used, the key is overwritten with zeros (zero-filled) in local RAM.

### C. Authenticated Encryption
- **Symmetric Cipher**: Payload encryption utilizes **AES-256-GCM** with a random 12-byte initialization vector (IV) generated via cryptographically secure random number generators (CSPRNG).
- **Associated Data Binding (AAD)**: Ciphertext integrity is bound to the conversation context by injecting the sorted cryptographic fingerprints of the participants (Safety Number) and the protocol version as Associated Data during the encryption and decryption steps.

---

## 2. Server Architecture & Security Hardening

The backend Flask server is engineered to be metadata-resistant and robust under concurrent traffic.

- **Stateless Message Queues**: Messages are routed to ephemeral memory queues identified by UUIDs. The server retains messages only until they are successfully fetched by the recipient, minimizing the storage footprint.
- **Queue Access Authorization**: WebSocket clients must authenticate using session tokens. The server enforces queue-level authorization checks to ensure a user can only pull messages from their designated queue.
- **Write-Ahead Logging (WAL)**: The SQLite authentication database utilizes WAL mode and an active busy timeout (5000ms) to ensure thread-safety and prevent database locks under high load.
- **Log Sanitation**: A custom logging filter automatically strips Base64 key material, authorization headers, and UUIDs to prevent sensitive data leakage in server output files.

---

## 3. Disappearing Messages

A decentralized, synchronized timer system facilitates automatic message destruction:
- **Timer Syncing**: Users can negotiate message lifetimes (15s, 60s, 5m, 30m) directly through secure control frames embedded in the encrypted payload.
- **Local Erasure**: When the countdown timer expires, client scripts delete the message from the local DOM tree and overwrite its decrypted content in client memory.

---

## 4. Local Area mDNS Discovery

To facilitate zero-configuration discovery in trusted networks:
- **mDNS Advertisement**: The server advertises its socket port over multicast DNS using the service type `_anonymus._tcp.local.`.
- **Automatic Client Resolution**: Android clients scanning the local network parse mDNS pointers to locate active server relays without requiring manual IP entry.

---

## 5. Android Client Hardening

The native Android app implements system-level protections to secure local data:
- **Google Tink Engine**: Cryptographic primitives are managed via Google's Tink library, isolating key material from standard application space.
- **Biometric Authentication**: Access to the app dashboard is locked behind biometric fingerprint scanning (with device PIN fallback) utilizing Android `BiometricPrompt`.
- **Anti-Screenshot Flag**: Enforces `WindowManager.LayoutParams.FLAG_SECURE` to block screenshots, screen sharing, and remote recording.
- **Cert Pinning (TOFU)**: Implements Trust-on-First-Use cert pinning. The client pins the server's TLS certificate fingerprint on first connection and flags any modifications.
