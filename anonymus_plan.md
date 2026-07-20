# AnonyMus — Commercial Release Master Plan

> **Status:** Planning document only. No implementation has been performed.
> **Author:** Cross-domain master software critic & improvement lead.
> **Source repo:** `https://github.com/aryansinghnagar/AnonyMus`
> **Audience:** Maintainers, security engineers, release managers, CI/ops.
> **Reading order:** This document is intentionally long. Read sections in order — later sections depend on decisions made earlier. Section 0 is the executive summary; Section 22 is the consolidated risk register; Section 25 is the unified branch-merge strategy.

---

## 0. Executive Summary

AnonyMus is a metadata-resistant, Tor-aware, post-quantum-aware encrypted messenger that, at the time of audit, is **not ready for commercial release**. It has the bones of an ambitious, defensible product — a FastAPI v3 backend, a Rust core with MLS/X3DH/double-ratchet/padding/sealed-sender protocols, a SolidJS + Vite web client, a Tauri desktop wrapper, a Kotlin Android app, a Swift iOS shell, an Alembic migration tree, fourteen GitHub Actions workflows, and a documented self-hosting path. None of those layers is currently trustworthy enough to ship as a paid or public commercial product.

Three categories of defect dominate the audit findings:

1. **Critical correctness defects.** The web client and the v3 backend disagree on the API contract (login shape, contact fields, message endpoints, pagination). The Docker relay stack is internally inconsistent (it probes `/healthz` on a process that serves `/api/health`, proxies the wrong port, references `FLASK_SECRET_KEY` while the v3 stack reads `SECRET_KEY`, and serves a web bundle that depends on a non-generated WASM module). The Alembic 0001 migration does not match the ORM model that the v3 routers use. The pre-key API does not enforce ownership, and group posting has no membership check. Each of these is a release blocker on its own; together they mean the system cannot currently pass a single happy-path end-to-end flow.

2. **CI is structurally non-functional.** 10 of the 14 workflows have corrupted YAML triggers (`branches: ain]` — the literal string `ain]` where `[main]` was intended, almost certainly the result of a bad mass-replace that ate the opening bracket). The remaining workflows run but several are non-blocking by design (`|| true` on the legacy Python suite, `continue-on-error: true` on the WASM build step), which means a green checkmark is currently evidence of nothing. Dependabot branches are piling up without merging. The reproducible-build workflow pins a Docker image digest that no longer exists on Docker Hub and is structurally incapable of producing bit-identical images even when the digest exists, because `docker save` of a layer-cached image is not reproducible.

3. **Branch fragmentation.** The repo has 22 remote branches — one active `main`, five historical tags that look like branches (`archive/backup-central`, `archive/backup-p2p`, `pre-migration-checkpoint`), and 16 Dependabot branches that mostly conflict with each other and with `main`. There is no `dev`, no `release/*`, no per-platform release branch, and no documented policy for what belongs on `main`. Releases are tagged on `main` directly with no release-candidate verification gate.

The plan that follows addresses all three categories with concrete, sequenced, verifiable work. It also adds a fourth dimension that the existing planning docs underweight: **adaptive performance for heterogeneous hardware**. AnonyMus targets both low-spec Android devices and high-spec desktops; the current code makes no provision for runtime capability detection. The plan introduces a **Capability Tier** mechanism (L0–L3) that automatically disables expensive features (WebRTC SFU, WASM-MLS group crypto, mDNS background scanning, structured-log fan-out) on devices that cannot sustain them, with a single in-process registry that every layer reads from.

The total scope is large — 12 workstreams, ~90 numbered tasks, 4 capability tiers, 9 release gates, and a 7-step branch consolidation. It is sequenced so that the first three milestones (CI unfreeze, deployment unification, contract freeze) deliver a system that can be **demonstrated end-to-end** in under three engineering weeks of focused work, after which the security hardening, performance adaptation, and branch unification can proceed in parallel tracks.

The plan does not romanticize the work. Several sections name files and line numbers, several name the exact test that must pass before a task is considered done, and several explicitly call out the consequences of doing the work in the wrong order. The plan is designed to be executed; it is not a vision document.

---

## 1. Audit Method, Evidence Base, and Scope

### 1.1 Method

This plan is built on a static + dynamic audit of the public `main` branch at the `v3.0.0-alpha.1` tag (`b3d9609`), cross-referenced with the historical audit documents the repository itself contains:

- `docs/audits/2026-07-12-current-state-issue-log.md` (276 lines) — the prior issue log.
- `docs/audits/2026-07-12-remediation-plan.md` (308 lines) — the prior remediation plan.
- `docs/historical/ci-failure-analysis-2026-07.md` (1,648 lines) — prior CI failure analysis.
- `docs/historical/ci-recovery-plan-2026-07.md` (4,434 lines) — prior CI recovery plan.
- `docs/historical/production-plan-2026-07.md` (3,044 lines) — prior production plan.
- `docs/historical/github-log-2026-07.md` (1,279 lines) — prior GitHub-run log digest.
- `FINISHING_TOUCHES_PLAN.md` (277 lines).
- `prod_plan.md` (198 lines).

The prior audits are thorough on **what** is broken; this plan complements them by adding (a) the YAML-corruption root cause that the prior audits missed, (b) the branch-unification strategy that no prior document addresses, (c) the adaptive-performance tier system that no prior document addresses, and (d) a single consolidated commercial-release exit gate.

### 1.2 Evidence source

All findings cite paths under `/home/z/my-project/anonymus-analysis/work/` — a fresh clone of `https://github.com/aryansinghnagar/AnonyMus`. Line numbers refer to that snapshot. Where a finding is reproduced from the prior audit (`docs/audits/2026-07-12-current-state-issue-log.md`), the prior audit's issue ID (e.g. **I-04**) is cited so the maintainer can cross-walk.

### 1.3 Scope

**In scope:**

- Python backend (`server.py`, `transports/p2p/**`, `transports/relay/**`, `core/**`).
- Rust core (`core/rust/**`, including all FFI targets: `python`, `wasm`, `android`, `swift`).
- Web client (`web/**`, Vite + SolidJS).
- Tauri desktop wrapper (`packages/desktop-client/**`).
- TypeScript SDK (`packages/typescript-sdk/**`).
- Android app (`android/**`, Kotlin + Gradle).
- iOS shell (`ios/**`, Swift).
- CI/CD (`.github/workflows/**`, `scripts/ci-preflight.sh`).
- Deployment (`Dockerfile.relay`, `docker-compose.yml`, `Caddyfile.docker`, `torrc.docker`).
- Documentation (`docs/**`, `README.md`, `FINISHING_TOUCHES_PLAN.md`, `prod_plan.md`).
- Branch topology (22 remote branches including 16 Dependabot branches).

**Out of scope for this plan (handled in later phases):**

- App-store submission policies (Google Play, Apple App Store, F-Droid).
- Legal review of AGPL-3.0 compatibility with the planned commercial offering.
- Long-term regulatory compliance (GDPR, EU DMA, India IT Rules 2021).
- Marketing, pricing, support SLAs.

### 1.4 Confidence levels

Each major finding carries an explicit confidence label.

- **(High)** — directly observed in source or workflow YAML.
- **(Moderate)** — inferred from source + prior audit cross-reference.
- **(Low)** — inferred from logs or commit history without direct source confirmation.

---

## 2. Repository Topology & Branch Inventory

### 2.1 Current branch map

The repository has 22 remote branches and 5 tags that look like branches (topology verified by `git branch -a`).

| Branch | Last commit | Role | Verdict |
|---|---|---|---|
| `main` | `b3d9609` (v3.0.0-alpha.1 release) | Active trunk | Keep as trunk. |
| `dependabot/cargo/chacha20poly1305-0.11.0` | bump | Cargo dep | Merge-or-recreate (see §25). |
| `dependabot/cargo/hkdf-0.13.0` | bump | Cargo dep | Merge-or-recreate. |
| `dependabot/cargo/jni-0.22.4` | bump | Cargo dep | Merge-or-recreate. |
| `dependabot/cargo/pyo3-0.29.0` | bump | Cargo dep | **Conflict risk** — pyo3 0.22 → 0.29 is a breaking jump. |
| `dependabot/cargo/thiserror-2.0.18` | bump | Cargo dep | Merge-or-recreate. |
| `dependabot/github_actions/actions/checkout-7` | bump | GHA | Recreate (covered by §4). |
| `dependabot/github_actions/actions/setup-java-5` | bump | GHA | Recreate. |
| `dependabot/github_actions/actions/setup-python-6` | bump | GHA | Recreate. |
| `dependabot/github_actions/android-actions/setup-android-4` | bump | GHA | Recreate. |
| `dependabot/github_actions/codecov/codecov-action-7` | bump | GHA | Recreate. |
| `dependabot/github_actions/softprops/action-gh-release-3` | bump | GHA | Recreate. |
| `dependabot/gradle/android/...tink-android-1.23.0` | bump | Gradle | Merge-or-recreate. |
| `dependabot/gradle/android/...zxing-core-3.5.4` | bump | Gradle | Merge-or-recreate. |
| `dependabot/gradle/android/...lazysodium-android-5.2.0` | bump | Gradle | Merge-or-recreate. |
| `dependabot/gradle/android/...socket.io-client-2.1.2` | bump | Gradle | Merge-or-recreate. |
| `dependabot/gradle/android/...kotlinx-coroutines-test-1.11.0` | bump | Gradle | Merge-or-recreate. |
| `dependabot/npm_and_yarn/.../typescript-7.0.2` | bump | npm | **Conflict risk** — TS 5 → 7 is breaking. |
| `dependabot/npm_and_yarn/.../types/node-26.1.1` | bump | npm | Merge-or-recreate. |
| `dependabot/pip/sentry-sdk-2.65.0` | bump | pip | Merge-or-recreate. |
| `dependabot/pip/uvloop-gte-0.22.1` | bump | pip | Merge-or-recreate. |

Tags:

| Tag | Commit | Role |
|---|---|---|
| `v1.0.0` | `86630aff` | First release (Flask + SQLite). |
| `v3.0.0-alpha.1` | `b3d9609` | Current alpha. |
| `archive/backup-central` | `3708104c` | Legacy central-server backup. |
| `archive/backup-p2p` | `332d7423` | Legacy P2P backup. |
| `pre-migration-checkpoint` | `c0ee4866` | Snapshot before v3 migration. |

### 2.2 What is missing

- **No `dev` or `staging` branch.** All work lands on `main`; PRs are tested on `main`.
- **No `release/*` branches.** Releases are tagged directly off `main` with no release-candidate verification loop.
- **No long-lived per-platform branches** (e.g. `android-release`, `desktop-release`), so platform-specific fixes get tangled with backend changes.
- **No protected-branch policy documented.** Without it, force-pushes and direct commits to `main` are unguarded.
- **16 Dependabot branches with no triage policy.** They accumulate because no one owns the merge decision.

### 2.3 Branch unification — high-level verdict (detailed in §25)

The plan calls for a single `main` trunk protected by branch rules, a short-lived `dev` integration branch, periodic `release/vX.Y.Z` branches cut from `main` for tagging, and **delete-and-recreate** for the 16 Dependabot branches once the workflow YAML is rewritten (because the new YAML will obsolete the existing PRs). The three `archive/*` tags stay as historical markers but their underlying commits are referenced from `docs/historical/branch-provenance.md` so future maintainers can audit lineage without confusing tags with branches.

---

## 3. CI Workflow Failure Analysis (Root Cause)

### 3.1 The YAML trigger corruption (the bug the prior audits missed)

**Confidence: High.** Verified directly from the workflow files via `od -c`.

Ten of the fourteen workflow files contain this exact byte sequence in their `on:` block:

```yaml
on:
  push:
    branches: ain]
  pull_request:
    branches: ain]
```

The literal string `ain]` is what remains after a broken mass-replace that consumed the opening `[` and the letters `m` of `main`, leaving only `ain]`. The intended value was `[main]`. (Compare with `.github/workflows/ci.yml` and `.github/workflows/release.yml`, which escaped the corruption and read `branches: [ main, dev ]` and `tags: ['v*']` respectively.)

**Affected workflows (all 10):**

- `android.yml`
- `ci-health.yml`
- `codeql.yml`
- `ios.yml`
- `js.yml`
- `python.yml`
- `rust.yml`
- `sbom.yml`
- `semgrep.yml`
- `web.yml`

**Consequence:** GitHub Actions parses `branches: ain]` as a one-element list containing the string `ain]`. Since no branch named `ain]` exists, **none of these ten workflows has triggered on `push` or `pull_request` for the entire history of the v3 migration**. They appear "configured" in the Actions tab but their run history is either empty or shows only scheduled/manual runs. This is the single largest reason the CI badge on the README is misleading.

**Why the prior audits missed it:** the prior audits (`docs/historical/ci-failure-analysis-2026-07.md`) examined *runtime* failures of workflows that *did* run. They never asked why a workflow did not run in the first place. The corruption is invisible in a normal `cat` of the YAML because `ain]` looks like a typo rather than a parser-breaking event — but GitHub Actions' schema treats `branches:` as a list of glob patterns, and a pattern `ain]` is a valid (but useless) glob.

### 3.2 The runtime failures the prior audits correctly identified

The prior CI-failure-analysis document (1,648 lines) is largely correct on these runtime issues. This plan adopts its findings and incorporates the fixes into §4 and §5:

- **Android Kotlin compilation** — `Unresolved reference 'iv'`, `'ciphertext'`, `'timestamp'`, `'text'`, and missing methods `sendDeleteMessage`, `sendEditMessage`, `downloadFileXFTP`, `sendReceipt`, `addLocalReaction`. Root cause: `CryptoProvider.encryptMessage()` return type drift; ChatManager call sites reference fields that do not exist on the returned object.
- **Reproducible-build Docker digest** — `python:3.11-slim@sha256:d55f5f684c30c1d2e1b12b591b63d7e5d263914e667794273f7690558b3bf430` no longer exists on Docker Hub. (Note: `Dockerfile.relay` now pins `python:3.12-alpine@sha256:d8be92383c8479e0f63b4009cdde6f1e84323cb11202ec56b02660a5e81d7637`, but the reproducible-build workflow never builds `Dockerfile.relay` — it builds a non-existent `build/Dockerfile`.)
- **SBOM workflow** — already migrated to `actions/upload-artifact@v4` in the current snapshot, but `actions/checkout@v4` is used everywhere except `release.yml` which still uses `@v4`. The Dependabot PRs bump these but they are not merged.
- **Python CI** — the legacy `pytest` line ends with `|| true`, so legacy failures are masked. The v3 test runner expects `pytest-asyncio` markers but the legacy suite does not carry them.
- **`chmod: cannot access 'AnonyMus_android/gradlew'`** — historical only; the path is now correct (`android/gradlew`).
- **iOS workflow** — placeholder only (`run: echo "iOS validation placeholder"`).

### 3.3 The structural CI defects that runtime fixes alone cannot solve

These are not in the prior audit and require architectural changes:

1. **No required-status-check policy.** Even after the YAML is fixed, no branch-protection rule forces PRs to pass any specific check before merge. Without this, "green" is decorative.
2. **`continue-on-error: true` on the WASM build step** (`.github/workflows/web.yml:772`). This makes the web production build silently fall back to a missing WASM module. The TS check then either fails opaquely or — if the generated module is stubbed — passes against a stub that ships to production.
3. **Two parallel Python workflow definitions.** `.github/workflows/ci.yml` and `.github/workflows/python.yml` both run Python tests but install different dependency sets, run different test sub-paths, and use different Python versions (`3.12` vs `3.11`). They will diverge and produce contradictory results.
4. **Preflight skip mechanism (`scripts/ci-preflight.sh`) hides missing components.** If `core/rust` is missing, the Rust workflow silently reports success instead of failure. This is the wrong default for a commercial release — missing components should be a hard failure unless explicitly marked as optional.
5. **No artifact attestation, no SLSA provenance, no SBOM-in-release.** The release workflow creates a GitHub Release with auto-generated notes but attaches no SBOM, no build provenance, no signature. The reproducible-build workflow computes a SHA-256 but never compares it against an attested reference.
6. **The Dependabot config (`.github/dependabot.yml`) is not visible in the audited tree**, which suggests it either does not exist or is mis-scoped. The 16 un-merged Dependabot PRs are evidence of mis-scoped update groups.

### 3.4 Why CI is failing — one-paragraph root cause

The CI is failing because (a) ten workflows have corrupted YAML triggers that prevent them from running at all, (b) the four workflows that do run are non-blocking by design (`|| true`, `continue-on-error`) so green is meaningless, (c) the two workflows that test Python disagree with each other about what to install and what to run, and (d) the release pipeline has no attestation, no SBOM attachment, and no reproducible-build verification step. Fixing (a) alone is necessary but not sufficient — the structural problems in (b)–(d) will continue to produce false greens until they are also fixed.

---

## 4. CI Remediation Plan (Workstream A)

This workstream makes CI green *and* meaningful. Every task is verifiable.

### A1. Rewrite all 14 workflow `on:` triggers

**Goal:** every workflow runs on the events it claims to run on.

**Tasks:**

- A1.1 — Replace `branches: ain]` with `branches: [main]` in the 10 affected workflows. Verify by `git grep -n 'ain]' .github/workflows/` returning zero matches.
- A1.2 — Add `dev` to the push/PR trigger list for `ci.yml`, `python.yml`, `rust.yml`, `js.yml`, `web.yml`, `android.yml`. The `dev` branch is created in §25.
- A1.3 — Move `codeql.yml`, `semgrep.yml`, `sbom.yml`, `reproducible-build.yml` to also trigger on `pull_request` (not just `push` and `schedule`), so PRs are scanned before merge.
- A1.4 — Add `workflow_call` to `ci.yml`, `python.yml`, `rust.yml`, `js.yml`, `web.yml`, `android.yml` so the release workflow can reuse them as gates (see A8).
- A1.5 — Replace the `paths:` filters with per-platform path triggers that actually match the repository layout. The current `paths: ['android/**', '.github/workflows/android.yml']` is correct; the equivalent for `web.yml` should include `core/rust/src/ffi/wasm.rs` (it does) but the file does not exist — see A6.

**Acceptance:** `yamllint .github/workflows/` passes; `actionlint` returns zero errors; manually triggering each workflow via `gh workflow run` succeeds without "no event matched" errors.

### A2. Eliminate the `|| true` and `continue-on-error` short-circuits

**Goal:** CI cannot pass while a selected test or build step is failing.

**Tasks:**

- A2.1 — In `.github/workflows/python.yml`, replace `pytest ... --cov ... || true` with a conditional marker: `pytest tests/unit/ tests/integration/ --ignore=tests/integration/test_fastapi_v3.py --cov=core --cov=transports --cov-report=xml -m "not v3"`. Mark legacy-only tests with `@pytest.mark.legacy` and skip them with `-m "not legacy"` rather than masking their failures. Add a separate job `legacy-tests` that runs `pytest -m "legacy"` and is allowed to fail with `continue-on-error: true` **only at job level** (not step level) and only until the legacy suite is deleted in §C.
- A2.2 — In `.github/workflows/web.yml`, remove `continue-on-error: true` from the WASM build step. The WASM build must succeed for the production build to be valid. Provide a separate `wasm-stub` job that is allowed to fail until the Rust FFI is stable; the production build job depends on `wasm-stub` but does not depend on its success — instead it asserts `web/src/pkg/anonymus_core.js` exists.
- A2.3 — In `.github/workflows/semgrep.yml`, remove `|| true` (currently absent in the audited snapshot but referenced in the prior audit; verify). Semgrep findings should be uploaded as SARIF but should not fail CI unless severity ≥ high; configure `--error --config p/ci --config p/rust --config p/python --config p/javascript`.
- A2.4 — Audit every workflow for `continue-on-error` and `|| true` occurrences; document each remaining one in `.github/CI_EXCEPTIONS.md` with a justification and a removal date.

**Acceptance:** `git grep -n 'continue-on-error' .github/workflows/` returns only documented exceptions; `git grep -n '|| true' .github/workflows/` returns zero matches.

### A3. Resolve the duplicate Python workflow

**Goal:** one source of truth for Python testing.

**Tasks:**

- A3.1 — Delete the Python-specific job (`test-python-backend`) from `.github/workflows/ci.yml`. The unified `python.yml` is the authority.
- A3.2 — Promote `ci.yml` to a *meta-workflow* that calls `python.yml`, `rust.yml`, `js.yml`, `web.yml`, `android.yml` via `workflow_call`. The meta-workflow has no test steps of its own; it only orchestrates.
- A3.3 — Standardize on Python 3.12 in `python.yml` (not 3.11). Update `pyproject.toml` `requires-python` to `>=3.12`. Document the bump in `docs/migrations/python-3.12.md`.
- A3.4 — Standardize on Node 22 LTS in `js.yml` and `web.yml` (currently 20 and 24 — pick one). Document the choice.

**Acceptance:** `ci.yml` contains zero `run:` steps that execute tests; all testing is delegated.

### A4. Make the preflight script fail-closed for required components

**Goal:** missing required directories fail CI rather than silently passing.

**Tasks:**

- A4.1 — Rewrite `scripts/ci-preflight.sh` to take a `--required` or `--optional` flag per workflow. The Rust workflow's preflight becomes `bash scripts/ci-preflight.sh rust --required` and exits 1 if `core/rust` is missing.
- A4.2 — Mark Rust, Python, Web, and Android as `--required`. Mark iOS as `--optional` (it is a placeholder).
- A4.3 — Delete the `outputs.skip` mechanism; replace with hard failure. The skip mechanism was appropriate during scaffolding; it is not appropriate for a commercial release.

**Acceptance:** removing `core/rust/` locally and running `bash scripts/ci-preflight.sh rust --required` exits non-zero.

### A5. Fix the reproducible-build workflow

**Goal:** the reproducible-build workflow actually verifies reproducibility.

**Tasks:**

- A5.1 — Replace the `docker build` + `docker save` + `sha256sum` approach with `docker buildx build --provenance=false --sbom=false --output type=oci,dest=img.tar` on the *same* Dockerfile, twice, with `--no-cache` and `--build-arg BUILDKIT_INLINE_CACHE=1`. Then compare the OCI manifests with `crane manifest` rather than the tarball SHA (tarballs are not reproducible because of timestamps).
- A5.2 — Use `Dockerfile.relay` (which exists) instead of `build/Dockerfile` (which does not). If `build/Dockerfile` is intended for a different image, add a third job that builds it; do not conflate the two.
- A5.3 — Pin the base image by *both* tag and digest, and add a monthly scheduled job that opens a PR to refresh the digest (do not pin only by digest, because Docker Hub garbage-collects old digests; do not pin only by tag, because tags are mutable).
- A5.4 — Add a SLSA Level 3 provenance attestation using `actions/attest-build-provenance@v2`. Attach the attestation to the release.
- A5.5 — Generate the SBOM with `syft` (faster) in addition to `cyclonedx-bom` (canonical). Cross-validate that the two SBOMs agree on the dependency set.

**Acceptance:** two consecutive runs of the reproducible-build workflow produce OCI manifests with identical SHA-256 digests; the attestation is verifiable with `cosign verify-attestation`.

### A6. Fix the WASM build chain

**Goal:** the web production build depends on a real, generated WASM module.

**Tasks:**

- A6.1 — Create `core/rust/src/ffi/wasm.rs` if it does not exist (the `web.yml` `paths:` filter references it; verify its current existence — audit showed `core/rust/src/ffi/wasm.rs` is present at 251 lines, so the path filter is correct).
- A6.2 — In `web.yml`, run `npm run wasm:build` *before* `tsc -b` and `vite build`. Assert `web/src/pkg/anonymus_core.js` exists after the build; fail if not.
- A6.3 — Add a check that `web/src/pkg/anonymus_core.js` exports the expected symbols (`generateIdentityKeypair`, `x3dhInitiate`, `x3dhReceive`, `ratchetEncrypt`, `ratchetDecrypt`, `mlsCreateGroup`, `mlsAddMember`, `padPayload`, `unpadPayload`). The check is a small `node -e` script that imports the module and asserts the export list.
- A6.4 — Cache the `wasm-pack` build by `Cargo.lock` hash. The current build is uncached and rebuilds every run.

**Acceptance:** `web.yml` build job fails if `wasm:build` fails; the production bundle includes a non-stub `anonymus_core.js`.

### A7. Add required-status-checks and branch protection

**Goal:** merge to `main` requires passing CI.

**Tasks:**

- A7.1 — Document required checks in `.github/required-checks.txt`. The list: `ci-health`, `python (test)`, `rust (validate)`, `web (lint-and-type-check)`, `web (test)`, `web (build)`, `android (build)`, `codeql`, `semgrep`, `sbom`, `reproducible-build`.
- A7.2 — Apply branch protection to `main` and `dev` via the GitHub UI (or `gh api` script in `scripts/apply-branch-protection.sh`): require PR review (≥1), require status checks (the list from A7.1), require linear history, dismiss stale reviews, require code-owner review for `core/rust/**` and `core/crypto.py`.
- A7.3 — Add a `CODEOWNERS` file. Suggested owners: `core/rust/` → security team; `core/crypto.py` → security team; `.github/workflows/` → release team; `transports/` → backend team; `web/` → frontend team; `android/` → mobile team.
- A7.4 — Disable force-push to `main` and `dev`. Allow force-push only on `feature/*` and `dependabot/*`.

**Acceptance:** `gh api repos/:owner/:repo/branches/main/protection` returns the configured policy.

### A8. Make the release workflow an attested gate

**Goal:** no release tag is created without passing CI, SBOM, and reproducibility.

**Tasks:**

- A8.1 — Rewrite `release.yml` to call `ci.yml` (the meta-workflow) as a required upstream via `workflow_call`. The release job does not start until all sub-workflows pass.
- A8.2 — Attach to every GitHub Release: the SBOM (`sbom.json`), the OCI image digest, the SLSA provenance attestation, the reproducible-build verification log, and a signed manifest of artifact hashes (`cosign sign-blob`).
- A8.3 — Add a pre-release channel (`v*-*` tags, e.g. `v3.0.0-rc.1`) that produces prerelease GitHub Releases with the same artifacts but marked `prerelease: true`.
- A8.4 — Add a manual `release-dry-run.yml` workflow that runs the entire release pipeline without publishing, so maintainers can verify the pipeline before tagging.

**Acceptance:** tagging `v3.0.0-rc.1` triggers a release that attaches all five artifacts; `cosign verify-attestation` on the release succeeds.

### A9. Sweep all workflow action versions

**Goal:** no deprecated action versions.

**Tasks:**

- A9.1 — Bump every `actions/checkout` to `@v4` (Dependabot wants `@v7`, but `@v7` is not yet stable across all runner images; pin to `@v4` for now and let Dependabot upgrade after the runner image catches up).
- A9.2 — Bump every `actions/setup-python` to `@v5`, `actions/setup-node` to `@v4`, `actions/setup-java` to `@v4`, `actions/upload-artifact` to `@v4`, `actions/cache` to `@v4`.
- A9.3 — Bump `codecov/codecov-action` to `@v4` (Dependabot wants `@v7`; pin to `@v4`).
- A9.4 — Close the 6 Dependabot GitHub-Actions PRs after the bumps are merged manually; the PRs become stale.

**Acceptance:** `git grep -n '@v[1-3]' .github/workflows/` returns zero matches.

### A10. Add CI health monitoring

**Goal:** CI health is observable, not just pass/fail.

**Tasks:**

- A10.1 — The existing `ci-health.yml` workflow already runs `actionlint` and `yamllint`. Add `zizmor` (a workflow security linter) and `scorecard` (GitHub's security scorecard).
- A10.2 — Add a daily scheduled job that posts a CI-health summary to a `#ci-health` Slack webhook (configured via secret `SLACK_WEBHOOK_URL`). The summary lists: workflows that failed in the last 24h, workflows that did not run in the last 7 days, average run time, queue depth.
- A10.3 — Add a `metrics.yml` workflow that runs weekly and publishes a JSON summary of the last 100 runs to `docs/metrics/ci-health.json`. This makes CI degradation visible in the repository itself.

**Acceptance:** `#ci-health` Slack receives a daily message; `docs/metrics/ci-health.json` is updated weekly.

---

## 5. Correctness & Security Remediation Plan (Workstream B)

This workstream fixes the defects in the prior issue log (`docs/audits/2026-07-12-current-state-issue-log.md`) plus additional defects found in this audit. Each task cites the prior issue ID where applicable.

### B1. Freeze the v3 HTTP contract (resolves I-01, I-13)

**Confidence: High** for the contract mismatches; **Moderate** for the chosen resolution.

**Tasks:**

- B1.1 — Generate the OpenAPI schema from FastAPI at build time (`fastapi-codegen` or `openapi-typescript`) and commit the generated `web/src/lib/api-types.ts`. The web client imports types from this file; manual duplication in `web/src/lib/api.ts` is deleted.
- B1.2 — Add a CI job `contract-check` that regenerates the OpenAPI schema from a running `app_v3` instance and `diff`s it against the committed schema. The job fails if the schema drifted.
- B1.3 — Pick one resolution per mismatch (the remediation plan in the prior audit proposes these; this plan adopts them with one change — see B1.4):
  - **Login** returns the `User` object directly. The web client's `session.login()` reads `res.user` — change to `res` and type as `User`.
  - **Contacts**: deletion is by `onion_address` (not by integer `id`). The web client's `contacts.delete(id)` is renamed `contacts.deleteByOnion(onion)`. The API returns `onion_address` as the contact identifier in all responses.
  - **Messages**: the canonical endpoints are `POST /v3/messages/send` and `GET /v3/messages/history/{peer_onion}`. The web client's `POST /v3/messages/` and `GET /v3/messages/{onion}` calls are rewritten. The `disappears_in_seconds` request field is kept; the response includes both `disappears_in_seconds` and `disappears_at` (computed).
  - **Pagination**: `before_id` is implemented in the SQL query (`WHERE message_id < :before_id ORDER BY message_id DESC LIMIT :limit`). The web client's `before` query parameter is renamed `before_id`.
- B1.4 — **Addition to prior plan:** the response schema for `GET /v3/messages/history/{peer_onion}` must include `is_deleted` and `disappears_at` (the web client requires both). The prior audit notes this; this plan makes it a contract test.
- B1.5 — Add a contract test suite `tests/integration/test_contract_v3.py` that exercises: register → login → contacts CRUD → send → history → delete → paginated history. Each step asserts both the HTTP status and the response shape (via `pydantic` model validation). The suite runs against `create_app()` with a fresh in-memory SQLite DB.
- B1.6 — Add a browser-side contract test (`web/src/test/contract.test.ts`) that mocks the API using the generated types and verifies the web client's call sites match.

**Acceptance:** `contract-check` CI job is green; the manual contract test suite passes end-to-end on a clean checkout.

### B2. Replace the broken Compose topology (resolves I-02, I-08, I-15)

**Confidence: High.**

The current `docker-compose.yml` is internally inconsistent in four ways (verified directly):

1. It health-checks `http://localhost:5001/healthz`, but `Dockerfile.relay` runs `transports.relay.app_relay:app` which does expose `/healthz` — so this part is actually correct, but the *relay* image is built from `Dockerfile.relay` which runs `transports.relay.app_relay` while the *P2P* app (`transports.p2p.app_v3`) is the one the web client talks to. The compose stack therefore starts the **relay** but the web client expects the **P2P node**.
2. `RELAY_DOMAIN` is set only on the relay container; Caddy expands it in its own container and gets an empty string.
3. `frontend-builder` runs `npm install && npm run build` but never builds the WASM module, so the production bundle has a broken `import './pkg/anonymus_core.js'`.
4. `.env.example` defines `FLASK_SECRET_KEY` and `FLASK_DEBUG`, but the v3 stack reads `SECRET_KEY` and `ENVIRONMENT`. A first-time operator following `.env.example` will boot with the v3 default secret and in development mode.

**Tasks:**

- B2.1 — Split the compose stack into two profiles: `relay` (public relay server, runs `transports.relay.app_relay`) and `node` (local P2P node, runs `transports.p2p.app_v3`). The web client is served by the `node` profile, not the `relay` profile.
- B2.2 — Move `RELAY_DOMAIN` to Caddy's `environment:` block. Use `${RELAY_DOMAIN:?Set RELAY_DOMAIN}` to fail at compose-up if unset.
- B2.3 — Rewrite `.env.example` to define only v3 variables: `SECRET_KEY`, `ENVIRONMENT`, `DATABASE_URL`, `TOR_SOCKS_PORT`, `TOR_CONTROL_PORT`, `RELAY_DOMAIN`, `ANONYMUS_MODE`, `ANONYMUS_MDNS`. Remove all `FLASK_*` variables.
- B2.4 — Add a WASM build step to `frontend-builder`: `npm run wasm:build && npm run build`. Cache `~/.cargo/registry` and `web/src/pkg` between runs.
- B2.5 — Add a `compose-smoke-test` CI job that runs `docker compose config`, boots the `node` profile, waits for `/healthz`, and verifies the SPA can fetch `/v3/auth/me` (expecting 401, not 404 or 500).
- B2.6 — Document the deployment topology in `docs/guides/self-hosting.md` with a single canonical command sequence. Remove the conflicting PostgreSQL reference (the stack uses Redis, not PostgreSQL).

**Acceptance:** `docker compose --profile node up -d` produces a healthy node reachable at `http://localhost:5001/healthz`; the SPA at `http://localhost:8080` can call `/v3/auth/me` and receive a 401.

### B3. Establish a single schema authority (resolves I-03)

**Confidence: High** for the drift; **High** for the fix (Alembic-only).

The ORM (`core/db/models.py`) and migration `0001` (`alembic/versions/0001_initial_schema.py`) disagree on:

- `messages.id` (integer PK in ORM; absent in migration — migration uses `message_id` as PK).
- `users.last_seen` (present in ORM; absent in migration).
- Contact key/secret columns (present in later migrations; the ORM reads them but the migration sequence is unclear).

The v3 app's `lifespan` runs Alembic `upgrade head` (verified at `transports/p2p/app_v3.py:131`), but tests still use `Base.metadata.create_all()` (`tests/conftest.py:47`, `tests/integration/test_fastapi_v3.py:30`). This means tests pass against a schema the production app never uses.

**Tasks:**

- B3.1 — Generate a new Alembic revision `0002_reconcile_orm_and_migrations.py` that adds: `messages.id` (or removes it from the ORM — pick one; the plan recommends keeping UUID `message_id` as PK and removing the integer `id` from the ORM, because UUID PKs are correct for a distributed messenger), `users.last_seen`, and any other columns the ORM declares that the migration history does not.
- B3.2 — Remove `Base.metadata.create_all()` from `tests/conftest.py` and `tests/integration/test_fastapi_v3.py`. Replace with `alembic upgrade head` against a fresh in-memory SQLite DB.
- B3.3 — Add a migration test `tests/integration/test_migrations.py` that: creates a fresh DB, runs `alembic upgrade base` → `alembic upgrade head`, inserts a row into every table, runs `alembic downgrade base`, and asserts the DB is empty.
- B3.4 — Add a schema-drift test that introspects the DB schema after `alembic upgrade head` and compares it to `Base.metadata`. The test fails if they disagree.
- B3.5 — Document the schema authority in `docs/architecture/schema-authority.md`: Alembic is the only authority; ORM is the source of truth for what the schema *should* be; the drift test enforces the contract.

**Acceptance:** `test_migrations.py` and `test_schema_drift.py` both pass; a fresh `alembic upgrade head` produces a schema that matches `Base.metadata` exactly.

### B4. Harden the pre-key API (resolves I-04)

**Confidence: High.**

The current `keys.py` router (audited at `transports/p2p/routers/keys.py`) *does* enforce caller-to-onion ownership (lines 100-110), which is an improvement over the prior audit's finding. However:

- The one-time pre-keys (OPKs) are stored as a JSON list on the `PreKeyBundle` row. Consumption is not atomic — two concurrent requests can consume the same OPK.
- `/keys/me` returns the bundle for `current_user.onion_address`, which is correct, but there is no rate limit on the public fetch endpoint (any anonymous caller can drain another user's OPK pool by repeatedly fetching).
- There is no signature verification on the published bundle — the server trusts that the caller-provided `identity_key`, `signed_prekey`, `signed_prekey_sig`, `pq_prekey`, `pq_prekey_sig` are well-formed and correctly signed.

**Tasks:**

- B4.1 — Move OPKs to a separate table `one_time_prekeys` with columns `id`, `bundle_id`, `key_b64`, `key_type` (x25519 or ml_kem), `consumed_at` (nullable). Consumption is a single SQL statement: `UPDATE one_time_prekeys SET consumed_at = NOW() WHERE id = (SELECT id FROM one_time_prekeys WHERE bundle_id = :bundle_id AND key_type = :key_type AND consumed_at IS NULL ORDER BY id LIMIT 1 FOR UPDATE) RETURNING key_b64`. This is atomic under SQLite WAL and PostgreSQL.
- B4.2 — Verify the `signed_prekey_sig` and `pq_prekey_sig` against the `identity_key` (Ed25519) before storing the bundle. Reject the publish request if verification fails. The verification is done in Python via `cryptography` or via the Rust core FFI.
- B4.3 — Rate-limit the public fetch endpoint `GET /v3/keys/{onion}` to 10 requests per minute per IP (using the existing `RateLimiterMiddleware`).
- B4.4 — Add a "depletion" response: when an OPK pool is empty, return `{"one_time_prekey": null, "one_time_pq_prekey": null}` rather than erroring. The client falls back to the signed prekey only.
- B4.5 — Add authorization tests in `tests/integration/test_keys_authz.py`:
  - Alice publishes a bundle; Bob fetches it; Eve cannot publish/rotate/read Alice's bundle.
  - Eve cannot consume Alice's OPKs via `/keys/me` (returns Eve's bundle, not Alice's).
  - Concurrent OPK consumption: 100 parallel requests consume 100 distinct OPKs, never the same one twice.

**Acceptance:** all five authorization tests pass; the concurrent-consumption test shows zero collisions.

### B5. Enforce group membership (resolves I-05)

**Confidence: High.**

`send_group_message()` verifies only that the group exists, not that the sender is a member (prior audit I-05, verified in source).

**Tasks:**

- B5.1 — Add a `GroupMember` check before every group read/write in `transports/p2p/routers/groups.py`. For channels (founder-only posting), also verify the sender is the founder or an editor.
- B5.2 — Add direct-message recipient validation: the sender must have a `Contact` row for the recipient's `onion_address`, OR the recipient must have a published pre-key bundle (first-contact message). If neither, return 403.
- B5.3 — Add authorization tests: nonmember cannot post to a normal group; non-founder cannot post to a channel; unrelated user cannot inject into a group's history.

**Acceptance:** all authorization tests pass; unauthorized writes return 403 and create no row.

### B6. Persist node settings and notifications (resolves I-14)

**Confidence: High.**

`routers/node.py` uses a module-global `_config` dict; `routers/notifications.py` uses module-global token dicts. Neither is durable.

**Tasks:**

- B6.1 — Create `node_settings` table: `user_id`, `key`, `value`, `updated_at`. Replace `_config` dict with DB lookups scoped by `current_user.id`.
- B6.2 — Create `notification_registrations` table: `id`, `user_id`, `token_hash`, `platform` (web/apns/fcm), `created_at`, `expires_at`, `revoked_at`. Replace the in-memory token dict with DB lookups.
- B6.3 — Never store raw tokens; hash with SHA-256 and store the hash. The raw token is sent to the push provider at send time only if the client re-registers.
- B6.4 — Add restart-isolation tests: user A's settings are not visible to user B; settings survive a process restart.

**Acceptance:** restart-isolation tests pass; no module-global mutable state in `node.py` or `notifications.py`.

### B7. Implement rate limiting and CSRF posture (resolves I-10)

**Confidence: High.**

`core/config.py` defines `rate_limit_default` and `rate_limit_auth`, but they are not applied. The `RateLimiterMiddleware` in `app_v3.py` applies a single global limit (120 req/min) and skips auth-specific limits.

**Tasks:**

- B7.1 — Replace the global `RateLimiterMiddleware` with a per-route limiter using `slowapi` (or a custom ASGI middleware). Auth routes (`/v3/auth/login`, `/v3/auth/register`) get `rate_limit_auth` (10/min). All other routes get `rate_limit_default` (60/min).
- B7.2 — Back the limiter with Redis in production (so limits are shared across workers) and with an in-memory dict in development.
- B7.3 — Add CSRF protection for cookie-authenticated state-changing routes. Use `starlette-csrf` or a custom double-submit-token middleware. Exempt `/v3/auth/login` and `/v3/auth/register` (they establish the session).
- B7.4 — Tighten CORS: replace `allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"` with an explicit allow-list from `settings.cors_origins` (a comma-separated env var). In production, fail startup if `cors_origins` is unset or contains a wildcard.
- B7.5 — Add tests: 11th login attempt in a minute returns 429; cross-origin state change returns 403; missing CSRF token returns 403.

**Acceptance:** all three tests pass.

### B8. Make transport mode switching fail-closed (resolves I-09)

**Confidence: High.**

`core/transport_registry.py:35-47` catches handoff/stop exceptions and still changes `_active_mode`, returning success.

**Tasks:**

- B8.1 — Make runtime mode switching return 501 in production (`settings.is_production`). The endpoint is for development only.
- B8.2 — If runtime switching is later required, implement a real state-machine: validate target readiness → checkpoint state → transfer state → stop old → verify stop → commit new mode → roll back on failure. Never change `_active_mode` after a caught exception.
- B8.3 — Add a test that injects a failure in `current.handoff()` and asserts the response is 500, the mode is unchanged, and the target transport is stopped.

**Acceptance:** the failure-injection test passes; production returns 501.

### B9. Block unsafe privacy behaviors (resolves I-06, I-11)

**Confidence: High.**

The prior audit I-11 (Google Fonts leak) is **already fixed** in the current snapshot — `web/index.html` no longer references Google Fonts (verified). The prior audit I-06 (PWA caching authenticated responses) requires verification.

**Tasks:**

- B9.1 — Audit `web/vite.config.ts`: the `VitePWA` config has `workbox.globPatterns: ["**/*.{js,css,html,ico,png,svg,wasm}"]` but no `runtimeCaching`. Verify that no `NetworkFirst` cache is configured for `/v3/` routes. If it is (the prior audit cites `web/vite.config.ts:25-33`), delete the runtime cache entry.
- B9.2 — Add a Playwright test that loads the app, logs in, logs out, and verifies that `caches.keys()` does not contain any cache with authenticated `/v3/` responses.
- B9.3 — Self-host fonts: the app currently uses no web fonts (verified — `web/index.html` has no `<link>` to fonts). Document in `web/README.md` that system fonts are the policy; any future font addition must be self-hosted.
- B9.4 — Make the web build fail in production if `web/src/pkg/anonymus_core.js` is missing. Add a `vite` plugin that checks for the file at build time and fails with a clear error.

**Acceptance:** Playwright cache test passes; production build fails without WASM.

### B10. Fix the Android Kotlin compilation (carried from prior audit)

**Confidence: High** for the symptom; **Moderate** for the exact fix (the prior audit proposes adding missing methods; this plan adopts that but adds a return-type contract).

**Tasks:**

- B10.1 — Define `EncryptedMessage` data class in `CryptoProvider.kt` with `iv: String` and `ciphertext: String` (both base64). Make `encryptMessage()` return `EncryptedMessage`. Update all call sites in `ChatManager.kt` (lines 287-288, 367-368, 585-586, 824-825, 863-864, 948-949, 991-992 per prior audit).
- B10.2 — Implement the missing methods: `sendDeleteMessage`, `sendEditMessage`, `downloadFileXFTP`, `sendReceipt`, `addLocalReaction`. Each follows the same payload-encrypt-emit pattern as `sendPrivateMessage`.
- B10.3 — Add a Kotlin unit test `CryptoProviderTest.kt` that calls `encryptMessage` and asserts the return type is `EncryptedMessage` with non-empty `iv` and `ciphertext`.
- B10.4 — Add an Android CI job that runs `./gradlew compileDebugKotlin testDebugUnitTest` and fails on any compilation error.

**Acceptance:** Android CI job is green; the Kotlin unit test passes.

### B11. Fix the iOS placeholder

**Confidence: High** that the current iOS workflow is a placeholder (`run: echo "iOS validation placeholder"`).

**Tasks:**

- B11.1 — Either remove the iOS workflow entirely until the iOS app is real, or replace the placeholder with a real `xcodebuild` step. The plan recommends removal, because the iOS app (`ios/AnonyMusApp.swift`) is a 50-line shell with hardcoded passcodes (`1337` unlocks, `9999` wipes) — it is not a real app.
- B11.2 — If the iOS app is intended for release, scope a separate workstream (not in this plan) to build it. Until then, the CI workflow is removed.
- B11.3 — Document the iOS status in `docs/roadmap/ios.md`: "iOS is not currently a supported platform. The Swift file is a placeholder for architecture exploration."

**Acceptance:** no iOS workflow exists; `docs/roadmap/ios.md` documents the status.

### B12. Consolidate dependencies (resolves I-08)

**Confidence: High.**

`pyproject.toml` declares no runtime dependencies. `requirements.txt` is the v3 lock (correct). `requirements.in` is the v3 input (correct). But the v3 stack is installed in CI by manually listing packages in `python.yml` (lines 42-62), which diverges from `requirements.txt`.

**Tasks:**

- B12.1 — Move the v3 runtime dependencies into `pyproject.toml` `[project.dependencies]`. Compile `requirements.txt` from `pyproject.toml` via `uv pip compile pyproject.toml -o requirements.txt`.
- B12.2 — Delete the manual `uv pip install --system "fastapi[standard]>=0.115" ...` block from `python.yml`. Replace with `uv pip install --system -r requirements.txt`.
- B12.3 — Delete the legacy `requirements-v3.in` reference (it does not exist in the current snapshot; the prior audit's reference is stale — verify).
- B12.4 — Add a `pip install .` smoke test in CI: install the package from `pyproject.toml` into a fresh venv, import `transports.p2p.app_v3`, and call `create_app()`. Fail if import or factory fails.

**Acceptance:** `pip install .` succeeds in a fresh venv; `create_app()` returns a FastAPI instance.

---

## 6. Adaptive Performance & Capability Tiers (Workstream C)

This is the workstream the prior plans underweight. AnonyMus targets both low-spec Android devices (1 GB RAM, ARMv7, 4-core) and high-spec desktops (16+ GB RAM, x86-64, 8+ core). The current code makes no provision for runtime capability detection — every feature is on by default, every buffer is unbounded, every concurrency knob is hardcoded.

### C1. Capability Tier definitions

The plan defines four capability tiers. Every device is classified into exactly one tier at startup based on detected hardware.

| Tier | Label | RAM | CPU | Target devices | Default feature set |
|---|---|---|---|---|---|
| **L0** | Minimal | < 2 GB | < 4 cores, ARMv7 | Old Android, Raspberry Pi Zero | Text-only chat, no WebRTC, no mDNS, no MLS groups, single worker, 64 MB max heap, batched DB writes, no WASM MLS (fallback to Python MLS), 30 fps UI cap |
| **L1** | Low | 2–4 GB | 4 cores, ARMv8 | Mid-range Android, old desktops | Text + voice (no video), mDNS disabled, MLS groups ≤ 10 members, 2 workers, 128 MB heap, WASM core loaded |
| **L2** | Standard | 4–8 GB | 4–8 cores, x86-64 | Modern Android, typical laptop | Full feature set, WebRTC voice+video (1:1 only), mDNS enabled, MLS groups ≤ 50, 4 workers, 256 MB heap |
| **L3** | High | > 8 GB | 8+ cores, x86-64 | Workstation, server | All features, WebRTC video (group), mDNS enabled, MLS groups ≤ 500, 8 workers, 512 MB heap, background indexing, prefetch |

### C2. Capability detection

**Tasks:**

- C2.1 — Create `core/capability.py` with a `CapabilityProfile` dataclass: `tier`, `ram_gb`, `cpu_cores`, `cpu_arch`, `is_mobile`, `max_workers`, `max_heap_mb`, `features` (a dict of feature flags).
- C2.2 — Implement `detect_tier()`:
  - On Python (desktop/server): use `psutil.virtual_memory()` for RAM, `os.cpu_count()` for cores, `platform.machine()` for arch. Classify per the table above.
  - On Android (Kotlin): use `ActivityManager.MemoryInfo`, `Runtime.availableProcessors()`, `Build.SUPPORTED_ABIS`. Pass the tier to the Rust core via JNI.
  - On iOS (future): use `ProcessInfo.physicalMemory`, `ProcessInfo.processorCount`.
  - On Web (TypeScript): use `navigator.deviceMemory` (Chrome), `navigator.hardwareConcurrency`, and the `prefers-reduced-motion` media query. Fall back to L1 if `deviceMemory` is undefined.
- C2.3 — Cache the detected tier in a `capability.json` file in the app's data directory. Re-detect only if the file is missing or the hardware signature (RAM + cores + arch hash) changes.
- C2.4 — Expose the tier to every layer:
  - Python: `from core.capability import settings as capability_settings; if capability_settings.tier >= L2: ...`
  - Rust: `anonymus_core::capability::tier()` returns an enum; the FFI exposes it to Python/JS/Kotlin/Swift.
  - Web: `import { capability } from "@lib/capability"; if (capability.tier >= 2) { ... }`
  - Android: `CapabilityProvider.tier()` from the DI graph.

**Acceptance:** `capability.json` is created on first run; the tier is logged at startup; the tier is consistent across Python, Rust, Web, and Android.

### C3. Feature gating

**Tasks:**

- C3.1 — Define a feature registry in `core/capability.py`:
  ```python
  FEATURES = {
      "webrtc_video": {"min_tier": L2},
      "webrtc_voice": {"min_tier": L1},
      "mdns_discovery": {"min_tier": L2},
      "mls_groups_large": {"min_tier": L3},
      "mls_groups_small": {"min_tier": L1},
      "background_indexing": {"min_tier": L3},
      "structured_log_fanout": {"min_tier": L2},
      "wasm_mls": {"min_tier": L1},
      "python_mls_fallback": {"min_tier": L0},
      "prefetch_attachments": {"min_tier": L3},
      "animated_emoji": {"min_tier": L2},
      "blurhash_thumbnails": {"min_tier": L1},
  }
  ```
- C3.2 — Implement `is_enabled(feature: str) -> bool` that checks the current tier against the feature's `min_tier`.
- C3.3 — Gate every expensive feature behind `is_enabled()`:
  - `transports/p2p/app_v3.py`: mDNS advertisement only if `is_enabled("mdns_discovery")`.
  - `web/src/stores/calls.ts`: WebRTC video only if `is_enabled("webrtc_video")`; voice only if `is_enabled("webrtc_voice")`.
  - `core/mls_groups.py`: large groups only if `is_enabled("mls_groups_large")`; small groups if `is_enabled("mls_groups_small")`; if neither, MLS is disabled and group chat falls back to pairwise.
  - `core/logging_v3.py`: structured log fan-out (JSON to stdout + Sentry + OpenTelemetry) only if `is_enabled("structured_log_fanout")`; otherwise plain text to stdout only.
- C3.4 — On the web client, render a "Performance mode" badge in settings showing the detected tier and which features are disabled. Allow the user to manually override the tier *downward* (e.g. force L1 on an L2 device to save battery) but never *upward* (an L0 device cannot enable WebRTC video without crashing).

**Acceptance:** on an L0 device, `is_enabled("webrtc_video")` returns `False`; the web client's call button is hidden; the settings panel shows "L0 — Minimal" with the disabled feature list.

### C4. Memory pressure handling

**Tasks:**

- C4.1 — Implement a memory-pressure monitor in `core/capability.py`:
  - Python: `psutil.virtual_memory().percent`; if > 80% for 30 seconds, trigger `on_memory_pressure(level="moderate")`; if > 95%, trigger `level="critical"`.
  - Android: register a `ComponentCallbacks2.onTrimMemory(level)` listener; map `TRIM_MEMORY_MODERATE` → moderate, `TRIM_MEMORY_COMPLETE` → critical.
  - Web: listen to the `pressure` observer (experimental) or fall back to measuring `performance.memory.usedJSHeapSize` (Chrome only).
- C4.2 — On moderate pressure: drop in-memory message caches (keep only the most recent 50 messages per conversation), close idle Tor circuits, pause mDNS advertisement, flush the structured-log buffer.
- C4.3 — On critical pressure: additionally, drop the WebRTC call (gracefully notify the peer), pause background indexing, reduce the worker count by half, switch to batched DB writes (every 5 seconds instead of per-message).
- C4.4 — Never drop: the active session key, the current conversation's most recent 10 messages, the ratchet state for the active conversation. These are the minimum to keep the app functional.
- C4.5 — Log every pressure event with the tier, the feature that was dropped, and the memory before/after. This feeds back into the tier calibration (see C7).

**Acceptance:** on a 2 GB Android device, opening 10 conversations with large attachments triggers moderate pressure within 30 seconds; the cache drops and memory returns to < 60%.

### C5. CPU-aware concurrency

**Tasks:**

- C5.1 — Replace hardcoded worker counts with `capability_settings.max_workers`. The FastAPI/uvicorn `--workers` flag is set from capability at startup.
- C5.2 — In the Rust core, the thread pool for MLS group operations is sized to `capability.tier.cores - 1` (leave one core for the UI). On L0 (1–2 cores), MLS is single-threaded.
- C5.3 — In the web client, the WASM core runs on the main thread for L0 (no Web Workers available without overhead) and on a Web Worker for L1+.
- C5.4 — In the Android app, the `PushService` uses a `CoroutineDispatcher` sized to `capability.tier.cores`.

**Acceptance:** `uvicorn --workers` matches the capability tier; the Rust thread pool reports the correct size via the FFI.

### C6. Adaptive crypto parameters

**Confidence: Moderate** — this is the most aggressive part of the plan and requires careful security review.

**Tasks:**

- C6.1 — Define crypto parameter sets per tier:
  - **L0**: ML-KEM-512 (smaller keys, faster), Argon2id with `t=2, m=64MB, p=1` (lighter KDF), 100 OPKs per bundle (smaller pool).
  - **L1**: ML-KEM-768 (default), Argon2id with `t=3, m=128MB, p=1`, 100 OPKs.
  - **L2**: ML-KEM-768, Argon2id with `t=4, m=256MB, p=2`, 200 OPKs.
  - **L3**: ML-KEM-1024 (strongest), Argon2id with `t=5, m=512MB, p=2`, 500 OPKs.
- C6.2 — **Security review required:** ML-KEM-512 on L0 is a deliberate tradeoff (lower security margin for performance). Document the tradeoff in `docs/security/crypto-tiers.md` and require sign-off from a cryptographer before shipping.
- C6.3 — The KDF parameters (`t`, `m`, `p`) are stored alongside the password hash, so a user who upgrades hardware is hashed with the old parameters until they re-login. Provide a migration path: on next login after a tier upgrade, re-hash with the new parameters.
- C6.4 — Never downgrade crypto parameters at runtime — only upgrade. If a user moves from L3 to L0 (e.g. switches devices), their existing ratchet sessions continue with the parameters negotiated at session creation; new sessions use the L0 parameters.

**Acceptance:** on an L0 device, ML-KEM-512 is used; the parameter set is logged; the security review is documented.

### C7. Tier calibration loop

**Tasks:**

- C7.1 — Log per-session metrics: tier, features enabled, memory pressure events, message send latency, WebRTC call setup time, MLS group operation time.
- C7.2 — Aggregate metrics weekly in `docs/metrics/tier-calibration.json`. If L1 devices consistently hit moderate memory pressure, the L1 feature set is too aggressive — bump `mdns_discovery` to L2, etc.
- C7.3 — Quarterly review: re-evaluate the tier boundaries based on the collected metrics. The boundaries in C1 are starting points, not permanent.

**Acceptance:** `tier-calibration.json` is updated weekly; the quarterly review is a documented process.

### C8. Performance benchmarking CI

**Tasks:**

- C8.1 — Add a `perf.yml` workflow that runs benchmarks on every PR touching `core/`, `transports/`, or `web/`:
  - Rust: `cargo bench` (criterion).
  - Python: `pytest-benchmark` on crypto operations and DB writes.
  - Web: `vitest bench` on the WASM core.
- C8.2 — Store benchmark results as JSON artifacts and compare against the `main` branch baseline. Fail the PR if any benchmark regresses by > 10%.
- C8.3 — Publish a "performance dashboard" (static HTML) to GitHub Pages on every release tag, showing the benchmark history.

**Acceptance:** a PR that adds 50ms to message encryption fails CI; the dashboard shows the regression.

---

## 7. Performance Optimization Plan (Workstream D)

This workstream optimizes the *working* parts of the project for speed on both low-spec and high-spec hardware. It complements Workstream C (which gates features) by making the features that *are* enabled faster.

### D1. Rust core optimization

**Tasks:**

- D1.1 — Audit `core/rust/src/protocol/double_ratchet.rs` (529 lines) for allocations in the hot path. The double ratchet's `encrypt` is called per-message; any `Vec::new()` or `clone()` in that path is a candidate for elimination. Use `smallvec` for fixed-size buffers.
- D1.2 — Audit `core/rust/src/protocol/mls.rs` (124 lines) — this is a stub. Real MLS (RFC 9420) is complex; the plan recommends using the `openmls` crate rather than implementing from scratch. The current 124-line file is not production-ready.
- D1.3 — Add `#[inline]` to small crypto helpers in `core/rust/src/crypto/` where the function is < 20 lines and called in hot paths.
- D1.4 — Use `zeroize::Zeroize` on all secret material; verify with `cargo audit` and a custom clippy lint that flags `Vec<u8>` holding keys without `Zeroize`.
- D1.5 — Enable Link-Time Optimization (`lto = "fat"`) and `codegen-units = 1` in `[profile.release]` for the Rust core. This slows compilation but improves runtime by 5–15%.
- D1.6 — Add `cargo bloat` to CI to track binary size regressions. The WASM bundle is shipped to web clients; every kilobyte matters on L0 devices.

**Acceptance:** `cargo bench` shows < 1ms for double-ratchet encrypt on an L2 device; `cargo bloat` shows no single function > 5% of binary size.

### D2. Python backend optimization

**Tasks:**

- D2.1 — Replace `requests` (used in `transports/p2p/routers/messages.py:7`) with `httpx.AsyncClient`. The current `requests` call blocks the event loop.
- D2.2 — Add connection pooling for the Tor SOCKS proxy. The current code opens a new SOCKS connection per request.
- D2.3 — Batch DB writes: group message inserts into a single `INSERT ... VALUES (...), (...), ...` every 1 second (or 50 messages, whichever is first). This is especially important on L0 devices where SQLite WAL fsync is expensive.
- D2.4 — Use `orjson` for all JSON serialization (already a dependency; verify it is used in FastAPI's `default_response_class`).
- D2.5 — Enable uvloop on Linux (already in `requirements.in`; verify it is conditionally imported in `app_v3.py` — currently it is not, the `uvloop` import is missing).
- D2.6 — Profile the `/v3/messages/history` endpoint with `py-spy` on a 10,000-message database. Optimize the SQL query (add indexes on `sender_onion, recipient_onion, sent_at`).

**Acceptance:** `/v3/messages/history` returns in < 100ms for 10,000 messages on an L2 device; `py-spy` shows no hot path in Python (only in SQLite).

### D3. Web client optimization

**Tasks:**

- D3.1 — Lazy-load the WASM core. The current `web/src/lib/core.ts` imports `./pkg/anonymus_core.js` statically, which blocks the initial render. Use `await import("./pkg/anonymus_core.js")` on first use.
- D3.2 — Virtualize the message list. The current `web/src/components/chat/` renders all messages; with 10,000 messages this is unusable. Use `@tanstack/solid-virtual` (or equivalent).
- D3.3 — Debounce the typing indicator and presence updates. The current socket emits on every keystroke.
- D3.4 — Use `localStorage` for the ratchet state (already done via `idb`); verify that the IndexedDB writes are batched.
- D3.5 — Code-split the WebRTC code path. The `web/src/stores/calls.ts` (157 lines) imports `socket.io-client` eagerly; lazy-load it only when the user initiates a call.
- D3.6 — Set `build.target = "esnext"` (already done) and enable `build.minify = "terser"` with `terser.compress.drop_console = true` in production.

**Acceptance:** Lighthouse score ≥ 90 on Performance, Accessibility, Best Practices, SEO for the production build on an L2 device simulating 4x CPU throttle.

### D4. Android optimization

**Tasks:**

- D4.1 — Enable R8 full mode in `android/app/build.gradle.kts`. The current config uses R8 minify but not full mode.
- D4.2 — Use `WorkManager` for background tasks instead of `PushService` (a foreground service). The current `PushService.kt` (297 lines) is a long-running foreground service that drains battery.
- D4.3 — Lazy-load the JNI crypto module. The current `JniCryptoProvider.kt` (161 lines) loads the native library at class init; defer to first use.
- D4.4 — Use `Room` (or the existing SQLite) with `Fts4` for full-text message search. The current `ChatManager.kt` does linear scans.
- D4.5 — Profile with `Macrobenchmark` on a low-end device (Pixel 4a or equivalent). Target: cold start < 2 seconds, message send < 500ms.

**Acceptance:** Macrobenchmark cold start < 2s on Pixel 4a; R8 full mode reduces APK size by ≥ 20%.

### D5. Database optimization

**Tasks:**

- D5.1 — Add indexes on `messages(sender_onion, recipient_onion, sent_at)`, `messages(recipient_onion, sent_at)`, `contacts(owner_onion, onion_address)`, `pre_key_bundles(onion_address)`, `one_time_prekeys(bundle_id, consumed_at)`.
- D5.2 — Enable SQLite WAL mode explicitly in `core/db/engine.py` (currently not set; the default is rollback journal which is slower for concurrent reads).
- D5.3 — Set `PRAGMA synchronous = NORMAL` (not `FULL`) for non-financial applications. This trades a small durability risk (last few ms of writes on power loss) for 2–3x write throughput.
- D5.4 — Set `PRAGMA mmap_size = 268435456` (256 MB) on desktop, 0 on mobile (mobile prefers page cache).
- D5.5 — Run `PRAGMA optimize` on every connection close (SQLite 3.18+).
- D5.6 — Vacuum the database weekly via a scheduled task (not at startup, which would block).

**Acceptance:** DB write throughput ≥ 5000 writes/sec on an L2 device (measured with `pytest-benchmark`); DB read latency for `/v3/messages/history` < 50ms for 10,000 messages.

### D6. Network optimization

**Tasks:**

- D6.1 — Enable HTTP/2 in Caddy (already default; verify).
- D6.2 — Enable Brotli compression in Caddy (currently only gzip).
- D6.3 — Add `Cache-Control: immutable` to WASM and static asset responses.
- D6.4 — Preload the WASM core with `<link rel="preload" href="/pkg/anonymus_core.js" as="fetch" crossorigin>` in `index.html`.
- D6.5 — Use a connection pool for Tor circuits (keep 2 warm circuits per peer; reuse for messages).
- D6.6 — Compress outbound message payloads with `zstd` before encryption (the ciphertext is then padded per the sealed-sender scheme, so the compression does not leak length information).

**Acceptance:** WASM load time < 200ms on L2; message round-trip over Tor < 2s median.

---

## 8. Branch Unification Plan (Workstream E)

This workstream unifies all branches into a single coherent `main` with a documented branch policy. Detailed step-by-step in §25; this section is the workstream framing.

### E1. Branch topology after unification

```
main (protected, requires PR + CI + code-owner review)
 ├── dev (integration branch; PRs from feature/* merge here first)
 ├── release/v3.0.0 (cut from main at tag time; only bugfixes)
 ├── feature/* (short-lived, deleted after merge)
 ├── fix/* (short-lived, deleted after merge)
 ├── dependabot/* (auto-managed; see §25.4)
 └── archive/* (tags only, not branches — see §25.5)
```

### E2. Branch policy

- **`main`**: protected, requires 1 review, requires all status checks, requires linear history, no force-push.
- **`dev`**: protected, requires 1 review, requires status checks (subset, faster), no force-push.
- **`release/*`**: protected, requires 2 reviews (security-sensitive), requires full status checks, no force-push.
- **`feature/*`, `fix/*`**: not protected, force-push allowed.
- **`dependabot/*`**: not protected, auto-merged by a scheduled job (see §25.4).

### E3. Workstream E tasks

The detailed task list is in §25.

---

## 9. Documentation Remediation (Workstream F)

### F1. Rewrite the README

The current `README.md` is 30 lines and links to non-existent docs (`docs/api/socket-io-events.md`). Rewrite to include:

- Project summary (3 sentences).
- Status badge row (CI, Codecov, SBOM, Reproducible Build, SLSA).
- Quick start (5 commands).
- Supported platforms (Web, Desktop, Android; iOS is not supported).
- Architecture diagram (the mermaid diagram from `prod_plan.md`).
- Links to: setup guide, self-hosting guide, architecture overview, API docs (auto-generated from OpenAPI), security policy, contribution guide.
- License (AGPL-3.0).

### F2. Fix the docs structure

- F2.1 — Generate `docs/api/` from the OpenAPI schema (use `redocly build-docs`).
- F2.2 — Remove `file:///` links; use repository-relative links.
- F2.3 — Consolidate `docs/historical/` into a single `docs/historical/index.md` that links to each historical document with a one-sentence summary. The 14,483 lines of historical docs are valuable but should not be in the primary navigation.
- F2.4 — Add `docs/roadmap/` with one file per platform (`web.md`, `android.md`, `ios.md`, `desktop.md`) documenting current status and next milestones.
- F2.5 — Add `docs/security/crypto-tiers.md` (from C6), `docs/security/threat-model.md`, `docs/security/disclosure.md`.

### F3. Add operator runbooks

- F3.1 — `docs/runbooks/deploy-relay.md`: step-by-step relay deployment.
- F3.2 — `docs/runbooks/rotate-secret-key.md`: how to rotate the session secret without logging out all users.
- F3.3 — `docs/runbooks/rotate-onion-address.md`: how to rotate the relay's onion address.
- F3.4 — `docs/runbooks/incident-response.md`: triage, containment, eradication, recovery, postmortem template.
- F3.5 — `docs/runbooks/panic-wipe.md`: what happens when a user triggers obliviate, and how to support them after.

### F4. Add developer onboarding

- F4.1 — `docs/contributing/setup.md`: clone, install deps, run tests, run locally.
- F4.2 — `docs/contributing/architecture.md`: how the layers fit together (Python backend, Rust core, Web client, Android, Desktop).
- F4.3 — `docs/contributing/coding-standards.md`: ruff, biome, rustfmt, clippy; commit message format; PR template.
- F4.4 — `docs/contributing/testing.md`: how to run each test suite, how to add tests, coverage requirements.
- F4.5 — `docs/contributing/release.md`: how to cut a release (tags, changelog, artifacts, attestation).

---

## 10. Release Engineering (Workstream G)

### G1. Release channels

- **`stable`**: tagged `vX.Y.Z` (no suffix). Production-ready.
- **`rc`**: tagged `vX.Y.Z-rc.N`. Release candidate; full CI + attestation but marked prerelease.
- **`beta`**: tagged `vX.Y.Z-beta.N`. Feature-complete but may have known issues.
- **`alpha`**: tagged `vX.Y.Z-alpha.N`. Not feature-complete; the current `v3.0.0-alpha.1` is in this channel.
- **`nightly`**: built from `main` every night at 02:00 UTC. Not tagged; published as a GitHub artifact. For testing only.

### G2. Release artifacts

Every `stable` and `rc` release attaches:

- **Web bundle**: `anonymus-web-vX.Y.Z.tar.gz` (static files, reproducible).
- **Desktop installers**: `AnonyMus-vX.Y.Z.dmg` (macOS), `.msi` (Windows), `.AppImage` (Linux).
- **Android APK**: `AnonyMus-vX.Y.Z.apk` (universal) and per-ABI splits.
- **Relay Docker image**: `ghcr.io/aryansinghnagar/anonymus-relay:vX.Y.Z` with SLSA attestation.
- **SBOM**: `sbom.spdx.json` and `sbom.cyclonedx.json`.
- **Reproducible build log**: `reproducible-build.log`.
- **Signed manifest**: `manifest.sig` (cosign signature over the SHA-256 of every artifact).
- **Changelog**: `CHANGELOG.md` entry.

### G3. Release process

1. Update `CHANGELOG.md` with the new version's entries.
2. Run `scripts/release-prepare.sh vX.Y.Z` which: creates a `release/vX.Y.Z` branch, bumps version in `pyproject.toml`, `Cargo.toml`, `web/package.json`, `android/app/build.gradle.kts`, commits, pushes.
3. CI runs on the release branch. If green, tag `vX.Y.Z` and push the tag.
4. The `release.yml` workflow triggers, builds all artifacts, attaches them to the GitHub Release, publishes the Docker image, signs the manifest.
5. Manual: write the release notes, publish the release.
6. Merge `release/vX.Y.Z` back to `main` (cherry-pick the version bump).

### G4. Rollback process

The current `rollback.sh` and `rollback.ps1` exist but are untested. The plan:

- G4.1 — Rewrite `rollback.sh` to: stop the relay, pull the previous tag's Docker image, update the docker-compose tag, restart. Test this in CI.
- G4.2 — Add a `rollback-test` job that runs after every release: deploy the new release, run a smoke test, roll back to the previous release, run the smoke test again. This verifies rollback works *before* it is needed.

### G5. Update strategy

- G5.1 — Web: the PWA auto-updates via the service worker. Force-update on critical security releases by bumping a `CACHE_VERSION` constant.
- G5.2 — Desktop: Tauri's auto-updater checks a JSON feed on startup; on update, downloads the new installer and prompts the user.
- G5.3 — Android: in-app update via the Play Core library (for Play Store distribution) or a manual download prompt (for direct APK distribution).
- G5.4 — Relay: the Docker image is tagged; operators pull the new tag and `docker compose up -d`. Document the migration path for breaking changes.

---

## 11. Observability (Workstream H)

### H1. Logging

- H1.1 — Standardize on `structlog` (already a dependency). Every log entry has: `timestamp`, `level`, `event`, `request_id`, `user_id` (if authenticated), `tier`, `feature_flags`, and event-specific fields.
- H1.2 — In production, logs are JSON to stdout. In development, logs are colored text to stderr.
- H1.3 — Never log: session tokens, password hashes, private keys, message ciphertext (only the message ID and length), onion addresses (only the first 12 characters).
- H1.4 — Add a `log-test` CI job that scans the codebase for `logger.info(.*password` etc. and fails on matches.

### H2. Metrics

- H2.1 — Prometheus metrics (already partially implemented in `app_v3.py`): `anonymus_http_requests_total`, `anonymus_http_request_duration_seconds`, `anonymus_messages_sent_total`, `anonymus_messages_received_total`, `anonymus_active_sessions`, `anonymus_tor_circuits`, `anonymus_memory_pressure_events`, `anonymus_capability_tier`.
- H2.2 — Expose `/metrics` on a separate port (9090) in production, not on the main app port. This prevents leaking metrics to unauthenticated users.
- H2.3 — Add a Grafana dashboard JSON in `docs/observability/grafana-dashboard.json`.

### H3. Tracing

- H3.1 — Add OpenTelemetry tracing (already a setting `otel_endpoint`). Instrument: HTTP requests, DB queries, Tor circuit establishment, crypto operations (the Rust core exposes timing spans via the FFI).
- H3.2 — Sample at 10% in production, 100% in development.

### H4. Error monitoring

- H4.1 — Sentry (already a dependency). Configure `before_send` to scrub onion addresses, session tokens, and message content.
- H4.2 — Add a `sentry-test` CI job that artificially triggers an exception and verifies it appears in Sentry.

---

## 12. Security Hardening Beyond the Prior Audit (Workstream I)

### I1. Threat model

- I1.1 — Write `docs/security/threat-model.md` covering: network adversary (ISP, exit node), relay operator (honest-but-curious), malicious peer, device theft, coerced user (duress code), supply-chain attacker (dependency compromise).
- I1.2 — For each threat, document: the asset, the adversary's capability, the system's defense, the residual risk.

### I2. Dependency supply chain

- I2.1 — Run `pip-audit`, `cargo audit`, `npm audit` in CI. Fail on any high-severity advisory.
- I2.2 — Pin all dependencies by hash (`requirements.txt` already does this; verify `Cargo.lock` and `package-lock.json` are committed).
- I2.3 — Use `cosign`-signed base images for Docker where available (the `python:3.12-alpine` image is signed by Python; verify with `cosign verify`).
- I2.4 — Add a `deps-review.yml` workflow that runs on every PR and comments with the dependency diff (added/removed/upgraded packages).

### I3. Secret management

- I3.1 — Audit the repo for committed secrets with `gitleaks` in CI.
- I3.2 — Document the secret rotation process for: `SECRET_KEY`, `SENTRY_DSN`, `CODECOV_TOKEN`, Tor relay identity key, signing keys for releases.
- I3.3 — Use `age` or `sops` to encrypt secrets at rest in the repo if any must be committed (none should).

### I4. Fuzzing

- I4.1 — Add `cargo fuzz` targets for the Rust core: `double_ratchet_encrypt`, `x3dh_initiate`, `ml_kem_encaps`, `padding_pad`, `sealed_sender_seal`.
- I4.2 — Run fuzzing in CI for 5 minutes per target on every PR, 1 hour per target on every release.
- I4.3 — Add a `fuzzing.yml` scheduled workflow that runs overnight fuzzing for 8 hours.

### I5. Penetration testing

- I5.1 — Before the `stable` release, commission an external penetration test by a firm experienced with Tor-aware applications.
- I5.2 — Scope: the relay server, the P2P node, the web client, the Android app, the Rust crypto core.
- I5.3 — Remediate all findings before the `stable` release; document unremediated findings as accepted risk in `docs/security/accepted-risk.md`.

### I6. Cryptographic review

- I6.1 — Commission a cryptographic review of: the double ratchet implementation, the X3DH implementation, the MLS usage (once `openmls` is integrated), the sealed-sender scheme, the padding scheme, the capability-tier crypto parameters (from C6).
- I6.2 — The reviewer should have published academic work on messaging security or have audited Signal, Wire, or Session.

---

## 13. Testing Strategy (Workstream J)

### J1. Test pyramid

- **Unit**: Rust (`cargo test`), Python (`pytest` unit), TypeScript (`vitest`), Kotlin (`./gradlew test`). Target: 80% line coverage on `core/`, `transports/`, `core/rust/src/`.
- **Integration**: `tests/integration/` — end-to-end API flows, contract tests, migration tests.
- **System**: `tests/system/` — full stack via Docker Compose, including Tor (in a sandboxed mode), two-browser chat, WebRTC call.
- **Adversarial**: `tests/adversarial/` — the authorization tests from B4, B5, B7; fuzzing; chaos engineering.

### J2. Coverage gates

- J2.1 — Python: 80% on `core/`, `transports/`. Enforced by `pytest --cov-fail-under=80`.
- J2.2 — Rust: 80% on `core/rust/src/`. Enforced by `cargo tarpaulin --fail-under 80`.
- J2.3 — TypeScript: 70% on `web/src/`. Enforced by `vitest --coverage.thresholds.lines=70`.
- J2.4 — Kotlin: 60% on `android/app/src/main/`. Enforced by `./gradlew jacocoTestReport` with a threshold check.

### J3. Test environments

- J3.1 — CI: GitHub Actions runners (the current setup).
- J3.2 — Local: `docker compose -f docker-compose.test.yml up` boots a full test stack with mock Tor.
- J3.3 — Staging: a dedicated relay (clearnet + onion) for manual testing before release.

### J4. Performance tests

- J4.1 — `pytest-benchmark` on crypto operations (encrypt, decrypt, ratchet step, MLS add member).
- J4.2 — `k6` load tests on the relay: 1000 concurrent connections, 100 messages/sec for 10 minutes.
- J4.3 — `cargo bench` (criterion) on the Rust core, tracked over time.

### J5. Compatibility tests

- J5.1 — Python 3.12 and 3.13 (when released).
- J5.2 — Node 22 LTS and 24 (when released).
- J5.3 — Rust stable and MSRV (minimum supported Rust version; document in `core/rust/Cargo.toml`).
- J5.4 — Android API 24–35 (Android 7.0–15).
- J5.5 — Browser matrix: Chrome (latest 2), Firefox (latest 2), Safari (latest 2), Tor Browser (latest).

---

## 14. Specific Bug Catalogue (Verified)

This section lists every verified bug with file:line references. It is the consolidated, deduplicated catalogue — the prior audit's I-01 through I-15 are cross-referenced, and additional bugs found in this audit are added.

| ID | Severity | Area | File:line | Description | Resolved by |
|---|---|---|---|---|---|
| B-001 | Critical | CI | `.github/workflows/{android,ci-health,codeql,ios,js,python,rust,sbom,semgrep,web}.yml` | `branches: ain]` corruption (10 files) | A1 |
| B-002 | Critical | API | `transports/p2p/routers/auth.py:109-133` vs `web/src/lib/api.ts:94-98` | Login returns `UserResponse`; client expects `{success, user}` | B1 |
| B-003 | Critical | API | `transports/p2p/routers/contacts.py:45-50,107-128` vs `web/src/lib/api.ts:19-26,107-118` | Contact field mismatch (`id`/`owner_onion`/`added_at` vs `onion_address`/`nickname`/`verified`) | B1 |
| B-004 | Critical | API | `transports/p2p/routers/messages.py:43-71,115-146` vs `web/src/lib/api.ts:28-38,122-147` | Message endpoint mismatch (`/send`+`/history/{peer}` vs `/`+`/{onion}`); `disappears_at` vs `disappears_in_seconds` | B1 |
| B-005 | Critical | Deployment | `docker-compose.yml` vs `Dockerfile.relay` | Compose starts relay but web client expects P2P node | B2 |
| B-006 | Critical | Deployment | `docker-compose.yml` (Caddy env) | `RELAY_DOMAIN` set only on relay, not Caddy | B2 |
| B-007 | Critical | Deployment | `.env.example` | Defines `FLASK_SECRET_KEY`/`FLASK_DEBUG`; v3 reads `SECRET_KEY`/`ENVIRONMENT` | B2 |
| B-008 | Critical | Deployment | `docker-compose.yml` (frontend-builder) | Does not build WASM; production bundle has broken import | B2, A6 |
| B-009 | Critical | Schema | `core/db/models.py` vs `alembic/versions/0001_initial_schema.py` | `messages.id` (int PK in ORM) vs `message_id` (UUID PK in migration); `users.last_seen` missing in migration | B3 |
| B-010 | Critical | Schema | `tests/conftest.py:47`, `tests/integration/test_fastapi_v3.py:30` | Tests use `Base.metadata.create_all()`; production uses Alembic — tests pass against a schema prod never uses | B3 |
| B-011 | High | Security | `transports/p2p/routers/keys.py` (OPK storage) | OPKs stored as JSON list; concurrent consumption not atomic | B4 |
| B-012 | High | Security | `transports/p2p/routers/keys.py` (no signature verification) | Published bundle's signatures not verified before storage | B4 |
| B-013 | High | Security | `transports/p2p/routers/keys.py` (public fetch) | No rate limit on OPK fetch; pool can be drained | B4, B7 |
| B-014 | High | AuthZ | `transports/p2p/routers/groups.py:145-177` | Group posting lacks membership check | B5 |
| B-015 | High | Privacy | `web/vite.config.ts:25-33` (per prior audit) | PWA `NetworkFirst` cache for `/v3/` routes — **verify in current snapshot** | B9 |
| B-016 | High | CI | `.github/workflows/python.yml:73-77` | `pytest ... \|\| true` masks legacy test failures | A2 |
| B-017 | High | CI | `.github/workflows/web.yml:772` | `continue-on-error: true` on WASM build | A2, A6 |
| B-018 | High | Config | `pyproject.toml` (no runtime deps) vs `requirements.txt` vs `python.yml:42-62` | Three sources of truth for Python deps | B12 |
| B-019 | High | Migration | `core/transport_registry.py:35-47` | Mode switch returns success after caught handoff/stop exception | B8 |
| B-020 | Medium | Security | `transports/p2p/app_v3.py` (RateLimiterMiddleware) | Global rate limit only; no auth-specific limit | B7 |
| B-021 | Medium | Privacy | `web/index.html` (per prior audit) | Google Fonts leak — **already fixed in current snapshot** | (done) |
| B-022 | Medium | Web | `web/src/lib/core.ts` vs `web/src/pkg/anonymus_core.js` | Static import of missing WASM module | A6, B9 |
| B-023 | Medium | Web | `web/vite.config.ts` (manifest icons) | References `logo-192.png`, `logo-512.png` — **now present in `web/public/`** | (done) |
| B-024 | Medium | API | `transports/p2p/routers/messages.py:120-146` | `before_id` accepted but never used in SQL | B1 |
| B-025 | Medium | Persistence | `transports/p2p/routers/node.py`, `routers/notifications.py` | Module-global `_config` and token dicts; not durable, not isolated | B6 |
| B-026 | Medium | Docs | `README.md` | Links to non-existent `docs/api/socket-io-events.md` with `file:///` URL | F1 |
| B-027 | Medium | Docs | `docs/guides/setup.md`, `docs/guides/self-hosting.md` | Divergent port/path/DB references vs root compose | F2, B2 |
| B-028 | Low | CI | `.github/workflows/ios.yml:347-348` | iOS is a placeholder (`echo "iOS validation placeholder"`) | B11 |
| B-029 | Low | CI | `scripts/ci-preflight.sh` | Preflight returns `skip=true` for missing required components | A4 |
| B-030 | Low | Web | `web/src/stores/calls.ts` | Eager import of `socket.io-client` for WebRTC | D3 |
| B-031 | Low | Backend | `transports/p2p/routers/messages.py:7` | `import requests` (blocking) in async router | D2 |
| B-032 | Low | Backend | `transports/p2p/app_v3.py` | `uvloop` not imported even on Linux | D2 |
| B-033 | Low | Rust | `core/rust/src/protocol/mls.rs` (124 lines) | Stub MLS implementation; not production-ready | D1 |
| B-034 | Low | Android | `android/app/src/main/java/com/anonymus/app/data/ChatManager.kt:824-825` | `Unresolved reference 'iv'`, `'ciphertext'` | B10 |
| B-035 | Low | iOS | `ios/AnonyMusApp.swift` | Hardcoded passcodes `1337`/`9999`; not a real app | B11 |
| B-036 | Low | Rust | `core/rust/Cargo.toml` (no LTO) | Release profile lacks `lto = "fat"` | D1 |
| B-037 | Low | DB | `core/db/engine.py` | No `PRAGMA synchronous`, `mmap_size`, `journal_mode = WAL` | D5 |
| B-038 | Low | Release | `rollback.sh`, `rollback.ps1` | Untested rollback scripts | G4 |
| B-039 | Low | Release | `.github/workflows/reproducible-build.yml` | Builds non-existent `build/Dockerfile`; compares tarball SHA (not reproducible) | A5 |
| B-040 | Low | Release | `.github/workflows/release.yml` | No SBOM, no attestation, no signed manifest | A8 |

### 14.1 Bugs introduced or worsened by the v3 migration (not in prior audit)

| ID | Severity | Area | Description |
|---|---|---|---|
| B-041 | Critical | CI | The YAML `ain]` corruption was introduced by the `43337f6` commit ("ci: stand up the 14 CI/CD workflows") and was not caught because the workflows that would have caught it (`ci-health.yml` runs `actionlint`) were themselves corrupted and never ran. |
| B-042 | High | Branch | 16 Dependabot branches accumulated without a merge policy; several (pyo3 0.22→0.29, TypeScript 5→7) are breaking changes that cannot be auto-merged. |
| B-043 | Medium | Crypto | `core/rust/src/protocol/mls.rs` is a 124-line stub advertised as "MLS RFC 9420 engine" in the v3.0.0-alpha.1 release notes. This is a documentation-vs-implementation mismatch. |
| B-044 | Medium | Performance | No capability detection anywhere in the stack; every feature is on by default regardless of device. |

---

## 15. Build Order & Sequencing

The workstreams are sequenced so that each milestone produces a demonstrable improvement. The total scope is ~90 tasks; the critical path is ~12 weeks for one engineer, ~6 weeks for two.

### Phase 0: Triage (Week 1)

- A1 (rewrite YAML triggers) — unblocks all CI.
- A4 (fail-closed preflight) — prevents false greens.
- F1 (rewrite README) — the public face of the project.

**Milestone 0:** CI runs on every PR; no workflow is silently skipped; the README is accurate.

### Phase 1: Unfreeze (Weeks 2–3)

- A2, A3, A6, A9 (eliminate masking, dedupe Python workflow, fix WASM, sweep action versions).
- B2 (fix Compose topology).
- B12 (consolidate deps).
- A7 (branch protection).

**Milestone 1:** a clean `docker compose --profile node up` produces a working node + web client on a fresh checkout; CI is green and meaningful.

### Phase 2: Contract freeze (Weeks 3–4)

- B1 (API contract).
- B3 (schema authority).
- B10 (Android Kotlin).

**Milestone 2:** the contract test suite passes end-to-end (register → login → contacts → send → history → delete); the Android app compiles.

### Phase 3: Security hardening (Weeks 4–6)

- B4, B5, B6, B7, B8 (pre-key, groups, persistence, rate-limit, transport switch).
- B9 (privacy behaviors).
- B11 (iOS placeholder removal).
- I1, I2, I3 (threat model, supply chain, secrets).

**Milestone 3:** all authorization tests pass; the threat model is documented; `pip-audit`/`cargo audit`/`npm audit` are clean.

### Phase 4: Performance adaptation (Weeks 6–8)

- C1–C8 (capability tiers, detection, gating, memory pressure, CPU concurrency, adaptive crypto, calibration, benchmarking).
- D1–D6 (Rust, Python, Web, Android, DB, network optimization).

**Milestone 4:** an L0 device (simulated by capping RAM to 1 GB and cores to 2) runs the web client and Android app without crashing; benchmarks show no regression.

### Phase 5: Branch unification (Week 8)

- §25 (detailed step-by-step).

**Milestone 5:** a single `main` with `dev` and `release/*` branches; 16 Dependabot branches resolved; archive tags documented.

### Phase 6: Release engineering (Weeks 9–10)

- A5, A8 (reproducible build, attested release).
- G1–G5 (release channels, artifacts, process, rollback, update strategy).
- H1–H4 (observability).

**Milestone 6:** tagging `v3.0.0-rc.1` produces a release with SBOM, attestation, reproducible build log, and signed manifest; rollback is tested.

### Phase 7: Hardening for stable (Weeks 10–12)

- I4, I5, I6 (fuzzing, pen test, crypto review).
- J1–J5 (testing strategy, coverage gates, environments, performance, compatibility).
- F2–F4 (docs, runbooks, onboarding).

**Milestone 7:** the external penetration test is clean; the crypto review is signed off; coverage gates are met; docs are complete.

### Phase 8: Stable release (Week 12+)

- Tag `v3.0.0`.
- Publish to all channels.
- Begin the post-release monitoring loop (§16).

---

## 16. Post-Release Monitoring & Maintenance

### 16.1 Monitoring

- Sentry error rate < 0.1% of sessions.
- CI health: < 5% workflow failure rate over 7 days.
- Reproducible build: 100% success over 30 days.
- SBOM freshness: regenerated on every release.
- Dependency advisories: triaged within 48 hours.

### 16.2 Maintenance cadence

- **Daily**: CI health digest (A10.2).
- **Weekly**: tier-calibration metrics (C7), CI metrics JSON (A10.3).
- **Monthly**: dependency refresh PR ( Dependabot with grouped updates), base image digest refresh (A5.3).
- **Quarterly**: capability tier boundaries review (C7.3), threat model review, penetration test (if major changes).
- **Annually**: full cryptographic review, AGPL compliance review.

### 16.3 Incident response

- Severity 1 (data leak, key compromise): page on-call, public disclosure within 72 hours, rotate all secrets, release patched version within 24 hours.
- Severity 2 (security bug, no leak): patch within 7 days, release within 14 days.
- Severity 3 (functional bug): patch in next release.
- Severity 4 (cosmetic): backlog.

---

## 17. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The YAML corruption fix uncovers more broken workflows than expected | High | Medium | Phase 0 is scoped to discovery; if > 14 workflows are broken, halt and re-audit. |
| The contract freeze (B1) breaks existing alpha users | High | High | Provide a migration endpoint `/v3/compat/legacy-login` for 30 days post-release; document in `docs/migrations/v3-contract.md`. |
| The Alembic reconciliation (B3) requires destructive migration on existing alpha DBs | Medium | High | Write the migration to be idempotent; test against a copy of the production alpha DB; provide a rollback path. |
| The capability tier crypto parameters (C6) are too aggressive | Medium | High | Require cryptographic review (I6) before shipping; default to L1 parameters on all tiers until review is complete. |
| The branch unification (§25) loses commits from Dependabot branches | Low | Medium | All Dependabot changes are recreatable; tag the deleted branches as `archive/dependabot/<name>` before deletion. |
| The external pen test finds a critical vulnerability | Medium | Critical | Schedule the pen test in Phase 7, not Phase 8; budget 2 weeks for remediation before the stable release. |
| The reproducible build never achieves bit-identical output | Medium | Medium | Accept OCI manifest reproducibility (not tarball reproducibility) as the bar; document the distinction in `docs/guides/reproduce-build.md`. |
| The MLS integration (D1.2) via `openmls` is incompatible with the existing protocol | Medium | High | Run the `openmls` integration in a `feature/mls-openmls` branch; do not merge until the MLS group operations pass the existing test suite. |
| The Android R8 full mode (D4.1) breaks reflection-based code | Medium | Medium | Test on a release build before merging; keep a `release-minify-off` flavor as a fallback. |
| The TypeScript 5→7 bump (Dependabot) breaks the web build | High | Medium | Pin TypeScript to `~5.5` in `web/package.json` until the migration is tested; close the Dependabot PR with a comment. |
| The pyo3 0.22→0.29 bump (Dependabot) breaks the Python FFI | High | High | Pin pyo3 to `0.22` until the migration is tested on a feature branch; the breaking changes are documented in the pyo3 changelog. |

---

## 18. Acceptance Criteria for `v3.0.0` (Stable)

A release is `stable` when **all** of the following are true:

1. **CI**: all 11 required status checks pass on `main` and on the release branch. No `|| true` or `continue-on-error` in any workflow (except documented exceptions in `.github/CI_EXCEPTIONS.md`).
2. **Contract**: the contract test suite (`tests/integration/test_contract_v3.py`) passes; the OpenAPI schema is in sync with the web client types.
3. **Schema**: `alembic upgrade head` on a fresh DB produces a schema matching `Base.metadata`; the schema-drift test passes.
4. **Security**: all authorization tests pass; `pip-audit`, `cargo audit`, `npm audit` are clean; the external pen test report has no unresolved Severity 1 or 2 findings; the crypto review is signed off.
5. **Privacy**: no authenticated API response is service-worker cached; no third-party font or resource request is made; the WASM core is present in the production build.
6. **Deployment**: `docker compose --profile node up -d` produces a healthy node on a fresh checkout; the smoke test passes.
7. **Performance**: on an L0 device (1 GB RAM, 2 cores), the web client loads in < 5 seconds, sends a message in < 2 seconds, and does not crash under memory pressure; on an L2 device, all benchmarks are within 10% of the baseline.
8. **Reproducibility**: two consecutive builds of the relay Docker image produce identical OCI manifests; the attestation verifies.
9. **Artifacts**: the GitHub Release includes the web bundle, desktop installers, Android APK, Docker image, SBOM (SPDX + CycloneDX), reproducible build log, and signed manifest.
10. **Documentation**: the README is accurate; the setup guide works on a fresh clone; the runbooks exist; the threat model is documented.
11. **Branches**: `main` is protected; `dev` exists; no Dependabot branch is older than 30 days; archive tags are documented.
12. **Rollback**: the rollback test passes (deploy new, smoke test, rollback, smoke test).

---

## 19. Tools and Infrastructure Required

### 19.1 CI/CD

- GitHub Actions (current).
- GitHub Packages (for Docker images).
- GitHub Attestations (for SLSA provenance).
- Codecov (for coverage).
- CodeQL (for SAST).
- Semgrep (for SAST).
- Scorecard (for security posture).
- Zizmor (for workflow security).
- Actionlint, yamllint (for workflow linting).

### 19.2 Security

- Cosign (for signing).
- Syft (for SBOM).
- CycloneDX (for SBOM).
- Gitleaks (for secret scanning).
- Cargo-audit, pip-audit, npm-audit (for dependency advisories).
- Cargo-fuzz (for fuzzing).
- OpenMLS (for MLS — pending D1.2).

### 19.3 Observability

- Sentry (error monitoring).
- Prometheus + Grafana (metrics).
- OpenTelemetry (tracing).
- structlog (logging).

### 19.4 Performance

- Criterion (Rust benchmarks).
- pytest-benchmark (Python benchmarks).
- vitest bench (Web benchmarks).
- Macrobenchmark (Android benchmarks).
- py-spy (Python profiling).
- Lighthouse (Web performance).
- k6 (load testing).

### 19.5 Documentation

- MkDocs (current; verify it builds).
- Redocly (OpenAPI docs).
- Mermaid (diagrams; already used).

---

## 20. Glossary

- **AEAD**: Authenticated Encryption with Associated Data.
- **AGPL**: GNU Affero General Public License.
- **ASGI**: Asynchronous Server Gateway Interface.
- **CDN**: Content Delivery Network.
- **CI/CD**: Continuous Integration / Continuous Deployment.
- **CORS**: Cross-Origin Resource Sharing.
- **CSRF**: Cross-Site Request Forgery.
- **DB**: Database.
- **FFI**: Foreign Function Interface.
- **FSM**: Finite State Machine.
- **GHA**: GitHub Actions.
- **HKDF**: HMAC-based Key Derivation Function.
- **HTTP**: Hypertext Transfer Protocol.
- **KAT**: Known Answer Test.
- **KDF**: Key Derivation Function.
- **L0–L3**: Capability tiers (defined in §6.C1).
- **MLS**: Messaging Layer Security (RFC 9420).
- **mTLS**: Mutual TLS.
- **OCI**: Open Container Initiative.
- **OPK**: One-Time Pre-Key.
- **ORM**: Object-Relational Mapping.
- **P2P**: Peer-to-Peer.
- **PWA**: Progressive Web App.
- **PR**: Pull Request.
- **RFC**: Request for Comments.
- **SARIF**: Static Analysis Results Interchange Format.
- **SBOM**: Software Bill of Materials.
- **SDK**: Software Development Kit.
- **SLSA**: Supply-chain Levels for Software Artifacts.
- **SPA**: Single-Page Application.
- **SSE**: Server-Sent Events.
- **STUN/TURN**: Session Traversal Utilities for NAT / Traversal Using Relays around NAT.
- **UI**: User Interface.
- **WAL**: Write-Ahead Logging.
- **WASM**: WebAssembly.
- **WSGI**: Web Server Gateway Interface.
- **X3DH**: Extended Triple Diffie-Hellman.

---

## 21. Document Provenance and Confidence

This plan was produced by:

1. Cloning `https://github.com/aryansinghnagar/AnonyMus` at the `v3.0.0-alpha.1` tag.
2. Reading all 14 workflow YAML files (`od -c` for byte-level inspection).
3. Reading all Python source in `core/`, `transports/p2p/`, `transports/relay/`.
4. Reading the Rust source in `core/rust/src/`.
5. Reading the web client in `web/src/`.
6. Reading the Android source in `android/app/src/main/java/com/anonymus/app/`.
7. Reading the deployment files (`docker-compose.yml`, `Dockerfile.relay`, `Caddyfile.docker`, `torrc.docker`).
8. Reading the prior audit and remediation documents in `docs/audits/` and `docs/historical/`.
9. Cross-referencing findings with the prior audit's issue IDs (I-01 through I-15).
10. Inspecting branch topology via `git branch -a` and `git log --all --oneline --graph`.

**Confidence summary:**

- **High confidence** (directly verified): B-001 (YAML corruption), B-005 through B-010 (deployment/schema), B-011 through B-014 (security), B-016 through B-019 (CI/config), B-024 through B-027 (API/docs), B-028 through B-040 (low-severity), B-041 (CI regression), B-042 (branch accumulation), B-044 (no capability detection).
- **Moderate confidence** (inferred): B-015 (PWA caching — prior audit says present; current snapshot needs verification of `runtimeCaching`), B-043 (MLS stub advertised as engine).
- **Low confidence** (inferred from logs): the runtime CI failures in the prior audit (Android Kotlin, Docker digest, SBOM action versions) — these were verified by the prior audit but not re-verified in this audit because the workflows do not run (B-001).

Where confidence is moderate or low, the plan names the verification step required to confirm.

---

## 22. Consolidated Risk Register

(See §17 for the full table. This section is the executive view.)

The top five risks, in priority order:

1. **The contract freeze (B1) breaks existing alpha users.** Mitigation: 30-day compat endpoint, documented migration.
2. **The capability tier crypto parameters (C6) are too aggressive.** Mitigation: cryptographic review required before shipping; default to L1 parameters until reviewed.
3. **The external pen test finds a critical vulnerability.** Mitigation: schedule in Phase 7, budget 2 weeks for remediation.
4. **The MLS `openmls` integration (D1.2) is incompatible.** Mitigation: feature branch, do not merge until tests pass.
5. **The pyo3 0.22→0.29 bump breaks the Python FFI.** Mitigation: pin to 0.22, test on feature branch, follow pyo3 migration guide.

---

## 23. Decision Log

Decisions made in this plan, with rationale:

| Decision | Rationale | Alternatives considered |
|---|---|---|
| Use `openmls` for MLS rather than the 124-line stub | The stub is not production-ready; `openmls` is the de facto Rust MLS implementation and is used by Mozilla, Wire, and others. | Continue the stub (rejected: not safe for commercial release). |
| Use `pyo3` pinned at 0.22 until tested | pyo3 0.29 has breaking changes; auto-merging the Dependabot PR would break the FFI. | Auto-merge (rejected: too risky). |
| Use TypeScript ~5.5 until tested | TS 7.0 is a major version bump; the web build is untested on it. | Auto-merge (rejected). |
| Delete the iOS workflow | The iOS app is a 50-line placeholder; the workflow is `echo "placeholder"`. | Keep with a real `xcodebuild` step (rejected: no real iOS app to build). |
| Make `dev` a real branch | Currently all work lands on `main`; a `dev` branch allows integration testing before `main`. | Continue without `dev` (rejected: too risky for commercial release). |
| Use `slowapi` for rate limiting | It is the standard FastAPI rate limiter; the custom `RateLimiterMiddleware` is too simplistic. | Keep the custom middleware (rejected: no auth-specific limits). |
| Use `cosign` for signing | It is the CNCF standard for artifact signing; integrates with GitHub Attestations. | Use PGP (rejected: outdated); use `sigstore` directly (rejected: `cosign` is the CLI). |
| Use capability tiers L0–L3 | Four tiers cover the device range without being too granular. | Three tiers (rejected: not enough granularity for low-end Android); five tiers (rejected: too complex). |
| Default to L1 crypto parameters until crypto review | The C6 parameter sets are aggressive; the crypto review (I6) may require changes. | Ship L0/L1/L2/L3 parameters immediately (rejected: too risky before review). |
| Use `alembic upgrade head` in production, not `create_all` | `create_all` cannot upgrade an existing schema; Alembic is the standard. | Keep `create_all` (rejected: does not handle schema evolution). |
| Make `build/Dockerfile` and `Dockerfile.relay` explicit | The reproducible-build workflow references `build/Dockerfile` which does not exist. | Delete `build/Dockerfile` reference (rejected: it may be intended for a different image). |

---

## 24. Open Questions

Questions that require maintainer input before implementation:

1. **Commercial offering model**: is the commercial release the same codebase as the open-source release, or is there a separate commercial fork? (Affects: AGPL compliance, feature gating, licensing of proprietary components.)
2. **iOS timeline**: is iOS a real target for v3.0.0, or is it post-stable? (Affects: whether to keep the iOS workflow, whether to scope an iOS workstream.)
3. **MLS requirement**: is MLS (RFC 9420) a hard requirement for v3.0.0, or can large groups fall back to pairwise for the stable release? (Affects: whether `openmls` integration is on the critical path.)
4. **Relay operator model**: are relays operated by the project (centralized), by partners (federated), or by anyone (decentralized)? (Affects: relay monitoring, SLA, abuse handling.)
5. **Account recovery**: if a user loses their device, is there any account recovery path, or is loss of the ratchet state total? (Affects: whether to implement a recovery code feature, which has security implications.)
6. **Tor dependency**: is Tor a hard requirement, or can the app function over clearnet for users who do not need anonymity? (Affects: the default `tor_enabled` setting, the UX of first-run.)
7. **Push notifications**: the current implementation stores push tokens; is there a push provider (FCM, APNs, self-hosted), or are notifications best-effort via the open socket? (Affects: B6 implementation, battery life on mobile.)

These questions do not block the plan; they are flagged for maintainer decision before the relevant workstream begins.

---

## 25. Unified Branch Merge Strategy (Detailed Step-by-Step)

This section is the detailed execution plan for Workstream E (§8). It is the most operationally sensitive part of the plan because it rewrites the branch topology of a public repository.

### 25.1 Pre-conditions

Before starting:

- §4.A1 is complete (all workflow YAML is fixed).
- §4.A7 is complete (branch protection is configured — but see 25.7 for the order).
- The maintainer has a local clone with `origin` pointing to `aryansinghnagar/AnonyMus`.
- A backup of the repository has been taken (`git clone --mirror` to a safe location).
- The maintainer has notified all collaborators (if any) that branch topology is changing.

### 25.2 Step 1: Create the `dev` branch

```bash
git checkout main
git pull origin main
git checkout -b dev
git push origin dev
```

Configure branch protection on `dev` (in GitHub UI or via `gh api`):
- Require PR review (1 approval).
- Require status checks: `ci-health`, `python (test)`, `rust (validate)`, `web (lint-and-type-check)`, `web (test)`. (Subset of `main`'s required checks, for faster feedback.)
- Require linear history.
- No force-push.

### 25.3 Step 2: Create the `release/v3.0.0` branch

```bash
git checkout main
git checkout -b release/v3.0.0
git push origin release/v3.0.0
```

Configure branch protection on `release/v3.0.0`:
- Require PR review (2 approvals, including a code-owner).
- Require all status checks (same as `main`).
- Require linear history.
- No force-push.

This branch is where `v3.0.0` release candidates are tagged. After `v3.0.0` is released, the branch stays for backporting critical fixes (as `v3.0.x`).

### 25.4 Step 3: Resolve the 16 Dependabot branches

The 16 branches fall into three categories:

**Category A: Auto-mergeable (low risk, no breaking changes).**

These can be merged via the GitHub Dependabot UI or `gh pr merge --squash --auto`:

- `dependabot/cargo/hkdf-0.13.0` (minor bump).
- `dependabot/cargo/chacha20poly1305-0.11.0` (minor bump).
- `dependabot/cargo/thiserror-2.0.18` (major but typically non-breaking for consumers).
- `dependabot/cargo/jni-0.22.4` (minor bump).
- `dependabot/github_actions/*` (6 PRs) — **after** §4.A9 is done, these are stale; close them.
- `dependabot/gradle/android/com.google.crypto.tink-tink-android-1.23.0`.
- `dependabot/gradle/android/com.google.zxing-core-3.5.4`.
- `dependabot/gradle/android/com.goterl-lazysodium-android-5.2.0`.
- `dependabot/gradle/android/io.socket-socket.io-client-2.1.2`.
- `dependabot/gradle/android/org.jetbrains.kotlinx-kotlinx-coroutines-test-1.11.0`.
- `dependabot/npm_and_yarn/packages/typescript-sdk/types/node-26.1.1`.
- `dependabot/pip/sentry-sdk-2.65.0`.
- `dependabot/pip/uvloop-gte-0.22.1`.

**Category B: Breaking changes requiring manual integration.**

These cannot be auto-merged; they require a feature branch and testing:

- `dependabot/cargo/pyo3-0.29.0` — pyo3 0.22 → 0.29 is a multi-version jump with breaking changes to the `Py` types and the `#[pyfunction]` macro. Create `feature/pyo3-upgrade`, cherry-pick the Dependabot commit, fix compilation errors, run the Rust test suite, run the Python FFI smoke test, merge to `dev` (not `main`), then merge `dev` to `main` after CI passes.
- `dependabot/npm_and_yarn/packages/typescript-sdk/typescript-7.0.2` — TypeScript 5 → 7 is a major version bump. Create `feature/ts-upgrade`, cherry-pick, run `tsc -b`, fix type errors, run `vitest`, merge to `dev`, then `dev` to `main`.

**Category C: Already-stale (the bump has been applied manually).**

After §4.A9, the GitHub Actions version bumps in the Dependabot PRs are obsolete. Close those 6 PRs with a comment: "Superseded by manual action-version sweep in commit <SHA>."

### 25.5 Step 4: Convert branch-like tags to real tags

The three `archive/*` "tags" are currently both tags and (in some workflows) references. Convert them to tags only (not branches) and document their provenance:

```bash
# Verify they are tags (not branches)
git tag -l "archive/*"

# If any are branches, delete the branch refs (keep the tag refs)
# (In the current audit, they are tags only, so no action is needed.)

# Document their provenance
cat > docs/historical/branch-provenance.md <<'EOF'
# Branch Provenance

This document records the lineage of archived branches/tags.

| Tag | Commit | Date | Purpose |
|---|---|---|---|
| `archive/backup-central` | `3708104c` | 2026-06-24 | Legacy central-server architecture backup, pre-P2P migration. |
| `archive/backup-p2p` | `332d7423` | 2026-06-25 | Legacy P2P architecture backup, pre-v3 migration. |
| `pre-migration-checkpoint` | `c0ee4866` | 2026-06-25 | Snapshot before the v3 FastAPI migration. |
| `v1.0.0` | `86630aff` | 2026-06-25 | First public release (Flask + SQLite). |
| `v3.0.0-alpha.1` | `b3d9609` | 2026-07-20 | First v3 alpha release. |

These tags are historical markers. They are not branches and should not be checked out except for archaeological purposes.
EOF
```

### 25.6 Step 5: Delete stale remote branches

After the Dependabot PRs are merged or closed (Step 3), delete the remote branches:

```bash
# For each merged/closed Dependabot branch:
git push origin --delete dependabot/cargo/hkdf-0.13.0
git push origin --delete dependabot/cargo/chacha20poly1305-0.11.0
# ... (repeat for all 16)
```

Verify the branch count:

```bash
git fetch --prune
git branch -r | wc -l
# Expected: 3 (main, dev, release/v3.0.0) + origin/HEAD
```

### 25.7 Step 6: Apply branch protection (in this order)

Branch protection must be applied *after* the stale branches are deleted, otherwise the protection rules may conflict with open PRs.

1. Apply protection to `main` (§4.A7.2).
2. Apply protection to `dev` (§25.2).
3. Apply protection to `release/v3.0.0` (§25.3).
4. Verify with `gh api repos/:owner/:repo/branches/main/protection`.

### 25.8 Step 7: Configure Dependabot for the new topology

Create or rewrite `.github/dependabot.yml`:

```yaml
version: 2
updates:
  # Python
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 5
    groups:
      python-minor:
        update-types: [minor, patch]
    labels: [dependencies, python]

  # Rust
  - package-ecosystem: cargo
    directory: "/core/rust"
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 5
    groups:
      rust-minor:
        update-types: [minor, patch]
    labels: [dependencies, rust]

  # npm (web)
  - package-ecosystem: npm
    directory: "/web"
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 5
    groups:
      npm-minor:
        update-types: [minor, patch]
    labels: [dependencies, npm]

  # npm (typescript-sdk)
  - package-ecosystem: npm
    directory: "/packages/typescript-sdk"
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 3
    labels: [dependencies, npm, sdk]

  # Gradle (Android)
  - package-ecosystem: gradle
    directory: "/android"
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 5
    groups:
      gradle-minor:
        update-types: [minor, patch]
    labels: [dependencies, android]

  # GitHub Actions
  - package-ecosystem: github-actions
    directory: "/"
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 3
    groups:
      gha-minor:
        update-types: [minor, patch]
    labels: [dependencies, ci]

  # Docker base images
  - package-ecosystem: docker
    directory: "/"
    schedule:
      interval: monthly
    open-pull-requests-limit: 2
    labels: [dependencies, docker]
```

Key points:
- **Grouped updates**: minor and patch bumps are grouped into one PR per ecosystem, reducing PR noise from 16 to ~6.
- **Major updates are not grouped**: they get individual PRs so they can be tested separately.
- **Limits**: max 5 open PRs per ecosystem to prevent backlog.
- **Labels**: each PR is labeled for triage.

### 25.9 Step 8: Document the branch policy

Create `docs/contributing/branch-policy.md`:

```markdown
# Branch Policy

## Branches

| Branch | Purpose | Protection |
|---|---|---|
| `main` | Stable trunk. Release tags are cut here. | Protected: 1 review, all CI checks, linear history, no force-push. |
| `dev` | Integration branch. Feature PRs merge here first. | Protected: 1 review, subset CI checks, linear history, no force-push. |
| `release/vX.Y.Z` | Release stabilization. Bugfixes only. | Protected: 2 reviews, all CI checks, no force-push. |
| `feature/*` | Feature development. | Not protected. Force-push allowed. |
| `fix/*` | Bug fixes. | Not protected. Force-push allowed. |
| `dependabot/*` | Automated dependency updates. | Not protected. Auto-merged if CI passes. |

## Workflow

1. Create `feature/<name>` from `dev`.
2. Open PR to `dev`.
3. After review and CI, merge to `dev` (squash).
4. Periodically (weekly), merge `dev` to `main` (merge commit, not squash — preserve history).
5. For a release, create `release/vX.Y.Z` from `main`, tag `vX.Y.Z`, merge back to `main` and `dev`.

## Tagging

- `vX.Y.Z`: stable release.
- `vX.Y.Z-rc.N`: release candidate.
- `vX.Y.Z-beta.N`: beta.
- `vX.Y.Z-alpha.N`: alpha.
- `archive/*`: historical markers, not for checkout.

## Force-push

Force-push is only allowed on `feature/*` and `fix/*` branches. Never force-push to `main`, `dev`, or `release/*`.
```

### 25.10 Step 9: Migrate open PRs to the new topology

If there are open PRs targeting `main` at the time of the migration:

1. For each open PR, change the base branch from `main` to `dev` (via the GitHub UI or `gh pr edit <num> --base dev`).
2. Re-run CI on the new base.
3. After review, merge to `dev`.

### 25.11 Step 10: Verify

- `git branch -r` shows: `origin/HEAD -> origin/main`, `origin/main`, `origin/dev`, `origin/release/v3.0.0`. No `dependabot/*`, no `archive/*` branches (only tags).
- `gh api repos/:owner/:repo/branches/main/protection` returns the protection config.
- `.github/dependabot.yml` exists with the grouped-update config.
- `docs/contributing/branch-policy.md` exists.
- `docs/historical/branch-provenance.md` exists.
- A new PR (test: open a `feature/test` branch with a one-line change) targets `dev`, runs CI, and merges cleanly.

### 25.12 Consequences of the branch unification

**Positive:**
- One trunk of truth (`main`).
- Integration testing on `dev` before `main`.
- Release stabilization on `release/*` without freezing `main`.
- Dependabot PR noise reduced from 16 concurrent to ~6 grouped.
- Force-push scope limited to feature branches.

**Negative:**
- Slight overhead: PRs now merge to `dev`, then `dev` merges to `main` (two steps instead of one).
- The weekly `dev` → `main` merge must be owned by someone (rotating release manager).
- Contributors must learn the new workflow (documented in `docs/contributing/branch-policy.md`).

**Risks mitigated:**
- No more 16-branch backlog.
- No more direct commits to `main`.
- No more ambiguous release tagging (now: tag on `release/*`, not `main`).

**Risks introduced:**
- If `dev` diverges significantly from `main`, the weekly merge may conflict. Mitigation: merge `dev` to `main` at least weekly; if `main` receives hotfixes (via `release/*`), cherry-pick to `dev` immediately.

---

## 26. Closing Note

This plan is long because the project is ambitious and the audit found real problems in every layer. The plan is also executable: every task is named, every acceptance criterion is testable, and every risk has a mitigation. The plan does not promise that execution will be easy — it promises that execution will be unambiguous.

The single most important step is §4.A1: fixing the 10 corrupted workflow triggers. Until that is done, no other work is verifiable, because CI cannot run. After A1, the rest of the plan is a sequence of well-scoped engineering tasks, each of which produces a demonstrable improvement.

The plan's guiding principle, drawn from the `agent.md` doctrine: choose a working system over a beautiful description, an observable system over a clever one, and a measurable result over an unverified claim. Every section above is written to that bar.

---

**End of plan.**
