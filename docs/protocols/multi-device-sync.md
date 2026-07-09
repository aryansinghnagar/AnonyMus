# AnonyMus Mobile-to-Desktop Syncing Specification

This document details the transport-level protocol, cryptographic handshake, and data validation rules for linking a new desktop client to a primary mobile instance.

---

## 1. Ephemeral Handshake Sequence

The pairing protocol is executed over the local network (Wi-Fi) to ensure high-speed backup data transfer without passing through internet relays.

```
+----------------+                   +--------------------+
|  Mobile App    |                   | Desktop Client     |
|  (Scan Camera) |                   | (Generates QR)     |
+-------+--------+                   +---------+----------+
        |                                      |
        |  1. Scan QR (IP, Port, K_desk)       |
        |------------------------------------->|
        |                                      |
        |  2. POST /sync/pairing (K_mob, Enc)  |
        |------------------------------------->|
        |                                      |
        |  3. 200 OK Response (Success)        |
        |<-------------------------------------|
```

### Protocol Steps:
1. **Desktop Initialization:**
   * Desktop client generates an ephemeral X25519 pairing keypair: `(sk_desk, pk_desk)`.
   * Desktop starts a temporary HTTP server on a local port (e.g. `8999`).
   * Desktop renders a QR code representing the payload:
     $$\text{QR} = \{ \text{"ip"}: \text{"192.168.1.50"}, \text{"port"}: 8999, \text{"k"}: \text{base64}(pk\_desk) \}$$
2. **Mobile Scan & Connection:**
   * Mobile app scans the QR code to extract the desktop's IP, port, and public key.
   * Mobile generates its own ephemeral X25519 keypair: `(sk_mob, pk_mob)`.
   * Mobile performs ECDH key agreement:
     $$\text{SharedSecret} = \text{ECDH}(sk\_mob, pk\_desk)$$
   * Mobile derives a symmetric encryption key utilizing HKDF-SHA256:
     $$\text{AES\_Key} = \text{HKDF}(\text{SharedSecret}, \text{salt}=\text{None}, \text{info}=\text{"AnonyMus-Device-Sync-Key"})$$
3. **Database Encapsulation:**
   * Mobile client creates a backup payload of its active SQLite database (`local_node.db`).
   * Mobile encrypts the database using AES-256-GCM with a secure random IV and `AES_Key`.
   * Mobile submits a HTTP POST request to `http://<desktop_ip>:<port>/api/sync/pairing` containing:
     ```json
     {
       "client_public_key": "base64(pk_mob)",
       "iv": "base64(iv)",
       "ciphertext": "base64(encrypted_db)"
     }
     ```
4. **Desktop Decryption & Import:**
   * Desktop server receives the payload, extracts `pk_mob`, performs the identical ECDH exchange, derives `AES_Key`, decrypts the database, and loads the active session state.

---

## 2. Security Considerations

### Man-in-the-Middle (MITM) Protection
Because the pairing public key `pk_desk` is shared physically via a **QR code**, the transmission channel is tamper-resistant. An attacker on the local network cannot substitute `pk_desk` with their own public key without changing the visual QR code scanned by the user.

### Passphrase Protection
To prevent a compromised backup from exposing hidden folders, **hidden profile passphrases and bcrypt hashes are never saved in cleartext inside the SQLite payload**. The desktop client requires the user to input the correct profile passphrase locally to unlock and decrypt hidden profile indexes.
