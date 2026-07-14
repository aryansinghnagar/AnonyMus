# Current-State Remediation Plan

This plan resolves the issues in
[the companion issue log](2026-07-12-current-state-issue-log.md). It chooses a
single migration-safe approach per issue and intentionally keeps planned
features separate from immediate defect repair.

## Governing decisions

1. **Do not deploy the v3 web client or FastAPI APIs yet.** The active migration
   has critical API, schema, and deployment incompatibilities.
2. **Choose FastAPI v3 as the new API authority, but retain the Flask path only
   as an explicitly supported legacy surface during a bounded transition.** Do
   not make one browser client straddle both API generations.
3. **Use OpenAPI-generated TypeScript types/client as the v3 contract source of
   truth.** Hand-written duplicate request/response interfaces caused I-01.
4. **Use Alembic only for v3 schema creation and upgrades.** Remove v3 runtime
   `create_all()` once migration bootstrap is in place.
5. **Treat privacy properties as release requirements.** No plaintext fallback,
   third-party fonts, or authenticated PWA response caching in release builds.

## Priority 0 — stop unsafe release paths

### R-01 — Freeze and test the v3 HTTP contract

**Resolves:** I-01, I-13, and part of I-14.

1. Write a versioned OpenAPI contract test for auth, contacts, messages, groups,
   node, keys, and notifications. Run it against `create_app()` using a fresh
   temporary database.
2. Generate the web client/types from `/v3/openapi.json`, or maintain a single
   checked-in schema file generated from the Pydantic models. Do not manually
   duplicate payload types.
3. Make one explicit API decision for each mismatch:
   - Login: return the `User` object directly and type the web client as `User`.
   - Contacts: expose `id` only if deletion is ID-based; otherwise change the UI
     to store/delete `onion_address`. Prefer **onion-address deletion** because
     `(owner_onion, onion_address)` is the domain identity.
   - Messages: retain REST nouns consistently, e.g. `POST /messages`,
     `GET /messages/{peer_onion}`, and `DELETE /messages/{message_id}`, or
     update every client call to the already chosen `/send` and `/history` form.
     Pick one and remove the other before release.
   - Use `disappears_in_seconds` for requests; expose `disappears_at` in the
     response.
   - Include all UI-required fields in the response schema, or remove those
     fields from the UI model.
4. Add browser-independent tests for register -> login -> contacts CRUD -> send
   -> history -> delete -> paginated history. These tests must fail on a 404,
   unexpected response shape, or missing field.

**Acceptance evidence:** generated client is unchanged after OpenAPI generation;
the contract suite passes and includes the above complete user flow.

### R-02 — Replace the broken Compose topology with one deployable v3 stack

**Resolves:** I-02, I-08, I-15.

Choose one supported deployment for v3:

- a FastAPI/ASGI service (`uvicorn` or `granian`) listening on a single named
  `PORT=5001`;
- an explicit static-web build service (or Caddy static file mount) that routes
  `/v3/*` to the ASGI service and serves the SPA fallback;
- Caddy receives `RELAY_DOMAIN` in its own `environment:` block;
- health checks use a real endpoint, preferably `/healthz`, on the same port
  Caddy proxies;
- Docker declares `ENVIRONMENT=production`, `SECRET_KEY`, and `DATABASE_URL`.

Use a small image built from a Dockerfile, with dependencies installed at image
build time from a single lock file. Do not run `pip install` at every container
startup. Keep the legacy Compose file only if it is renamed and documented as a
separate legacy deployment.

Add a CI smoke test that executes `docker compose config`, boots the compose
profile, waits for health, verifies Caddy -> `/healthz`, and verifies the SPA
can fetch one v3 health/API route.

**Acceptance evidence:** compose starts without manual environment patching;
all three paths (container health, Caddy proxy, web bundle) return expected
responses.

### R-03 — Establish a single v3 schema authority

**Resolves:** I-03.

1. Generate an Alembic revision from the current ORM model and manually review
   it. Do not edit the existing applied `0001` revision on an environment that
   may already contain it; add a forward migration to reconcile it.
2. Decide whether `messages.id` is required. Prefer one stable primary key:
   retain UUID `message_id` as the primary key and remove the unused integer
   `id`, or introduce the integer key through a carefully tested migration.
3. Add every required model column/index/foreign key to the Alembic history,
   including `last_seen` and contact key fields if they remain part of v3.
4. Replace `Base.metadata.create_all()` in production lifespan with
   `alembic upgrade head` as a deployment/init step. `create_all()` may remain
   only in isolated tests.
5. Replace the legacy-only schema drift test with a v3 migration test that
   upgrades an empty DB to head and runs a representative ORM CRUD flow.

**Acceptance evidence:** a fresh Alembic database supports the full v3 contract
suite; upgrading a prior fixture database preserves rows and reaches head.

### R-04 — Block unsafe privacy behaviors in release builds

**Resolves:** I-06, I-11, and the release implication of planned web crypto.

1. Delete runtime caching for `/v3/` entirely. Cache only immutable static
   assets. If offline metadata is later required, encrypt it per identity and
   clear it on logout through an explicitly designed local storage policy.
2. Self-host Inter/JetBrains Mono (or use system fonts) and remove all Google
   Fonts preconnect/style links.
3. Make the web build fail when the WASM core is absent in production. A
   development-only mock may exist only behind an explicit dev flag and must
   visibly label the UI as insecure.
4. Keep message sending disabled until an established/loaded ratchet session
   encrypts and authenticates the payload. Never represent base64 plaintext as
   ciphertext outside a local development fixture.

**Acceptance evidence:** service-worker manifest has no API runtime cache;
network tests show no third-party font requests; production build fails without
the core and no message can leave the client in plaintext.

## Priority 1 — repair security and correctness boundaries

### R-05 — Make pre-key storage authenticated, durable, and atomic

**Resolves:** I-04.

1. Create durable tables keyed by the authenticated user's immutable ID/onion
   identity. Bind `publish`, `rotate`, and `me` to that identity; remove the
   caller-controlled owner field or reject mismatches.
2. Verify base64url encoding, exact key lengths, and Ed25519 signatures before
   accepting a bundle. Record key IDs and publication/rotation timestamps.
3. Fetch-and-consume an OPK in one database transaction with row locking or a
   conditional update. Return depletion state without exposing an unrelated
   bundle.
4. Add authorization tests with Alice/Bob/Eve proving Eve cannot publish,
   rotate, read, or consume Alice's data except through the intended public
   peer-bundle retrieval path.
5. Do not expose this endpoint to production clients until the ratchet/X3DH
   integration uses this durable protocol state.

**Acceptance evidence:** ownership, validation, multi-worker, restart, and
concurrent OPK-consumption tests pass.

### R-06 — Enforce group membership and validate direct-message recipients

**Resolves:** I-05 and hardens messaging.

1. Add a membership existence check before every group read/write. For a
   channel, require both membership (if channels require it) and founder/editor
   authorization based on a defined role model.
2. Validate direct-message recipients against the authenticated user's contact
   relation, unless the product deliberately supports first-contact messages.
   If it does, define a pending-contact state rather than silently accepting any
   onion string.
3. Add authorization tests for nonmember normal groups, channel members,
   founders, and unrelated users.

**Acceptance evidence:** all unauthorized writes return 403 and create no row.

### R-07 — Persist node settings and notifications per account

**Resolves:** I-14.

1. Add tables for account/node configuration and notification registrations;
   include owner identity, token hash (not raw token if practical), creation,
   expiry, and revocation metadata.
2. Scope every read/write by `current_user`. Never search a global dictionary
   for "my" state.
3. Integrate notification enqueueing with verified message-delivery events, not
   merely an in-process helper. Define restart, retry, cleanup, and multi-worker
   behavior.
4. Leave invites explicitly unavailable (501/feature flag) until Tor and X3DH
   are truly implemented; do not issue `pending.onion` as an apparently valid
   invite.

**Acceptance evidence:** restart and two-user isolation tests pass; disabled
invites are unambiguous to API consumers.

### R-08 — Implement rate limiting and explicit CSRF/origin posture for v3

**Resolves:** I-10 and closes a transition gap.

1. Add an ASGI-compatible limiter backed by durable/shared storage for auth
   endpoints. Use the already defined auth/default limits only after wiring
   them into middleware/decorators.
2. Decide on same-origin deployment as the default. Enforce an explicit
   allow-list for development origins; do not use wildcard-looking host strings
   such as `http://localhost:*` as a policy.
3. For cookie-authenticated state-changing routes, use CSRF tokens or strict
   origin validation in addition to `SameSite=Strict`.
4. Add tests for rate-limit exhaustion, CORS preflight/origin rejection, and
   CSRF/origin rejection.

**Acceptance evidence:** automated tests show the 11th configured auth request
is rejected and cross-origin state changes cannot execute.

### R-09 — Make mode switching fail closed or remove it from production

**Resolves:** I-09.

The best short-term approach is to make transport mode **startup-only** in
production and return 403/501 for runtime switching. It avoids pretending a
stateful migration is atomic when it is not.

If runtime switching remains a product requirement later, implement a durable
state-machine workflow: validate target readiness, checkpoint state, transfer
state, stop old transport, verify stop, commit the new active mode, and roll
back the target on failure. Never change `_active_mode` after a caught
handoff/stop exception.

**Acceptance evidence:** production rejects runtime switches, or a failure
injection suite proves no success response is returned while both transports
are active or state is lost.

## Priority 2 — make verification and delivery trustworthy

### R-10 — Replace permissive CI with enforceable gates

**Resolves:** I-07, I-12, I-15.

1. Remove `|| true` from tests and Semgrep. If a legacy suite is intentionally
   unsupported, mark/select those tests explicitly and track removal or repair
   in a dated issue; do not hide failures.
2. Make web CI first build/restore the WASM package, then run TypeScript,
   Biome, Vitest, and production build. Alternatively commit a typed generated
   module interface and make the build explicitly choose development mock versus
   release WASM.
3. Add a test that every PWA manifest/include asset exists. Add generated-client
   freshness checks and OpenAPI contract tests.
4. Separate legacy and v3 jobs, publish their exact test selection and coverage,
   and make each required job blocking.

**Acceptance evidence:** CI cannot pass when a selected test, lint/type check,
SAST rule, route contract, or required generated artifact fails.

### R-11 — Consolidate dependencies and settings

**Resolves:** I-08.

1. Put v3 runtime dependencies in `[project.dependencies]` or compile one
   authoritative `requirements-v3.txt` from `requirements-v3.in`; pin and use
   that same set in local setup, CI, and Docker.
2. Keep legacy dependencies in a separate explicitly named legacy lock file.
3. Standardize variable names: use `SECRET_KEY`, `PORT`, `ENVIRONMENT`, and
   `DATABASE_URL` for v3, or explicitly map legacy names during the transition.
   Fail startup in production for missing/known-default secrets regardless of
   which variable name was used.
4. Ensure `pip install .` succeeds for the selected supported surface, or stop
   presenting it as installable packaging until it does.

**Acceptance evidence:** a clean virtual environment, CI, and Docker all
install the same resolved dependency set and boot with the same documented
environment file.

### R-12 — Rewrite the operator and developer documentation from executable facts

**Resolves:** I-15.

1. Replace `file:///` links with repository-relative links and restore/create
   the claimed API document only if it is maintained.
2. Declare which deployment is current: legacy Flask, v3 ASGI, or both. Give
   only tested commands, port names, health routes, and required variables.
3. Replace the stock web README with development, test, secure-build, and
   deployment instructions.
4. Add CI link checking and a docs smoke-test that runs every documented setup
   command in a disposable environment where feasible.

**Acceptance evidence:** a new developer can follow the docs from a clean clone
to a healthy service and web UI without undocumented substitutions.

## Suggested execution order

1. R-02 (deployment) and R-11 (environment/dependencies) establish a runnable
   v3 baseline.
2. R-03 (schema) before writing any integration data.
3. R-01 (contract) before continuing frontend work.
4. R-04, R-05, R-06, R-07, and R-08 before exposing privacy/security-sensitive
   routes.
5. R-10 and R-12 turn the repaired behavior into a repeatable release gate.
6. Resume intentionally planned capabilities only after these gates pass.

## Deferred roadmap work and its correct acceptance bar

These are not defect fixes, but must be complete before a production
privacy-messenger release:

- **Web ratchet encryption:** test vectors shared with the Rust core, ratchet
  state persistence, replay/out-of-order handling, and no plaintext fallback.
- **Tor invite/X3DH:** real hidden-service lifecycle, authenticated invite
  protocol, expiry/revocation, and integration tests under Tor.
- **Notifications:** durable queue/outbox, idempotent delivery, restart/multiple
  worker behavior, and no message content in notifications.
- **iOS:** a real build/test job only after the client exists; until then the CI
  job should be removed or clearly non-required.

## Exit criteria for a v3 release candidate

- Fresh install and documented Compose deployment succeed.
- Alembic upgrade reaches head and v3 CRUD/contract tests pass.
- Generated client and OpenAPI contract are in sync.
- No authenticated API responses are service-worker cached; no third-party font
  request is made.
- Pre-key/group/node authorization tests include adversarial multi-user cases.
- All required CI jobs are blocking and green without ignored failures.
- The release configuration cannot send a plaintext message or boot with a
  default session secret.
