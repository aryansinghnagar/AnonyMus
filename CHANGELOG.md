# Changelog

All notable changes to AnonyMus are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **audit remediation — 2026-08-19.** LAN pairing broker now uses a 256-bit
  random pairing token (base32-encoded, 52 chars) instead of a brute-forceable
  6-digit numeric PIN. The HKDF salt for AES-GCM key derivation is now a fresh
  per-pairing random 16-byte value (was the PIN itself, which admitted offline
  brute-force against the GCM authentication tag). The pairing handler enforces
  per-IP rate limiting: 5 failed attempts per 60s, 30-minute cooldown after 10
  failures. Exception messages are no longer leaked to the client (audit fix
  ANO-SEC-001 / ANO-SEC-009, CVSS 9.1 → mitigated).
- **audit remediation — 2026-08-19.** Database key derivation switched from
  PBKDF2-HMAC-SHA256 (10,000 iterations, hardcoded constant salt) to Argon2id
  (t=3, m=65536, p=4) when the ``argon2-cffi`` package is available, with a
  PBKDF2 fallback at 600,000 iterations (OWASP 2023 minimum). The salt is
  now per-user random 16 bytes (``generate_db_salt()``). The legacy
  ``derive_db_key_legacy`` function is retained for one-shot migration of
  existing plaintext databases (audit fix ANO-SEC-002, CVSS 8.1 → mitigated).
- **audit remediation — 2026-08-19.** Coturn TURN credentials in
  ``docker-compose.yml`` are now read from the ``COTURN_USER`` and
  ``COTURN_PASSWORD`` environment variables (was hardcoded
  ``anonymus:turnpassword``). The compose file now fails fast with
  ``:?`` syntax if either is unset (audit fix ANO-SEC-003, CVSS 7.5 →
  mitigated).
- **audit remediation — 2026-08-19.** P2P file upload endpoint
  ``/v3/files/p2p/upload/{chunk_id}`` now requires an Ed25519 signature over
  ``(chunk_id || timestamp)`` from the uploader, verified against the public
  key encoded in their v3 onion address. Per-uploader subdirectories prevent
  cross-uploader overwrites. Per-uploader rate limiting (50 chunks / 5
  minutes) prevents quota-exhaustion DoS (audit fix ANO-SEC-004, CVSS 7.5 →
  mitigated).
- **audit remediation — 2026-08-19.** Relay ``/nodes/register`` and
  ``/nodes/heartbeat`` endpoints now require an Ed25519 signature over
  ``(onion_address || timestamp)`` from the requester, verified against the
  public key encoded in the v3 onion address. The onion_address field is
  constrained to ``^[a-z2-7]{56}\.onion$`` (62 chars exactly). Timestamp
  skew must be ≤ 5 minutes to prevent replay (audit fix ANO-SEC-005,
  CVSS 7.4 → mitigated).
- **audit remediation — 2026-08-19.** CI workflows no longer hardcode
  ``FLASK_SECRET_KEY=ci-testing-secret-key-do-not-use-in-production``. Each
  CI run now derives a unique key from ``github.run_id`` and
  ``github.run_attempt``. The hardcoded value was added to the
  ``_PLACEHOLDER_SECRETS`` allowlist in ``server.py`` so the runtime check
  rejects it if a developer accidentally copies it into a production
  environment (audit fix ANO-SEC-006, CVSS 7.5 → mitigated).
- **audit remediation — 2026-08-19.** ``/metrics`` endpoint (both p2p and
  relay apps) now requires either loopback access or a bearer token matching
  ``ANONYMUS_METRICS_TOKEN``. The token is compared with
  ``secrets.compare_digest`` (constant-time) to prevent timing attacks
  (audit fix ANO-SEC-007, CVSS 7.5 → mitigated).
- **audit remediation — 2026-08-19.** Database encryption is now enforced
  in production: ``core/db/engine.py`` raises ``RuntimeError`` if
  ``settings.environment == "production"`` AND ``settings.db_key`` is empty.
  When ``db_key`` is set and the ``sqlcipher3`` package is installed, the
  engine automatically upgrades the URL scheme to ``sqlite+sqlcipher://``
  and emits ``PRAGMA key`` on each connection. A development-mode warning
  is logged when ``db_key`` is empty (audit fix ANO-SEC-008, CVSS 8.5 →
  mitigated).
- **audit remediation — 2026-08-19.** Admin secret comparison in
  ``server.py::is_authorized_admin`` now uses ``secrets.compare_digest``
  (was ``==``, vulnerable to timing attacks) (audit fix ANO-SEC-024,
  CVSS 3.5 → mitigated).
- **audit remediation — 2026-08-19.** Disguise mode no longer masquerades
  the Windows binary as ``NetworkDiagnostics.exe`` / "Windows Network
  Diagnostics Utility". The launcher window title is now "Secure Local
  Service" and the Inno Setup installer uses honest naming
  (``AnonyMus.exe``, ``AnonyMus Secure Messenger``) (audit fix
  ANO-SEC-011, CVSS 5.0 → mitigated).
- **audit remediation — 2026-08-19.** Hardcoded developer Ed25519 public
  key for supporter-badge verification is now overridable via the
  ``SUPPORTER_BADGE_PUBLIC_KEY`` environment variable (was hardcoded in
  ``core/crypto.py``). The default value is retained for backward
  compatibility with existing badges (audit fix ANO-CODE-001 /
  ANO-SEC-023, CVSS 3.5 → mitigated).

### Fixed

- **audit remediation — 2026-08-19.** Web chat (``ChatArea.tsx``) now
  renders decrypted plaintext instead of raw ``atob(msg.ciphertext_b64)``
  mojibake. The store in ``messages.ts`` had already wired up the Double
  Ratchet decryption pipeline, but the UI was still calling ``atob()``
  on the (now plaintext-encoded-as-base64) field. A new
  ``renderMessageBody`` helper gracefully falls back to a "🔒 Encrypted
  message — decryption pending" placeholder when decryption fails (audit
  fix ANO-UX-001, CVSS 6.5 → mitigated).

### Added

- `AUDIT_REMEDIATION.md` at the repo root, documenting every fix applied
  in response to the deep forensic audit. Each entry cross-references the
  finding ID (ANO-*), the file touched, and the rationale.
- ``.env.example`` now documents every audit-fix environment variable
  (``DB_KEY``, ``COTURN_USER``, ``COTURN_PASSWORD``, ``FLASK_SECRET_KEY``,
  ``ANONYMUS_ADMIN_SECRET``, ``ANONYMUS_METRICS_TOKEN``,
  ``SUPPORTER_BADGE_PUBLIC_KEY``) with generation instructions.
