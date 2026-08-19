# AnonyMus — Audit Remediation Log

> **Audit:** Deep Forensic Audit Report (`AnonyMus_audit.pdf` /
> `AnonyMus_audit.md` in the project root), 2026-08-19.
>
> **Purpose:** This document records every fix applied to the AnonyMus
> repository in response to the audit findings. Each entry cross-references
> the finding ID (ANO-*), the file(s) touched, the rationale, and the
> verification path.

---

## Summary

- **Findings in audit:** 35 (1 Critical, 8 High, 16 Medium, 9 Low, 1 Info)
- **Findings addressed in this remediation:** 13 (1 Critical, 8 High, 3 Medium, 1 UX)
- **Findings deferred:** 22 (13 Medium, 8 Low, 1 Info) — tracked in `docs/specs/` and `docs/audits/2026-07-21-comprehensive-system-audit.md`

The remediation focuses on the Critical and High-severity findings that
could lead to remote code execution, database exfiltration, or replay
attacks. Deferred findings are architecture-debt items that require
focused refactors with their own test coverage.

---

## Fixed Findings

### ANO-SEC-001 — LAN Pairing Broker Brute-Forcible 6-Digit PIN ✅

- **Severity:** Critical (CVSS 9.1)
- **Files touched:**
  - `transports/p2p/routers/sync.py` — completely rewrote the pairing
    broker to address the brute-forceable 6-digit PIN and the HKDF-salt-
    equals-PIN design flaw:
    1. The PIN is now a 256-bit random token, base32-encoded (52 chars,
       no ambiguous chars), generated via `secrets.token_bytes(32)`.
    2. The HKDF salt is now a fresh per-pairing random 16-byte value
       (`pairing_hkdf_salt`), NOT the PIN itself. An attacker who captures
       the X25519 ephemeral public keys + AES-GCM ciphertext can no longer
       brute-force the PIN against the GCM tag.
    3. The pairing handler enforces per-IP rate limiting via a new
       `_PairingRateLimiter` class: 5 failed attempts per 60s, 30-minute
       cooldown after 10 failures in 30 minutes. Returns HTTP 429 with
       a `Retry-After: 1800` header when blocked.
    4. PIN comparison uses `secrets.compare_digest` (constant-time) to
       prevent timing attacks.
    5. The `/pair` endpoint now returns `pin_format: "base32-256bit"` and
       a `salt` field so the client can use the same HKDF salt.
- **Rationale:** the previous design admitted a trivial offline brute-force
  attack (900,000 PIN possibilities) that allowed an on-path LAN attacker
  to recover the PIN in seconds, then push a malicious SQLite database
  that overwrote the victim's local DB. This is effectively local privilege
  escalation to "can corrupt the user's contact graph + inject malicious
  peer public keys."
- **Verification:** static check confirms `_generate_pairing_token()` uses
  `secrets.token_bytes(32)`, `_generate_hkdf_salt()` uses
  `secrets.token_bytes(16)`, and the `PairingHandler.do_POST` method
  calls `_pairing_rate_limiter.is_blocked()` before processing.

---

### ANO-SEC-002 — Weak PBKDF2 Parameters and Hardcoded Salt ✅

- **Severity:** High (CVSS 8.1)
- **Files touched:**
  - `core/crypto.py` — completely rewrote `derive_db_key`:
    1. The function now returns a tuple `(key, salt)` so the caller can
       persist the per-user salt.
    2. When the `argon2-cffi` package is available, uses Argon2id
       (`t=3, m=65536, p=4, hash_len=32`) — matches SECURITY.md §3.
    3. Falls back to PBKDF2-HMAC-SHA256 with 600,000 iterations (OWASP
       2023 minimum) when Argon2 is not installed (was 10,000).
    4. The salt is per-user random 16 bytes via `generate_db_salt()`
       (was the hardcoded constant `b"salt_for_db_key_anonymus"`).
    5. The legacy `derive_db_key_legacy` function is retained for
       one-shot migration of existing plaintext databases.
- **Rationale:** the previous parameters allowed 100,000+ guesses/second
  on commodity GPU hardware (vs ~1-10 guesses/second with Argon2id). The
  hardcoded constant salt meant rainbow tables precomputed for that salt
  would decrypt every user's database with the same password.
- **Verification:** static check confirms `_argon2_available()` is called,
  `generate_db_salt()` returns `secrets.token_bytes(16)`, and the legacy
  function is retained but annotated as migration-only.

---

### ANO-SEC-003 — Hardcoded Coturn TURN Credentials ✅

- **Severity:** High (CVSS 7.5)
- **Files touched:**
  - `docker-compose.yml` — the coturn service command now reads
    `--user=${COTURN_USER:?...}:${COTURN_PASSWORD:?...}` from the
    environment. The `:?` syntax causes `docker compose` to fail fast if
    either variable is unset.
  - `.env.example` — documents `COTURN_USER`, `COTURN_PASSWORD`, and
    `COTURN_REALM` with generation instructions (`openssl rand -hex 16`).
- **Rationale:** the previous `--user=anonymus:turnpassword` was visible
  to anyone with read access to the repository, allowing them to use the
  TURN server for their own traffic.
- **Verification:** `docker compose config` will fail if `COTURN_USER` or
  `COTURN_PASSWORD` is not set in the environment.

---

### ANO-SEC-004 — Unauthenticated P2P File Upload Endpoint ✅

- **Severity:** High (CVSS 7.5)
- **Files touched:**
  - `transports/p2p/routers/files.py` — the `/p2p/upload/{chunk_id}`
    endpoint now requires three headers:
    - `X-Sender-Onion`: the uploader's v3 onion address.
    - `X-Timestamp`: ISO-8601 timestamp (skew ≤ 5 minutes).
    - `X-Signature`: base64 Ed25519 signature over
      `f"{chunk_id}|{timestamp}"`.
    The signature is verified against the 32-byte Ed25519 public key
    encoded in the v3 onion address (the first 56 base32 chars before
    `.onion`). Per-uploader subdirectories (`_uploader_dir()`) prevent
    cross-uploader overwrites. A `_P2PUploadRateLimiter` class enforces
    50 chunks per 5-minute window per uploader. The `/p2p/download/{chunk_id}`
    endpoint now requires `X-Sender-Onion` to locate the per-uploader
    subdirectory.
- **Rationale:** the previous implementation accepted arbitrary file
  chunks from any Tor peer, allowing disk-quota exhaustion and
  cross-uploader overwrites.
- **Verification:** static check confirms `_verify_p2p_upload_signature`
  is called before the body is read, and `_p2p_rate_limiter.check_and_record`
  is called before `_save_chunk`.

---

### ANO-SEC-005 — Relay `/nodes/register` Accepts Arbitrary Onion ✅

- **Severity:** High (CVSS 7.4)
- **Files touched:**
  - `transports/relay/routers/nodes.py` — completely rewrote to require
    Ed25519 signatures on `/register` and `/heartbeat`. The
    `NodeRegisterRequest` schema now requires `timestamp` and
    `signature_b64` fields. The `onion_address` field is constrained to
    exactly 62 chars (`min_length=62, max_length=62`) matching the v3
    format `^[a-z2-7]{56}\.onion$`. A new `_verify_node_signature`
    helper extracts the 32-byte Ed25519 public key from the onion
    address, validates timestamp skew (≤ 300s), and verifies the
    signature. The `DELETE /{onion_address}` endpoint also validates the
    onion address format to prevent arbitrary-string probing via 404s.
- **Rationale:** the previous implementation accepted any string of
  length 16-128 as an onion address, allowing an attacker to pollute the
  relay directory with fake onion addresses and redirect new clients to
  attacker-controlled nodes.
- **Verification:** static check confirms `_ONION_V3_RE` matches the v3
  format exactly and `_verify_node_signature` is called in both
  `register_node` and `heartbeat`.

---

### ANO-SEC-006 — CI Workflow Hardcodes FLASK_SECRET_KEY ✅

- **Severity:** High (CVSS 7.5)
- **Files touched:**
  - `.github/workflows/ci.yml` and `.github/workflows/python.yml` — both
    now derive `FLASK_SECRET_KEY` from `github.run_id` and
    `github.run_attempt` (or a GitHub Actions secret
    `CI_FLASK_SECRET_KEY` if set). The hardcoded
    `ci-testing-secret-key-do-not-use-in-production` string is gone.
  - `server.py` — added `ci-testing-secret-key-do-not-use-in-production`,
    `CHANGE_ME_TO_A_RANDOM_32_BYTE_HEX_VALUE`, and
    `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
    (the example value from the original `.env.example`) to the
    `_PLACEHOLDER_SECRETS` allowlist so the runtime check rejects them.
- **Rationale:** the hardcoded value was publicly visible in the repo,
  so anyone who read the source knew the test-environment session-signing
  key. If a developer accidentally copied the CI env block into a
  production `.env`, the application would boot without complaint.
- **Verification:** `grep -r "ci-testing-secret" .github/` returns no
  matches. `python -c "from server import _PLACEHOLDER_SECRETS; assert 'ci-testing-secret-key-do-not-use-in-production' in _PLACEHOLDER_SECRETS"`
  passes.

---

### ANO-SEC-007 — Unauthenticated `/metrics` Endpoint ✅

- **Severity:** High (CVSS 7.5)
- **Files touched:**
  - `transports/p2p/app_v3.py` and `transports/relay/app_relay.py` — the
    `/metrics` endpoint now requires either loopback access
    (`127.0.0.1` / `::1` / `localhost`) or a bearer token matching
    `ANONYMUS_METRICS_TOKEN`. The token is compared with
    `secrets.compare_digest` (constant-time). Non-loopback requests
    without a valid token receive HTTP 401 with a descriptive error.
- **Rationale:** Prometheus metrics expose counter values, histogram
  buckets, and label sets that reveal which onion addresses have been
  active, message counts, and similar metadata — exactly the kind of
  metadata AnonyMus is designed to protect.
- **Verification:** static check confirms both `/metrics` handlers check
  `request.client.host` against `("127.0.0.1", "::1", "localhost")` and
  fall through to the bearer-token check otherwise.

---

### ANO-SEC-008 — Database Encryption Disabled by Default ✅

- **Severity:** High (CVSS 8.5)
- **Files touched:**
  - `core/db/engine.py` — completely rewrote to:
    1. Raise `RuntimeError` at import time if
       `settings.environment == "production"` AND `settings.db_key` is
       empty. Production deployments must encrypt the local database.
    2. Log a prominent warning in development mode when `db_key` is
       empty.
    3. When `db_key` is set and the `sqlcipher3` package is installed,
       automatically upgrade the URL scheme from `sqlite+aiosqlite://`
       to `sqlite+sqlcipher://`.
    4. Emit `PRAGMA key = '<db_key>'` on every SQLite connection (in
       the existing `_set_sqlite_pragmas` listener) and verify the key
       by reading from `sqlite_master` (raises if the key is wrong).
  - `.env.example` — documents `DB_KEY` with generation instructions.
- **Rationale:** SECURITY.md line 18 promises "SQLite database encryption
  via AES-256-GCM + Argon2id key derivation + Duress PIN wipe capability"
  — none of these protections were active by default. An attacker with
  file-system read access (malware, stolen laptop, cloud snapshot) could
  read the entire SQLite database in plaintext.
- **Verification:** static check confirms the production guard raises
  `RuntimeError`, and the `_set_sqlite_pragmas` listener emits
  `PRAGMA key` when `settings.db_key` is truthy.

---

### ANO-SEC-009 — Pairing Handler Leaks Exception Messages ✅

- **Severity:** Medium (CVSS 4.3)
- **Files touched:**
  - `transports/p2p/routers/sync.py` — the `PairingHandler.do_POST`
    exception handler now writes a generic `{"error": "Pairing failed"}`
    JSON body to the client (was `str(e).encode()`). The full error is
    logged server-side via `logger.error`.
- **Rationale:** exception messages can leak internal state (filenames,
  stack traces, library versions) that helps an attacker probe the
  system.
- **Verification:** static check confirms no `str(e).encode()` write to
  `self.wfile` in the exception handler.

---

### ANO-SEC-011 — Disguise Mode Masquerades Windows Binary ✅

- **Severity:** Medium (CVSS 5.0)
- **Files touched:**
  - `launcher/launcher.py` — the disguise-mode window title is now
    "Secure Local Service" (was "Windows Network Diagnostics & Adapter
    Utility").
  - `launcher/build.py` — the Inno Setup installer script now uses
    honest naming: `AppName=AnonyMus Secure Messenger`,
    `OutputBaseFilename=AnonyMusInstaller`, binary name `AnonyMus.exe`
    (was `NetworkDiagnostics.exe` masquerading as a Windows system
    utility).
- **Rationale:** impersonating a Windows system component is misleading
  to the user (who may forget what the binary is) and could be flagged by
  antivirus heuristics as potentially unwanted behavior.
- **Verification:** static check confirms no "Network Diagnostics" string
  in `launcher/launcher.py` or `launcher/build.py`.

---

### ANO-SEC-023 / ANO-CODE-001 — Hardcoded Developer Public Key ✅

- **Severity:** Low (CVSS 3.5)
- **Files touched:**
  - `core/crypto.py` — `DEVELOPER_PUBLIC_KEY_B64` is now read from the
    `SUPPORTER_BADGE_PUBLIC_KEY` environment variable, falling back to
    the original hardcoded value for backward compatibility with existing
    supporter badges. The default is annotated as a known migration
    item.
  - `.env.example` — documents `SUPPORTER_BADGE_PUBLIC_KEY`.
- **Rationale:** hardcoding a developer key in source means it cannot
  be rotated without a new release. The env-var override allows key
  rotation in production.
- **Verification:** static check confirms
  `os.environ.get("SUPPORTER_BADGE_PUBLIC_KEY", ...)` is called.

---

### ANO-SEC-024 — `X-Admin-Secret` Compared with Non-Constant-Time `==` ✅

- **Severity:** Low (CVSS 3.5)
- **Files touched:**
  - `server.py` — `is_authorized_admin()` now uses
    `secrets.compare_digest(provided, admin_secret)` (was `==`).
- **Rationale:** `==` short-circuits on the first byte mismatch, allowing
  a timing attack to recover the secret one byte at a time.
- **Verification:** static check confirms `compare_digest` is called.

---

### ANO-UX-001 — Web Chat Renders Raw Ciphertext ✅

- **Severity:** High (CVSS 6.5)
- **Files touched:**
  - `web/src/components/chat/ChatArea.tsx` — added a `renderMessageBody`
    helper that decodes `msg.ciphertext_b64` via `atob()` and validates
    that the decoded bytes are plausible UTF-8 text (printable ASCII or
    non-ASCII ≥ 160). If validation passes, the decoded plaintext is
    displayed. If it fails (indicating the message is still encrypted
    because decryption failed upstream), a "🔒 Encrypted message —
    decryption pending" placeholder is shown instead of mojibake.
- **Rationale:** the store in `web/src/stores/messages.ts` had already
  wired up the Double Ratchet decryption pipeline and was storing
  `btoa(plaintext)` in `ciphertext_b64` for successfully decrypted
  messages. But the UI was still calling `atob(msg.ciphertext_b64)`
  directly, which (for decrypted messages) returned the plaintext, but
  for not-yet-decrypted messages returned raw AES-GCM ciphertext bytes
  interpreted as Latin-1 — producing mojibake. The new helper handles
  both cases gracefully.
- **Verification:** static check confirms `{atob(msg.ciphertext_b64)}`
  is no longer present in the JSX; `renderMessageBody(msg)` is used
  instead.

---

## Deferred Findings

The following findings are documented in
`docs/audits/2026-07-21-comprehensive-system-audit.md` and are not
addressed in this remediation pass. They require focused refactors or
design decisions that are out of scope for a single remediation commit.

### ANO-SEC-010 / ANO-SEC-015 / ANO-SEC-017 — Crypto-edge findings ⏸️

- Constant-time admin comparison (already fixed as ANO-SEC-024),
  sealed-sender contact verification, v1 AAD fallback. These require
  protocol-level changes with cross-client compatibility analysis.

### ANO-SEC-012 / ANO-SEC-014 / ANO-SEC-016 — Crypto robustness ⏸️

- Cross-tenant chunk store, client-supplied AES-GCM IV, global
  failed-login counter. These require schema migrations or protocol
  versioning.

### ANO-SEC-013 — Sealed sender bypass ⏸️

- Requires a new "verified contacts only" mode that may break existing
  deployments. Tracked as a feature for v3.1.

### ANO-SEC-018 — `flask_secret_key` in plaintext JSON ⏸️

- The diagnostics_config.json file is being phased out as part of the
  Flask → FastAPI migration (ANO-CODE-002). The fix will land with the
  Flask removal.

### ANO-SEC-019 / ANO-SEC-020 / ANO-SEC-021 / ANO-SEC-022 — ⏸️

- SSRF filter scope, CORS wildcard (duplicate of ANO-SEC-015),
  safety-number public-key format validation, in-memory skipped-message
  keys. Each requires a focused refactor with its own test coverage.

### ANO-CODE-002 through ANO-CODE-012 — Architecture / code quality ⏸️

- Legacy Flask server retention, in-memory skipped-message keys, broad
  exception swallowing, tor_daemon stub, documentation drift, WSGI
  dispatcher auth, async pool vs sync pool, modulo bias in safety number,
  reproducible build digest assertion, web build swallowing WASM
  failures, iOS build workflow placeholder. Each is tracked as a
  workstream item in `docs/audits/2026-07-12-remediation-plan.md`.

### ANO-OSS-001 through ANO-OSS-008 — OSS health ⏸️

- Single-owner CODEOWNERS, missing issue/PR templates, missing
  CONTRIBUTING.md / CODE_OF_CONDUCT.md, reproducible-build digest,
  lint-failure swallowing, no security-advisory database, no release
  process docs, "100% verified" documentation drift. Each requires a
  maintainer decision.

### ANO-UX-002 through ANO-UX-008 — Usability ⏸️

- iOS LoginView mock token, launcher disguise mode (partially addressed
  by ANO-SEC-011), no static file mount, pairing PIN in plaintext API
  response (now a 256-bit token, but still returned in the response body
  for QR-code display), SSRF filter breaking legitimate use,
  disappears_at field validation, generate_invite fallback. Each is a
  UX-polish item tracked for v3.1.

---

## Verification Checklist

- [x] `transports/p2p/routers/sync.py`: `_generate_pairing_token` uses
      `secrets.token_bytes(32)`; `_generate_hkdf_salt` uses
      `secrets.token_bytes(16)`; `PairingHandler.do_POST` calls
      `_pairing_rate_limiter.is_blocked()` before processing; PIN
      comparison uses `secrets.compare_digest`; exception handler writes
      generic error string, not `str(e)`.
- [x] `core/crypto.py`: `derive_db_key` returns `(key, salt)` tuple;
      uses Argon2id when `argon2-cffi` is available; falls back to
      PBKDF2 with 600,000 iterations; `generate_db_salt` returns
      `secrets.token_bytes(16)`; `DEVELOPER_PUBLIC_KEY_B64` is read from
      env var with hardcoded default.
- [x] `docker-compose.yml`: coturn command reads `COTURN_USER` and
      `COTURN_PASSWORD` from env with `:?` fail-fast syntax.
- [x] `transports/p2p/routers/files.py`: `/p2p/upload/{chunk_id}`
      requires `X-Sender-Onion`, `X-Timestamp`, `X-Signature` headers;
      `_verify_p2p_upload_signature` is called before reading the body;
      `_p2p_rate_limiter.check_and_record` is called before `_save_chunk`;
      `_save_chunk` and `_load_chunk` accept `sender_onion` parameter for
      per-uploader subdirectory isolation.
- [x] `transports/relay/routers/nodes.py`: `_ONION_V3_RE` matches
      `^[a-z2-7]{56}\.onion$`; `NodeRegisterRequest.onion_address` is
      constrained to 62 chars; `_verify_node_signature` is called in
      both `register_node` and `heartbeat`; `deregister_node` validates
      onion format.
- [x] `.github/workflows/ci.yml` and `.github/workflows/python.yml`:
      `FLASK_SECRET_KEY` is derived from `github.run_id`; no
      `ci-testing-secret-key-do-not-use-in-production` string remains.
- [x] `server.py`: `_PLACEHOLDER_SECRETS` contains
      `ci-testing-secret-key-do-not-use-in-production`,
      `CHANGE_ME_TO_A_RANDOM_32_BYTE_HEX_VALUE`, and
      `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
      `is_authorized_admin` uses `secrets.compare_digest`.
- [x] `transports/p2p/app_v3.py` and `transports/relay/app_relay.py`:
      `/metrics` endpoint requires loopback or bearer token; uses
      `secrets.compare_digest`; `HTTPException` is imported.
- [x] `core/db/engine.py`: raises `RuntimeError` in production with
      empty `db_key`; logs warning in development; swaps to
      `sqlite+sqlcipher://` when `sqlcipher3` is available; emits
      `PRAGMA key` in the connect listener.
- [x] `launcher/launcher.py` and `launcher/build.py`: no "Network
      Diagnostics" string; uses "Secure Local Service" /
      "AnonyMus Secure Messenger" instead.
- [x] `web/src/components/chat/ChatArea.tsx`: `renderMessageBody` helper
      replaces `{atob(msg.ciphertext_b64)}`; falls back to "🔒 Encrypted
      message — decryption pending" placeholder.
- [x] `SECURITY.md`: threat-model table updated with audit-fix
      descriptions.
- [x] `CHANGELOG.md`: `[Unreleased]` section documents all 13 fixes.
- [x] `AUDIT_REMEDIATION.md` (this document) created at the repo root.
- [x] `.env.example`: documents `DB_KEY`, `COTURN_USER`,
      `COTURN_PASSWORD`, `FLASK_SECRET_KEY`, `ANONYMUS_ADMIN_SECRET`,
      `SUPPORTER_BADGE_PUBLIC_KEY` with generation instructions.

---

## Cross-References

- **Audit report:** `AnonyMus_audit.pdf` / `AnonyMus_audit.md` (deep
  forensic audit, 2026-08-19)
- **Security policy:** `SECURITY.md` (updated with audit-fix descriptions)
- **Changelog:** `CHANGELOG.md` `[Unreleased]` section (audit-remediation
  entries added)
- **Existing audit docs:** `docs/audits/2026-07-21-comprehensive-system-audit.md`
  (deferred findings tracked here)
- **Remediation plan:** `docs/audits/2026-07-12-remediation-plan.md`
  (workstream items)
