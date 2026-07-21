# AnonyMus — Comprehensive Remaining Issues & Remediation Plan

**Audit date:** 2026-07-20
**Repository snapshot:** detached HEAD at `dc73d2a` (`fix(ci): set continue-on-error on biome check…`)
**Working tree:** dirty (`Cargo.lock`, `core/rust/Cargo.toml`, `requirements.txt` modified; not part of this audit’s defect set)
**Prior baseline:** [2026-07-12 current-state issue log](2026-07-12-current-state-issue-log.md) and [remediation plan](2026-07-12-remediation-plan.md)
**Confidence:** **high** for source-level contract, security, and architecture findings; **moderate** for runtime behavior not executed under full Tor/WASM; **low/unknown** for live multi-peer Tor e2e and Android instrumented tests (not run here).

---

## 0. How to read this document

This is not a feature wishlist. It is a defect inventory of **bugs, errors, vulnerabilities, operational hazards, test/CI blind spots, documentation lies, and incomplete security properties** still present in the tree.

Severity:

| Level | Meaning |
| --- | --- |
| **Critical** | Breaks core product function or enables high-impact compromise if the path is used/deployed |
| **High** | Significant security, privacy, data-integrity, or multi-user isolation failure |
| **Medium** | Real defect with limited blast radius, or security/privacy degradation |
| **Low** | Correctness nits, maintainability debt, weak hygiene that compounds risk |
| **Info** | Incomplete roadmap work that is dangerous only if marketed as done |

IDs use prefix **R-** (Remaining, 2026-07-20). Where an issue maps to the July 12 log, the old **I-** ID is noted.

### What improved since 2026-07-12 (do not re-open as-is)

| Old ID | Status now | Notes |
| --- | --- | --- |
| I-01 (partial) | **Partially fixed** | Message routes now match client nouns (`POST /v3/messages/`, `GET /v3/messages/{onion}`, `disappears_at`). Contact delete by `id` works. Login still returns a thin `UserResponse` vs client `User` shape. |
| I-02 (partial) | **Partially fixed** | Compose health checks hit `/healthz` on 5001; `SECRET_KEY` / `ENVIRONMENT` / `DATABASE_URL` present; node service uses uvicorn. Caddy/frontend/wasm/relay topology still broken (see R-02). |
| I-03 (partial) | **Partially fixed** | Alembic chain extended; reconcile migration exists; lifespan runs `alembic upgrade head`. ORM vs migration PK/column drift remains. |
| I-04 (partial) | **Partially fixed** | Pre-keys moved to DB; ownership checks on publish/rotate; `/keys/me` scopes to user. Signature verification, atomic OPK consume, and key length validation still missing. |
| I-05 | **Fixed** | Group send checks `GroupMember` membership. Residual: unsolicited member injection on create. |
| I-06 | **Fixed** | Workbox no longer NetworkFirst-caches `/v3/*`. |
| I-07 (partial) | **Partially fixed** | Python CI no longer ends with `\|\| true`. Other continue-on-error / non-gating paths remain. |
| I-08 (partial) | **Partially fixed** | `requirements.txt` now includes FastAPI stack. `pyproject.toml` still declares no runtime deps; dual config names remain. |
| I-10 (partial) | **Partially fixed** | In-memory global rate limiter exists; not auth-specific, not durable, not multi-worker safe. |
| I-11 | **Fixed** | Google Fonts links removed from `web/index.html`. Legacy Flask CSP still allows Google Fonts. |
| I-13 | **Fixed** | History pagination uses `before` and applies `sent_at` cursor. |
| I-14 (partial) | **Partially fixed** | Notifications partially DB-backed; node `_config` still in-memory; notify helper still touches legacy DB. |

---

## 1. Executive summary

AnonyMus is a **multi-generation hybrid**: legacy Flask/Socket.IO P2P + Relay, a FastAPI v3 surface, a SolidJS web client, Rust crypto core (with placeholder WASM), Android, and a stub iOS app. The commercial claim set (E2EE, sealed sender, PQ hybrid, Tor P2P, panic wipe, dual-mode transport) is **far ahead of the integrated reliability of those claims**.

**Top release blockers (must fix before any production or “secure messenger” claim):**

1. **Web crypto is not production-capable** — checked-in WASM is a throw-stub; real `.wasm` binary absent; Docker build masks `wasm:build` failure.
2. **Dual database / dual migration / dual transport stacks** — silent state split between `local_node.db` (legacy SQL) and `anonymus.db` (SQLAlchemy/Alembic).
3. **Pre-key and messaging crypto trust boundaries incomplete** — no server-side signature verification; OPK consume races; sealed-sender resolve trusts client assertion.
4. **Unauthenticated P2P and file surfaces** enable spam, storage DoS, and unauthenticated message injection (sealed path).
5. **Deploy topology still cannot ship a coherent full stack** — Caddy→relay only, frontend builder not ordered, WASM optional, Coturn hard-coded credentials.
6. **iOS is a hard-coded demo**, not a client.
7. **Session/API contract still drifts** — `User` shape, missing fields, Socket.IO port mismatch in Vite proxy.

If this were a third-party audit kickoff package, the honest status is: **not audit-ready for cryptographic product claims**. Architecture intent is ambitious; integration integrity is incomplete.

---

## 2. Scope, method, and limits

### In scope

- Python backend: `core/`, `transports/p2p/`, `transports/relay/`, `server.py`, `cli.py`
- Web client: `web/`
- Rust core + FFI: `core/rust/`
- Alembic + legacy SQL migrations
- Docker / Compose / Caddy / Tor configs
- CI workflows under `.github/workflows/`
- Android (`android/`) and iOS (`ios/`) surface review
- Docs claims vs code reality
- Prior issue log re-verification

### Method

- Full tree inventory and cross-contract comparison (API routers ↔ web client types ↔ models ↔ migrations ↔ Compose)
- Security-oriented reading of auth, crypto, P2P ingress, file transfer, sessions, rate limiting
- AST parse of all Python sources: **0 syntax errors**
- File presence checks for WASM artifacts
- Grep-driven defect mining (`TODO`/`pass` handoffs, rate limits, CSRF, secrets, trust managers)

### Not executed in this environment

- `pytest` (not installed in the agent Python)
- Full Docker Compose boot
- Tor multi-node e2e
- Android instrumentation / iOS simulator
- `wasm-pack` / Cargo full crypto KAT under this shell
- Live Semgrep/CodeQL

Findings that depend on those are marked **runtime-unverified**.

---

## 3. System map (current reality)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Clients                                                                 │
│  SolidJS web  │  Android (OkHttp+Socket.IO)  │  iOS stub  │  CLI/SDK     │
└───────┬───────────────────┬─────────────────────┬────────────────────────┘
        │ /v3 REST + cookies│  mixed /api + /v3   │ hardcodes              │
┌───────▼───────────────────▼─────────────────────▼────────────────────────┐
│  FastAPI v3 (app_v3)          │  Legacy Flask P2P/Relay (server.py)      │
│  SessionMiddleware            │  CSRF (Flask-WTF) + security_headers     │
│  In-memory rate limit         │  eventlet WSGI dispatcher                │
└───────┬───────────────────────┴──────────┬───────────────────────────────┘
        │                                  │
┌───────▼──────────┐              ┌────────▼─────────┐
│ SQLAlchemy async │              │ sqlite raw SQL   │
│ anonymus.db      │  ← split →   │ local_node.db    │
│ Alembic          │              │ SQL migrations/  │
└──────────────────┘              └──────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────────────────┐
│  Crypto: Python DR + pq_kem(liboqs)  │  TS DR in browser  │  Rust core   │
│  (three implementations; not one source of truth in production web)      │
└──────────────────────────────────────────────────────────────────────────┘
```

This split is the root cause of many “works in one path, dead in another” defects.

---

## 4. Architecture-level problems

### R-A01 — Dual runtime authority (Critical / Architecture)

**Problem:** Two full servers coexist:

- Legacy: `server.py` + `transports/p2p/server.py` + `transports/relay/server.py` (Flask + Socket.IO + eventlet)
- V3: `transports/p2p/app_v3.py` (FastAPI + python-socketio mount)

Docker `node` profile runs FastAPI. Docker `relay` profile runs `transports.relay.app_relay:app`. Root `server.py` remains the dual-mode dispatcher for non-Docker / launcher paths. Docs still teach a mixture of both.

**Impact:** Operators and clients cannot know which contract is authoritative. Features land on one stack and not the other. Tests span both with different CSRF and session models.

**Remediation:**

1. Declare **one** production authority: FastAPI v3 (or explicitly freeze Flask as legacy-only with a sunset date).
2. Delete or quarantine the non-authority stack behind `legacy/` + CI job that only runs until sunset.
3. One OpenAPI contract; generate web/Android types from it.

---

### R-A02 — Dual database files and dual migration systems (Critical / Data)

**Problem:**

| Layer | File / mechanism | Used by |
| --- | --- | --- |
| Legacy | `local_node.db` via `DB_FILE`, raw SQL in `transports/p2p/database.py`, SQL files under `transports/p2p/migrations/` | Flask P2P, `notify_contact()`, parts of node reset |
| V3 | `anonymus.db` / `DATABASE_URL`, SQLAlchemy models, Alembic under `alembic/versions/` | FastAPI routers |

`notifications.notify_contact()` writes the **legacy** DB. V3 register/poll use **SQLAlchemy** `NotificationQueue`. Those are not the same store unless someone carefully unifies paths (they do not by default).

**Impact:** “Notifications work in unit tests of one path” while production v3 message delivery never sets the flag the poller sees. Panic wipe / reset can wipe one DB and leave the other.

**Remediation:**

1. Single DB URL and single connection layer for the active stack.
2. Delete or adapt `notify_contact` to async SQLAlchemy.
3. Stop shipping two migration frameworks for the same tables.

---

### R-A03 — ORM ↔ Alembic residual schema drift (High / Data)

**Evidence:**

- Alembic `0001` creates `messages` with **`message_id` PK** and **no integer `id`**.
- ORM `Message` has **integer `id` PK** + unique `message_id`.
- Same pattern for `groups` / `group_messages`.
- Reconcile migration `82c9e7fd389a` adds `last_seen`, `is_blocked`, `is_deleted` but **does not introduce integer PKs** or align FKs fully.
- ORM `User` has no `is_blocked` column that the reconcile migration may add.
- Contact/group `profile_id` FK assumes `profiles` row `default` exists (seeded only if profiles table created by migration 698e…).

**Impact:** Fresh Alembic DB can fail ORM inserts/selects depending on SQLAlchemy reflection assumptions; SQLite may auto-add quirks that mask Postgres failures. Schema-drift tests still center on legacy SQL snapshots, not full ORM↔Alembic parity.

**Remediation:**

1. Generate a single forward migration from current ORM metadata; make models the source of truth.
2. Pick one PK strategy (prefer UUID `message_id` as PK; drop unused integer `id`, or migrate properly).
3. Add CI test: empty DB → `alembic upgrade head` → representative ORM CRUD for every model.

---

### R-A04 — Triple crypto implementation without a single production binding (Critical / Crypto)

| Implementation | Location | Status |
| --- | --- | --- |
| Python Double Ratchet + PQ hybrid | `core/double_ratchet.py`, `core/pq_kem.py` | Server-side / legacy-oriented |
| TypeScript Double Ratchet | `web/src/lib/crypto.ts` | Used by web send/receive |
| Rust primitives + protocol modules | `core/rust/` | Intended WASM/PyO3 core; web binding is a **placeholder** |

**Checked-in web WASM:**

- `web/src/lib/pkg/anonymus_core.js` — stub that **throws** `"WASM not initialized"`
- `anonymus_core_bg.wasm` — **MISSING**
- `core.ts` falls back to an insecure stub only in non-PROD; PROD throws — so **production web messaging cannot initialize crypto at all** unless a real wasm-pack output is injected at build time (Docker currently allows build to continue without it).

**Impact:** Either (a) production web fails closed on crypto load, or (b) a misconfigured build ships with stub/dev crypto. Both are release blockers for an E2EE messenger.

**Remediation:**

1. Make `npm run wasm:build` **mandatory** in CI and Docker; fail the image if `.wasm` missing.
2. Delete checked-in throw-stubs or replace with build-generated artifacts only.
3. Long-term: one DR implementation (Rust) with thin TS/Python bindings; delete parallel TS DR once parity tests pass.

---

### R-A05 — Transport mode switch is not a real migration (High / Reliability)

**Evidence:** `core/transport_registry.py` continues mode swap even if handoff/stop fails; both adapters implement `handoff()` as `pass`.

**Impact:** Control plane reports success while sessions, queues, and listeners are inconsistent. Unsafe to expose as “graceful switch.”

**Remediation:** Fail closed on handoff errors; implement real handoff or remove the API from production builds.

---

### R-A06 — Capability claim inflation (High / Product integrity)

Docs/audit readiness and RFCs describe sealed sender, PQXDH, MLS, padding, multi-device sync, panic wipe, etc. Several are partial:

- MLS: Rust/Python scaffolding exists; not end-to-end in web UX.
- PQ hybrid: env-gated, liboqs optional, web path does not use PQ.
- Invites: fallback `pending.onion` on Tor failure.
- Multi-device: tables/tests exist; not a complete product surface.
- iOS: calculator shell with passcodes `1337` / `9999`.

**Impact:** External auditors and users will treat claims as implemented. That creates legal and security liability.

**Remediation:** Feature flags with explicit “not production” labels; gate marketing/docs to verified evals only.

---

## 5. Defect catalog (remaining)

### 5.1 Critical

#### R-01 — Production web crypto cannot load (WASM missing / stub)

**Area:** Web / Crypto / Build
**Maps to:** I-12 (worsened: JS stub now present but still non-functional)
**Evidence:**

- `web/src/lib/pkg/anonymus_core.js` always throws on init.
- No `anonymus_core_bg.wasm` in tree.
- `docker-compose.yml` frontend-builder: `(npm run wasm:build || true)`.
- `web/src/lib/core.ts` stub AEAD is **nonce + plaintext** (no real encryption) for dev.

**Impact:** Secure messaging in the browser is not shippable. A forced stub path is catastrophic (plaintext under the guise of ciphertext).

**Plan:**

1. CI job: wasm-pack build → artifact upload → web build consumes artifact.
2. Docker: fail if wasm missing; remove `|| true`.
3. Runtime: refuse send/receive UI unless `isStub()===false` and `protocolVersion()` matches.
4. Add integration test that production build bundle contains `.wasm` and encrypt/decrypt round-trips.

---

#### R-02 — Compose / Caddy deploy topology still incoherent

**Area:** Deployment
**Maps to:** I-02
**Evidence:**

- Caddy reverse_proxies `/v3/*` only to **`relay:5001`**, not `node`.
- `frontend-builder` is not a dependency of `caddy`; volume may be empty on first boot.
- Relay profile and node profile share env but different apps; SPA always pointed at relay.
- Socket.IO and non-`/v3` paths are not proxied in Caddyfile.
- Coturn ships with hard-coded `--user=anonymus:turnpassword`.

**Impact:** “docker compose up” does not produce a working full-stack messenger.

**Plan:**

1. One compose profile per product mode with correct upstream service names.
2. Caddy routes: static SPA + `/v3/*` + `/socket.io/*` + `/p2p/*` + health.
3. `depends_on` frontend build completion (or multi-stage image with prebuilt `dist`).
4. Secrets for TURN from env; never hard-code.

---

#### R-03 — Sealed-sender resolution trusts client-supplied identity

**Area:** Messaging / AuthZ / Crypto
**Evidence:** `POST /v3/messages/{id}/resolve_sender` accepts `sender_onion` from the client after only checking that onion is an accepted contact. It does **not** require proof that the sealed envelope decrypted to that onion under the recipient’s key on the server (and the server cannot decrypt E2EE payload — so the trust model must be carefully designed).

Worse: if contact check fails, the **message is deleted**, which is a DoS vector if an attacker can cause resolve attempts.

On the client, decrypt success is local, but the API allows any authenticated user who received a sealed message to attribute it to any accepted contact (forging social metadata in the DB).

**Impact:** Sender attribution integrity is weak; spam/DoS via resolve path; sealed-sender privacy model is incomplete server-side (server still often stores real `sender_onion` on send path when not sealed).

**Plan:**

1. Store sealed messages with `sender_onion='sealed'` only; never write real sender until client posts a **MAC/signature** binding decrypted sender identity to message_id (or keep attribution client-local only).
2. Do not delete messages on failed resolve without rate limits and proof-of-work / authz.
3. Spec the sealed-sender threat model in an RFC and test it.

---

#### R-04 — Unauthenticated P2P ingress accepts traffic with weak/forgable identity

**Area:** P2P / Network
**Evidence:**

- `POST /p2p/handshake`, `/p2p/message`, `/p2p/delete`, `/v3/files/p2p/*` have **no mutual authentication** beyond “you can reach the onion.”
- Handshake accepts any onion string matching regex and upserts contacts.
- Sealed messages skip contact checks on receipt.
- Sequence checks are spoofable when sender string is attacker-controlled.

**Impact:** Spam, contact-list pollution, sealed-message storage DoS, disk fill, Socket.IO event spam to the local UI.

**Plan:**

1. Require first-message path only via invite tokens or pre-established contact keys.
2. Rate-limit and challenge inbound onion requests (per-circuit if possible).
3. Authenticate frames with identity signatures over (seq, ciphertext hash, recipient).
4. Cap sealed unknown-sender storage.

---

#### R-05 — File chunk store is unauthenticated, unbounded, in-memory

**Area:** Files / DoS
**Evidence:** `transports/p2p/routers/files.py` uses module-global `_chunks: dict[str, bytes]`. P2P upload requires **no auth**. 10 MB per chunk × unlimited IDs = memory exhaustion. No TTL, no quota, no authz on download.

**Impact:** Trivial remote DoS against a node; data leak of any guessed/leaked `chunk_id`.

**Plan:**

1. AuthN/AuthZ for local endpoints; capability tokens for P2P chunks.
2. Disk-backed encrypted blob store with TTL and per-user quotas.
3. Random 256-bit chunk IDs; single-download tokens.

---

### 5.2 High

#### R-06 — Pre-key bundle cryptographic validation incomplete

**Area:** Keys / Crypto
**Maps to:** I-04 residual
**Evidence:**

- No verification that `signed_prekey_sig` is a valid Ed25519 signature by `identity_key` over `signed_prekey`.
- No length/decoding checks on base64 key material (field descriptions claim sizes; code does not enforce).
- OPK pop is read-modify-write **without row locking** (`SELECT` then assign list without `WITH FOR UPDATE` / version column) → two concurrent fetches can consume the same OPK.
- Publish allows **bootstrap** binding of any onion to a user with `onion_address is None` (first writer wins account takeover of onion identity).

**Impact:** Key substitution, OPK double-spend, identity squatting on first login.

**Plan:**

1. Verify signatures with Rust/Python crypto before accept.
2. Enforce exact decoded lengths.
3. Atomic OPK consume in one SQL update with compare-and-swap or `json_each` + delete.
4. Onion binding only via controlled Tor identity issuance, not free-form client claim.

---

#### R-07 — Double Ratchet / session establishment correctness defects (web)

**Area:** Web Crypto
**Evidence (non-exhaustive):**

1. **Sequence number for API** uses `existing.length` in `sendMessage`, not the DR session’s `seqSend` — desync under deletes/reloads.
2. **Bob init** uses `identity.privateKey` as DH private for `initBob` — confuses long-term identity with ratchet DH key lifecycle; breaks if identity key type/purpose diverges.
3. **Alice/Bob role** via string compare of base64 public keys is unstable across encodings.
4. **HKDF chain step** uses empty IKM and chain key as salt — inverted vs common DR constructions; must be proven against the Python/Rust KAT or it is a interop bug.
5. **Skipped message keys** stored as hex in IndexedDB without encryption-at-rest beyond browser profile protection.
6. **No associated data** (AD) binding identity/session in AEAD.
7. Decrypt failures fall back to showing raw ciphertext objects in UI (`loadMessages` catch).

**Impact:** Interop failure, ratchet desync, silent plaintext UX confusion, weak transcript consistency.

**Plan:**

1. Align web DR with Rust KAT vectors; delete divergent TS crypto once bound to WASM.
2. Persist and send `session.seqSend`; never use UI list length.
3. Encrypt session state at rest with a key derived from user secret / device unlock.
4. Fail closed in UI on decrypt error (padlock + error), never render ciphertext as text.

---

#### R-08 — Contact API returns `shared_secret_b64` to the browser

**Area:** Privacy / Crypto hygiene
**Evidence:** `ContactResponse` includes `shared_secret_b64`; web `Contact` type expects it and DR init reads it from contact list.

**Impact:** XSS or extension compromise immediately yields all pairwise secrets. Even without XSS, local storage of long-term shared secrets in API responses expands the attack surface.

**Plan:** Keep shared secrets only in IndexedDB/keystore after handshake; never return them from REST after initial negotiation (or never store server-side at all for pure E2EE).

---

#### R-09 — Session and auth weaknesses on v3

**Area:** Auth
**Evidence:**

- Cookie sessions via Starlette `SessionMiddleware`; no explicit idle/absolute timeout config in app code.
- No CSRF token on FastAPI state-changing routes (relies on `SameSite=strict` + CORS regex). Acceptable for pure same-site SPA; fragile if any cross-site subdomain or non-browser client misconfiguration appears.
- Rate limit: **120 req/min/IP global**, not the configured `rate_limit_auth=10/minute`; in-memory only (useless multi-worker; resets on restart).
- Registration reveals username existence (`409`).
- Login normalizes username with `.lower()` but depends on registration lowercasing (OK) — ensure all paths consistent.
- `SECRET_KEY` default `CHANGE_ME_IN_PRODUCTION` blocked only when `ENVIRONMENT=production`; mis-set env still dangerous.
- FastAPI path does not use the Flask `security_headers` module → missing CSP/HSTS/COOP on v3 responses unless Caddy adds them (Caddyfile does not).

**Impact:** Session fixation/long-lived cookies, brute force easier than intended, XSS impact amplified without CSP, header gap vs legacy.

**Plan:**

1. Auth-specific limiter (Redis-backed in multi-instance).
2. Absolute + idle session expiry; rotate session on login.
3. Optional double-submit CSRF for defense in depth.
4. Uniform security headers middleware on FastAPI.
5. Generic auth errors; rate-limit registration.

---

#### R-10 — Message send lacks recipient policy / spam controls

**Area:** Messaging
**Evidence:** Authenticated user can `POST /v3/messages/` to **any** `recipient_onion` string; no contact requirement; server stores and attempts Tor delivery.

**Impact:** Outbound spam engine; storage growth; potential abuse of node as Tor traffic source.

**Plan:** Require accepted contact or pending first-contact policy; quotas; optional proof-of-work for first message.

---

#### R-11 — Group create injects arbitrary members without consent

**Area:** Groups / AuthZ
**Evidence:** `create_group` adds all `member_onions` as members with no invite/accept flow.

**Impact:** Victims appear in groups they never joined; metadata leak of social graph on multi-device sync later.

**Plan:** Invite/accept workflow; members added only after signed accept.

---

#### R-12 — Notifications token isolation incomplete

**Area:** Notifications
**Maps to:** I-14 residual
**Evidence:**

- Poll/clear accept arbitrary tokens; **no check** that tokens belong to `current_user`.
- Anyone who learns a token can poll presence of new mail (metadata) or clear it (DoS).
- `notify_contact` still uses legacy DB.

**Impact:** Cross-user metadata oracle if tokens leak; broken delivery if dual-DB.

**Plan:** Store tokens hashed, scoped to owner; authorize poll/clear; unify DB.

---

#### R-13 — Panic wipe / reset incomplete and oversold

**Area:** Local security
**Evidence:**

- Server obliviate: single-pass random overwrite (not multi-pass, not guaranteed on SSD/CoW/WAL siblings beyond listed suffixes).
- Client panic wipe deletes IndexedDB async without awaiting completion reliably before redirect.
- Does not clear service worker caches, HTTP cache, or Android keystore equivalents.
- `os._exit(0)` hard-kills without flushing other secrets in memory.
- iOS wipe is a print statement.

**Impact:** Coercion resistance claims are not met.

**Plan:** Document real guarantees; await all client deletions; clear SW caches; encrypt DB with key discarded on wipe; do not claim forensic-grade erase on flash storage.

---

#### R-14 — Hard-coded secrets and demo credentials

**Area:** Secrets
**Evidence:**

- Coturn: `anonymus:turnpassword` in compose.
- iOS unlock `1337`, duress `9999`.
- Developer badge public key hard-coded (expected) but badge verification is trivial to spoof if private key process is weak.
- Host-specific liboqs path: `C:/Users/Aryan/_oqs/...` in `pq_kem.py` (portability + environment coupling).

**Impact:** Trivial call interception on TURN; iOS is zero security; non-portable PQ loading.

**Plan:** Env-only secrets; remove demo passcodes; portable liboqs discovery.

---

#### R-15 — PBKDF2 parameters inadequate for DB key derivation

**Area:** Crypto
**Evidence:** `derive_db_key` uses **10,000** iterations and a **static salt** `salt_for_db_key_anonymus`.

**Impact:** Offline brute force of weak passwords is cheap; static salt enables precomputation across installs.

**Plan:** Argon2id (Rust already has argon2 module) with random per-DB salt stored beside ciphertext; ≥ OWASP parameters.

---

#### R-16 — Dual Socket.IO / proxy port mismatch

**Area:** Web / Realtime
**Evidence:** Vite proxies `/v3` → `5001` but `/socket.io` → `5000`. FastAPI mounts socket at `/socket.io` on the v3 app (5001). Legacy listens 5000.

**Impact:** Realtime receive path broken in default dev setup; racey dual servers if both run.

**Plan:** Single port; proxy both to the same upstream.

---

### 5.3 Medium

#### R-17 — User DTO contract still mismatched

**Area:** Web/API
**Maps to:** I-01 residual
**Evidence:** API `UserResponse` = `{username, onion_address?}`; client `User` expects `{id, username, onion_address, created_at}`. Login sets user from response; `id`/`created_at` undefined.

**Impact:** UI bugs, future features using `user.id` fail; TypeScript lies.

**Plan:** OpenAPI-generated client; align fields.

---

#### R-18 — Bootstrap identity key placeholder on contact add

**Area:** Contacts / Crypto
**Evidence:** If no pre-key bundle, handshake uses `public_key: "bootstrap_key_placeholder"`.

**Impact:** Peers may accept garbage keys; later DR fails or is attackable.

**Plan:** Block contact add until identity keys published.

---

#### R-19 — Invite system fails open to `pending.onion`

**Area:** Node
**Evidence:** `generate_invite` catches Tor errors and returns `pending.onion` or existing onion.

**Impact:** Users share non-functional invite links believing they work.

**Plan:** Return 503 with explicit error; never mint fake onions.

---

#### R-20 — Rate limiter and metrics cardinality

**Area:** Ops / Security
**Evidence:**

- In-memory limiter dictionary grows with unique IPs (slow memory leak under scan).
- Prometheus labels include full `path` → high cardinality on message IDs/onions if path params not normalized (currently raw `request.url.path`).

**Impact:** Memory growth; metrics explosion; weaker abuse defense.

**Plan:** Redis token bucket; normalize paths to route templates.

---

#### R-21 — Alembic failure is logged but startup continues

**Area:** Reliability
**Evidence:** `app_v3` lifespan catches migration errors, logs, and still serves traffic.

**Impact:** App runs against wrong/empty schema → cryptic 500s and partial writes.

**Plan:** Fail closed on migration failure in production.

---

#### R-22 — Legacy Flask CSP still phones home to CDNs/fonts

**Area:** Privacy
**Evidence:** `core/security_headers.py` allows `cdn.socket.io`, `cdnjs.cloudflare.com`, Google Fonts.

**Impact:** Metadata leak on legacy UI path; contradicts product privacy stance.

**Plan:** Self-host all assets; tighten CSP to `'self'` only.

---

#### R-23 — Android TOFU / hostname verification gaps

**Area:** Android
**Evidence:** Custom trust manager pins SPKI on first use (good TOFU) but `hostnameVerifier` allows `host`, `localhost`, `127.0.0.1` only when `trustSelfSigned` — still easy to misconfigure. PushService duplicates trust logic. Session cookie stored in prefs.

**Impact:** First-use MITM if attacker present at first connect; cookie theft if device compromised.

**Plan:** Prefer system CA + certificate pinning for known relays; warn loudly on TOFU first pin; encrypt prefs.

---

#### R-24 — CI still soft-fails important gates

**Area:** CI
**Maps to:** I-07 residual
**Evidence:**

- Codecov `fail_ci_if_error: false`
- Semgrep SARIF upload `continue-on-error: true` (scan itself may still fail the job — verify; upload masking hides GH code scanning integration failures)
- Web biome step previously given continue-on-error (commit message at HEAD)
- Docker wasm `|| true`
- Path filters may skip workflows on unrelated doc changes that still affect security narrative

**Impact:** Green badges without assurance.

**Plan:** Fail closed on SAST and wasm; only soft-fail truly flaky third parties with separate badges.

---

#### R-25 — Documentation still diverges from code

**Area:** Docs
**Maps to:** I-15
**Evidence:**

- README uses `file:///` links and references missing `docs/api/socket-io-events.md`.
- Setup guide still centers Flask secrets, Redis optional story, and incomplete v3 uvicorn instructions.
- Web README may still be template-like relative to real architecture.
- Audit readiness claims PBKDF2 10k and other specifics as if production-hardened.

**Impact:** Operators deploy insecurely; auditors get a false map.

**Plan:** Rewrite setup around one stack; link-check in CI; mark draft RFCs clearly.

---

#### R-26 — Group messaging incomplete vs claims

**Area:** Groups
**Evidence:** Send path exists; no list-history endpoint parity with DMs in the reviewed router surface; no MLS application to group ciphertext in the FastAPI path; members not cryptographically bound.

**Impact:** Groups are a shared ciphertext dump, not a secure group protocol.

**Plan:** Either implement MLS end-to-end or label groups experimental.

---

#### R-27 — `requests` blocking I/O in async app (mitigated by to_thread but fragile)

**Area:** Performance
**Evidence:** P2P transmit uses `requests` + `time.sleep` in worker threads; no connection pooling; retries up to 5 with exponential backoff can pile up under load.

**Impact:** Thread exhaustion; delayed event loop responsiveness if mis-awaited elsewhere.

**Plan:** Use `httpx` async with SOCKS; bounded task queue; circuit breaker.

---

#### R-28 — mDNS LAN discovery privacy

**Area:** Privacy
**Evidence:** Optional mDNS advertises onion in TXT properties on LAN; discovery endpoint returns peer list to any authenticated user.

**Impact:** Local network observers learn onion identities — often undesirable for a Tor messenger.

**Plan:** Default off (already env-gated); never put onion in cleartext TXT; document risk.

---

### 5.4 Low

#### R-29 — Duplicate `_get_current_user` helpers

Multiple routers reimplement session lookup instead of sharing `auth.get_current_user`. Drift risk (already: some 404 vs 401 on missing user).

#### R-30 — `MessageResponse` sealed_sender validator swallows JSON errors

Silent nulling of sealed metadata hides corruption.

#### R-31 — Logging may still include truncated onions

Useful for debug; still metadata. Ensure production redaction policy.

#### R-32 — `pyproject.toml` packages include `tests` in wheel

Shipping tests in the installable package is sloppy and increases attack surface of distributions.

#### R-33 — Detached HEAD / dirty tree in this worktree

Operational hazard for agents and humans committing from wrong ref.

#### R-34 — Placeholder / empty modules

Several `pass` handoffs, incomplete accept_invite, empty docs/api directory.

#### R-35 — TypeScript `sealed_sender?: any`

Loses type safety on a security-sensitive field.

#### R-36 — Android/iOS feature parity gap

Android is substantial; iOS is a shell. Product matrix should say so.

#### R-37 — Reproducible build attestation vs dirty inputs

Attestation JSON exists; wasm stub and soft-fail builds undermine reproducible secure client claims.

#### R-38 — Eventlet + asyncio dual worlds

Legacy eventlet and FastAPI asyncio coexistence is a footgun for shared libraries (dns, ssl, greening).

---

### 5.5 Info — incomplete roadmap (dangerous only if sold as done)

| Item | Location | Gate |
| --- | --- | --- |
| Full MLS group E2EE | `core/mls_groups.py`, Rust `mls.rs` | Interop eval |
| PQXDH in web | Rust FFI exists; web unused | Web integration + KAT |
| Multi-device sync productization | routers/sync, week25 tests | Threat model + UX |
| Desktop Tauri client | `packages/desktop-client` | Hardening review |
| External audit readiness | `docs/audits/audit_readiness.md` | Only after R-01–R-15 |

---

## 6. Vulnerability-oriented view (attacker stories)

| Attacker | Realistic path with current code | Severity |
| --- | --- | --- |
| Network attacker on first Android TOFU | Pin attacker cert | High |
| Authenticated local API user | Spam messages, fill file chunk memory via P2P upload if exposed, poll others’ notify tokens | High |
| Tor peer | Handshake spam, sealed message flood, unauthenticated file upload | High |
| Malicious contact | DR desync / implementation bugs; placeholder keys | Medium–High |
| XSS in web | Steal session cookie + IndexedDB identity keys + shared secrets from API | Critical (impact) |
| Operator misconfig | Default/weak SECRET_KEY, no WASM, TURN password defaults | Critical |
| Coercive seizure | Panic wipe incomplete on SSD; iOS fake wipe | High vs claims |
| Supply chain / CI greenwash | Soft-fail wasm/SAST → ship broken crypto | Critical |

---

## 7. Test & verification gaps

1. **No pytest in this audit environment** — remaining suite quality unverified here; CI is the source of truth but soft-fails remain.
2. **Contract tests** (`tests/integration/test_contract_v3.py`) exist — expand to every client field and negative authz cases.
3. **Schema drift tests** still legacy-centric; add Alembic↔ORM.
4. **No adversarial tests** for OPK double-consume, sealed resolve forgery, P2P spam.
5. **Web e2e** Playwright present; must run against real WASM, not stub.
6. **KAT** for DR must include web WASM and Python parity.
7. **Load tests** absent for rate limiter and chunk store.
8. **Mobile:** Android unit crypto tests exist; iOS none meaningful.

---

## 8. Remediation plan (ordered)

### Phase 0 — Stop the bleeding (1–3 days)

| ID | Action | Exit criteria |
| --- | --- | --- |
| P0.1 | Fail Docker/CI if WASM binary missing; remove `|| true` | Image build red without wasm |
| P0.2 | Disable or auth-gate P2P file upload and sealed flood storage | Unauth upload returns 401/403 |
| P0.3 | Remove Coturn hard-coded password; require env | Compose fails without secret |
| P0.4 | Fail app start if Alembic upgrade fails in production | Process exits non-zero |
| P0.5 | Block message send in UI when `isStub()` | No stub ciphertext leaves browser |
| P0.6 | Label iOS as non-production in README | No “iOS app” claim without caveat |

### Phase 1 — Make one stack true (1–2 weeks)

| ID | Action | Exit criteria |
| --- | --- | --- |
| P1.1 | Choose FastAPI v3 + single DB as authority | Docs + compose + CI only start that stack |
| P1.2 | Delete dual notify path; SQLAlchemy only | Restart + multi-user isolation tests pass |
| P1.3 | Alembic migration fully matches ORM | CRUD suite on migrated empty DB |
| P1.4 | OpenAPI → generated TS client | Hand-written `api.ts` types removed or generated |
| P1.5 | Fix Vite proxy + Caddy routes | Dev and prod realtime + REST work |

### Phase 2 — Crypto integrity (2–4 weeks)

| ID | Action | Exit criteria |
| --- | --- | --- |
| P2.1 | Real wasm-pack artifact in CI | Encrypt/decrypt KAT in browser CI |
| P2.2 | Verify pre-key signatures + atomic OPK | Concurrent fetch test: unique OPKs |
| P2.3 | Align DR with Rust KAT; fix seq handling | Cross-client message vectors pass |
| P2.4 | Stop returning shared secrets over REST | API schema without secrets |
| P2.5 | Argon2id + random salt for DB keys | Parameters documented + tested |
| P2.6 | Sealed-sender attribution redesign | Spec + tests for forge resistance |

### Phase 3 — AuthZ, abuse, privacy (2 weeks)

| ID | Action | Exit criteria |
| --- | --- | --- |
| P3.1 | Contact-gated messaging + group invites | Authz tests Alice/Bob/Eve |
| P3.2 | Redis rate limits; auth-specific | 11th login attempt → 429 |
| P3.3 | Security headers on FastAPI; CSP self-only | Header integration test |
| P3.4 | Notification token ownership | Eve cannot poll Alice token |
| P3.5 | File chunk tokens + TTL + quota | DoS test bounded |

### Phase 4 — Platform honesty & mobile (ongoing)

| ID | Action | Exit criteria |
| --- | --- | --- |
| P4.1 | Android pinning review + encrypted storage | Threat model doc signed off |
| P4.2 | iOS rebuild or remove from release matrix | Store listing matches reality |
| P4.3 | Transport switch: implement or remove | No success-on-failure |
| P4.4 | External audit package only after P0–P3 | Audit readiness checklist green |

---

## 9. Suggested ownership cut of the backlog

| Stream | Owns | First ticket |
| --- | --- | --- |
| Crypto | Rust core + web bindings | R-01, R-07, R-06 |
| Backend API | FastAPI routers + models | R-03, R-04, R-10, R-12 |
| Data | Alembic + engine | R-A02, R-A03, R-21 |
| Deploy | Compose/Caddy/CI | R-02, R-24, R-14 |
| Clients | Web/Android/iOS | R-17, R-16, R-23, R-36 |
| Docs | Truthfulness | R-25, R-A06 |

---

## 10. Explicit non-goals of this plan

- Designing new product features (channels, payments, etc.)
- Rewriting the entire system in one PR
- Claiming residual risk is zero after remediation (flash wipe, global passive Tor adversary, etc. remain out of scope as in the threat model)

---

## 11. Immediate next actions (operator)

1. Treat **current main/detached tip as non-releasable** for any “secure messenger” marketing.
2. Open tracking issues for **R-01 through R-16** at minimum.
3. Run locally (when toolchain available):
   ```bash
   # must fail today if honest
   test -f web/src/lib/pkg/anonymus_core_bg.wasm
   npm --prefix web run wasm:build
   npm --prefix web run build
   pytest tests/unit tests/integration -m "not legacy"
   docker compose config
   ```
4. Re-run this audit after Phase 0–1; expect Critical count to drop only when WASM + single DB + deploy topology are proven with evidence artifacts under `docs/audits/evidence/`.

---

## 12. Appendix A — File index of highest-risk code

| Path | Why |
| --- | --- |
| `web/src/lib/pkg/anonymus_core.js` | Throw-stub crypto entry |
| `web/src/lib/core.ts` | Insecure dev stub AEAD |
| `web/src/lib/crypto.ts` / `stores/messages.ts` | DR + send path |
| `transports/p2p/routers/keys.py` | Pre-key trust boundary |
| `transports/p2p/routers/messages.py` | Resolve sender / send |
| `transports/p2p/routers/p2p.py` | Unauthenticated ingress |
| `transports/p2p/routers/files.py` | Memory chunk DoS |
| `transports/p2p/routers/notifications.py` | Dual DB + token authz |
| `transports/p2p/app_v3.py` | Lifespan, CORS, limiter |
| `core/db/models.py` + `alembic/versions/*` | Schema authority |
| `transports/p2p/database.py` | Legacy parallel DB |
| `docker-compose.yml` / `Caddyfile.docker` | Deploy topology |
| `core/crypto.py` | Weak PBKDF2 |
| `core/pq_kem.py` | Host-specific paths, optional PQ |
| `core/transport_registry.py` | False-success mode switch |
| `ios/AnonyMusApp.swift` | Hard-coded passcodes |
| `android/.../ChatManager.kt` | TOFU TLS |

---

## 13. Appendix B — Scoreboard (approximate)

| Category | Critical | High | Medium | Low | Info |
| --- | --- | --- | --- | --- | --- |
| Architecture | 3 | 2 | 0 | 1 | 1 |
| Crypto/E2EE | 2 | 4 | 1 | 0 | 2 |
| AuthZ/AuthN | 1 | 3 | 2 | 1 | 0 |
| Deploy/CI/Ops | 1 | 1 | 3 | 2 | 0 |
| Clients | 0 | 1 | 3 | 2 | 1 |
| Docs/Claims | 0 | 1 | 1 | 1 | 1 |
| **Total (unique R-*)** | **~5** | **~11** | **~12** | **~10** | **~5** |

Counts are approximate because some IDs span categories; use the catalog, not the scoreboard, for work tracking.

---

## 14. Verdict

**Confidence: high.**
AnonyMus has substantial scaffolding and several real fixes since 2026-07-12, but it remains a **migration-in-progress with critical crypto packaging, dual-state, and abuse-surface defects**. Shipping this as a privacy-preserving messenger without Phase 0–2 would be irresponsible relative to the claims in README, RFCs, and audit-readiness docs.

The correct engineering posture: **one stack, real WASM, verified DR KATs, authenticated P2P, single DB, fail-closed deploy** — then invite external audit.
