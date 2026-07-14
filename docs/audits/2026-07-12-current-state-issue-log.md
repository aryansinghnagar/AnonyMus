# Current-State Issue Log

**Audit date:** 2026-07-12
**Repository snapshot:** dirty working tree; the uncommitted Solid/Vite client and
FastAPI router changes were included. Legacy Flask assets removed from the working
tree were treated as a migration, not as a defect by themselves.

## Scope and method

This is a source, configuration, and test-harness audit of the active
`AnonyMus` repository. It covers the Python/FastAPI and Flask paths, the new web
client, Docker/CI, Rust integration boundaries, and the shipped documentation.

Evidence collected:

- All 40 Python source files parsed successfully with `ast.parse`.
- Test execution was **not possible locally** because this runtime lacks
  `pytest`, `ruff`, and `pyright`; Node cannot resolve the OneDrive workspace
  through the sandbox, and Cargo cannot create its build lock. These are audit
  environment constraints, not application findings.
- Source-level route, response, configuration, migration, and deployment
  contracts were cross-checked directly.

Severity expresses the impact if the affected path is used or deployed. It does
not imply a planned feature should already exist.

## Verified defects and operational problems

| ID | Severity | Area | Finding |
| --- | --- | --- | --- |
| I-01 | Critical | Web/API | The web client and FastAPI API contract disagree on login, contacts, and messages. The migrated UI cannot complete normal chat operations. |
| I-02 | Critical | Deployment | The primary Docker Compose relay is internally inconsistent: it starts/probes/proxies different ports and paths, and does not serve the new web client. |
| I-03 | Critical | Data | The Alembic schema and ORM schema are incompatible; an Alembic-created database will not satisfy the v3 ORM. |
| I-04 | High | Cryptography | Pre-key APIs permit cross-user bundle replacement and disclosure; one-time keys are held only in process memory. |
| I-05 | High | Authorization | Any authenticated user who knows a non-channel group ID can post to that group without being a member. |
| I-06 | High | Privacy | The PWA caches authenticated `/v3/` GET responses in a shared service-worker cache. |
| I-07 | High | CI | The Python workflow deliberately masks all legacy test failures. |
| I-08 | High | Packaging/config | Python dependency and runtime configuration sources are split and incompatible with the v3 service. |
| I-09 | High | Migration | Runtime mode switching reports success after a failed stop/handoff and both adapters implement no handoff. |
| I-10 | Medium | Security | v3 authentication has no implemented rate limiter despite rate-limit settings being defined. |
| I-11 | Medium | Privacy | The browser shell makes direct Google Fonts requests, contradicting the metadata-resistant/Tor privacy claim. |
| I-12 | Medium | Web build | The web build relies on a missing generated WASM module and missing PWA logo assets. CI makes WASM generation non-blocking. |
| I-13 | Medium | API | History pagination accepts `before_id` but never applies it; callers cannot advance beyond the newest page. |
| I-14 | Medium | Persistence | Node settings and notification registrations are global, in-memory state; they are lost on restart and are not isolated per user. |
| I-15 | Medium | Documentation | Setup, self-hosting, README, and reproducible-build claims describe divergent or missing interfaces and files. |

### I-01 — Web/API contract mismatch

**Evidence**

- The FastAPI login handler returns a `UserResponse`; the web client declares
  `{ success, user }` and `session.login()` reads `res.user`.
  See `transports/p2p/routers/auth.py:109-133`,
  `web/src/lib/api.ts:94-98`, and `web/src/stores/session.ts:28-33`.
- Contacts returned by the API contain only `onion_address`, `nickname`, and
  `verified`, while the client requires `id`, `owner_onion`, and `added_at`.
  The client deletes `/contacts/{id}`, but the server deletes by onion address.
  See `routers/contacts.py:45-50,107-128` and `web/src/lib/api.ts:19-26,107-118`.
- The server exposes `POST /v3/messages/send` and
  `GET /v3/messages/history/{peer_onion}`. The client calls `POST
  /v3/messages/` and `GET /v3/messages/{onion}`. It sends `disappears_at`,
  while the server accepts `disappears_in_seconds`. Server responses omit the
  client-required `is_deleted` and `disappears_at` fields.
  See `routers/messages.py:43-71,115-146` and `web/src/lib/api.ts:28-38,122-147`.

**Impact:** login leaves the UI user state undefined; contact deletion and
message history/send requests return 404 or use incompatible payloads. This is
not an unfinished feature: both sides claim to implement the same released v3
surface.

### I-02 — Docker relay cannot satisfy its own topology

**Evidence**

- Compose supplies `RELAY_PORT=5001`, exposes 5001, and health-checks
  `http://localhost:5001/health` (`docker-compose.yml:10-16,30-44`).
- `server.py` only reads `PORT`, defaults to 5000, and exposes
  `/api/health`, not `/health` (`server.py:58-63,81-89,151-153`).
- Caddy proxies `relay:5001`, but the process listens on 5000
  (`Caddyfile.docker:1-6`).
- `RELAY_DOMAIN` is set only on the relay container, while Caddy expands the
  variable in its own container and has no matching environment declaration.
- The Compose stack starts `server.py` (the legacy WSGI dispatcher), whereas
  the new UI is written for FastAPI `/v3`; it contains no static web service or
  web build output.

**Impact:** the relay health check fails, Caddy cannot reach the upstream, and
the new web client has no deployable backend/frontend route in the documented
stack.

### I-03 — Alembic and ORM schemas drift

**Evidence**

- The `Message` ORM has integer `id` plus unique `message_id`; migration 0001
  makes `message_id` the primary key and has no `id` column.
- The ORM declares `User.last_seen` and contact key/secret columns that
  migration 0001 does not create.
- Startup uses `Base.metadata.create_all()` rather than Alembic. `create_all`
  never alters an existing Alembic-created table.

Relevant files: `core/db/models.py`, `alembic/versions/0001_initial_schema.py`,
and `transports/p2p/app_v3.py:55-68`. The existing schema-drift test compares
only legacy SQL migrations to legacy schema snapshots; it does not cover the
ORM/Alembic contract (`tests/unit/test_schema_drift.py`).

**Impact:** a database created through the committed Alembic path can fail at
ORM reads/inserts, and two incompatible migration authorities exist.

### I-04 — Pre-key API does not enforce ownership or durability

**Evidence**

- Any authenticated user can publish or rotate a bundle for any syntactically
  valid onion address (`routers/keys.py:88-108,115-133`).
- `/keys/me` returns the first dictionary entry, not the requesting user's
  bundle (`routers/keys.py:141-159`).
- All bundles and one-time pre-keys live in a module-level dictionary. They are
  lost on restart and do not work across workers (`routers/keys.py:30-33`).

**Impact:** an authenticated attacker can replace a target's published keys,
and a user can receive another user's key material from `/keys/me`. This route
must not be exposed as a usable pre-key service before ownership binding,
signature validation, durable storage, and transactional consumption exist.

### I-05 — Group posting lacks membership authorization

**Evidence:** `send_group_message()` verifies only that the group exists. It
checks founder-only posting for channels but never verifies a `GroupMember`
record for normal groups (`routers/groups.py:145-177`).

**Impact:** any logged-in user who learns a group UUID can inject ciphertext
into that group's history. The endpoint's summary promises a group message,
so this is an authorization defect rather than missing group delivery work.

### I-06 — PWA cache can retain authenticated private responses

**Evidence:** `web/vite.config.ts:25-33` configures a `NetworkFirst` runtime
cache for every `/v3/` URL. API calls carry session cookies
(`web/src/lib/api.ts:68-82`). Workbox cache keys do not include the user's
cookie, so cached GET responses such as `/v3/auth/me`, contacts, message
history, node information, and key bundles can be replayed when offline after
logout or to a later user of the same browser profile.

**Impact:** local disclosure of account/contact/message metadata. Do not cache
authenticated API data in the service worker.

### I-07 — CI is configured to accept failing tests

**Evidence:** the legacy test command ends with `|| true`
(`.github/workflows/python.yml:73-77`). The Semgrep workflow likewise masks
scanner failure (`.github/workflows/semgrep.yml:24-27`).

**Impact:** a green workflow does not establish that the legacy suite or SAST
scan passed; regression detection is materially weakened.

### I-08 — v3 dependency and configuration contract is fragmented

**Evidence**

- `pyproject.toml` declares no runtime dependencies (`pyproject.toml:1-23`).
- `requirements.txt` is a lock for legacy Flask dependencies. The v3 stack is
  only an uncompiled `requirements-v3.in`; CI manually installs a different,
  incomplete package list (`.github/workflows/python.yml:42-62`).
- The documented Compose environment supplies `FLASK_SECRET_KEY`, while the
  v3 `Settings.secret_key` reads `SECRET_KEY`; Compose also omits
  `ENVIRONMENT`, `DATABASE_URL`, and v3 dependencies.
  See `docker-compose.yml:10-16` and `core/config.py:29-43`.

**Impact:** `pip install .` does not produce an executable application; local,
CI, and Docker environments can resolve different dependency sets. A FastAPI
deployment based on Compose would sign sessions with the v3 default secret and
remain in development-mode cookie settings unless separately configured.

### I-09 — Runtime transport switching is not atomic or state-preserving

**Evidence**

- The registry starts the target, catches an exception from old transport
  handoff/stop, then still changes the active mode and returns success
  (`core/transport_registry.py:20-48`).
- Both `handoff()` methods are `pass`
  (`transports/p2p/adapter.py:37-39`, `transports/relay/adapter.py:56-58`).

**Impact:** the control endpoint can report a successful transport migration
while the former transport did not stop or state was discarded. It is unsafe to
advertise this as graceful switching.

### I-10 — v3 auth rate limiting is configured but absent

**Evidence:** `core/config.py` defines `rate_limit_default` and
`rate_limit_auth`, but `app_v3.py` and the v3 routers apply no limiter.

**Impact:** v3 register/login can be brute-forced or used for account
enumeration more readily than the legacy Flask path.

### I-11 — External font requests leak metadata

**Evidence:** `web/index.html:17-20` preconnects to and loads CSS/fonts from
`fonts.googleapis.com` and `fonts.gstatic.com`.

**Impact:** opening the client reveals timing and IP/Tor-exit metadata to a
third party, contrary to the product's stated privacy properties.

### I-12 — Web build inputs and PWA assets are missing

**Evidence**

- `web/src/lib/core.ts` statically references
  `./pkg/anonymus_core.js`, which is absent from the tree.
- The web CI makes `wasm-pack` failure non-blocking, but performs a TypeScript
  check before the build job generates that package.
- `vite.config.ts` references `logo.png`, `logo-192.png`, and `logo-512.png`;
  `web/public/` only contains `favicon.svg` and `icons.svg`.

**Impact:** type/build reproducibility depends on an untracked generated module
and PWA icon URLs resolve to missing resources. The exact web commands could
not be run in this sandbox because Node cannot traverse the OneDrive root.

### I-13 — Message pagination is advertised but nonfunctional

**Evidence:** `message_history()` accepts `before_id` but never uses it in its
SQL statement (`routers/messages.py:120-146`). The client also calls the
different query name `before` (`web/src/lib/api.ts:123-126`).

**Impact:** older history cannot be loaded reliably and repeated requests return
the newest page.

### I-14 — Node and notification state is non-durable and non-isolated

**Evidence:** `routers/node.py` uses one module-global `_config` dictionary;
`routers/notifications.py` uses module-global token dictionaries. Neither is
stored in the database nor keyed to `current_user`.

**Impact:** settings/tokens vanish on restart, diverge between workers, and one
account can change the relay setting observed by another account. This is a
functional defect even if the eventual durable implementation is planned.

### I-15 — Documentation has false or broken operational guidance

**Evidence**

- `README.md` links to the nonexistent `docs/api/socket-io-events.md` using a
  local `file:///` URL.
- `docs/guides/setup.md` documents a different build Compose stack and port
  than the root Compose file; its Docker description says PostgreSQL while the
  root stack defines Redis but no PostgreSQL service.
- `docs/guides/self-hosting.md` tells users `RELAY_PORT=5001` is the listener
  even though `server.py` reads `PORT`.
- The v3 web README remains the stock Solid template and omits backend/API,
  privacy, testing, and deployment requirements.

**Impact:** a new operator cannot reproducibly install or validate the system
from the committed documentation.

## Deliberately incomplete roadmap work — not recorded as defects

The following items are acknowledged as incomplete by the source and are **not
counted as bugs solely for being unbuilt**. They remain release gates if the
application is advertised as production-ready:

- Real Double Ratchet/WASM encryption in the web send path
  (`web/src/stores/messages.ts:42-65`). The present base64 "ciphertext" must
  be restricted to development and never shipped for private messaging.
- Tor invite creation/acceptance and X3DH execution (`routers/node.py`).
- Durable notification fan-out and delivery integration.
- iOS implementation/validation; CI explicitly labels it a placeholder.
- Stable Rust WASM FFI build, provided it is consistently gated before web
  release rather than silently bypassed.

## Existing working-tree risk

The current checkout contains modified backend routers, deleted legacy web
assets, and untracked v3 frontend/router files. Treat these as one atomic
migration branch. Do not deploy or partially commit them independently; the
current interface contracts already demonstrate that they are not integrated.
