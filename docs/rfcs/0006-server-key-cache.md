# RFC 0006: Server-Side Database Key Cache Design

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

Storing database decryption keys (such as `db_key`) inside client-side session cookies or local storage presents a high risk. If an attacker intercepts the cookie or compromises the user's browser, they can extract the key and decrypt the entire message archive at rest.

## 2. Goals & Non-Goals

### Goals
- Eradicate `db_key` transmission or storage in client-side cookies/storage.
- Store derived database keys in a volatile, secure, server-side memory store.
- Bind database access authorization to ephemeral session tokens.

### Non-Goals
- Persistent storage of raw derived database decryption keys on the server disk.

## 3. Design Details

The system employs a volatile server-side cache:
1. **Opaque Token Mapping:** On successful login, the client receives an ephemeral random token `db_key_id` stored inside the encrypted session cookie.
2. **Server-Side Store:** The server process holds a thread-safe `_DB_KEY_CACHE` dictionary in memory.
3. **Decryption Access:** When the client queries database records, the server uses `db_key_id` to lookup the master `db_key` and decrypt the columns.
4. **Invalidation:** Logging out or session expiration automatically destroys the key in the cache.

```
[ Client Browser ]                      [ Server Memory Cache ]
        |                                         |
        |--- 1. POST /login --------------------->| (Derives db_key)
        |<-- 2. Sets db_key_id cookie ------------| (Stores db_key mapped to db_key_id)
        |                                         |
        |--- 3. GET /api/messages (db_key_id) --->| (Looks up db_key and decrypts DB)
```

## 4. Security & Privacy Implications

- **Cookie Compromise Protection:** An attacker stealing the Flask session cookie only gains access to the current session (under 8 hours) but cannot recover the static database decryption key at rest.
- **Cache Eviction Policies:** The cache must be cleared periodically to prevent memory leaks or key residue retention on session timeouts.

## 5. Backward Compatibility

All clients must authenticate to establish the server-side cache entry; direct database accesses without establishing a cache reference are rejected.
