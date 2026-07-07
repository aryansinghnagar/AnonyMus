# RFC 0002: Cryptographic Design and Ratchet System

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

AnonyMus requires end-to-end encryption (E2EE) to guarantee message privacy and integrity even when messages transit through potentially compromised or hostile relays.

## 2. Goals & Non-Goals

### Goals
- Secure message content from intermediary eavesdroppers.
- Enforce message authenticity and integrity using authenticated encryption.
- Derive conversation keys dynamically using a key derivation function.

### Non-Goals
- Complete post-quantum security in the baseline version (relegated to hybrid post-quantum extensions).
- Full double-ratchet (DH ratchet + symmetric ratchet) in the initial release (relegated to Q2 upgrades).

## 3. Design Details

The system utilizes an **ECDH P-256 + HKDF-SHA256 + AES-256-GCM** chain ratchet:
1. **Initial Handshake:** Peers exchange P-256 public keys via the exchange mechanism. They execute ECDH to compute a shared secret.
2. **Key Derivation:** The shared secret is passed through HKDF-SHA256 to generate the initial root chain key.
3. **Symmetric Ratcheting:** For each message, HKDF-SHA256 ratchets the chain key, yielding a new message-specific key and next chain key.
4. **Encryption:** Message plaintext is encrypted with AES-256-GCM. The initialization vector (IV) is 12 bytes. Role, sequence number, and session ID are bound as Additional Authenticated Data (AAD) to prevent message redirection and replay.

```
       [ Shared Secret ]
               |
               v
         HKDF-SHA256 ----> [ Chain Key 0 ]
                                 |
                                 +---> HKDF-SHA256 ---> [ Message Key 0 ] (AES-GCM)
                                 |
                                 v
                           [ Chain Key 1 ]
                                 |
                                 +---> HKDF-SHA256 ---> [ Message Key 1 ] (AES-GCM)
                                 |
                                 v
                                ...
```

## 4. Security & Privacy Implications

- **Forward Secrecy:** Symmetric ratcheting ensures that if a message key is compromised, previous messages remain secure. However, root key compromise exposes all future messages unless a full DH ratchet is performed.
- **Fail-Closed Operations:** The decryption helper must propagate cryptographic exceptions rather than failing silently or returning plaintext, preventing padding oracle attacks and metadata leakages.

## 5. Backward Compatibility

Any changes to key derivation or ratchet algorithms must be versioned within the AAD envelope to allow legacy clients to parse historical messages.
