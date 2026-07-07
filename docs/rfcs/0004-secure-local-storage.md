# RFC 0004: Client-Side SQLite Database Encryption at Rest

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

Decentralized chats store message history and contact metadata on the local device. If a device is lost or compromised by local malware, this history must remain secure from unauthorized inspection.

## 2. Goals & Non-Goals

### Goals
- Secure the SQLite database at rest using symmetric encryption (AES-256-GCM).
- Derivate the database decryption key securely from user-supplied passwords.
- Limit database exposure in runtime memory.

### Non-Goals
- In-memory SQLite DB file encryption utilizing full SQLCipher file-level block encryption in this baseline version (implemented as a custom Python crypto-wrapper layer instead).

## 3. Design Details

The application implements a cryptographic layer:
1. **Key Derivation:** On registration/setup, a unique 16-byte random salt `db_key_salt` is generated and saved in the SQLite configuration table. During login, PBKDF2-HMAC-SHA256 with 600,000 iterations derives the user's master key (`db_key`).
2. **Field-Level Encryption:** Sensitive conversation columns (`messages.message`, `contacts.shared_secret`) are encrypted before database insertion using AES-GCM (via `core/crypto.py`).
3. **Decryption Key Storage:** The raw derived `db_key` is cached in a thread-safe server-side dictionary memory cache `_DB_KEY_CACHE` mapped to an opaque random token `db_key_id` in the user's Flask session, keeping the key out of client cookies or static configurations.

## 4. Security & Privacy Implications

- **Brute Force Defense:** The 600,000 iteration PBKDF2 threshold slows down offline dictionary attacks significantly.
- **Fail-Closed Operations:** If database decryption fails, the application must immediately abort the session and dump error frames safely without returning plaintext database contents.

## 5. Backward Compatibility

For users registered with previous iterations (10k PBKDF2), the login sequence attempts a fallback derivation before failing, allowing seamless login migrations.
