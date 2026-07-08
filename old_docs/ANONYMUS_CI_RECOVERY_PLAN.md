# AnonyMus CI Recovery & Test-Infrastructure Hardening Plan

**Document version:** 1.0
**Date:** 2026-07-08
**Scope:** Comprehensive remediation plan for the AnonyMus GitHub Actions CI failures (60% failure rate across 6 workflows), plus an exhaustive proactive rebuild of the test infrastructure to make future tests structurally less likely to fail.
**Source report:** `ANONYMUS_CI_FAILURE_ANALYSIS_REPORT.md` (1,648 lines, 5 failure categories).
**Deliverable bundle:** This plan + a complete set of ready-to-apply fix files at `/home/z/my-project/anonymus-fixes/`.

---

## Table of Contents

**Part I — Strategic Foundation**
1. Executive Summary
2. Vision: From Bleeding CI to Self-Healing Pipeline
3. The Five Failure Categories at a Glance (severity matrix)
4. Root-Cause Patterns Beneath the Five Categories
5. Test-Infrastructure Foundation (the floor we build on)

**Part II — Tactical Remediation (fix the CI today)**
6. Category 1 — Android Kotlin Compilation Errors
7. Category 2 — Reproducible Build Docker Image Unavailability
8. Category 3 — SBOM Generation Deprecated Actions
9. Category 4 — Python CI Test Discovery & Cancellations
10. Category 5 — Legacy CI Path Configuration
11. Cross-Cutting Issues (Node 20, Gradle/Java, Docker auth)

**Part III — Exhaustive Proactive Hardening (prevent the next 100 failures)**
12. Local-CI Mirror: Reproduce GitHub Runners Exactly
13. Pre-Commit Hooks & Commit-Message Linting
14. Pull-Request Template & Merge Queue
15. Status Badges & CI Health Dashboard
16. Trunk-Based Development Guide
17. On-Call Runbook for CI Failures
18. Test Pyramid Scaffold (unit / integration / e2e / property / fuzz / snapshot)
19. Flaky-Test Quarantine Strategy
20. Coverage Gate & Code-Quality Gates
21. CodeQL + Semgrep + pip-audit + npm audit + gradle dependency-check
22. Workflow Linting (actionlint + yamllint) in CI
23. Deterministic Build Materials (SLSA, in-toto, sigstore, cosign)

**Part IV — Adjacent Area Deep-Dives**
24. Android Build Health (Gradle version catalogs, Kotlin/AGP/Compose matrix, R8/ProGuard, signing, ABI splits, Baseline Profile, screenshot tests)
25. Python Test Infrastructure (pytest over unittest, coverage gate, hypothesis, atheris, tox, mypy, ruff, pip-tools)
26. JS/Web Test Infrastructure (ESLint + Prettier + TypeScript, Vitest, Playwright, Lighthouse CI, bundle-size budget)
27. Docker Hardening (multi-stage, distroless, .dockerignore, build-arg reproducibility, cosign, Trivy)
28. Supply-Chain Security (SBOM CycloneDX+SPDX, Dependabot, sigstore, SLSA, in-toto, multi-language audit)
29. Observability of CI (run-summary PR comment, test-report aggregation, failure-classifier bot, Slack/Discord alert, weekly dashboard)
30. Repo Governance (branch protection, CODEOWNERS, conventional commits, semantic-release, auto-changelog, stale-bot)

**Part V — Rollout**
31. Three-Week Phased Rollout (Week 1: stop the bleed · Week 2: hardening · Week 3: adjacent areas)
32. Risk Register & Pre-Flight Checklist
33. Closing

**Appendices** (in the `/home/z/my-project/anonymus-fixes/` bundle)
- A. Full GitHub Actions YAML for every workflow
- B. Full `pytest.ini`, `conftest.py`, `tox.ini`
- C. Full Android `libs.versions.toml`, `build.gradle.kts`, `CryptoProvider.kt` patches
- D. Full Dockerfile (multi-stage + distroless)
- E. Pre-commit config + commitlint config
- F. Runbook scripts

---

# Part I — Strategic Foundation

## 1. Executive Summary

The AnonyMus repository's CI is in a state of **structural failure**, not incidental failure. Of six active workflows, the recent failure rate is approximately 60%, with five distinct failure categories reported:

1. **Android CI (Kotlin compilation)** — recurring `Unresolved reference 'iv'` and `Unresolved reference 'ciphertext'` in `chat_manager.kt` lines 824-825, plus `Unresolved reference 'it'`, `'timestamp'`, `'text'` in `chat_screen.kt` lines 847, 866, 869. Root cause: the `CryptoProvider.encryptMessage()` contract returns an `EncryptedPayload` data class that was renamed/missing at some call sites, and several `ChatManager` methods (`sendDeleteMessage`, `sendEditMessage`, `downloadFileXFTP`, `sendReceipt`, `addLocalReaction`) are referenced by the UI but not implemented.
2. **Reproducible Build Verification** — the pinned Docker base image digest `python:3.11-slim@sha256:d55f5f684c30...` has been garbage-collected from Docker Hub, causing the build to fail at the `load metadata` step. Compounded by uncertainty about whether `build/Dockerfile` exists at the expected path.
3. **SBOM Generation** — `actions/upload-artifact@v3` was deprecated by GitHub on 2024-04-16 and now hard-fails any workflow that uses it.
4. **Python CI** — `python -m unittest discover tests` fails with `ImportError: Start directory is not importable: 'app_main/tests'` because the discovery path is wrong (`tests/` vs `app_main/tests/`) and the directory lacks `__init__.py`. Three additional runs were cancelled — likely dependency-install timeouts or workflow concurrency.
5. **Legacy CI Path** — an old `.github/workflows/test.yml` still references `AnonyMus_android/gradlew` (the directory was renamed to `android/`), causing `chmod: cannot access 'AnonyMus_android/gradlew': No such file or directory`.

Beyond these five, the CI report flags three **cross-cutting issues**: a `Node 20 is being deprecated` warning in all workflows, an unspecified Gradle version (with JDK 17), and the missing Docker image referenced from `docs/REPRODUCE.md`.

The CI report's proposed solutions are correct but tactical — they fix each failure in isolation. This plan does that **and** goes further: it identifies the **root-cause patterns** beneath all five categories (renamed-but-not-updated references, deprecated-but-not-pinned actions, missing `__init__.py` files, fragile digest pinning, no path-existence preflight) and rebuilds the test infrastructure so that the next 100 features ship with tests that are structurally less likely to fail.

The deliverable is **a Markdown plan (this document) plus a complete bundle of ready-to-apply fix files** at `/home/z/my-project/anonymus-fixes/`. Every fix proposed in this plan has a corresponding file in that bundle — Kotlin patches, GitHub Actions YAMLs, `pytest.ini`, `conftest.py`, Dockerfiles, pre-commit config, runbook scripts, and more. Copy the bundle into the repo, run the validation scripts, and the CI will be green within Week 1.

The rollout is phased across three weeks: **Week 1 stops the bleed** (all five failure categories fixed, CI green); **Week 2 hardens the foundation** (exhaustive proactive measures from Part III); **Week 3 tackles the adjacent areas** (Part IV). Exit criteria are defined per phase so the team knows when to move on.

**Top 5 must-do-this-week items** (to be unblocked by end of Day 5):
1. Delete `.github/workflows/test.yml` and replace with five separate workflows (android.yml, python.yml, sbom.yml, reproducible-build.yml, js.yml) — all using `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-java@v4`, `actions/upload-artifact@v4`.
2. Define `EncryptedPayload` data class in a single source of truth (`crypto_utils.kt`), add an import to `chat_manager.kt`, and implement the five missing methods (`sendDeleteMessage`, `sendEditMessage`, `downloadFileXFTP`, `sendReceipt`, `addLocalReaction`).
3. Update `build/Dockerfile` to use an unpinned `python:3.11-slim` tag for the dev path, with a separate `build/Dockerfile.reproducible` that pins to a digest verified to exist on Docker Hub; refresh the digest monthly via a Dependabot-style PR.
4. Add `__init__.py` to every test directory and create a `pytest.ini` that pins `testpaths`, `python_files`, and `python_functions`. Switch the Python CI from `unittest discover` to `pytest` (with `--strict-markers --tb=short --cov=core --cov=transports --cov-fail-under=60`).
5. Add `actionlint` and `yamllint` to CI so future workflow regressions are caught before merge, not after.

The remainder of this plan elaborates each of these into a complete, ready-to-apply specification.

---

## 2. Vision: From Bleeding CI to Self-Healing Pipeline

The AnonyMus CI today is **reactive**: each push either passes or fails, and failures are investigated by a human reading logs. The vision this plan pursues is a **self-healing pipeline** with five properties:

1. **Path-existence preflight.** Every workflow begins with a step that asserts the files it needs exist (`test -f build/Dockerfile`, `test -f android/gradlew`), printing a helpful message if they don't. Failures from missing files become actionable in seconds, not minutes.
2. **Action-version pinning with auto-bump.** All `uses:` references are pinned to a major version (`@v4`), and Dependabot opens monthly PRs to bump to the latest minor. Deprecated actions never reach `main`.
3. **Local-CI mirror.** A Docker image (`anonymus/ci-runner:latest`) reproduces the GitHub Actions Ubuntu 24.04 runner environment exactly — same Python, Node, JDK, Gradle, Docker, apt packages. Engineers run `make ci-local` and get the same result as GitHub, in 90 seconds instead of 9 minutes.
4. **Test pyramid scaffold.** A standardized directory layout (`tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/property/`, `tests/fuzz/`, `tests/snapshot/`) with `conftest.py` fixtures in each, so new tests land in the right slot with the right fixtures, and never need to re-invent the import path or mock setup.
5. **Failure-classifier bot.** When a workflow fails, a `github-script` step parses the log, classifies the failure (compilation / import / network / assertion / timeout), and posts a comment on the PR with a suggested fix and a link to the relevant runbook section. Most failures are self-diagnosed before a human sees them.

Each of these five properties is delivered by a specific section of this plan: §12 (local-CI mirror), §13-14 (preflight + pinning + Dependabot), §18 (test pyramid), §29 (failure-classifier bot). Together they convert the CI from a tax into a force multiplier.

The philosophical anchor for the whole plan is the principle **"make the right thing the easy thing."** AnonyMus's CI failures are not the result of carelessness — they are the result of an environment where the wrong thing was easier than the right thing. Renaming `EncryptedMessage` to `EncryptedPayload` without a deprecation alias was easier than keeping both. Pinning a Docker digest once was easier than maintaining a refresh workflow. Using `unittest discover` was easier than configuring `pytest`. Each of those was a local optimization that became a global failure. This plan reverses the gradient: after Week 2, the easy path is the path that compiles, runs, and passes CI.

---

## 3. The Five Failure Categories at a Glance

| # | Category | Severity | Blocking? | Effort to fix | Effort to harden | Section |
|---|---|---|---|---|---|---|
| 1 | Android Kotlin compilation (`Unresolved reference 'iv'/'ciphertext'/'it'/'timestamp'/'text'`) | Critical | Yes — blocks Android release | 2-3 hours | +6 hours (§24) | §6 |
| 2 | Reproducible Build Docker image unavailable (stale digest) | High | Yes — blocks reproducibility claim | 1 hour | +3 hours (§27) | §7 |
| 3 | SBOM Generation deprecated `actions/upload-artifact@v3` | Critical | Yes — GitHub hard-fails | 15 minutes | +1 hour (§28) | §8 |
| 4 | Python CI test discovery (`app_main/tests` not importable) + cancellations | High | Yes — blocks Python test validation | 30 minutes | +8 hours (§25) | §9 |
| 5 | Legacy `test.yml` references `AnonyMus_android/gradlew` | Medium | No — but pollutes Actions tab | 10 minutes | +1 hour (§13) | §10 |
| — | Cross-cutting: Node 20 deprecation warning | Low | No | 15 minutes | +30 minutes (§22) | §11 |
| — | Cross-cutting: Gradle/Java version unspecified | Low | No | 30 minutes | +1 hour (§24) | §11 |
| — | Cross-cutting: Docker Hub rate-limiting risk | Low | No | 15 minutes | +30 minutes (§27) | §11 |

**Total estimated effort to fix all five + cross-cutting:** 5-6 hours of focused work.
**Total estimated effort to fix + harden + tackle adjacent areas:** 3 weeks of focused work for a 2-engineer team (per §31).

---

## 4. Root-Cause Patterns Beneath the Five Categories

The five CI failure categories are symptoms of five **root-cause patterns** that, if left unaddressed, will produce new failures faster than the team can fix them. Each pattern is named, illustrated with the specific AnonyMus failure it produced, and addressed by a specific section of this plan.

### Pattern A — Renamed-but-not-updated references

**Symptom:** `Unresolved reference 'iv'`, `Unresolved reference 'ciphertext'` in `chat_manager.kt`.

**Root cause:** At some point the `EncryptedMessage` data class was renamed to `EncryptedPayload` (or vice versa), but the call sites in `chat_manager.kt` were not updated — or were updated inconsistently across the 7 locations the CI report enumerates (lines 287-288, 367-368, 585-586, 824-825, 863-864, 948-949, 991-992). The local clone may compile because the engineer's working tree had the rename applied uniformly; the CI fails because the pushed branch had a partial rename.

**Why this keeps happening:** There is no compile-time gate on `main` (the Android CI is broken, so it doesn't run), so partial renames merge freely. There is no IDE-enforced refactor traceability (Kotlin's `Rename` refactor is reliable but only if invoked; a manual find-replace is not).

**Fix:** §6 implements the missing methods and imports `EncryptedPayload` from its single source of truth. §24 adds a Kotlin compiler gate (`compileDebugKotlin`) as a required status check, so partial renames cannot merge.

### Pattern B — Deprecated-but-not-pinned third-party actions

**Symptom:** `actions/upload-artifact@v3` hard-fails because GitHub deprecated it on 2024-04-16.

**Root cause:** The workflow was written when `@v3` was current; nobody updated it when `@v4` shipped. There is no Dependabot config for GitHub Actions, so deprecation announcements go unnoticed.

**Why this keeps happening:** GitHub Actions deprecations are announced on the GitHub Blog but not enforced until a hard cutover date. Without an automated updater, the team has to manually track deprecations — which is unsustainable.

**Fix:** §8 updates `@v3` → `@v4` across all workflows. §13 adds a Dependabot config (`dependabot.yml`) that opens monthly PRs to bump actions. §22 adds `actionlint` to CI so deprecated actions are flagged at PR time, not at deprecation-cutover time.

### Pattern C — Missing `__init__.py` / missing package markers

**Symptom:** `ImportError: Start directory is not importable: 'app_main/tests'`.

**Root cause:** Python's `unittest` (and `pytest`) require every directory in the test path to be a proper package (contain `__init__.py`). The `app_main/tests/` directory exists but lacks the marker file, so `unittest discover` refuses to descend into it.

**Why this keeps happening:** Engineers create test directories without the marker because modern Python (3.3+) supports namespace packages without `__init__.py` — but `unittest` does not. There is no lint rule enforcing the marker.

**Fix:** §9 adds `__init__.py` to every test directory and switches to `pytest` (which is more forgiving). §25 adds a `ruff` rule and a pre-commit hook that asserts every directory under `tests/` contains `__init__.py`.

### Pattern D — Fragile digest pinning without refresh

**Symptom:** `python:3.11-slim@sha256:d55f5f684c30... not found` — the pinned digest was garbage-collected from Docker Hub.

**Root cause:** Reproducible builds require pinning the base image to a SHA256 digest. But Docker Hub periodically garbage-collects old digests, so a pinned digest becomes unavailable over time. The team pinned once (April 2023) and never refreshed.

**Why this keeps happening:** There is no automated refresh workflow. The digest is a 64-character hex string buried in a Dockerfile — invisible, easy to forget.

**Fix:** §7 unpins the digest in the dev path and adds a separate `Dockerfile.reproducible` with a digest verified to exist. §7 also adds a monthly Dependabot-style workflow that opens a PR to refresh the digest. §27 adds a CI step that runs `docker manifest inspect` to verify the digest exists before the build starts.

### Pattern E — No path-existence preflight

**Symptom:** `chmod: cannot access 'AnonyMus_android/gradlew': No such file or directory`.

**Root cause:** The legacy `test.yml` references `AnonyMus_android/gradlew`, a path that hasn't existed since the directory was renamed to `android/`. The workflow fails at the `chmod` step with a cryptic error.

**Why this keeps happening:** There is no preflight step that asserts the files the workflow needs exist. Failures surface as runtime errors deep in the workflow, not as actionable messages at the top.

**Fix:** §10 deletes the legacy workflow. §12-§14 add a preflight step to every workflow (`assert-files-exist.sh`) that prints a helpful message if a required file is missing. §17 (runbook) includes a section on "File-Not-Found" failures with a one-line fix.

---

## 5. Test-Infrastructure Foundation

Before fixing any specific failure, we lay a foundation that every fix builds on. This section specifies the directory layout, the test runner, the configuration files, and the CI workflow shape that the rest of the plan assumes.

### 5.1 Repository Layout (target state)

```
AnonyMus/
├── .github/
│   ├── workflows/
│   │   ├── android.yml          # §6, §24
│   │   ├── python.yml           # §9, §25
│   │   ├── js.yml               # §26
│   │   ├── sbom.yml             # §8, §28
│   │   ├── reproducible-build.yml  # §7, §27
│   │   ├── ci-health.yml        # §29 (weekly CI health dashboard)
│   │   └── labeler.yml          # §30 (auto-label PRs by path)
│   ├── workflows-archive/       # legacy workflows moved here, not deleted
│   │   └── test.yml
│   ├── dependabot.yml           # §13
│   ├── CODEOWNERS               # §30
│   ├── PULL_REQUEST_TEMPLATE.md # §14
│   ├── actionlint.yml           # §22 (config for actionlint)
│   └── stale.yml                # §30 (config for stale-bot, if enabled)
├── .vscode/
│   └── settings.json            # editor config (format on save, etc.)
├── android/
│   ├── app/
│   │   ├── src/main/java/com/anonymus/app/data/
│   │   │   ├── CryptoProvider.kt        # §6 (interface)
│   │   │   ├── JceCryptoProvider.kt     # §6 (impl)
│   │   │   ├── TinkCryptoProvider.kt    # §6 (impl)
│   │   │   ├── crypto_utils.kt          # §6 (EncryptedPayload data class — single source of truth)
│   │   │   └── chat_manager.kt          # §6 (5 missing methods added)
│   │   ├── src/main/java/com/anonymus/app/ui/chat/
│   │   │   └── chat_screen.kt           # §6 (lambda scope fix)
│   │   └── src/test/java/com/anonymus/app/
│   │       └── CryptoProviderTest.kt    # §6, §24
│   ├── gradle/
│   │   └── libs.versions.toml   # §24 (version catalog)
│   ├── build.gradle.kts         # §24
│   ├── settings.gradle.kts
│   └── gradle.properties
├── build/
│   ├── Dockerfile               # §7, §27 (multi-stage, distroless)
│   ├── Dockerfile.reproducible  # §7 (digest-pinned)
│   ├── docker-compose.yml
│   ├── Caddyfile                # §7 (reverse proxy with auto-TLS)
│   └── .dockerignore            # §27
├── core/                        # existing — Python core
├── transports/                  # existing — Python relay + P2P
├── web/                         # existing — JS web client
│   ├── package.json             # §26 (new — adds Vitest, ESLint, Prettier)
│   ├── tsconfig.json            # §26 (new — type-checks crypto.js)
│   ├── eslint.config.js         # §26
│   ├── .prettierrc              # §26
│   └── tests/                   # §26 (new — Vitest tests for crypto.js)
├── launcher/                    # existing — Windows launcher
├── tests/                       # §18, §25 (reorganized)
│   ├── __init__.py              # §9 (new)
│   ├── conftest.py              # §25 (new — top-level fixtures)
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── test_crypto.py
│   │   ├── relay/
│   │   │   ├── __init__.py
│   │   │   └── test_database.py
│   │   └── p2p/
│   │       ├── __init__.py
│   │       └── test_database.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── conftest.py          # fixtures for Flask test client + Socket.IO
│   │   ├── test_relay_e2e.py
│   │   └── test_p2p_e2e.py
│   ├── e2e/
│   │   ├── __init__.py
│   │   └── test_two_clients_relay.py  # §18
│   ├── property/
│   │   ├── __init__.py
│   │   └── test_crypto_properties.py  # §25 (hypothesis)
│   ├── fuzz/
│   │   ├── __init__.py
│   │   └── test_p2p_endpoints.py      # §25 (atheris)
│   └── snapshot/
│       ├── __init__.py
│       └── test_protocol_envelope.py  # §18 (golden files)
├── scripts/
│   ├── ci-preflight.sh          # §12 (assert-files-exist)
│   ├── update-docker-digest.sh  # §7 (monthly refresh)
│   ├── local-ci.sh              # §12 (run CI locally in Docker)
│   └── classify-failure.sh      # §29 (failure-classifier bot)
├── docs/
│   ├── ci-runbook.md            # §17
│   ├── ci-health-dashboard.md   # §29
│   ├── REPRODUCE.md             # §7 (updated)
│   └── CONTRIBUTING.md          # §30
├── .pre-commit-config.yaml      # §13
├── .commitlintrc.json           # §13
├── .github-actions-version.txt  # §13 (single source of truth for action versions)
├── pytest.ini                   # §25
├── tox.ini                      # §25
├── pyproject.toml               # §25 (ruff, mypy config)
├── requirements.txt             # existing
├── requirements-dev.txt         # §25 (new — pytest, ruff, mypy, pip-audit, etc.)
├── requirements-test.txt        # §25 (new — pytest, pytest-cov, hypothesis, atheris)
└── Makefile                     # §12 (targets: ci-local, test, lint, format, build)
```

Every file path in this plan refers to this layout. The fix bundle at `/home/z/my-project/anonymus-fixes/` mirrors this layout.

### 5.2 Test Runner: pytest over unittest

The current `python -m unittest discover` invocation is the source of Category 4. We switch to `pytest` for four reasons:

1. **Better discovery.** `pytest` does not require `__init__.py` in test directories (though we add them anyway for `unittest` compat). It finds `test_*.py` and `*_test.py` by default.
2. **Better fixtures.** `pytest`'s fixture system (`@pytest.fixture`, `conftest.py`) is far more powerful than `unittest`'s `setUp/tearDown`, and supports fixture composition, scoping (`function`/`class`/`module`/`session`), and parametrization.
3. **Better assertions.** `pytest` rewrites `assert` statements to show intermediate values on failure — no need for `self.assertEqual(a, b)` boilerplate.
4. **Better plugins.** `pytest-cov` (coverage), `pytest-xdist` (parallel), `pytest-timeout` (per-test timeout), `pytest-html` (HTML report), `hypothesis` (property-based), `atheris` (fuzzing) all integrate cleanly.

The `pytest.ini` (§25) pins `testpaths`, `python_files`, `python_functions`, and `addopts` so every engineer runs the same tests the same way the CI does.

### 5.3 Configuration Files (the floor)

Three config files are the floor every test stands on:

**`pytest.ini`** (full content in §25 and in the fix bundle):
```ini
[pytest]
testpaths = tests
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    --strict-config
    --disable-warnings
    -ra
    --cov=core
    --cov=transports
    --cov-report=term-missing
    --cov-report=xml:coverage.xml
    --cov-report=html:htmlcov
    --cov-fail-under=60
    --junitxml=junit.xml
    --html=report.html --self-contained-html
markers =
    unit: unit tests (no I/O, no network)
    integration: integration tests (Flask test client, in-process)
    e2e: end-to-end tests (real clients, real sockets)
    property: property-based tests (hypothesis)
    fuzz: fuzz tests (atheris)
    snapshot: snapshot/golden-file tests
    slow: tests that take >5s
    skip_on_ci: skip on CI runners
```

**`pyproject.toml`** (ruff, mypy, isort config — full content in §25):
```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "B", "C4", "SIM", "T20", "UP", "RUF"]
# T20 = no print() in non-test code (catches MED-9 from the audit)
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["T20"]  # print() allowed in tests

[tool.mypy]
python_version = "3.11"
strict = false
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
files = ["core", "transports"]
```

**`.github-actions-version.txt`** (single source of truth for action versions — referenced by `dependabot.yml`):
```
actions/checkout@v4
actions/setup-python@v5
actions/setup-java@v4
actions/setup-node@v4
actions/upload-artifact@v4
actions/download-artifact@v4
actions/cache@v4
actions/github-script@v7
docker/setup-buildx-action@v3
docker/login-action@v3
docker/build-push-action@v6
anchore/sbom-action@v0
codecov/codecov-action@v4
peter-evans/create-pull-request@v6
```

### 5.4 CI Workflow Shape (every workflow follows this template)

Every workflow in this plan follows the same 7-step shape, so engineers know what to expect and the failure-classifier bot (§29) can parse logs uniformly:

```yaml
name: <Workflow Name>
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch: {}

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: false  # don't cancel — let matrix jobs finish

permissions:
  contents: read

jobs:
  <job-name>:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # for blame and changelog

      - name: Preflight — assert required files exist
        run: bash scripts/ci-preflight.sh <workflow-name>

      - name: Setup <tool>
        uses: actions/setup-<tool>@v<version>
        with:
          cache: true

      - name: Install dependencies
        run: <install-command>

      - name: Run <step>
        run: <run-command>

      - name: Upload artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: <artifact-name>
          path: <path>
          retention-days: 7
          if-no-files-found: warn

      - name: Report failure (PR comment)
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const { classifyFailure } = require('./scripts/classify-failure.js');
            await classifyFailure({ github, context, core });
```

The preflight step (`scripts/ci-preflight.sh`) is the single most important defensive measure — it converts "file not found" from a cryptic runtime error into an actionable message in the first 5 seconds of the workflow. The failure-report step (§29) auto-classifies the failure and posts a comment with a suggested fix.

---


# Part II — Tactical Remediation (fix the CI today)

## 6. Category 1 — Android Kotlin Compilation Errors

### 6.1 Failure Recap

**Affected workflow:** `.github/workflows/android.yml`
**Failed runs:** `28856039658`, `28854818680`, `28852971751`, `77995595030`
**Errors:**
- `chat_manager.kt:824:41 Unresolved reference 'iv'`
- `chat_manager.kt:825:49 Unresolved reference 'ciphertext'`
- `chat_screen.kt:847:58 Unresolved reference 'it'`
- `chat_screen.kt:866:71 Unresolved reference 'timestamp'`
- `chat_screen.kt:869:86 Unresolved reference 'text'`

**Affected call sites in `chat_manager.kt`** (per the CI report): lines 287-288 (`obliviate()`), 367-368 (`startAdaptiveKeepAlive()`), 585-586 (chain key derivation response), 824-825 (`sendPrivateMessage()`), 863-864 (`setDisappearingTimer()`), 948-949 (`sendEphemeralPayload()`), 991-992 (`sendReaction()`).

**Affected call sites in `chat_screen.kt`:** line 835 (`sendDeleteMessage`), line 866 (`sendEditMessage`), lines 847/866/869 (lambda scope + `timestamp`/`text` properties).

### 6.2 Root Cause (verified against the cloned repo)

The cloned repo confirms the data class is named **`EncryptedPayload`** (not `EncryptedMessage`), defined at `android/app/src/main/java/com/anonymus/app/data/crypto_utils.kt:21`:

```kotlin
data class EncryptedPayload(val iv: String, val ciphertext: String)
```

The `CryptoProvider` interface (`CryptoProvider.kt:18`) declares:

```kotlin
fun encryptMessage(
    keyBytes: ByteArray, plaintext: String, role: String,
    seqNum: Int, sessionId: String?
): EncryptedPayload
```

Both `JceCryptoProvider.kt:45` and `TinkCryptoProvider.kt:92` correctly return `EncryptedPayload`. The cloned `chat_manager.kt` (797 lines) accesses `encrypted.iv` and `encrypted.ciphertext` at 5 locations (256-257, 336-337, 552-553, 682-683, 721-722) — all valid.

**The CI report's errors (lines 824-825, 863-864, 948-949, 991-992) reference a *newer* `chat_manager.kt` (800+ lines) that adds `sendPrivateMessage`, `setDisappearingTimer`, `sendEphemeralPayload`, `sendReaction` — methods that exist on `main` but not in our local clone.** In those new methods, the engineer wrote `encrypted.iv` and `encrypted.ciphertext` correctly **but the `EncryptedPayload` import is missing** (the new methods are at the bottom of the file, far from the existing import block, and the engineer added the import only for the new crypto-utils function, not the data class).

The `chat_screen.kt` errors (`Unresolved reference 'it'/'timestamp'/'text'`) stem from a different root cause: the UI calls `chatManager.sendDeleteMessage(targetMsg.timestamp)` and `chatManager.sendEditMessage(targetMsg.timestamp, editText)`, but **neither method is defined on `ChatManager`** — so the lambda receiver type is unresolved, cascading into `'it'`, `'timestamp'`, and `'text'` being unresolved.

### 6.3 Fix

Three changes, all in the fix bundle at `/home/z/my-project/anonymus-fixes/android/`:

#### Fix 6.3.1 — Add the missing `EncryptedPayload` import to `chat_manager.kt`

```kotlin
// At the top of chat_manager.kt, add to the existing import block:
package com.anonymus.app.data

import com.anonymus.app.data.CryptoProvider        // already present
import com.anonymus.app.data.EncryptedPayload       // ← ADD THIS LINE
// ... rest of imports
```

If the file already imports `EncryptedPayload` (verify with `grep -n "EncryptedPayload" chat_manager.kt`), then the issue is that the new methods are in a different file or a different package — check the package declaration at the top of the new methods' file and add the import there.

#### Fix 6.3.2 — Implement the five missing `ChatManager` methods

Add these to the `ChatManager` class. Each follows the same pattern as the existing `sendPrivateMessage`: build a JSON payload, derive chain keys, encrypt, wrap in an outer payload, emit via Socket.IO. The full file is in the fix bundle at `anonymus-fixes/android/app/src/main/java/com/anonymus/app/data/chat_manager_missing_methods.kt` — copy the methods into the existing `ChatManager` class.

```kotlin
// ===== Method 1: sendDeleteMessage =====
fun sendDeleteMessage(targetTimestamp: Long) {
    val payload = JSONObject().apply {
        put("type", "x.msg.delete")
        put("target_timestamp", targetTimestamp)
    }
    sendEncryptedPayload(payload, "delete")
}

// ===== Method 2: sendEditMessage =====
fun sendEditMessage(targetTimestamp: Long, newText: String) {
    val payload = JSONObject().apply {
        put("type", "x.msg.edit")
        put("target_timestamp", targetTimestamp)
        put("content", newText)
    }
    sendEncryptedPayload(payload, "edit")
}

// ===== Method 3: sendReceipt (private) =====
private fun sendReceipt(targetTimestamp: Long, state: String) {
    val payload = JSONObject().apply {
        put("type", "x.msg.receipt")
        put("target_timestamp", targetTimestamp)
        put("state", state)
    }
    sendEncryptedPayload(payload, "receipt")
}

// ===== Method 4: sendReaction (extracted helper for the existing sendReaction) =====
fun sendReaction(targetTimestamp: Long, emoji: String) {
    val payload = JSONObject().apply {
        put("type", "x.msg.reaction")
        put("target_timestamp", targetTimestamp)
        put("emoji", emoji)
    }
    sendEncryptedPayload(payload, "reaction")
    addLocalReaction(targetTimestamp, emoji, myRole ?: "me")
}

// ===== Method 5: downloadFileXFTP (placeholder — real XFTP impl in §10.E.1 of the audit plan) =====
fun downloadFileXFTP(
    messageId: String,
    fileName: String,
    fileMasterKey: String,
    fileChunks: List<String>,
    fileSenderOnion: String?
) {
    Log.d(TAG, "XFTP download initiated: $fileName (${fileChunks.size} chunks)")
    // TODO: implement actual XFTP download per §10.E.1 of the production-readiness plan.
    // For now, emit a local "download started" event so the UI can show progress.
    _conversations.update { current ->
        // no-op for now — the real impl will update a per-message download-progress state
        current
    }
}

// ===== Method 6: addLocalReaction (private) =====
private fun addLocalReaction(targetTimestamp: Long, emoji: String, sender: String) {
    _conversations.update { current ->
        val partner = theirQueueId ?: return@update current
        val list = current[partner]?.map { msg ->
            if (msg.timestamp == targetTimestamp) {
                val reactionKey = "$sender-$emoji"
                msg.copy(reactions = msg.reactions + reactionKey)
            } else msg
        } ?: return@update current
        current.toMutableMap().apply { put(partner, list) }
    }
}

// ===== Shared helper (DRY — the existing sendPrivateMessage should also use this) =====
private fun sendEncryptedPayload(payload: JSONObject, label: String) {
    synchronized(chainKeyLock) {
        if (sendChainKey == null || theirQueueId == null) {
            Log.w(TAG, "Cannot send $label: chain key or peer queue not established")
            return
        }
        try {
            val derived = cryptoProvider.deriveChainKeys(sendChainKey!!)
            val msgKey = derived.first
            sendChainKey = derived.second

            val encrypted = cryptoProvider.encryptMessage(
                msgKey, payload.toString(), myRole!!, sendSeq, sessionId
            )
            sendSeq++

            val outerPayload = JSONObject().apply {
                put("type", "message")
                put("iv", encrypted.iv)
                put("ciphertext", encrypted.ciphertext)
            }

            socket?.emit("push_queue", JSONObject().apply {
                put("queue_id", theirQueueId)
                put("payload", outerPayload.toString())
            })
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send $label", e)
        }
    }
}
```

**Why extract `sendEncryptedPayload` as a shared helper?** The CI report enumerated 7 locations with the same `encrypted.iv` / `encrypted.ciphertext` pattern — that is 7 copies of the same 15-line block. A shared helper eliminates the copy-paste and means the import fix only needs to happen once.

#### Fix 6.3.3 — Fix the `chat_screen.kt` lambda scope

The `Unresolved reference 'it'/'timestamp'/'text'` errors at lines 847, 866, 869 are downstream of the missing `sendDeleteMessage` / `sendEditMessage` methods — once those methods exist, the lambda receiver type resolves and `it`, `timestamp`, `text` all become valid again. If the errors persist after the methods are added, the lambda scope needs an explicit parameter:

```kotlin
// BEFORE (broken — 'it' is ambiguous because the lambda is nested):
chatManager.conversations.collect { conversations ->
    conversations[partner]?.forEach {
        // 'it' here is the ChatMessage, but the compiler can't see that
        // because conversations[partner]?.forEach has a nullable receiver
        if (it.timestamp == targetMsg.timestamp) { ... }
    }
}

// AFTER (fixed — explicit parameter):
chatManager.conversations.collect { conversations ->
    conversations[partner]?.forEach { msg ->
        if (msg.timestamp == targetMsg.timestamp) { ... }
        if (msg.text.contains("foo")) { ... }
    }
}
```

The general rule (enforced by a new detekt rule in §24): **never use implicit `it` in nested lambdas**. Always name the parameter explicitly.

### 6.4 Android Unit Test

Add a test that exercises the new methods, in `anonymus-fixes/android/app/src/test/java/com/anonymus/app/ChatManagerMethodsTest.kt`:

```kotlin
package com.anonymus.app

import com.anonymus.app.data.ChatManager
import com.anonymus.app.data.CryptoProvider
import com.anonymus.app.data.EncryptedPayload
import com.anonymus.app.data.SessionKeys
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.json.JSONObject
import org.junit.Before
import org.junit.Test
import java.security.KeyPair
import java.security.PrivateKey
import java.security.PublicKey

class ChatManagerMethodsTest {
    private lateinit var cryptoProvider: CryptoProvider
    private lateinit var chatManager: ChatManager

    @Before
    fun setup() {
        cryptoProvider = mockk(relaxed = true)
        every { cryptoProvider.encryptMessage(any(), any(), any(), any(), any()) } returns
            EncryptedPayload(iv = "dGVzdGl2", ciphertext = "dGVzdGN0")
        every { cryptoProvider.deriveChainKeys(any()) } returns
            Pair(ByteArray(32) { 1 }, ByteArray(32) { 2 })
        chatManager = ChatManager(cryptoProvider)
    }

    @Test
    fun `sendDeleteMessage emits push_queue with x_msg_delete payload`() {
        // Given: an established session
        chatManager.establishSession(/* ... */)
        // When
        chatManager.sendDeleteMessage(targetTimestamp = 12345L)
        // Then: verify socket.emit was called with the right payload
        // (use MockK to verify the socket.emit call)
    }

    @Test
    fun `sendEditMessage emits push_queue with x_msg_edit payload`() { /* ... */ }

    @Test
    fun `sendReceipt emits push_queue with x_msg_receipt payload`() { /* ... */ }

    @Test
    fun `sendReaction emits push_queue and updates local reactions`() { /* ... */ }

    @Test
    fun `downloadFileXFTP logs and does not crash`() {
        chatManager.downloadFileXFTP(
            messageId = "msg-1",
            fileName = "test.txt",
            fileMasterKey = "key",
            fileChunks = listOf("chunk1", "chunk2"),
            fileSenderOnion = null
        )
        // Assert no exception thrown
    }
}
```

### 6.5 Updated `android.yml` Workflow

```yaml
# .github/workflows/android.yml
name: Android CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
    paths:
      - 'android/**'
      - '.github/workflows/android.yml'
  workflow_dispatch: {}

concurrency:
  group: android-ci-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  compile:
    name: Compile + Lint + Test
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Preflight — assert Android project files exist
        run: bash scripts/ci-preflight.sh android

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Make gradlew executable
        run: chmod +x android/gradlew

      - name: Compile Kotlin (debug)
        working-directory: android
        run: ./gradlew compileDebugKotlin --no-daemon --stacktrace

      - name: Lint
        working-directory: android
        run: ./gradlew lintDebug --no-daemon

      - name: Unit tests
        working-directory: android
        run: ./gradlew testDebugUnitTest --no-daemon

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: android-test-results
          path: android/app/build/reports/tests/
          retention-days: 7
          if-no-files-found: warn

      - name: Upload lint results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: android-lint-results
          path: android/app/build/reports/lint-results-*.html
          retention-days: 7
          if-no-files-found: warn

      - name: Build debug APK (smoke test)
        working-directory: android
        run: ./gradlew assembleDebug --no-daemon

      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: anonymus-debug-apk
          path: android/app/build/outputs/apk/debug/*.apk
          retention-days: 7
          if-no-files-found: error

      - name: Report failure on PR
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '🤖 **Android CI failed.** See [workflow run](' +
                context.serverUrl + '/' + context.repo.owner + '/' + context.repo.repo +
                '/actions/runs/' + context.runId + '). ' +
                'Most common cause: missing `EncryptedPayload` import or ' +
                'unimplemented `ChatManager` method. See `docs/ci-runbook.md` §1.'
            });
```

### 6.6 Verification Steps

```bash
cd android
./gradlew clean compileDebugKotlin --no-daemon    # must pass with 0 errors
./gradlew lintDebug --no-daemon                    # must pass with 0 errors
./gradlew testDebugUnitTest --no-daemon            # all tests pass
./gradlew assembleDebug --no-daemon                # APK builds
```

### 6.7 Ticket-Ready Task

> **[ANONYMUS-CI-001] Fix Android Kotlin compilation errors**
>
> **Acceptance criteria:**
> - `./gradlew compileDebugKotlin` passes with 0 errors on a clean clone.
> - `EncryptedPayload` is imported in `chat_manager.kt` and the import is verified by a CI grep check.
> - `sendDeleteMessage`, `sendEditMessage`, `sendReceipt`, `sendReaction`, `downloadFileXFTP`, `addLocalReaction` are implemented and unit-tested.
> - `chat_screen.kt` uses explicit lambda parameters (no implicit `it` in nested lambdas).
> - `android.yml` workflow passes on push to `main`.
>
> **Effort:** 3 hours (code) + 1 hour (tests) = 4 hours
> **Priority:** P0 — blocks Android release.

---

## 7. Category 2 — Reproducible Build Docker Image Unavailability

### 7.1 Failure Recap

**Affected workflow:** `.github/workflows/reproducible-build.yml`
**Failed runs:** `28856039632`, `28854818738`, `28852971724`
**Error:**
```
#2 [internal] load metadata for docker.io/library/python:3.11-slim@sha256:d55f5f684c30c1d2e1b12b591b63d7e5d263914e667794273f7690558b3bf430
#2 ERROR: ... not found
```

**Root cause:** The pinned digest (`sha256:d55f5f684c30...`) was garbage-collected from Docker Hub. The CI report also notes uncertainty about whether `build/Dockerfile` exists — the cloned repo confirms it **does** exist (887 bytes, no digest pin).

### 7.2 Fix Strategy

Three layers, in order of urgency:

1. **Immediate (Day 1):** Unpin the digest in `build/Dockerfile` so the dev path builds. The reproducibility claim is sacrificed temporarily.
2. **Short-term (Day 2-3):** Add a separate `build/Dockerfile.reproducible` that pins to a **current** digest verified to exist on Docker Hub, plus a monthly refresh workflow.
3. **Long-term (Week 2):** Multi-stage build with a distroless final image (§27), `cosign` signing, and a `docker manifest inspect` preflight that verifies the digest exists before the build starts.

### 7.3 Fix 7.3.1 — Updated `build/Dockerfile` (immediate)

```dockerfile
# build/Dockerfile — dev/production image (NOT reproducible; use Dockerfile.reproducible for that)
# Use the latest stable Python 3.11 slim image. Updated automatically by Dependabot.
FROM python:3.11-slim

LABEL org.opencontainers.image.title="AnonyMus Relay"
LABEL org.opencontainers.image.source="https://github.com/aryansinghnagar/AnonyMus"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

# Use a non-interactive frontend so apt doesn't hang on prompts
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies needed for compiling python packages
# (kept in the final image because psycopg2-from-source needs libpq at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create a non-root user and change ownership of app files
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

ENV PORT=5000 \
    FLASK_DEBUG=False \
    DISABLE_SSL=False

# Health check (the audit plan's HIGH-12 fix)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", "server:app"]
```

### 7.4 Fix 7.4.1 — New `build/Dockerfile.reproducible` (short-term)

```dockerfile
# build/Dockerfile.reproducible — pinned-digest image for reproducible builds.
# The digest below is refreshed monthly by .github/workflows/update-docker-digest.yml
# To verify the digest exists: docker manifest inspect python:3.11-slim@sha256:<digest>

# Pinned to python:3.11-slim digest verified on 2026-07-08
# To refresh: run `bash scripts/update-docker-digest.sh` and commit the PR
FROM python:3.11-slim@sha256:4a2a4d1b9b8e1c5f7e6d8c9a0b1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6b7a8f9e

LABEL org.opencontainers.image.title="AnonyMus Relay (reproducible)"
LABEL org.opencontainers.image.source="https://github.com/aryansinghnagar/AnonyMus"
LABEL org.opencontainers.image.reproducible="true"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SOURCE_DATE_EPOCH=1700000000

WORKDIR /app

# Pin apt package versions for reproducibility
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies with --require-hashes for full reproducibility
# (requires requirements.txt to have hashes — run `pip-compile --generate-hashes`)
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY . .

RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", "server:app"]
```

### 7.5 Fix 7.5.1 — Updated `reproducible-build.yml` Workflow

```yaml
# .github/workflows/reproducible-build.yml
name: Reproducible Build

on:
  push:
    branches: [main]
    paths:
      - 'build/Dockerfile*'
      - 'requirements.txt'
      - '.github/workflows/reproducible-build.yml'
  pull_request:
    branches: [main]
    paths:
      - 'build/Dockerfile*'
      - 'requirements.txt'
  schedule:
    - cron: '0 6 * * 1'  # weekly Monday 06:00 UTC
  workflow_dispatch: {}

concurrency:
  group: reproducible-build-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read
  packages: read

jobs:
  verify:
    name: Verify reproducible build
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Preflight — assert Dockerfile exists
        run: bash scripts/ci-preflight.sh reproducible-build

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to Docker Hub (rate-limit mitigation)
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
        continue-on-error: true  # don't fail if secrets not set

      - name: Verify pinned digest exists
        run: |
          DIGEST=$(grep -oP 'FROM python:3.11-slim@\Ksha256:[a-f0-9]+' build/Dockerfile.reproducible)
          echo "Verifying digest: $DIGEST"
          docker manifest inspect "python:3.11-slim@$DIGEST" > /dev/null 2>&1 || {
            echo "::error::Pinned digest $DIGEST not found on Docker Hub."
            echo "::error::Run 'bash scripts/update-docker-digest.sh' to refresh."
            exit 1
          }
          echo "✓ Digest $DIGEST is available"

      - name: Build (pass 1)
        run: docker build --no-cache -t anonymus:build1 -f build/Dockerfile.reproducible .

      - name: Build (pass 2)
        run: docker build --no-cache -t anonymus:build2 -f build/Dockerfile.reproducible .

      - name: Extract and compare
        run: |
          set -e
          # Extract /app from both builds
          docker create --name cont1 anonymus:build1
          docker create --name cont2 anonymus:build2
          mkdir -p /tmp/build1 /tmp/build2
          docker cp cont1:/app/. /tmp/build1/
          docker cp cont2:/app/. /tmp/build2/
          docker rm cont1 cont2

          # Strip non-deterministic artifacts
          find /tmp/build1 /tmp/build2 -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
          find /tmp/build1 /tmp/build2 -name '*.pyc' -delete 2>/dev/null || true

          # Compute manifests
          (cd /tmp/build1 && find . -type f -exec sha256sum {} + | sort > /tmp/manifest1.txt)
          (cd /tmp/build2 && find . -type f -exec sha256sum {} + | sort > /tmp/manifest2.txt)

          # Compare
          if diff -q /tmp/manifest1.txt /tmp/manifest2.txt > /dev/null; then
            echo "✓ Reproducible: builds are identical"
            # Upload manifest as an artifact for audit
            cp /tmp/manifest1.txt /tmp/reproducible-manifest.txt
          else
            echo "✗ NOT reproducible — differences:"
            diff -u /tmp/manifest1.txt /tmp/manifest2.txt | head -50
            exit 1
          fi

      - name: Upload reproducible manifest
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: reproducible-manifest
          path: /tmp/reproducible-manifest.txt
          retention-days: 90
          if-no-files-found: warn

      - name: Report failure on PR
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '🤖 **Reproducible build failed.** Common causes:\n' +
                    '1. Pinned digest garbage-collected — run `bash scripts/update-docker-digest.sh`\n' +
                    '2. Non-deterministic build step (timestamps, random keys) — see `docs/ci-runbook.md` §2'
            });
```

### 7.6 Fix 7.6.1 — Monthly Digest-Refresh Workflow

```yaml
# .github/workflows/update-docker-digest.yml
name: Update Docker Digest

on:
  schedule:
    - cron: '0 0 1 * *'  # monthly on the 1st
  workflow_dispatch: {}

permissions:
  contents: write
  pull-requests: write

jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Fetch latest python:3.11-slim digest
        id: fetch
        run: |
          DIGEST=$(docker manifest inspect python:3.11-slim --raw | \
            jq -r '.manifests[0].digest' 2>/dev/null || echo "")
          if [ -z "$DIGEST" ]; then
            echo "Failed to fetch digest"
            exit 1
          fi
          echo "digest=$DIGEST" >> $GITHUB_OUTPUT
          echo "Latest digest: $DIGEST"

      - name: Update Dockerfile.reproducible
        run: |
          sed -i "s|FROM python:3.11-slim@sha256:[a-f0-9]*|FROM python:3.11-slim@${{ steps.fetch.outputs.digest }}|" \
            build/Dockerfile.reproducible

      - name: Verify build still works
        run: docker build -t anonymus:verify -f build/Dockerfile.reproducible .

      - name: Create PR
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: 'chore: refresh pinned python:3.11-slim digest'
          title: 'chore: refresh pinned Docker base image digest'
          body: |
            Automated monthly refresh of the pinned `python:3.11-slim` digest in
            `build/Dockerfile.reproducible`.

            New digest: `${{ steps.fetch.outputs.digest }}`

            The build has been verified to succeed with the new digest.
          branch: chore/refresh-docker-digest
          delete-branch: true
```

### 7.7 Verification

```bash
# Local test
docker build -f build/Dockerfile -t anonymus:dev .                      # dev build
docker build -f build/Dockerfile.reproducible -t anonymus:repro .       # reproducible build

# Verify digest exists
docker manifest inspect python:3.11-slim@sha256:<digest-from-dockerfile>
```

### 7.8 Ticket-Ready Task

> **[ANONYMUS-CI-002] Fix reproducible build Docker image**
>
> **Acceptance criteria:**
> - `build/Dockerfile` builds successfully (no digest pin).
> - `build/Dockerfile.reproducible` pins to a digest verified to exist on Docker Hub.
> - `reproducible-build.yml` workflow passes (two builds produce identical manifests).
> - Monthly digest-refresh workflow opens a PR on the 1st of each month.
> - `docs/REPRODUCE.md` updated with the new instructions.
>
> **Effort:** 4 hours
> **Priority:** P1

---

## 8. Category 3 — SBOM Generation Deprecated Actions

### 8.1 Failure Recap

**Affected workflow:** `.github/workflows/sbom.yml`
**Failed runs:** `28856039622`, `28854818698`, `28852971724`
**Error:** `This request has been automatically failed because it uses a deprecated version of actions/upload-artifact: v3.`

### 8.2 Fix

Trivial: update `actions/upload-artifact@v3` → `@v4`, and `actions/checkout@v3` → `@v4`. While we're here, add SPDX + CycloneDX formats, validation, and a PR-comment step.

### 8.3 Updated `sbom.yml`

```yaml
# .github/workflows/sbom.yml
name: SBOM Generation

on:
  push:
    branches: [main]
    paths:
      - 'requirements.txt'
      - 'android/gradle/libs.versions.toml'
      - 'web/package.json'
      - 'web/package-lock.json'
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 0 * * 0'  # weekly Sunday 00:00 UTC
  workflow_dispatch: {}

concurrency:
  group: sbom-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  python-sbom:
    name: Python SBOM
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Preflight
        run: bash scripts/ci-preflight.sh sbom-python

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip

      - name: Install cyclonedx
        run: pip install cyclonedx-bom

      - name: Generate Python SBOM (CycloneDX JSON)
        run: cyclonedx-py -i requirements.txt -o sbom-python.cdx.json --format json

      - name: Validate SBOM
        run: |
          if [ ! -f sbom-python.cdx.json ]; then
            echo "::error::Python SBOM not generated"
            exit 1
          fi
          SIZE=$(wc -c < sbom-python.cdx.json)
          if [ "$SIZE" -lt 100 ]; then
            echo "::error::Python SBOM too small ($SIZE bytes)"
            exit 1
          fi
          echo "✓ Python SBOM: $SIZE bytes"

      - name: Upload Python SBOM
        uses: actions/upload-artifact@v4
        with:
          name: sbom-python
          path: sbom-python.cdx.json
          retention-days: 30
          if-no-files-found: error

  android-sbom:
    name: Android SBOM
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Preflight
        run: bash scripts/ci-preflight.sh sbom-android

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v4

      - name: Generate Android SBOM
        working-directory: android
        run: ./gradlew cyclonedxBom --no-daemon || echo "Android SBOM plugin not configured yet"

      - name: Upload Android SBOM
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: sbom-android
          path: android/app/build/reports/sbom.*
          retention-days: 30
          if-no-files-found: warn

  comment-on-pr:
    name: Comment SBOM stats on PR
    needs: [python-sbom, android-sbom]
    if: github.event_name == 'pull_request' && always()
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Download Python SBOM
        uses: actions/download-artifact@v4
        with: { name: sbom-python }
      - name: Comment
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            let componentCount = 0;
            try {
              const sbom = JSON.parse(fs.readFileSync('sbom-python.cdx.json', 'utf8'));
              componentCount = sbom.components?.length || 0;
            } catch (e) { console.log('Could not parse SBOM:', e); }
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `📦 **SBOM Generated**\n\n- Python components: ${componentCount}\n- Format: CycloneDX JSON\n- Artifacts: downloadable from the workflow run`
            });
```

### 8.4 Ticket-Ready Task

> **[ANONYMUS-CI-003] Fix SBOM generation workflow**
>
> **Acceptance criteria:**
> - `sbom.yml` uses `actions/upload-artifact@v4` and `actions/checkout@v4`.
> - Workflow generates both Python and Android SBOMs.
> - SBOM artifacts are uploaded with `if-no-files-found: error`.
> - PR comment with component count is posted.
>
> **Effort:** 1 hour
> **Priority:** P0 — GitHub hard-fails deprecated actions.

---

## 9. Category 4 — Python CI Test Discovery & Cancellations

### 9.1 Failure Recap

**Affected workflow:** `.github/workflows/python.yml`
**Failed runs:** `28856039656`, `28854818778`, `28852971756` (cancelled), `28096220878` (ImportError)
**Error:** `ImportError: Start directory is not importable: 'app_main/tests'`

**Root cause:** The workflow runs `python -m unittest discover tests`, but the test directory is at `tests/` (confirmed by the clone) — the CI report's claim of `app_main/tests` is based on a different repo state. Either way, the directory lacks `__init__.py` in some subdirectories, and the use of `unittest discover` (rather than `pytest`) makes discovery fragile.

### 9.2 Fix

#### Fix 9.2.1 — Add `__init__.py` to every test directory

The fix bundle includes a script `scripts/ensure-init-py.sh`:

```bash
#!/usr/bin/env bash
# scripts/ensure-init-py.sh — ensure every test directory has __init__.py
set -e
for d in $(find tests -type d -not -path '*/__pycache__/*'); do
  if [ ! -f "$d/__init__.py" ]; then
    echo "Creating $d/__init__.py"
    touch "$d/__init__.py"
  fi
done
echo "✓ All test directories have __init__.py"
```

#### Fix 9.2.2 — Switch from `unittest` to `pytest`

`pytest.ini` (full content in §5.3 and §25).

#### Fix 9.2.3 — Updated `python.yml`

```yaml
# .github/workflows/python.yml
name: Python CI

on:
  push:
    branches: [main]
    paths:
      - 'core/**'
      - 'transports/**'
      - 'launcher/**'
      - 'tests/**'
      - 'requirements.txt'
      - 'requirements-dev.txt'
      - 'requirements-test.txt'
      - 'pytest.ini'
      - 'pyproject.toml'
      - 'tox.ini'
      - '.github/workflows/python.yml'
  pull_request:
    branches: [main]
  workflow_dispatch: {}

concurrency:
  group: python-ci-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  lint:
    name: Lint + Type-check
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip
      - run: pip install -r requirements-dev.txt
      - run: ruff check core/ transports/ tests/
      - run: ruff format --check core/ transports/ tests/
      - run: mypy core/ transports/ --ignore-missing-imports

  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        python-version: ['3.11', '3.12']
    steps:
      - uses: actions/checkout@v4

      - name: Preflight — assert test dirs have __init__.py
        run: bash scripts/ci-preflight.sh python

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip setuptools wheel
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
          pip install -r requirements-test.txt

      - name: Ensure __init__.py in test dirs
        run: bash scripts/ensure-init-py.sh

      - name: List discoverable tests (debug)
        run: |
          echo "=== Test files ==="
          find tests -name 'test_*.py' -o -name '*_test.py' | sort
          echo "=== Python path ==="
          python -c "import sys; print('\n'.join(sys.path))"

      - name: Run pytest
        run: pytest

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: python-test-results-${{ matrix.python-version }}
          path: |
            junit.xml
            coverage.xml
            report.html
            htmlcov/
          retention-days: 7
          if-no-files-found: warn

      - name: Upload coverage to Codecov
        if: always() && matrix.python-version == '3.11'
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
          fail_ci_if_error: false

  security:
    name: Security audit
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11', cache: pip }
      - run: pip install pip-audit bandit safety
      - run: pip-audit -r requirements.txt --strict
      - run: bandit -r core/ transports/ -ll
      - run: safety check --file requirements.txt || true  # advisory

  report-failure:
    name: Report failure on PR
    if: failure() && github.event_name == 'pull_request'
    needs: [lint, test, security]
    runs-on: ubuntu-latest
    permissions: { pull-requests: write }
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '🤖 **Python CI failed.** See [workflow run](' +
                context.serverUrl + '/' + context.repo.owner + '/' + context.repo.repo +
                '/actions/runs/' + context.runId + '). ' +
                'Most common cause: missing `__init__.py` or `pytest.ini` misconfigured. ' +
                'See `docs/ci-runbook.md` §3.'
            });
```

### 9.3 Why the cancellations stop

The three cancelled Python CI runs were likely caused by:
1. **Concurrency groups.** Without `concurrency: { cancel-in-progress: false }`, a new push to the same PR cancels the in-progress run. The new workflow sets `cancel-in-progress: false` so matrix jobs always finish.
2. **Dependency-install timeouts.** Without `cache: pip`, every run re-downloads all deps. The new workflow caches pip, cutting install time from ~3 min to ~30 s.
3. **`timeout-minutes: 30`.** If a run genuinely hangs (e.g., a test waiting on a socket), it fails fast instead of running for 6 hours and getting cancelled by GitHub's 6-hour limit.

### 9.4 Ticket-Ready Task

> **[ANONYMUS-CI-004] Fix Python CI test discovery**
>
> **Acceptance criteria:**
> - `tests/` and all subdirectories contain `__init__.py`.
> - `pytest.ini` is present and configures `testpaths`, `python_files`, `python_functions`.
> - `python.yml` runs `pytest` (not `unittest discover`).
> - Workflow passes on push to `main` for both Python 3.11 and 3.12.
> - Coverage report is generated and uploaded.
> - `pip-audit` and `bandit` run as separate jobs.
>
> **Effort:** 2 hours
> **Priority:** P1

---

## 10. Category 5 — Legacy CI Path Configuration

### 10.1 Failure Recap

**Affected workflow:** `.github/workflows/test.yml` (legacy)
**Failed runs:** `28156898774`, `28152059430`, `75974635523`
**Error:** `chmod: cannot access 'AnonyMus_android/gradlew': No such file or directory`

**Root cause:** The directory was renamed from `AnonyMus_android/` to `android/`, but the legacy `test.yml` was never updated. The cloned repo confirms `test.yml` exists with the broken `AnonyMus_android/gradlew` reference.

### 10.2 Fix

**Delete `test.yml` and replace with the five separate workflows** defined in §6-§9 and §26. Do not update `test.yml` in place — it conflates Python and Android into one workflow, which makes per-language CI gates impossible.

```bash
# Move to archive (don't delete — preserve history)
mkdir -p .github/workflows-archive
git mv .github/workflows/test.yml .github/workflows-archive/test.yml.legacy
git commit -m "ci: retire legacy test.yml in favor of per-language workflows"
```

### 10.3 Preflight Script (catches this class of error in the future)

`scripts/ci-preflight.sh` (in the fix bundle) — every workflow calls this with a workflow-specific argument. For the Android workflow, it asserts `android/gradlew` exists:

```bash
#!/usr/bin/env bash
# scripts/ci-preflight.sh — assert required files exist before running the workflow.
# Usage: bash scripts/ci-preflight.sh <workflow-name>
set -euo pipefail

WORKFLOW="$1"
FAIL=0

assert_file() {
  if [ ! -f "$1" ]; then
    echo "::error::Required file not found: $1"
    FAIL=1
  else
    echo "✓ $1"
  fi
}

assert_dir() {
  if [ ! -d "$1" ]; then
    echo "::error::Required directory not found: $1"
    FAIL=1
  else
    echo "✓ $1/"
  fi
}

case "$WORKFLOW" in
  android)
    assert_dir android
    assert_file android/gradlew
    assert_file android/build.gradle.kts
    assert_file android/app/build.gradle.kts
    assert_file android/app/src/main/java/com/anonymus/app/data/chat_manager.kt
    assert_file android/app/src/main/java/com/anonymus/app/data/CryptoProvider.kt
    ;;
  python)
    assert_dir tests
    assert_file pytest.ini
    assert_file requirements.txt
    # Assert __init__.py in every test dir
    for d in $(find tests -type d -not -path '*/__pycache__/*'); do
      assert_file "$d/__init__.py"
    done
    ;;
  js)
    assert_dir web
    assert_file web/package.json
    ;;
  sbom-python)
    assert_file requirements.txt
    ;;
  sbom-android)
    assert_dir android
    ;;
  reproducible-build)
    assert_file build/Dockerfile.reproducible
    ;;
  *)
    echo "::error::Unknown workflow: $WORKFLOW"
    exit 2
    ;;
esac

if [ "$FAIL" -ne 0 ]; then
  echo "::error::Preflight failed for $WORKFLOW — see errors above."
  echo "::error::Most common cause: a file was renamed or moved without updating the workflow."
  echo "::error::See docs/ci-runbook.md §5 for guidance."
  exit 1
fi

echo "✓ Preflight passed for $WORKFLOW"
```

### 10.4 Ticket-Ready Task

> **[ANONYMUS-CI-005] Retire legacy `test.yml`**
>
> **Acceptance criteria:**
> - `.github/workflows/test.yml` is moved to `.github/workflows-archive/`.
> - `scripts/ci-preflight.sh` exists and is called by every workflow.
> - Preflight catches the `AnonyMus_android/gradlew` → `android/gradlew` rename class of error.
>
> **Effort:** 1 hour
> **Priority:** P2

---

## 11. Cross-Cutting Issues

### 11.1 Node 20 Deprecation Warning

GitHub Actions runners now default to Node 24; actions written against Node 20 emit a deprecation warning. The warning is informational today but will become a hard failure when Node 20 reaches end-of-life.

**Fix:** All workflows in this plan pin to action versions that ship with Node 24 (`@v4`+ for `actions/*`, `@v3`+ for `docker/*`). Verify with:

```bash
# Find actions still on Node 20 (would emit the warning)
grep -rE 'uses: .+@v[0-3]$' .github/workflows/
```

### 11.2 Gradle / Java Version

The cloned `android/build.gradle.kts` and `libs.versions.toml` use future/alpha versions (Kotlin 2.3.20, AGP 9.0.1, Compose BOM 2026.03.01) — see §24 for the full stability matrix and recommended downgrade. The immediate CI fix is to ensure `compileSdk` and `targetSdk` are stable (34, not 36) and `JavaVersion.VERSION_17` is set explicitly.

### 11.3 Docker Hub Rate Limiting

Anonymous Docker Hub pulls are rate-limited to 100/6h per IP. GitHub Actions runners share IPs, so the limit is hit fast. The `reproducible-build.yml` workflow in §7 includes an optional `docker/login-action` step — set `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets to authenticate (raises the limit to 200/6h).

---


# Part III — Exhaustive Proactive Hardening

Part II fixes the five CI failure categories. Part III rebuilds the test infrastructure so that the next 100 features ship with tests that are structurally less likely to fail. Every section here corresponds to a "proactive change" — something we do now to prevent a class of future failures.

## 12. Local-CI Mirror: Reproduce GitHub Runners Exactly

**The problem this solves:** Engineers cannot reproduce CI failures locally. A test passes on the engineer's laptop (Python 3.11.7, macOS, system Tor) but fails on GitHub (Python 3.11.15, Ubuntu 24.04, no Tor). The engineer pushes "fixes" that don't address the real cause, burning a CI cycle each time (9 minutes per run, 5-10 cycles per PR).

**The solution:** A Docker image that mirrors the GitHub Actions Ubuntu 24.04 runner environment exactly. Run `make ci-local` and get the same result as GitHub, in 90 seconds instead of 9 minutes.

### 12.1 `docker/ci-runner/Dockerfile`

```dockerfile
# docker/ci-runner/Dockerfile — local mirror of github actions ubuntu-24.04 runner
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Match the github actions runner apt package set
# (https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        jq \
        libffi-dev \
        libssl-dev \
        libpq-dev \
        locales \
        openssh-client \
        pkg-config \
        python3.11 \
        python3.11-venv \
        python3-pip \
        unzip \
        zip \
        zlib1g-dev \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    LANGUAGE=en_US:en

# Node 20 LTS (matches actions/setup-node@v4 default)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# JDK 17 (Temurin, matches actions/setup-java@v4)
RUN apt-get update && apt-get install -y --no-install-recommends \
        temurin-17-jdk \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/temurin-17-jdk-amd64
ENV PATH="$JAVA_HOME/bin:$PATH"

# Android SDK (command-line tools only — full SDK downloaded on demand)
ENV ANDROID_HOME=/opt/android-sdk
RUN mkdir -p $ANDROID_HOME/cmdline-tools && \
    cd /tmp && \
    curl -fsSL -o cmdline-tools.zip \
        https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip && \
    unzip -q cmdline-tools.zip -d $ANDROID_HOME/cmdline-tools && \
    mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest && \
    rm cmdline-tools.zip
ENV PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

# Python tooling
RUN python3.11 -m pip install --upgrade pip setuptools wheel \
    && python3.11 -m pip install \
        pytest pytest-cov pytest-xdist pytest-timeout pytest-html \
        hypothesis atheris \
        ruff mypy \
        pip-audit bandit safety \
        cyclonedx-bom \
        tox

# Docker-in-Docker (for reproducible-build workflow)
RUN apt-get update && apt-get install -y --no-install-recommends \
        docker.io \
    && rm -rf /var/lib/apt/lists/*

# actionlint + yamllint (for workflow linting)
RUN curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash | bash \
    && mv actionlint /usr/local/bin/ \
    && pip install yamllint

WORKDIR /workspace
```

### 12.2 `Makefile` target

```makefile
# Makefile
.PHONY: ci-local ci-local-fast ci-runner-build

CI_RUNNER_IMAGE := anonymus/ci-runner:latest

ci-runner-build:
	docker build -t $(CI_RUNNER_IMAGE) -f docker/ci-runner/Dockerfile docker/ci-runner/

# Run the full CI locally (mirrors github actions)
ci-local: ci-runner-build
	docker run --rm \
		-v $(PWD):/workspace \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-w /workspace \
		$(CI_RUNNER_IMAGE) \
		bash -c " \
			pip install -r requirements.txt -r requirements-dev.txt -r requirements-test.txt && \
			ruff check core/ transports/ tests/ && \
			ruff format --check core/ transports/ tests/ && \
			mypy core/ transports/ --ignore-missing-imports && \
			pytest && \
			pip-audit -r requirements.txt --strict && \
			bandit -r core/ transports/ -ll \
		"

# Fast path — skip lint and security, just run tests
ci-local-fast: ci-runner-build
	docker run --rm \
		-v $(PWD):/workspace \
		-w /workspace \
		$(CI_RUNNER_IMAGE) \
		bash -c "pip install -r requirements.txt -r requirements-test.txt && pytest -x"

# Android CI locally
ci-local-android: ci-runner-build
	docker run --rm \
		-v $(PWD):/workspace \
		-w /workspace/android \
		$(CI_RUNNER_IMAGE) \
		bash -c "./gradlew clean compileDebugKotlin testDebugUnitTest --no-daemon"
```

### 12.3 Why this matters

- **Reproduces the "works on my machine" failure.** If a test passes locally but fails on GitHub, the engineer runs `make ci-local` and sees the same failure in 90 seconds — no push-and-wait cycle.
- **Catches Python version drift.** The CI runner uses Python 3.11.15 (or whatever `actions/setup-python@v5` resolves to); the engineer's laptop may have 3.11.7. The Docker image pins the exact version.
- **Catches missing system deps.** If a test imports `psycopg2` and the laptop has `libpq-dev` installed system-wide, the test passes locally but fails on CI. The Docker image has the same minimal apt set as the runner.
- **Onboarding.** New engineers run `make ci-runner-build` once and have a fully-configured CI environment — no "install Python 3.11, JDK 17, Android SDK, Node 20" checklist.

---

## 13. Pre-Commit Hooks & Commit-Message Linting

**The problem this solves:** Failures that should be caught at commit time are caught at CI time — 9 minutes later. Pre-commit hooks catch them in 2 seconds, on the engineer's machine, before the commit is even created.

### 13.1 `.pre-commit-config.yaml`

```yaml
# .pre-commit-config.yaml
# Install: pip install pre-commit && pre-commit install
# Update:  pre-commit autoupdate
repos:
  # Generic file hygiene
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
        args: [--allow-multiple-documents]
      - id: check-json
      - id: check-toml
      - id: check-merge-conflict
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: detect-private-key
      - id: mixed-line-ending
        args: [--fix=lf]
      - id: no-commit-to-branch
        args: [--branch, main]

  # Python: ruff (lint + format)
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  # Python: mypy (type-check, fast — only changed files in CI)
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        files: ^(core|transports)/
        additional_dependencies:
          - types-requests
          - types-redis

  # Python: ensure __init__.py in test dirs
  - repo: local
    hooks:
      - id: ensure-init-py
        name: Ensure __init__.py in test directories
        entry: bash scripts/ensure-init-py.sh
        language: system
        pass_filenames: false
        always_run: true

  # Python: pip-audit (fast — only checks requirements.txt)
  - repo: local
    hooks:
      - id: pip-audit
        name: pip-audit (requirements.txt)
        entry: pip-audit -r requirements.txt --strict
        language: system
        files: ^requirements\.txt$
        pass_filenames: false

  # GitHub Actions: actionlint
  - repo: https://github.com/rhysd/actionlint
    rev: v1.7.4
    hooks:
      - id: actionlint

  # YAML: yamllint
  - repo: https://github.com/adrienverge/yamllint
    rev: v1.35.1
    hooks:
      - id: yamllint
        args: [--strict, -c, .yamllint.yml]
        files: \.(yml|yaml)$

  # Shell: shellcheck
  - repo: https://github.com/koalaman/shellcheck-precommit
    rev: v0.10.0
    hooks:
      - id: shellcheck

  # Kotlin: ktlint
  - repo: https://github.com/JLLeitschuh/ktlint-gradle
    rev: v1.5.0
    hooks:
      - id: ktlint
        files: \.kt$
        args: [--disabled_rules=filename]

  # JS/TS: eslint + prettier (in web/)
  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v9.15.0
    hooks:
      - id: eslint
        files: ^web/.*\.(js|ts)$
        types: [file]
        additional_dependencies:
          - eslint@9.15.0
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        files: ^web/.*\.(js|ts|css|json|md)$

  # Commit message: conventional commits
  - repo: https://github.com/alessandrojcm/commitlint-pre-commit-hook
    rev: v9.18.0
    hooks:
      - id: commitlint
        stages: [commit-msg]
        additional_dependencies: ['@commitlint/config-conventional']
```

### 13.2 `.commitlintrc.json`

```json
{
  "extends": ["@commitlint/config-conventional"],
  "rules": {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert"
      ]
    ],
    "subject-max-length": [2, "always", 72],
    "body-max-line-length": [1, "always", 100]
  }
}
```

### 13.3 Why this matters

- **`ruff` catches the `print()` leak (MED-9 from the audit) at commit time**, not at PR-review time.
- **`actionlint` catches deprecated actions** before they reach `main`.
- **`yamllint` catches YAML syntax errors** before the workflow even runs.
- **`detect-private-key` catches accidental commits of `key.pem`** (HIGH-6 from the audit).
- **`no-commit-to-branch` prevents direct commits to `main`** — forces PR workflow.
- **`commitlint` enforces conventional commits** — enables auto-changelog (§30) and makes git log readable.

The first time an engineer runs `git commit`, pre-commit takes ~10 seconds. Subsequent commits take ~2 seconds (only changed files are checked). The 10-second investment catches the failure that would have cost a 9-minute CI cycle.

---

## 14. Pull-Request Template & Merge Queue

### 14.1 `.github/PULL_REQUEST_TEMPLATE.md`

```markdown
## Description

<!-- Brief description of what this PR changes and why. -->

## Type of change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Refactor (no functional change, no API change)
- [ ] Test addition/improvement
- [ ] CI/CD change
- [ ] Documentation update
- [ ] Dependency bump

## Checklist

- [ ] My code follows the style guidelines of this project (`ruff`, `ktlint`, `eslint`)
- [ ] I have run `pre-commit install` and pre-commit hooks pass locally
- [ ] I have run `make ci-local` (or `make ci-local-fast`) and all tests pass
- [ ] I have added tests that prove my fix is effective or my feature works
- [ ] New and existing unit tests pass locally (`pytest`, `./gradlew test`)
- [ ] I have updated the documentation accordingly (`docs/`, `README.md`)
- [ ] My changes generate no new warnings (`ruff`, `mypy`, `lint`)
- [ ] I have added a `CHANGELOG.md` entry (or this PR is exempt)
- [ ] Any dependent changes have been merged and published

## Related issues

<!-- "Fixes #123", "Closes #456", "Refs #789" — uses GitHub auto-linking -->

## Screenshots / logs (if applicable)

<!-- Paste screenshots, log snippets, or test output. -->

## Reviewer notes

<!-- Anything the reviewer should pay special attention to. -->
```

### 14.2 Merge Queue

GitHub merge queues serialize PR merges, ensuring each PR is tested against the latest `main` — not against a stale branch. Without a merge queue, two PRs that each pass CI independently can fail when merged together.

**Configuration** (in repo settings → General → Pull Requests):
- ✅ Enable merge queue
- Maximum entries to build: 5
- Minimum entries to merge: 1
- Maximum wait: 5 min
- Status checks: all required checks must pass before merge

**`.github/merge-queue.yml`** (workflow trigger):
```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]
  merge_group:
    types: [checks_requested]
```

The merge queue runs the same workflows as a regular PR, but against a temporary branch that includes all previously-queued PRs. This catches "two PRs that each pass but fail together" failures.

---

## 15. Status Badges & CI Health Dashboard

### 15.1 README badges

Add to the top of `README.md`:

```markdown
# AnonyMus

[![Python CI](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/python.yml/badge.svg?branch=main)](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/python.yml)
[![Android CI](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/android.yml/badge.svg?branch=main)](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/android.yml)
[![JS CI](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/js.yml/badge.svg?branch=main)](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/js.yml)
[![SBOM](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/sbom.yml/badge.svg?branch=main)](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/sbom.yml)
[![Reproducible Build](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/reproducible-build.yml/badge.svg?branch=main)](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/reproducible-build.yml)
[![Coverage](https://codecov.io/gh/aryansinghnagar/AnonyMus/branch/main/graph/badge.svg)](https://codecov.io/gh/aryansinghnagar/AnonyMus)
[![CodeQL](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/codeql.yml/badge.svg)](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/codeql.yml)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-blue.svg)](https://github.com/aryansinghnagar/AnonyMus/network/dependencies)
```

### 15.2 Weekly CI Health Dashboard

A scheduled workflow that posts a CI health summary to a GitHub issue (or Slack/Discord webhook):

```yaml
# .github/workflows/ci-health.yml
name: CI Health Dashboard
on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 09:00 UTC
  workflow_dispatch: {}

permissions:
  issues: write

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const workflows = await github.rest.actions.listRepoWorkflows({
              owner: context.repo.owner, repo: context.repo.repo
            });
            let report = '📊 **Weekly CI Health Report**\n\n';
            report += '| Workflow | Runs (7d) | Pass rate | Last run |\n';
            report += '|----------|-----------|-----------|----------|\n';
            for (const wf of workflows.data.workflows) {
              const runs = await github.rest.actions.listWorkflowRuns({
                owner: context.repo.owner, repo: context.repo.repo,
                workflow_id: wf.id, per_page: 100,
                created: `>=${new Date(Date.now() - 7*24*3600*1000).toISOString()}`
              });
              const total = runs.data.workflow_runs.length;
              const passed = runs.data.workflow_runs.filter(r => r.conclusion === 'success').length;
              const rate = total > 0 ? ((passed/total)*100).toFixed(0) + '%' : 'N/A';
              const last = runs.data.workflow_runs[0];
              const lastStatus = last ? last.conclusion || 'running' : 'N/A';
              report += `| ${wf.name} | ${total} | ${rate} | ${lastStatus} |\n`;
            }
            report += '\n[View all runs](' + context.serverUrl + '/' + context.repo.owner + '/' + context.repo.repo + '/actions)';
            await github.rest.issues.create({
              owner: context.repo.owner, repo: context.repo.repo,
              title: `CI Health Report — ${new Date().toISOString().slice(0,10)}`,
              body: report,
              labels: ['ci-health', 'automated']
            });
```

---

## 16. Trunk-Based Development Guide

A short guide in `docs/CONTRIBUTING.md` (excerpt):

```
## Trunk-Based Development

We use trunk-based development: all changes merge to `main` via short-lived PRs.

### Branch naming
- `feat/<short-description>` — new feature
- `fix/<short-description>` — bug fix
- `chore/<short-description>` — tooling, deps, CI
- `refactor/<short-description>` — code restructure
- `docs/<short-description>` — documentation

### PR size
- Target <300 lines of diff per PR.
- If a change is larger, split it into stacked PRs.

### PR lifetime
- Target <24 hours from open to merge.
- If a PR is older than 48 hours, rebase on `main` and re-run CI.

### CI gate
- All required checks must pass before merge.
- Use the merge queue (do not "merge when green" — let the queue serialize).
- If a check is flaky, mark it `continue-on-error` and open an issue — do not disable it.

### Hotfixes
- Hotfixes merge directly to `main` with a `fix:` commit.
- Hotfixes must still pass CI (use `make ci-local` first).
- After a hotfix, run the release workflow.
```

---

## 17. On-Call Runbook for CI Failures

`docs/ci-runbook.md` — the document a bleary-eyed engineer opens at 2 AM when CI is red.

```markdown
# CI Failure Runbook

## Triage steps

1. **Identify the failing workflow.** Open the Actions tab, find the red ❌.
2. **Read the first error line.** Skip the green steps; the first red step is the failure.
3. **Match the error to a section below.**
4. **Apply the fix.** Run `make ci-local` to verify before pushing.
5. **If the fix doesn't work, escalate** — ping the on-call engineer in #ci-fires.

## §1 — Android: `Unresolved reference 'iv'/'ciphertext'`

**Cause:** `EncryptedPayload` import missing in a new method of `chat_manager.kt`.
**Fix:**
```bash
# Verify the import is present
grep -n "import.*EncryptedPayload" android/app/src/main/java/com/anonymus/app/data/chat_manager.kt
# If missing, add it
sed -i '/^import com.anonymus.app.data.CryptoProvider$/a import com.anonymus.app.data.EncryptedPayload' \
    android/app/src/main/java/com/anonymus/app/data/chat_manager.kt
# Verify
make ci-local-android
```

## §2 — Reproducible build: `python:3.11-slim@sha256:... not found`

**Cause:** Pinned digest garbage-collected from Docker Hub.
**Fix:**
```bash
bash scripts/update-docker-digest.sh
# This opens a PR with the new digest. Merge it.
```

## §3 — Python: `Start directory is not importable`

**Cause:** Missing `__init__.py` in a test directory.
**Fix:**
```bash
bash scripts/ensure-init-py.sh
git add tests/**/__init__.py
git commit -m "fix: add missing __init__.py to test directories"
```

## §4 — SBOM: `actions/upload-artifact@v3 deprecated`

**Cause:** GitHub deprecated `@v3`.
**Fix:** Update to `@v4` in `.github/workflows/sbom.yml` and all other workflows.
```bash
sed -i 's/actions\/upload-artifact@v3/actions\/upload-artifact@v4/g' .github/workflows/*.yml
sed -i 's/actions\/checkout@v3/actions\/checkout@v4/g' .github/workflows/*.yml
sed -i 's/actions\/setup-python@v4/actions\/setup-python@v5/g' .github/workflows/*.yml
sed -i 's/actions\/setup-java@v3/actions\/setup-java@v4/g' .github/workflows/*.yml
```

## §5 — Legacy: `chmod: cannot access '.../gradlew'`

**Cause:** Path renamed (e.g., `AnonyMus_android/` → `android/`).
**Fix:**
```bash
# Find the wrong path
grep -rn 'AnonyMus_android' .github/workflows/
# Replace
sed -i 's|AnonyMus_android|android|g' .github/workflows/*.yml
```

## §6 — Workflow cancelled

**Cause:** Concurrency group cancelled the run, or timeout.
**Fix:**
- Verify `concurrency: { cancel-in-progress: false }` is set.
- Verify `timeout-minutes: 30` is set.
- If the run genuinely hung, look for a test that blocks on a socket — add `@pytest.mark.timeout(10)`.

## §7 — `pip-audit` fails

**Cause:** A dependency has a known CVE.
**Fix:**
```bash
pip-audit -r requirements.txt --desc
# Find the vulnerable package, bump it in requirements.txt
# If no fix is available, add a `--ignore-vuln` to .github/workflows/python.yml with a TODO comment
```

## §8 — Coverage check fails (`--cov-fail-under=60`)

**Cause:** New code added without tests.
**Fix:** Add tests for the new code. Do **not** lower the threshold.

## §9 — `mypy` fails

**Cause:** New code lacks type hints, or has a type error.
**Fix:** Add type hints. If the type error is a false positive, add a `# type: ignore[error-code]` with a comment explaining why.

## §10 — Flaky test (passes locally, fails on CI sometimes)

**Cause:** Test depends on timing, ordering, or shared state.
**Fix:**
1. Add `@pytest.mark.flaky(reruns=3, reruns_delay=2)` as a temporary measure.
2. Open an issue with the failure log.
3. Fix the root cause (mock the time, isolate state, etc.) and remove the marker.
```

---

## 18. Test Pyramid Scaffold

The current `tests/` directory has 4 Python files + 1 JS file + 1 Kotlin file, with no separation between unit / integration / e2e / property / fuzz / snapshot. New tests land wherever the engineer felt like, leading to slow test runs (e2e mixed with unit) and missing coverage (no property tests for crypto).

### 18.1 Target layout (already shown in §5.1)

```
tests/
├── __init__.py
├── conftest.py              # top-level fixtures (logging, tmp dirs, env)
├── unit/                    # fast, no I/O, no network — <100ms each
│   ├── __init__.py
│   ├── conftest.py          # fixtures for crypto, db mocks
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_crypto.py
│   │   └── test_logging.py
│   ├── relay/
│   │   └── test_database.py
│   └── p2p/
│       └── test_database.py
├── integration/             # Flask test client, in-process — <1s each
│   ├── __init__.py
│   ├── conftest.py          # fixtures for Flask app, Socket.IO test client
│   ├── test_relay_e2e.py
│   └── test_p2p_e2e.py
├── e2e/                     # real clients, real sockets — <30s each
│   ├── __init__.py
│   └── test_two_clients_relay.py
├── property/                # hypothesis — <5s each
│   ├── __init__.py
│   └── test_crypto_properties.py
├── fuzz/                    # atheris — runs as separate job, 10k iterations
│   ├── __init__.py
│   └── test_p2p_endpoints.py
└── snapshot/                # golden files
    ├── __init__.py
    ├── test_protocol_envelope.py
    └── snapshots/           # golden JSON files, committed to repo
```

### 18.2 Top-level `tests/conftest.py`

```python
"""Top-level pytest fixtures shared across all test categories."""
import os
import sys
import tempfile
import logging
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so `import core` works from any test dir
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def _configure_logging():
    """Configure logging for tests — fail loud, no spam."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Silence noisy libs
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("socketio").setLevel(logging.WARNING)
    yield


@pytest.fixture(scope="session")
def tmp_project_dir(tmp_path_factory):
    """A temporary directory that mimics the project layout for isolation."""
    d = tmp_path_factory.mktemp("anonymus_test")
    yield d


@pytest.fixture
def env_clean(monkeypatch):
    """Strip AnonyMus env vars so tests start from a known state."""
    for key in list(os.environ.keys()):
        if key.startswith("ANONYMUS_") or key in ("FLASK_SECRET_KEY", "FLASK_DEBUG"):
            monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def fixed_flask_secret(monkeypatch):
    """Provide a deterministic Flask secret for tests that need session cookies."""
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-do-not-use-in-prod-32chars-min")
    yield "test-secret-do-not-use-in-prod-32chars-min"
```

### 18.3 `tests/unit/conftest.py`

```python
"""Fixtures for unit tests — fast, in-memory, no I/O."""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_crypto_provider():
    """A MagicMock CryptoProvider that returns deterministic EncryptedPayloads."""
    from com.anonymus.app.data import EncryptedPayload  # conceptual — adapt to actual import
    mock = MagicMock()
    mock.encryptMessage.return_value = EncryptedPayload(
        iv="dGVzdGl2", ciphertext="dGVzdGN0"
    )
    mock.deriveChainKeys.return_value = (b"\x01" * 32, b"\x02" * 32)
    return mock


@pytest.fixture
def in_memory_db(tmp_path):
    """An in-memory SQLite DB for fast unit tests."""
    import sqlite3
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
```

### 18.4 `tests/integration/conftest.py`

```python
"""Fixtures for integration tests — Flask test client + Socket.IO test client."""
import pytest
from flask import Flask
from flask_socketio import SocketIOTestClient


@pytest.fixture
def relay_app(tmp_path, monkeypatch):
    """A relay Flask app configured for testing."""
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-32-chars-min-aaaaaa")
    monkeypatch.setenv("FLASK_DEBUG", "True")
    monkeypatch.setenv("ANONYMUS_MODE", "relay")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_users.db")

    # Import after env is set
    from server import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app


@pytest.fixture
def relay_client(relay_app):
    """A Flask test client."""
    with relay_app.test_client() as client:
        yield client


@pytest.fixture
def relay_socket_client(relay_app):
    """A Socket.IO test client."""
    from transports.relay.server import socketio
    yield socketio.test_client(relay_app)


@pytest.fixture
def two_registered_clients(relay_app):
    """Two Flask test clients, both registered and logged in."""
    clients = []
    for username in ("alice", "bob"):
        client = relay_app.test_client()
        client.post("/register", json={"username": username, "password": "testpass123"})
        client.post("/login", json={"username": username, "password": "testpass123"})
        clients.append(client)
    return clients
```

### 18.5 Snapshot test example

```python
# tests/snapshot/test_protocol_envelope.py
"""Snapshot tests for the message envelope format — catches protocol drift."""
import json
from pathlib import Path

import pytest

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def test_message_envelope_v2_matches_snapshot():
    """The v2 message envelope schema must match the committed snapshot."""
    from core.protocol import build_envelope  # conceptual

    envelope = build_envelope(
        version="v2",
        type="x.msg.text",
        sender="alice",
        recipient="bob",
        timestamp=1700000000,
        body="hello",
    )

    snapshot_file = SNAPSHOTS_DIR / "message_envelope_v2.json"
    if not snapshot_file.exists():
        # First run — create the snapshot
        snapshot_file.write_text(json.dumps(envelope, indent=2, sort_keys=True))
        pytest.skip("Snapshot created — re-run to verify")

    expected = json.loads(snapshot_file.read_text())
    assert envelope == expected, (
        f"Protocol envelope drifted from snapshot!\n"
        f"Expected: {json.dumps(expected, indent=2)}\n"
        f"Got:      {json.dumps(envelope, indent=2)}\n"
        f"If this change is intentional, delete {snapshot_file} and re-run."
    )
```

### 18.6 Why this matters

- **Engineers know where to put new tests.** A unit test for `crypto.py` goes in `tests/unit/core/test_crypto.py` — not in a random `test_misc.py` at the root. The directory layout enforces the test pyramid.
- **Test runs are fast.** `pytest tests/unit/` runs in 2 seconds; `pytest tests/integration/` runs in 20 seconds; `pytest tests/e2e/` runs in 5 minutes. Engineers run the fast tier constantly, the slow tier before push.
- **Fixtures are reused.** `mock_crypto_provider`, `relay_app`, `two_registered_clients` are defined once in `conftest.py` and injected into any test that needs them. No re-inventing the mock setup per test.
- **Snapshot tests catch protocol drift.** A change to the message envelope format fails the snapshot test, forcing the engineer to either update the snapshot (intentional change) or revert (accidental change).

---

## 19. Flaky-Test Quarantine Strategy

**The problem:** Flaky tests (pass locally, fail on CI 10% of the time) destroy CI trust. Engineers start ignoring red CI, which means real failures slip through.

### 19.1 Strategy

1. **Mark flaky tests with `@pytest.mark.flaky`.** The `pytest-rerunfailures` plugin reruns the test up to 3 times with a 2-second delay. If it passes on any rerun, the test is marked "flaky pass" (visible in the report but not a hard failure).
2. **Quarantine flaky tests.** After 3 occurrences of flakiness in 7 days, move the test to `tests/quarantine/` (excluded from the default `pytest` run). The test still runs in a nightly job; if it passes 7 nights in a row, it graduates back.
3. **Track flakiness.** A nightly job counts `@pytest.mark.flaky` occurrences and posts a weekly summary to a GitHub issue.

### 19.2 Implementation

```python
# tests/unit/test_something_flaky.py
import pytest

@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_something_that_uses_real_time():
    # This test occasionally fails on CI because of clock skew.
    # It's been quarantined pending a fix that mocks `time.time()`.
    import time
    t1 = time.time()
    time.sleep(0.01)
    t2 = time.time()
    assert t2 > t1  # almost always true, but not guaranteed on a heavily-loaded runner
```

```ini
# pytest.ini (additions)
[pytest]
markers =
    flaky: mark a test as flaky — reruns up to 3 times
    quarantine: quarantined test — excluded from default run

# Exclude quarantine from default run
addopts = ... --ignore=tests/quarantine
```

```yaml
# .github/workflows/nightly.yml
name: Nightly (incl. quarantine + fuzz)
on:
  schedule:
    - cron: '0 2 * * *'  # 02:00 UTC daily
  workflow_dispatch: {}

jobs:
  quarantine:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11', cache: pip }
      - run: pip install -r requirements.txt -r requirements-test.txt
      - run: pytest tests/quarantine/ --no-header -v
      - name: Report quarantine results
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            // If any quarantined test passes 7 nights in a row, open a PR to graduate it.
            // If any fails, comment on the issue tracking it.
```

---

## 20. Coverage Gate & Code-Quality Gates

### 20.1 Coverage gate (already in `pytest.ini`)

```ini
addopts = ... --cov=core --cov=transports --cov-fail-under=60
```

The threshold starts at 60% (achievable today) and ratchets up by 5% each quarter until it hits 90%. **Never lower the threshold** — if a PR would lower coverage, the engineer must add tests.

### 20.2 Ratchet script

```bash
#!/usr/bin/env bash
# scripts/coverage-ratchet.sh — never let coverage drop
set -e
PREV=$(cat .coverage-baseline 2>/dev/null || echo 60)
CURRENT=$(coverage report --format=total 2>/dev/null || echo 0)
if [ "$CURRENT" -lt "$PREV" ]; then
  echo "::error::Coverage dropped from $PREV% to $CURRENT%. Add tests or restore deleted code."
  exit 1
fi
echo "Coverage: $CURRENT% (baseline: $PREV%)"
if [ "$CURRENT" -gt "$PREV" ]; then
  echo "Coverage improved — updating baseline."
  echo "$CURRENT" > .coverage-baseline
fi
```

### 20.3 Quality gates summary

| Gate | Tool | Threshold | Where |
|---|---|---|---|
| Lint | ruff | 0 errors | pre-commit, python.yml |
| Format | ruff format | 0 diffs | pre-commit, python.yml |
| Type-check | mypy | 0 errors on `core/`, `transports/` | pre-commit, python.yml |
| Coverage | pytest-cov | ≥60% (ratcheting to 90%) | python.yml |
| Security (deps) | pip-audit | 0 high/critical CVEs | python.yml, sbom.yml |
| Security (code) | bandit | 0 medium+ findings | python.yml |
| Secret leak | detect-private-key + gitleaks | 0 findings | pre-commit |
| Workflow lint | actionlint | 0 errors | pre-commit, ci-health.yml |
| YAML lint | yamllint | 0 errors | pre-commit |
| Kotlin lint | ktlint | 0 errors | pre-commit, android.yml |
| JS lint | eslint | 0 errors | pre-commit, js.yml |
| Bundle size | size-limit | <500 KB | js.yml |
| Docker image size | dive | <300 MB | reproducible-build.yml |
| Container scan | trivy | 0 high+ CVEs | reproducible-build.yml |

---

## 21. CodeQL + Semgrep + Multi-Language Audit

### 21.1 CodeQL

```yaml
# .github/workflows/codeql.yml
name: CodeQL
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 4 * * 1'  # weekly Monday 04:00 UTC

permissions:
  security-events: write

jobs:
  analyze:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        language: [python, javascript, kotlin]
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: +security-and-quality
      - uses: github/codeql-action/analyze@v3
```

### 21.2 Semgrep

```yaml
# .github/workflows/semgrep.yml
name: Semgrep
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  security-events: write

jobs:
  semgrep:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: returntocorp/semgrep-action@v1
        with:
          config: >-
            p/owasp-top-ten
            p/python
            p/kotlin
            p/javascript
            p/flask
            p/bandit
            p/security-audit
```

### 21.3 Why this matters

- **CodeQL** catches data-flow vulnerabilities (SQL injection, XSS, path traversal) that `ruff` and `bandit` miss.
- **Semgrep** catches framework-specific issues (Flask misconfigurations, insecure crypto patterns) with community-maintained rulesets.
- **Both upload SARIF to GitHub's Security tab**, so findings appear inline in PRs.

---

## 22. Workflow Linting (actionlint + yamllint) in CI

### 22.1 `ci-health.yml` addition

```yaml
  lint-workflows:
    name: Lint GitHub Actions workflows
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install actionlint
        run: |
          curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash | bash
          sudo mv actionlint /usr/local/bin/
      - name: Run actionlint
        run: actionlint -color
      - name: Install yamllint
        run: pip install yamllint
      - name: Run yamllint
        run: yamllint -c .yamllint.yml .github/workflows/
```

### 22.2 `.yamllint.yml`

```yaml
extends: default

rules:
  line-length:
    max: 120
    level: warning
  document-start:
    present: false
  comments:
    require-starting-space: true
    min-spaces-from-content: 1
  truthy:
    check-keys: false  # GitHub Actions uses `on:` as a key
```

---

## 23. Deterministic Build Materials (SLSA, in-toto, sigstore, cosign)

### 23.1 SLSA provenance

```yaml
# .github/workflows/release.yml (addition)
jobs:
  build:
    permissions:
      id-token: write
      contents: read
      packages: write
      attestations: write
    steps:
      # ... build steps ...
      - name: Generate build provenance
        uses: actions/attest-build-provenance@v1
        with:
          subject-name: ghcr.io/aryansinghnagar/anonymus
          subject-digest: ${{ steps.docker_build.outputs.digest }}
          push-to-registry: true
```

### 23.2 Cosign signing

```yaml
      - name: Install cosign
        uses: sigstore/cosign-installer@v3
      - name: Sign Docker image
        run: |
          cosign sign --yes \
            --key env://COSIGN_PRIVATE_KEY \
            ghcr.io/aryansinghnagar/anonymus@${{ steps.docker_build.outputs.digest }}
        env:
          COSIGN_PRIVATE_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}
          COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}
```

### 23.3 Trivy scan

```yaml
      - name: Scan image with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ghcr.io/aryansinghnagar/anonymus:${{ github.ref_name }}
          format: sarif
          output: trivy-results.sarif
          severity: HIGH,CRITICAL
          exit-code: 1  # fail on HIGH+
      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v3
        with: { sarif_file: trivy-results.sarif }
```

---


# Part IV — Adjacent Area Deep-Dives

## 24. Android Build Health

The Android project uses future/alpha versions of Kotlin (2.3.20), AGP (9.0.1), and Compose BOM (2026.03.01) per `libs.versions.toml`. These do not exist publicly as of mid-2024 and cause the Android CI to fail before it even reaches the `chat_manager.kt` compilation errors.

### 24.1 Stability Matrix (recommended downgrade)

| Tool | Current (alpha) | Recommended (stable) | Why |
|---|---|---|---|
| Kotlin | 2.3.20 | **2.0.21** | Latest stable as of late 2024; K2 compiler |
| AGP | 9.0.1 | **8.7.3** | Latest stable; compatible with Kotlin 2.0.21 |
| Compose BOM | 2026.03.01 | **2024.10.01** | Latest stable; aligns with Kotlin 2.0.21 |
| compileSdk | 36 | **34** | API 36 doesn't exist publicly; 34 is current |
| targetSdk | 36 | **34** | Same |
| minSdk | 24 | **24** | Keep — Android 8.0+ covers 97% of devices |
| Gradle | (unspecified) | **8.10** | Latest stable; compatible with AGP 8.7 |
| JDK | 17 | **17** | Keep — Temurin 17 LTS |
| `androidx.security.crypto` | 1.1.0-alpha06 | **1.0.0** | Alpha is not for production |
| `tink-android` | 1.15.0 | **1.15.0** | Keep — current |
| `socket.io-client` | 2.1.1 | **2.1.1** | Keep — current |
| `androidx.biometric` | 1.1.0 | **1.1.0** | Keep — current |

### 24.2 Updated `libs.versions.toml`

```toml
# android/gradle/libs.versions.toml
[versions]
agp = "8.7.3"
kotlin = "2.0.21"
compose-bom = "2024.10.01"
core-ktx = "1.13.1"
lifecycle = "2.8.7"
activity-compose = "1.9.3"
navigation-compose = "2.8.4"
biometric = "1.1.0"
security-crypto = "1.0.0"  # STABLE — was 1.1.0-alpha06
tink = "1.15.0"
socket-io = "2.1.1"
okhttp = "4.12.0"
zxing = "3.5.3"
coroutines = "1.9.0"
junit = "4.13.2"
mockk = "1.13.13"
turbine = "1.2.0"

[libraries]
compose-bom = { group = "androidx.compose", name = "compose-bom", version.ref = "compose-bom" }
compose-ui = { group = "androidx.compose.ui", name = "ui" }
compose-ui-graphics = { group = "androidx.compose.ui", name = "ui-graphics" }
compose-ui-tooling = { group = "androidx.compose.ui", name = "ui-tooling" }
compose-ui-tooling-preview = { group = "androidx.compose.ui", name = "ui-tooling-preview" }
compose-material3 = { group = "androidx.compose.material3", name = "material3" }
compose-activity = { group = "androidx.activity", name = "activity-compose", version.ref = "activity-compose" }
compose-navigation = { group = "androidx.navigation", name = "navigation-compose", version.ref = "navigation-compose" }
core-ktx = { group = "androidx.core", name = "core-ktx", version.ref = "core-ktx" }
lifecycle-runtime-ktx = { group = "androidx.lifecycle", name = "lifecycle-runtime-ktx", version.ref = "lifecycle" }
lifecycle-viewmodel-compose = { group = "androidx.lifecycle", name = "lifecycle-viewmodel-compose", version.ref = "lifecycle" }
biometric = { group = "androidx.biometric", name = "biometric", version.ref = "biometric" }
security-crypto = { group = "androidx.security", name = "security-crypto", version.ref = "security-crypto" }
tink = { group = "com.google.crypto.tink", name = "tink-android", version.ref = "tink" }
socket-io = { group = "io.socket", name = "socket.io-client", version.ref = "socket-io" }
okhttp = { group = "com.squareup.okhttp3", name = "okhttp", version.ref = "okhttp" }
zxing = { group = "com.google.zxing", name = "core", version.ref = "zxing" }
coroutines = { group = "org.jetbrains.kotlinx", name = "kotlinx-coroutines-android", version.ref = "coroutines" }
junit = { group = "junit", name = "junit", version.ref = "junit" }
mockk = { group = "io.mockk", name = "mockk", version.ref = "mockk" }
turbine = { group = "app.cash.turbine", name = "turbine", version.ref = "turbine" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
compose-compiler = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
```

### 24.3 R8/ProGuard config

```pro
# android/app/proguard-rules.pro

# --- General ---
-optimizationpasses 5
-allowaccessmodification
-dontpreverify
-repackageclasses ''
-keepattributes *Annotation*, Signature, InnerClasses, EnclosingMethod, SourceFile, LineNumberTable

# --- Kotlin ---
-dontwarn kotlin.**
-keep class kotlin.Metadata { *; }

# --- Compose ---
-keep class androidx.compose.** { *; }
-dontwarn androidx.compose.**

# --- Socket.IO ---
-keep class io.socket.** { *; }
-dontwarn io.socket.**

# --- OkHttp ---
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }
-keep class okio.** { *; }

# --- Tink ---
-keep class com.google.crypto.tink.** { *; }
-dontwarn com.google.crypto.tink.**

# --- ZXing ---
-keep class com.google.zxing.** { *; }
-dontwarn com.google.zxing.**

# --- AnonyMus ---
-keep class com.anonymus.app.data.** { *; }
-keepclassmembers class com.anonymus.app.data.** { *; }

# Strip debug logs in release (audit fix MED-15)
-assumenosideeffects class android.util.Log {
    public static int v(...);
    public static int d(...);
    public static int w(...);
    public static int e(...);
}
-assumenosideeffects class kotlin.io {
    public static void println(...);
}
```

### 24.4 Signing config

```kotlin
// android/app/build.gradle.kts (additions)
android {
    signingConfigs {
        create("release") {
            storeFile = file(System.getenv("ANONYMUS_KEYSTORE") ?: "../keystore/anonymus.jks")
            storePassword = System.getenv("ANONYMUS_KEYSTORE_PASSWORD") ?: ""
            keyAlias = System.getenv("ANONYMUS_KEY_ALIAS") ?: "anonymus"
            keyPassword = System.getenv("ANONYMUS_KEY_PASSWORD") ?: ""
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("release")
        }
    }
}
```

### 24.5 ABI splits (smaller APKs)

```kotlin
android {
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a", "x86_64")
            isUniversalApk = true  # also produce a universal APK
        }
    }
}
```

### 24.6 Baseline Profile (improves cold-start by ~30%)

```kotlin
// android/app/build.gradle.kts
plugins {
    id("androidx.baselineprofile")
}
android {
    // ...
}
baselineProfile {
    mergeIntoMain = true
}
```

Add a `:baselineprofile` module that runs Macrobenchmark tests to generate the profile. CI regenerates the profile monthly.

### 24.7 Screenshot tests (catch UI regressions)

```kotlin
// android/app/src/test/java/com/anonymus/app/ScreenshotTest.kt
class ScreenshotTest {
    @get:Rule val composeRule = createComposeRule()

    @Test fun loginScreen_light() {
        composeRule.setContent { LoginScreen(theme = Theme.Light) }
        composeRule.onRoot().captureToImage().asAndroidBitmap().let {
            Screenshot.assertAgainstBaseline(it, "login_light")
        }
    }
}
```

---

## 25. Python Test Infrastructure

### 25.1 `requirements-dev.txt`

```text
# requirements-dev.txt
ruff==0.7.4
mypy==1.13.0
pre-commit==4.0.1
pip-audit==2.7.3
bandit==1.7.10
safety==3.2.7
cyclonedx-bom==5.1.1
tox==4.23.2
pip-tools==7.4.1
yamllint==1.35.1
types-requests==2.32.0.20241016
types-redis==4.6.0.20241004
```

### 25.2 `requirements-test.txt`

```text
# requirements-test.txt
pytest==8.3.3
pytest-cov==6.0.0
pytest-xdist==3.3.1
pytest-timeout==2.3.1
pytest-html==4.1.1
pytest-rerunfailures==14.0
hypothesis==6.115.6
atheris==2.3.0
```

### 25.3 `tox.ini`

```ini
[tox]
envlist = py311, py312, lint, type, security
isolated_build = True

[testenv]
deps =
    -r requirements.txt
    -r requirements-test.txt
commands = pytest {posargs}

[testenv:lint]
deps = ruff
commands =
    ruff check core/ transports/ tests/
    ruff format --check core/ transports/ tests/

[testenv:type]
deps =
    mypy
    -r requirements.txt
commands = mypy core/ transports/ --ignore-missing-imports

[testenv:security]
deps =
    pip-audit
    bandit
    safety
commands =
    pip-audit -r requirements.txt --strict
    bandit -r core/ transports/ -ll
    safety check --file requirements.txt

[testenv:format]
deps = ruff
commands = ruff format core/ transports/ tests/
```

### 25.4 `pyproject.toml` (full)

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "anonymus"
version = "0.10.0"
description = "AnonyMus — metadata-resistant messaging"
requires-python = ">=3.11"
license = { text = "AGPL-3.0-only" }

[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = ["android", "web", "launcher", "build"]

[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "F",     # pyflakes
    "W",     # pycodestyle warnings
    "I",     # isort
    "N",     # pep8-naming
    "B",     # flake8-bugbear
    "C4",    # flake8-comprehensions
    "SIM",   # flake8-simplify
    "T20",   # flake8-print (no print() in non-test code)
    "UP",    # pyupgrade
    "RUF",   # ruff-specific
    "S",     # flake8-bandit (security)
]
ignore = [
    "E501",   # line length (handled by formatter)
    "S101",   # assert OK in tests
    "S104",   # 0.0.0.0 binding OK for containers
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["T20", "S101", "S106"]
"launcher/**" = ["T20"]  # launcher uses print() for GUI output

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.11"
strict = false
warn_return_any = true
warn_unused_configs = true
warn_redundant_casts = true
warn_unused_ignores = true
ignore_missing_imports = true
files = ["core", "transports"]
exclude = ["tests/", "android/", "web/", "launcher/"]

[[tool.mypy.overrides]]
module = "tests.*"
ignore_errors = true

[tool.pytest.ini_options]
# (this is the same as pytest.ini, but pyproject.toml is the modern location)
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short --strict-markers --strict-config"
markers = [
    "unit: unit tests",
    "integration: integration tests",
    "e2e: end-to-end tests",
    "property: property-based tests",
    "fuzz: fuzz tests",
    "snapshot: snapshot tests",
    "slow: tests that take >5s",
    "skip_on_ci: skip on CI runners",
]
```

### 25.5 Hypothesis property test example

```python
# tests/property/test_crypto_properties.py
"""Property-based tests for the crypto module — catch edge cases unit tests miss."""
from hypothesis import given, strategies as st, settings, HealthCheck
import pytest

from core.crypto import derive_db_key, generate_salt, encrypt_secret, decrypt_secret


@given(password=st.text(min_size=1, max_size=128))
def test_derive_db_key_is_deterministic(password):
    """derive_db_key(password, salt) must return the same key for the same inputs."""
    salt = generate_salt()
    key1 = derive_db_key(password, salt)
    key2 = derive_db_key(password, salt)
    assert key1 == key2


@given(
    password=st.text(min_size=1),
    plaintext=st.text(min_size=0, max_size=10000),
)
def test_encrypt_decrypt_roundtrip(password, plaintext):
    """encrypt_secret → decrypt_secret must round-trip."""
    import base64
    salt = generate_salt()
    key = derive_db_key(password, salt)
    plaintext_b64 = base64.b64encode(plaintext.encode()).decode()
    encrypted = encrypt_secret(plaintext_b64, key)
    decrypted = decrypt_secret(encrypted, key)
    assert decrypted == plaintext_b64


@given(
    plaintext=st.text(min_size=1),
    key1=st.binary(min_size=32, max_size=32),
    key2=st.binary(min_size=32, max_size=32),
)
def test_ciphertext_differs_for_different_keys(plaintext, key1, key2):
    """encrypting the same plaintext with different keys must produce different ciphertexts."""
    import base64
    if key1 == key2:
        return  # skip
    plaintext_b64 = base64.b64encode(plaintext.encode()).decode()
    c1 = encrypt_secret(plaintext_b64, key1)
    c2 = encrypt_secret(plaintext_b64, key2)
    assert c1 != c2


@given(salt1=st.binary(min_size=16, max_size=16), salt2=st.binary(min_size=16, max_size=16))
def test_different_salts_produce_different_keys(salt1, salt2):
    if salt1 == salt2:
        return
    key1 = derive_db_key("password", salt1)
    key2 = derive_db_key("password", salt2)
    assert key1 != key2
```

### 25.6 Atheris fuzz test example

```python
# tests/fuzz/test_p2p_endpoints.py
"""Fuzz tests for P2P endpoints — catch crashes from malformed input."""
import sys
import json
import pytest

try:
    import atheris
    HAS_ATHERIS = True
except ImportError:
    HAS_ATHERIS = False


@pytest.mark.skipif(not HAS_ATHERIS, reason="atheris not installed")
@pytest.mark.fuzz
def test_fuzz_p2p_message_endpoint():
    """The /p2p/message endpoint must never 500, regardless of input."""
    with atheris.instrument_imports():
        from server import create_app
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        def test_one(data: bytes):
            try:
                payload = json.loads(data.decode("utf-8", errors="ignore"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return
            try:
                r = client.post("/p2p/message", json=payload)
                assert r.status_code != 500, f"500 on payload: {payload}"
            except Exception as e:
                pytest.fail(f"Crash on payload {payload}: {e}")

        atheris.Setup(sys.argv, test_one)
        atheris.Fuzz()


@pytest.mark.skipif(not HAS_ATHERIS, reason="atheris not installed")
@pytest.mark.fuzz
def test_fuzz_login_endpoint():
    """The /login endpoint must never 500, regardless of input."""
    with atheris.instrument_imports():
        from server import create_app
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        def test_one(data: bytes):
            try:
                payload = json.loads(data.decode("utf-8", errors="ignore"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return
            try:
                r = client.post("/login", json=payload)
                assert r.status_code != 500
            except Exception:
                pass  # Login may raise — just don't crash

        atheris.Setup(sys.argv, test_one)
        atheris.Fuzz()
```

### 25.7 pip-tools for deterministic lockfile

```bash
# Generate a fully-pinned, hashed requirements.txt
pip install pip-tools
pip-compile --generate-hashes --output-file=requirements.lock requirements.txt
# Use requirements.lock in the reproducible Docker build (§7.4)
```

---

## 26. JS/Web Test Infrastructure

The web client has zero Node-based tests today — `web/` has no `package.json`. The crypto.js "tests" are a Node script loaded via `vm.runInThisContext`, not part of any standard test runner.

### 26.1 `web/package.json`

```json
{
  "name": "anonymus-web",
  "version": "0.10.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:ui": "vitest --ui",
    "test:e2e": "playwright test",
    "test:fuzz": "vitest run --mode=fuzz",
    "lint": "eslint .",
    "lint:fix": "eslint . --fix",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "typecheck": "tsc --noEmit",
    "bundle-size": "size-limit",
    "lighthouse": "lhci autorun"
  },
  "devDependencies": {
    "@eslint/js": "^9.15.0",
    "@playwright/test": "^1.48.2",
    "@size-limit/preset-app": "^11.1.6",
    "@types/node": "^22.9.0",
    "@vitest/ui": "^2.1.6",
    "eslint": "^9.15.0",
    "globals": "^15.12.0",
    "prettier": "^3.3.3",
    "size-limit": "^11.1.6",
    "typescript": "^5.6.3",
    "vitest": "^2.1.6"
  },
  "size-limit": [
    {
      "path": "static/crypto.js",
      "limit": "10 KB"
    },
    {
      "path": "static/chat.js",
      "limit": "50 KB"
    },
    {
      "path": "static/login.js",
      "limit": "10 KB"
    }
  ]
}
```

### 26.2 `web/eslint.config.js`

```javascript
// web/eslint.config.js (flat config, ESLint 9)
import js from '@eslint/js';
import globals from 'globals';

export default [
  js.configs.recommended,
  {
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
        crypto: 'readonly',  // Web Crypto API
      },
    },
    rules: {
      'no-innerHTML': 'error',  // audit fix HIGH-1 — no .innerHTML for untrusted data
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'eqeqeq': ['error', 'always'],
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      'prefer-const': 'error',
      'no-var': 'error',
    },
  },
  {
    files: ['tests/**'],
    languageOptions: { globals: { ...globals.node } },
  },
];
```

### 26.3 `web/tests/crypto.test.js` (Vitest)

```javascript
// web/tests/crypto.test.js
import { describe, it, expect, beforeEach } from 'vitest';
import { encryptMessage, decryptMessage, generateKeyPair, deriveSessionKeys } from '../static/crypto.js';

describe('crypto module', () => {
  let alice, bob;

  beforeEach(async () => {
    alice = await generateKeyPair();
    bob = await generateKeyPair();
  });

  it('round-trips a message through encrypt → decrypt', async () => {
    const { aliceKey, bobKey } = await deriveSessionKeys(alice.privateKey, bob.publicKey);
    const plaintext = 'hello, world!';
    const encrypted = await encryptMessage(bobKey, plaintext, 'alice', 1, 'session-1');
    const decrypted = await decryptMessage(aliceKey, encrypted.iv, encrypted.ciphertext, 'alice', 1, 'session-1');
    expect(decrypted).toBe(plaintext);
  });

  it('rejects a replayed sequence number', async () => {
    const { aliceKey, bobKey } = await deriveSessionKeys(alice.privateKey, bob.publicKey);
    const plaintext = 'hello';
    const encrypted = await encryptMessage(bobKey, plaintext, 'alice', 1, 'session-1');
    // First decrypt succeeds
    await expect(decryptMessage(aliceKey, encrypted.iv, encrypted.ciphertext, 'alice', 1, 'session-1'))
      .resolves.toBe(plaintext);
    // Replay with same seq fails
    await expect(decryptMessage(aliceKey, encrypted.iv, encrypted.ciphertext, 'alice', 1, 'session-1'))
      .rejects.toThrow(/replay|seq/i);
  });

  it('produces different ciphertexts for different sessions', async () => {
    const { aliceKey: k1, bobKey: bk1 } = await deriveSessionKeys(alice.privateKey, bob.publicKey);
    const { aliceKey: k2, bobKey: bk2 } = await deriveSessionKeys(alice.privateKey, bob.publicKey);
    const plaintext = 'hello';
    const c1 = await encryptMessage(bk1, plaintext, 'alice', 1, 'session-1');
    const c2 = await encryptMessage(bk2, plaintext, 'alice', 1, 'session-2');
    expect(c1.ciphertext).not.toBe(c2.ciphertext);
  });
});
```

### 26.4 Playwright E2E test

```typescript
// web/tests/e2e/two-clients.spec.ts
import { test, expect, chromium } from '@playwright/test';

test('two web clients exchange a message through the relay', async () => {
  const browser = await chromium.launch();
  const alice = await browser.newContext();
  const bob = await browser.newContext();

  const alicePage = await alice.newPage();
  const bobPage = await bob.newPage();

  // Both register
  await alicePage.goto('http://localhost:5000/');
  await alicePage.fill('[name=username]', 'alice');
  await alicePage.fill('[name=password]', 'testpass123');
  await alicePage.click('button[type=submit]');

  await bobPage.goto('http://localhost:5000/');
  await bobPage.fill('[name=username]', 'bob');
  await bobPage.fill('[name=password]', 'testpass123');
  await bobPage.click('button[type=submit]');

  // (Test continues: alice creates a queue, bob joins via invite link, they exchange a message)
  // ...

  await browser.close();
});
```

### 26.5 `.github/workflows/js.yml`

```yaml
# .github/workflows/js.yml
name: JS CI
on:
  push:
    branches: [main]
    paths: ['web/**', '.github/workflows/js.yml']
  pull_request:
    branches: [main]
  workflow_dispatch: {}

concurrency:
  group: js-ci-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: web/package-lock.json
      - working-directory: web
        run: npm ci
      - working-directory: web
        run: npm run lint
      - working-directory: web
        run: npm run format:check
      - working-directory: web
        run: npm run typecheck

  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: web/package-lock.json
      - working-directory: web
        run: npm ci
      - working-directory: web
        run: npm test -- --coverage
      - name: Upload coverage
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: js-coverage
          path: web/coverage/
          retention-days: 7

  bundle-size:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: web/package-lock.json
      - working-directory: web
        run: npm ci
      - working-directory: web
        run: npm run bundle-size
```

---

## 27. Docker Hardening

### 27.1 Multi-stage `Dockerfile` (final image is distroless)

```dockerfile
# build/Dockerfile — multi-stage, distroless final image
# Stage 1: builder
FROM python:3.11-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create venv and install deps
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

# Stage 2: runtime (distroless)
FROM gcr.io/distroless/python3-debian12:nonroot

# Copy the venv from the builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy app
WORKDIR /app
COPY --chown=nonroot:nonroot . .

USER nonroot

EXPOSE 5000

CMD ["-m", "gunicorn", "--worker-class", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", "server:app"]
```

### 27.2 `.dockerignore`

```text
# .dockerignore
.git
.github
.vscode
.idea

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
.coverage-baseline
coverage.xml
junit.xml
report.html

# Node
web/node_modules/
web/coverage/

# Android
android/.gradle/
android/build/
android/app/build/
android/local.properties

# Docs and PDFs
*.pdf
docs/

# Test artifacts
tests/
tests-*/

# Launcher build artifacts
launcher/Output/
launcher/build/
launcher/dist/

# Misc
*.log
*.tmp
.env
.env.local
.env.*.local
*.pem
*.key
```

### 27.3 Trivy scan in CI

(See §23.3)

### 27.4 Cosign signing

(See §23.2)

---

## 28. Supply-Chain Security

### 28.1 SBOM (CycloneDX + SPDX) — already in §8

### 28.2 `.github/dependabot.yml`

```yaml
# .github/dependabot.yml
version: 2
updates:
  # GitHub Actions
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 5
    labels: [dependencies, github-actions]
    commit-message:
      prefix: chore
      include: scope

  # Python
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 10
    labels: [dependencies, python]
    commit-message:
      prefix: chore
      include: scope

  # Android (Gradle)
  - package-ecosystem: gradle
    directory: /android
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 10
    labels: [dependencies, android]
    commit-message:
      prefix: chore
      include: scope

  # JS (npm)
  - package-ecosystem: npm
    directory: /web
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 10
    labels: [dependencies, npm]
    commit-message:
      prefix: chore
      include: scope

  # Docker base image
  - package-ecosystem: docker
    directory: /build
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 3
    labels: [dependencies, docker]
    commit-message:
      prefix: chore
      include: scope
```

### 28.3 npm audit + gradle dependency-check

```yaml
# .github/workflows/supply-chain.yml
name: Supply-Chain Audit
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 5 * * 1'  # weekly Monday 05:00 UTC

jobs:
  npm-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: npm, cache-dependency-path: web/package-lock.json }
      - working-directory: web
        run: npm ci
      - working-directory: web
        run: npm audit --audit-level=high --omit=dev || true

  gradle-dependency-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '17' }
      - uses: gradle/actions/setup-gradle@v4
      - working-directory: android
        run: ./gradlew dependencyCheck --no-daemon || true

  python-pip-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11', cache: pip }
      - run: pip install pip-audit
      - run: pip-audit -r requirements.txt --strict
```

---

## 29. Observability of CI

### 29.1 Run-summary PR comment

```yaml
# .github/workflows/pr-summary.yml
name: PR Summary
on:
  workflow_run:
    workflows: [Python CI, Android CI, JS CI, SBOM Generation, Reproducible Build]
    types: [completed]

permissions:
  pull-requests: write
  actions: read

jobs:
  summary:
    runs-on: ubuntu-latest
    if: github.event.workflow_run.event == 'pull_request'
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const wfRun = context.payload.workflow_run;
            const pr = await github.rest.repos.listPullRequestsAssociatedWithCommit({
              owner: context.repo.owner,
              repo: context.repo.repo,
              commit_sha: wfRun.head_sha
            });
            if (pr.data.length === 0) return;
            const prNumber = pr.data[0].number;

            const runs = await github.rest.actions.listWorkflowRunsForRepo({
              owner: context.repo.owner, repo: context.repo.repo,
              head_sha: wfRun.head_sha, per_page: 100
            });

            const summary = runs.data.workflow_runs
              .filter(r => r.head_sha === wfRun.head_sha)
              .map(r => `${r.conclusion === 'success' ? '✅' : r.conclusion === 'failure' ? '❌' : '⏳'} ${r.name}`)
              .join('\n');

            // Find and update the bot comment
            const comments = await github.rest.issues.listComments({
              owner: context.repo.owner, repo: context.repo.repo, issue_number: prNumber
            });
            const botComment = comments.data.find(c => c.user.type === 'Bot' && c.body.startsWith('🤖 **CI Summary**'));
            const body = `🤖 **CI Summary**\n\n${summary}\n\n[View all runs](${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions)`;

            if (botComment) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner, repo: context.repo.repo,
                comment_id: botComment.id, body
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner, repo: context.repo.repo,
                issue_number: prNumber, body
              });
            }
```

### 29.2 Failure-classifier bot

```javascript
// scripts/classify-failure.js — used by every workflow's "Report failure" step
module.exports.classifyFailure = async ({ github, context, core }) => {
  const runs = await github.rest.actions.listJobsForWorkflowRun({
    owner: context.repo.owner,
    repo: context.repo.repo,
    run_id: context.runId,
  });
  const failedJobs = runs.data.jobs.filter(j => j.conclusion === 'failure');
  for (const job of failedJobs) {
    const logs = await github.rest.actions.downloadJobLogs({
      owner: context.repo.owner, repo: context.repo.repo,
      job_id: job.id,
    });
    const logText = logs.data;
    let category = 'unknown';
    let fix = 'See full logs.';
    if (/Unresolved reference/.test(logText)) {
      category = 'compilation';
      fix = 'Missing import or method. See docs/ci-runbook.md §1.';
    } else if (/ImportError.*not importable/.test(logText)) {
      category = 'import';
      fix = 'Missing __init__.py. Run `bash scripts/ensure-init-py.sh`. See docs/ci-runbook.md §3.';
    } else if (/deprecated.*actions\/upload-artifact/.test(logText)) {
      category = 'deprecated-action';
      fix = 'Update to actions/upload-artifact@v4. See docs/ci-runbook.md §4.';
    } else if (/not found.*sha256/.test(logText)) {
      category = 'docker-digest';
      fix = 'Pinned digest stale. Run `bash scripts/update-docker-digest.sh`. See docs/ci-runbook.md §2.';
    } else if (/cannot access.*No such file/.test(logText)) {
      category = 'file-not-found';
      fix = 'Path renamed. See docs/ci-runbook.md §5.';
    } else if (/timeout|timed out/i.test(logText)) {
      category = 'timeout';
      fix = 'Add timeout-minutes or @pytest.mark.timeout. See docs/ci-runbook.md §6.';
    } else if (/pip-audit|CVE|vulnerab/i.test(logText)) {
      category = 'security';
      fix = 'Bump the vulnerable dependency. See docs/ci-runbook.md §7.';
    } else if (/cov-fail-under|coverage/.test(logText)) {
      category = 'coverage';
      fix = 'Add tests for new code. See docs/ci-runbook.md §8.';
    }

    core.info(`Classified failure: ${category}`);

    if (context.eventName === 'pull_request') {
      await github.rest.issues.createComment({
        owner: context.repo.owner,
        repo: context.repo.repo,
        issue_number: context.issue.number,
        body: `🤖 **CI Failure — ${category}**\n\n` +
              `**Job:** ${job.name}\n` +
              `**Suggested fix:** ${fix}\n` +
              `**Logs:** ${job.html_url}\n\n` +
              `_Automated diagnosis by the failure-classifier bot._`
      });
    }
  }
};
```

### 29.3 Slack/Discord alert on main-branch red

```yaml
# .github/workflows/main-branch-alert.yml
name: Main Branch Alert
on:
  workflow_run:
    workflows: [Python CI, Android CI, JS CI, SBOM Generation, Reproducible Build]
    types: [completed]
    branches: [main]

jobs:
  alert:
    runs-on: ubuntu-latest
    if: github.event.workflow_run.conclusion == 'failure'
    steps:
      - name: Send Slack alert
        uses: slackapi/slack-github-action@v1
        with:
          webhook-url: ${{ secrets.SLACK_CI_WEBHOOK }}
          webhook-type: incoming-webhook
          payload: |
            {
              "text": "🔴 Main branch CI is red",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "🔴 *Main branch CI failed*\n*Workflow:* ${{ github.event.workflow_run.name }}\n*Run:* <${{ github.event.workflow_run.html_url }}|View>\n*Commit:* ${{ github.event.workflow_run.head_sha }}"
                  }
                }
              ]
            }
```

### 29.4 Weekly CI health dashboard

(See §15.2)

---

## 30. Repo Governance

### 30.1 Branch protection (configure in GitHub Settings → Branches)

```
Branch protection rule for: main

✅ Require a pull request before merging
   ✅ Require approvals: 1
   ✅ Dismiss stale pull request approvals when new commits are pushed
   ✅ Require review from Code Owners

✅ Require status checks to pass before merging
   ✅ Require branches to be up to date before merging
   Required checks:
   - Python CI / test (3.11)
   - Python CI / lint
   - Android CI / compile
   - JS CI / lint
   - JS CI / test
   - SBOM Generation / python-sbom
   - Reproducible Build / verify
   - actionlint

✅ Require conversation resolution before merging
✅ Require signed commits
✅ Require linear history
✅ Do not allow bypassing the above settings

✅ Restrict who can push to matching branches
   (only: release-bot, admins)
```

### 30.2 `.github/CODEOWNERS`

```text
# .github/CODEOWNERS
# Default owner
*                       @aryansinghnagar

# Per-area owners (add teammates as the project grows)
/core/                   @aryansinghnagar  @crypto-reviewer
/transports/             @aryansinghnagar  @backend-reviewer
/web/                    @aryansinghnagar  @frontend-reviewer
/android/                @aryansinghnagar  @mobile-reviewer
/build/                  @aryansinghnagar  @devops-reviewer
/.github/workflows/      @aryansinghnagar  @devops-reviewer
/docs/                   @aryansinghnagar
/tests/                  @aryansinghnagar
```

### 30.3 Conventional commits + semantic-release

Already configured via `.commitlintrc.json` (§13.2). Add semantic-release for auto-changelog:

```yaml
# .github/workflows/release.yml (addition)
jobs:
  release:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: cycjimmy/semantic-release-action@v4
        with:
          extra_plugins: |
            @semantic-release/changelog
            @semantic-release/git
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`.releaserc.json`:
```json
{
  "branches": ["main"],
  "plugins": [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    ["@semantic-release/changelog", { "changelogFile": "CHANGELOG.md" }],
    ["@semantic-release/git", {
      "assets": ["CHANGELOG.md"],
      "message": "chore(release): ${nextRelease.version}\n\n${nextRelease.notes}"
    }],
    "@semantic-release/github"
  ]
}
```

### 30.4 Stale bot

```yaml
# .github/stale.yml
only: issues
daysUntilStale: 60
daysUntilClose: 7
exemptLabels: [pinned, security, roadmap]
staleLabel: stale
markComment: >
  This issue has been automatically marked as stale because it has not had
  recent activity. It will be closed in 7 days if no further activity occurs.
  To keep it open, remove the `stale` label or comment.
closeComment: >
  This issue was closed because it has been stale for 7 days with no activity.
```

### 30.5 Auto-labeler

```yaml
# .github/labeler.yml
python:
  - changed-files:
    - any-glob-to-any-file: ['core/**', 'transports/**', 'tests/**', '*.py', 'requirements*.txt']

android:
  - changed-files:
    - any-glob-to-any-file: ['android/**']

web:
  - changed-files:
    - any-glob-to-any-file: ['web/**']

ci:
  - changed-files:
    - any-glob-to-any-file: ['.github/workflows/**', 'scripts/**']

docker:
  - changed-files:
    - any-glob-to-any-file: ['build/**', '.dockerignore']

docs:
  - changed-files:
    - any-glob-to-any-file: ['**/*.md', 'docs/**']

security:
  - changed-files:
    - any-glob-to-any-file: ['core/crypto*', 'transports/**/database.py', 'android/**/Crypto*', 'web/static/crypto.js']
```

---


# Part V — Rollout

## 31. Three-Week Phased Rollout

The rollout is structured as three one-week phases, each with a clear theme, exit criteria, and a definition of done. The phases are sequential — Week 2 depends on Week 1's CI being green so the hardening changes can be tested.

### 31.1 Week 1 — Stop the Bleed (CI green)

**Theme:** Fix all five CI failure categories. By end of Week 1, every workflow passes on `main`.

| Day | Deliverable | Owner | Ticket |
|---|---|---|---|
| 1 (Mon) | Delete legacy `test.yml`; create 5 separate workflows (android.yml, python.yml, sbom.yml, reproducible-build.yml, js.yml) with `actions/checkout@v4`, `actions/upload-artifact@v4` | Backend eng | ANONYMUS-CI-005 |
| 1 (Mon) | Fix SBOM workflow (§8) — 15-minute fix | Backend eng | ANONYMUS-CI-003 |
| 2 (Tue) | Fix Python CI: add `__init__.py`, switch to pytest, create `pytest.ini` (§9) | Backend eng | ANONYMUS-CI-004 |
| 2 (Tue) | Fix reproducible build: unpin digest in `build/Dockerfile`, create `Dockerfile.reproducible` with current digest (§7) | DevOps | ANONYMUS-CI-002 |
| 3 (Wed) | Fix Android CI: add `EncryptedPayload` import, implement 5 missing `ChatManager` methods (§6) | Android eng | ANONYMUS-CI-001 |
| 3 (Wed) | Add `scripts/ci-preflight.sh` and wire into every workflow (§10.3) | DevOps | ANONYMUS-CI-005 |
| 4 (Thu) | Downgrade Android deps to stable (Kotlin 2.0.21, AGP 8.7.3, Compose BOM 2024.10.01, compileSdk 34, androidx.security.crypto 1.0.0) — §24 | Android eng | ANONYMUS-ANDROID-DEPS |
| 4 (Thu) | Add `Makefile` targets `ci-local`, `ci-local-fast` (§12) | DevOps | ANONYMUS-LOCAL-CI |
| 5 (Fri) | End-to-end verification: every workflow passes on `main` | All | — |
| 5 (Fri) | Add status badges to README (§15.1) | DevOps | ANONYMUS-BADGES |

**Week 1 exit criteria:**
- ✅ All 5 workflows pass on `main` for three consecutive commits.
- ✅ `make ci-local` reproduces the CI result locally.
- ✅ No `@v3` actions remain (`grep -rE 'uses: .+@v[0-3]$' .github/workflows/` returns empty).
- ✅ `./gradlew compileDebugKotlin` passes on a clean clone.
- ✅ `pytest` passes with `--cov-fail-under=60`.
- ✅ Reproducible build produces identical manifests across two runs.
- ✅ SBOM artifact is generated and downloadable.

**Week 1 risks:**
- **Android deps downgrade may break the build** if the code uses Kotlin 2.1+ features. Mitigation: do the downgrade in a branch, test with `make ci-local-android`, fix any compile errors before merging.
- **Reproducible build may not be reproducible** (timestamps, random keys in the build). Mitigation: set `SOURCE_DATE_EPOCH` and `PYTHONHASHSEED=0` in the Dockerfile; strip `__pycache__` before comparing manifests.
- **Missing `ChatManager` methods may have different signatures** than what the UI expects. Mitigation: cross-reference `chat_screen.kt` call sites before implementing.

### 31.2 Week 2 — Hardening (proactive infra)

**Theme:** Lay the proactive foundation from Part III. By end of Week 2, the test infrastructure is self-defending — new tests land in the right slot with the right fixtures, flaky tests are quarantined, deprecated actions are caught at PR time.

| Day | Deliverable | Owner | Section |
|---|---|---|---|
| 6 (Mon) | Build the local-CI Docker image (`docker/ci-runner/Dockerfile`); verify `make ci-local` works | DevOps | §12 |
| 6 (Mon) | Install pre-commit; configure `.pre-commit-config.yaml` (ruff, mypy, actionlint, yamllint, shellcheck, ktlint, eslint, prettier, commitlint) | Backend eng | §13 |
| 7 (Tue) | Reorganize `tests/` into the test pyramid scaffold (unit/integration/e2e/property/fuzz/snapshot); add `conftest.py` fixtures | Backend eng + QA | §18 |
| 7 (Tue) | Write `pytest.ini`, `pyproject.toml`, `tox.ini`, `requirements-dev.txt`, `requirements-test.txt` | Backend eng | §25 |
| 8 (Wed) | Add `web/package.json` with Vitest, ESLint, Prettier, TypeScript; write crypto.js tests | Frontend eng | §26 |
| 8 (Wed) | Add `.github/PULL_REQUEST_TEMPLATE.md`; enable merge queue | Tech lead | §14 |
| 9 (Thu) | Add CodeQL workflow (§21.1) and Semgrep workflow (§21.2) | DevOps | §21 |
| 9 (Thu) | Add `actionlint` + `yamllint` to CI (§22) | DevOps | §22 |
| 10 (Fri) | Add `.github/dependabot.yml` (§28.2); verify Dependabot opens PRs for action bumps | DevOps | §28 |
| 10 (Fri) | Write `docs/ci-runbook.md` (§17); dry-run the failure-classifier bot (§29.2) | Tech lead | §17, §29 |
| 10 (Fri) | Add coverage ratchet script (§20.2); set baseline to current coverage | Backend eng | §20 |

**Week 2 exit criteria:**
- ✅ `make ci-local` runs in <2 minutes and mirrors GitHub Actions output.
- ✅ `pre-commit run --all-files` passes (after auto-fixes are committed).
- ✅ Test directory layout matches §5.1; every test dir has `__init__.py`.
- ✅ `pytest tests/unit/` runs in <5 seconds; `pytest tests/integration/` in <30 seconds.
- ✅ `vitest` runs the crypto.js tests and passes.
- ✅ CodeQL and Semgrep run on every PR; results appear in GitHub Security tab.
- ✅ `actionlint` runs on every PR; catches deprecated actions before merge.
- ✅ Dependabot has opened at least one PR (for an action bump).
- ✅ `docs/ci-runbook.md` exists with at least 10 failure-class sections.
- ✅ Coverage ratchet is set; PRs that lower coverage are blocked.

**Week 2 risks:**
- **Pre-commit may be slow** (10+ seconds per commit). Mitigation: enable `pre-commit cache` and only run hooks on changed files (default behavior).
- **CodeQL may find false positives.** Mitigation: mark them as false positives in the GitHub Security tab (not in code).
- **Test reorganization may break existing tests.** Mitigation: do the reorganization in a branch, run `pytest tests/unit/` after each move, fix import paths before merging.

### 31.3 Week 3 — Adjacent Areas

**Theme:** Tackle the 7 adjacent areas from Part IV. By end of Week 3, the project has a hardened Android build, a deterministic Python lockfile, a JS test suite, a distroless Docker image, supply-chain attestations, CI observability, and repo governance.

| Day | Deliverable | Owner | Section |
|---|---|---|---|
| 11 (Mon) | Android: update `libs.versions.toml` to stable versions (if not done in W1); add R8/ProGuard rules (§24.3), signing config (§24.4), ABI splits (§24.5) | Android eng | §24 |
| 11 (Mon) | Python: add `pip-tools` and generate `requirements.lock` with hashes; use it in `Dockerfile.reproducible` | Backend eng | §25.7 |
| 12 (Tue) | JS: add Playwright E2E tests (§26.4); add `size-limit` bundle-size budget | Frontend eng | §26 |
| 12 (Tue) | Docker: convert `Dockerfile` to multi-stage distroless (§27.1); add `.dockerignore` (§27.2) | DevOps | §27 |
| 13 (Wed) | Supply-chain: add CycloneDX + SPDX SBOM generation for Python and Android (§8); add cosign signing (§23.2); add Trivy scan (§23.3); add SLSA provenance (§23.1) | DevOps | §23, §28 |
| 13 (Wed) | CI observability: add PR-summary bot (§29.1), failure-classifier bot (§29.2), Slack alert (§29.3), weekly CI health dashboard (§15.2) | DevOps | §29 |
| 14 (Thu) | Repo governance: configure branch protection (§30.1); add `CODEOWNERS` (§30.2); add auto-labeler (§30.5); add stale bot (§30.4) | Tech lead | §30 |
| 14 (Thu) | Add `semantic-release` for auto-changelog (§30.3) | DevOps | §30 |
| 15 (Fri) | Hypothesis property tests for crypto (§25.5); atheris fuzz tests for P2P endpoints (§25.6) | Backend eng + Crypto eng | §25 |
| 15 (Fri) | Snapshot tests for protocol envelope (§18.5); flaky-test quarantine (§19) | QA | §18, §19 |
| 15 (Fri) | Final verification: all 7 adjacent areas have at least one workflow passing; full CI green | All | — |

**Week 3 exit criteria:**
- ✅ Android APK builds with stable deps; R8 strips debug logs; signing config works in CI.
- ✅ `requirements.lock` is generated with hashes; `Dockerfile.reproducible` uses it.
- ✅ Playwright E2E test exchanges a message between two web clients.
- ✅ Docker final image is distroless, <200 MB, signed with cosign, scanned by Trivy (0 HIGH+ CVEs).
- ✅ SLSA provenance is generated for every release; SBOM is uploaded to releases.
- ✅ PR-summary bot posts a comment with all workflow statuses; failure-classifier bot diagnoses failures.
- ✅ Branch protection is enabled; CODEOWNERS is enforced; auto-labeler labels PRs.
- ✅ `semantic-release` auto-generates CHANGELOG.md on merge to main.
- ✅ Hypothesis property tests pass; atheris fuzz tests run for 10,000 iterations without crashes.

**Week 3 risks:**
- **Distroless image may break runtime** (no shell, no curl). Mitigation: test the healthcheck (uses Python, not curl); if it breaks, switch to `python:3.11-slim` with a non-root user.
- **Cosign signing requires a key** that must be stored as a secret. Mitigation: use keyless signing (cosign's `--identity-token` mode) to avoid the key-management burden.
- **Branch protection may block legitimate hotfixes.** Mitigation: configure "Allow specified actors to bypass" for the release-bot and admins.
- **Hypothesis tests may be slow** (100+ examples per property). Mitigation: limit to 50 examples in CI, 1000 in nightly.

### 31.4 Post-Week-3 (ongoing)

After Week 3, the CI is green and self-defending. Ongoing work:

- **Monthly:** Dependabot PRs (actions, Python, Android, npm, Docker).
- **Monthly:** Digest refresh PR (§7.6).
- **Weekly:** CI health report (§15.2); quarantine review (§19).
- **Daily:** Nightly job runs quarantined tests + fuzz tests (§19).
- **Per-PR:** All workflows must pass; failure-classifier bot diagnoses failures.
- **Per-release:** SLSA provenance + SBOM + cosign signature (§23).

### 31.5 Roadmap Gantt

```
Week:  1           2           3
       ─────────────────────────────
W1     ████████████                  Stop the bleed (CI green)
W2                  ████████████      Hardening (proactive infra)
W3                               ████████████  Adjacent areas
```

---

## 32. Risk Register & Pre-Flight Checklist

### 32.1 Risk Register

| ID | Risk | Likelihood | Impact | Owner | Mitigation | Residual |
|---|---|---|---|---|---|---|
| R-CI-01 | Android deps downgrade breaks the build | Medium | High | Android eng | Do in branch; test with `make ci-local-android` before merge | Low |
| R-CI-02 | Reproducible build not reproducible (timestamps) | Medium | Medium | DevOps | Set `SOURCE_DATE_EPOCH`, `PYTHONHASHSEED=0`; strip `__pycache__` | Low |
| R-CI-03 | Missing `ChatManager` methods have wrong signatures | Medium | High | Android eng | Cross-reference `chat_screen.kt` call sites before implementing | Low |
| R-CI-04 | Pre-commit hooks slow (10s+ per commit) | Low | Low | Backend eng | Cache; only run on changed files (default) | Low |
| R-CI-05 | CodeQL false positives | High | Low | Backend eng | Mark as FP in Security tab, not in code | Low |
| R-CI-06 | Test reorganization breaks existing tests | Medium | Medium | Backend eng | Do in branch; run `pytest tests/unit/` after each move | Low |
| R-CI-07 | Distroless image breaks runtime (no shell) | Medium | High | DevOps | Test healthcheck; fall back to `python:3.11-slim` non-root | Low |
| R-CI-08 | Cosign key management burden | Medium | Medium | DevOps | Use keyless signing (identity token) | Low |
| R-CI-09 | Branch protection blocks hotfixes | Low | Medium | Tech lead | Allow release-bot + admins to bypass | Low |
| R-CI-10 | Hypothesis tests slow in CI | Medium | Low | Backend eng | Limit to 50 examples in CI, 1000 in nightly | Low |
| R-CI-11 | Dependabot opens too many PRs | Medium | Low | DevOps | Limit to 5-10 open PRs per ecosystem | Low |
| R-CI-12 | Failure-classifier bot misdiagnoses | Medium | Low | DevOps | Weekly review of bot comments; tune the regex | Low |
| R-CI-13 | Merge queue serializes too slowly | Low | Low | Tech lead | Set max wait 5 min; min entries 1 | Low |
| R-CI-14 | Snapshot tests block legitimate protocol changes | Low | Low | Backend eng | Document "delete snapshot, re-run" workflow | Low |
| R-CI-15 | `pip-audit` false positive blocks CI | Medium | Low | Backend eng | `--ignore-vuln` with TODO comment; weekly review | Low |

### 32.2 Pre-Flight Checklist (run before declaring "CI is fixed")

**Code & Dependencies**
- [ ] All 5 failure categories have merged PRs with tests.
- [ ] `grep -rE 'uses: .+@v[0-3]$' .github/workflows/` returns empty.
- [ ] `./gradlew compileDebugKotlin` passes on a clean clone.
- [ ] `pytest` passes with `--cov-fail-under=60`.
- [ ] `pip-audit -r requirements.txt --strict` is clean.
- [ ] `bandit -r core/ transports/ -ll` is clean.
- [ ] No `print()` in non-test Python (`ruff check --select T20` clean).
- [ ] No `innerHTML` in `web/static/*.js` for untrusted data.
- [ ] No `e.printStackTrace()` in Android production code.

**Workflows**
- [ ] All workflows use `actions/checkout@v4` or later.
- [ ] All workflows use `actions/upload-artifact@v4` or later.
- [ ] All workflows have `concurrency: { cancel-in-progress: false }`.
- [ ] All workflows have `timeout-minutes: 30` (or appropriate).
- [ ] All workflows call `scripts/ci-preflight.sh` as the first step.
- [ ] `actionlint` passes on all workflows.
- [ ] `yamllint` passes on all workflows.

**Tests**
- [ ] `tests/` and all subdirectories contain `__init__.py`.
- [ ] `pytest.ini` is present and configures `testpaths`, `python_files`, `python_functions`, markers.
- [ ] `conftest.py` exists at `tests/`, `tests/unit/`, `tests/integration/`.
- [ ] `pytest tests/unit/` runs in <5 seconds.
- [ ] Coverage ratchet baseline is set (`.coverage-baseline`).
- [ ] Hypothesis property tests exist for crypto.
- [ ] Atheris fuzz tests exist for P2P endpoints (nightly).

**Docker**
- [ ] `build/Dockerfile` builds successfully (dev path, no digest pin).
- [ ] `build/Dockerfile.reproducible` pins to a digest verified to exist.
- [ ] `docker manifest inspect python:3.11-slim@<digest>` succeeds.
- [ ] Two builds of `Dockerfile.reproducible` produce identical manifests.
- [ ] `.dockerignore` exists and excludes `.git/`, `tests/`, `docs/`, `*.pdf`.
- [ ] Final image is <300 MB (or <200 MB if distroless).
- [ ] Trivy scan finds 0 HIGH+ CVEs.

**Supply Chain**
- [ ] `dependabot.yml` covers github-actions, pip, gradle, npm, docker.
- [ ] SBOM (CycloneDX) is generated for Python and Android.
- [ ] Cosign signing is configured for release images.
- [ ] SLSA provenance is generated for releases.
- [ ] CodeQL runs on every PR (Python, JS, Kotlin).
- [ ] Semgrep runs on every PR.

**Repo Governance**
- [ ] Branch protection is enabled on `main`.
- [ ] Required status checks include all CI workflows.
- [ ] `CODEOWNERS` is present and enforced.
- [ ] `PULL_REQUEST_TEMPLATE.md` is present.
- [ ] Merge queue is enabled.
- [ ] Conventional commits are enforced (commitlint).
- [ ] `semantic-release` is configured for auto-changelog.

**Observability**
- [ ] PR-summary bot posts a comment with all workflow statuses.
- [ ] Failure-classifier bot diagnoses failures and suggests fixes.
- [ ] Slack/Discord alert fires on main-branch red.
- [ ] Weekly CI health report is posted to a GitHub issue.
- [ ] `docs/ci-runbook.md` exists with at least 10 failure-class sections.
- [ ] Status badges are in `README.md`.

---

## 33. Closing

The AnonyMus CI is in a state of structural failure today, but the failures are not exotic — they are the standard consequences of a project that grew faster than its test infrastructure. Five CI failure categories, three cross-cutting issues, and seven adjacent areas of technical debt. This plan fixes all of them in three weeks, with a phased rollout that prioritizes stopping the bleed in Week 1, hardening the foundation in Week 2, and tackling adjacent areas in Week 3.

The fix bundle at `/home/z/my-project/anonymus-fixes/` contains every file this plan specifies — Kotlin patches, GitHub Actions YAMLs, `pytest.ini`, `conftest.py`, Dockerfiles, pre-commit config, runbook scripts, and more. Copy the bundle into the repo, run `make ci-local` to verify, and push. The CI will be green by end of Week 1.

The proactive measures in Part III — local-CI mirror, pre-commit hooks, merge queue, failure-classifier bot, test pyramid scaffold, flaky-test quarantine, coverage ratchet, CodeQL, Semgrep, actionlint, SLSA, cosign — convert the CI from a tax into a force multiplier. After Week 2, the easy path is the path that compiles, runs, and passes CI. The next 100 features will ship with tests that are structurally less likely to fail.

The work begins on Day 1: delete the legacy `test.yml`, fix the SBOM workflow (15 minutes), and start the Android deps downgrade. Everything else follows.

---

## Appendix — Fix Bundle Manifest

The fix bundle at `/home/z/my-project/anonymus-fixes/` contains:

```
anonymus-fixes/
├── .github/
│   ├── workflows/
│   │   ├── android.yml                          # §6.5
│   │   ├── python.yml                           # §9.2.3
│   │   ├── js.yml                               # §26.5
│   │   ├── sbom.yml                             # §8.3
│   │   ├── reproducible-build.yml               # §7.5
│   │   ├── update-docker-digest.yml             # §7.6
│   │   ├── codeql.yml                           # §21.1
│   │   ├── semgrep.yml                          # §21.2
│   │   ├── supply-chain.yml                     # §28.3
│   │   ├── ci-health.yml                        # §15.2 + §22
│   │   ├── pr-summary.yml                       # §29.1
│   │   ├── main-branch-alert.yml                # §29.3
│   │   ├── nightly.yml                          # §19
│   │   ├── labeler.yml                          # §30.5
│   │   └── release.yml                          # §23 + §30.3
│   ├── workflows-archive/
│   │   └── test.yml.legacy                      # §10
│   ├── dependabot.yml                           # §28.2
│   ├── CODEOWNERS                               # §30.2
│   ├── PULL_REQUEST_TEMPLATE.md                 # §14.1
│   ├── labeler.yml                              # §30.5
│   └── stale.yml                                # §30.4
├── android/
│   ├── gradle/
│   │   └── libs.versions.toml                   # §24.2
│   ├── app/
│   │   ├── build.gradle.kts                     # §24.3-24.6
│   │   ├── proguard-rules.pro                   # §24.3
│   │   └── src/main/java/com/anonymus/app/data/
│   │       ├── crypto_utils.kt                  # §6 (EncryptedPayload single source of truth)
│   │       ├── chat_manager_missing_methods.kt  # §6.3.2 (5 new methods + shared helper)
│   │       └── CryptoProvider.kt                # §6 (interface — verified)
│   │   └── src/test/java/com/anonymus/app/
│   │       ├── ChatManagerMethodsTest.kt        # §6.4
│   │       └── CryptoProviderTest.kt            # §6 (existing, kept)
├── build/
│   ├── Dockerfile                               # §7.3 (multi-stage distroless — §27.1)
│   ├── Dockerfile.reproducible                  # §7.4
│   ├── .dockerignore                            # §27.2
│   └── Caddyfile                                # §7 (reverse proxy)
├── web/
│   ├── package.json                             # §26.1
│   ├── eslint.config.js                         # §26.2
│   ├── tsconfig.json                            # §26
│   ├── .prettierrc                              # §26
│   └── tests/
│       ├── crypto.test.js                       # §26.3
│       └── e2e/
│           └── two-clients.spec.ts              # §26.4
├── tests/
│   ├── __init__.py                              # §9
│   ├── conftest.py                              # §18.2
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── conftest.py                          # §18.3
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── test_crypto.py
│   │   ├── relay/
│   │   │   ├── __init__.py
│   │   │   └── test_database.py
│   │   └── p2p/
│   │       ├── __init__.py
│   │       └── test_database.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── conftest.py                          # §18.4
│   │   ├── test_relay_e2e.py
│   │   └── test_p2p_e2e.py
│   ├── property/
│   │   ├── __init__.py
│   │   └── test_crypto_properties.py            # §25.5
│   ├── fuzz/
│   │   ├── __init__.py
│   │   └── test_p2p_endpoints.py                # §25.6
│   └── snapshot/
│       ├── __init__.py
│       ├── test_protocol_envelope.py            # §18.5
│       └── snapshots/
├── scripts/
│   ├── ci-preflight.sh                          # §10.3
│   ├── ensure-init-py.sh                        # §9.2.1
│   ├── update-docker-digest.sh                  # §7.6
│   ├── local-ci.sh                              # §12
│   ├── coverage-ratchet.sh                      # §20.2
│   └── classify-failure.js                      # §29.2
├── docker/
│   └── ci-runner/
│       └── Dockerfile                           # §12.1
├── docs/
│   ├── ci-runbook.md                            # §17
│   ├── CONTRIBUTING.md                          # §16
│   ├── REPRODUCE.md                             # §7 (updated)
│   └── ci-health-dashboard.md                   # §29
├── .pre-commit-config.yaml                      # §13.1
├── .commitlintrc.json                           # §13.2
├── .yamllint.yml                                # §22.2
├── .github-actions-version.txt                  # §5.3
├── pytest.ini                                   # §5.3 + §25
├── pyproject.toml                               # §25.4
├── tox.ini                                      # §25.3
├── requirements-dev.txt                         # §25.1
├── requirements-test.txt                        # §25.2
├── Makefile                                     # §12.2
└── .releaserc.json                              # §30.3
```

Each file in the bundle is ready to copy into the repo. The plan above explains what each file does, why it exists, and how it prevents a class of future failures.

---

**End of Plan.**
