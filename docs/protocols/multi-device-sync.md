# AnonyMus Multi-Device LAN Synchronization Protocol (v3.0)

This document specifies the transport-level protocol, cryptographic handshake, rate limiting, and replay prevention rules for synchronizing state between client devices over a Local Area Network (LAN).

---

## 1. Cryptographic Handshake & Pairing Sequence (`ANO-SEC-001`)

The pairing protocol is executed over the local Wi-Fi network (default port `8999`) to ensure high-speed, direct synchronization without traversing external relays.

```
+-------------------+                    +--------------------+
| Secondary Client  |                    |  Primary Device    |
| (Initiator)       |                    |  (Pairing Host)    |
+---------+---------+                    +---------+----------+
          |                                        |
          |  1. Enter IP, Port & Pairing Token     |
          |  (Out-of-band Token: 256-bit Base32)   |
          |--------------------------------------->|
          |                                        |
          |  2. POST /v3/sync/pairing              |
          |     (pk_sec, iv, ciphertext, salt)     |
          |--------------------------------------->|
          |                                        |
          |  3. Validate Token & Decrypt DB        |
          |                                        |
          |  4. 200 OK (Sync Successful)           |
          |<---------------------------------------|
```

### Protocol Steps:
1. **Primary Device Host Initialization:**
   * Primary device generates an ephemeral X25519 pairing keypair: `(sk_pri, pk_pri)`.
   * Generates a cryptographically strong 256-bit random pairing token (`base32`-encoded, 52 characters).
   * Generates a fresh, per-pairing 16-byte random HKDF salt.
   * Binds a local HTTP pairing broker on port `8999`.
2. **Secondary Device Connection:**
   * User enters or scans the host IP, port, and the 256-bit pairing token.
   * Secondary generates an ephemeral X25519 keypair: `(sk_sec, pk_sec)`.
   * Computes ECDH shared secret:
     $$\text{SharedSecret} = \text{X25519}(sk\_sec, pk\_pri)$$
   * Derives symmetric encryption key using HKDF-SHA256 with the pairing token and the fresh random 16-byte salt:
     $$\text{Sync\_Key} = \text{HKDF-SHA256}(\text{SharedSecret} \parallel \text{PairingToken}, \text{salt}=\text{salt}_{16\text{B}}, \text{info}=\text{"AnonyMus-LAN-Sync-v3"})$$
3. **Encrypted Payload Submission:**
   * Secondary submits an HTTP POST request to `/v3/sync/pairing`:
     ```json
     {
       "client_public_key": "<base64_encoded_pk_sec>",
       "salt": "<base64_encoded_16B_salt>",
       "iv": "<base64_encoded_12B_iv>",
       "ciphertext": "<base64_encoded_encrypted_payload>",
       "timestamp": 1755678900
     }
     ```
4. **Primary Validation & Decryption:**
   * Primary checks that the request timestamp skew is $\le 300\text{s}$.
   * Validates pairing token and derives $\text{Sync\_Key}$.
   * Authenticates and decrypts ciphertext using AES-256-GCM.
   * Atomically merges contact rosters and message stores.

---

## 2. Security Controls & Defenses

### A. Brute-Force Rate Limiting (`ANO-SEC-001`)
- The sync broker enforces strict per-IP rate limiting: maximum 5 failed attempts per 60-second window.
- Exceeding 10 cumulative failures triggers an automatic 30-minute IP cooldown.
- Failure responses return generic error status codes without detailed exception traces (`ANO-SEC-009`).

### B. Replay Attack Prevention
- Incoming synchronization envelopes are checked against a monotonic sliding-window FIFO deque (`core/sync.py`) tracking recently processed transaction identifiers.
- Replayed sequence nonces or expired envelopes are rejected immediately.

### C. Passphrase & Secret Segregation
- Database encryption keys (`DB_KEY`), duress PINs, and raw credentials are never transmitted during synchronization. The recipient device derives its own independent storage keys upon import.
