# AnonyMus Master Testing Guide & Failure Mode Matrix

## 1. Overview & Testing Philosophy

AnonyMus adheres to a **fail-closed, verification-first** engineering doctrine. Cryptographic security, transport routing, and user metadata protections must never fail silently. Every layer of the system is instrumented with deterministic test gates, Known Answer Tests (KAT), integration contracts, and automated linters.

---

## 2. Test Suite Architecture

```
AnonyMus Test Suite
├── Python Backend (pytest)
│   ├── Unit Tests (tests/unit/)
│   ├── Integration Tests (tests/integration/)
│   ├── Cryptographic KAT (tests/unit/test_kat_crypto.py)
│   ├── TreeKEM MLS Groups (tests/unit/test_mls_groups.py)
│   ├── Hardware Capability Tiers (tests/unit/test_capability_tiers.py)
│   └── Schema Parity & Drift (tests/unit/test_schema_drift.py)
├── Rust Core (cargo test)
│   ├── Primitives (X25519, ML-KEM-768, Argon2id, AEAD)
│   ├── Double Ratchet State Engine
│   └── UniFFI / WASM / JNI FFI Layers
├── Web Client (Vitest & tsc)
│   ├── Unit Tests (web/src/test/core.test.ts)
│   ├── Type Check (npx tsc -b --noEmit)
│   └── PWA Production Bundle (npm run build)
└── GitHub Actions CI Suite
    ├── web.yml, python.yml, rust.yml, android.yml, ios.yml, js.yml
    └── Security & Audit: codeql.yml, semgrep.yml, sbom.yml, ci-health.yml
```

---

## 3. Failure Mode Matrix & Boundary Stress Conditions

| Component / Subsystem | Stress / Extreme Condition | Expected System Behavior & Failure Mitigation | Verification Test |
|---|---|---|---|
| **Post-Quantum Crypto** | Tampered ciphertext or corrupted public key bytes | Throws explicit `AnonymusError::Decrypt` / AEAD tag failure. Never emits partial plaintext. | `tests/unit/test_kat_crypto.py` |
| **Double Ratchet** | Out-of-order messages arriving 100+ steps ahead | Stores skipped keys up to `max_skip` limit; rejects keys exceeding bound to prevent DoS memory exhaustion. | `tests/unit/p2p/test_protocol.py` |
| **RFC 9420 MLS Groups** | Member attempts decryption with outdated epoch state | Rejects decryption attempt with `EpochMismatchError`. Triggers key catch-up request. | `tests/unit/test_mls_groups.py` |
| **Tor Transport** | Sudden loss of Tor Control Port / Socket reset | Retries socket reconnect with exponential backoff; queues outgoing messages locally without leaking IP. | `tests/unit/test_tor_daemon.py` |
| **Multi-Device Sync** | Secondary device sends sync envelope with timestamp skew > 300s | Rejects envelope with `ValueError("Timestamp out of bounds")` to prevent replay attacks. | `tests/unit/test_multi_device_sync.py` |
| **Hardware Tiers (L0)** | Host RAM < 2GB or CPU Cores <= 2 | Automatically scales down PBKDF2 iterations to 100k, reduces DB cache to 2MB, disables UI animations. | `tests/unit/test_capability_tiers.py` |
| **SQLite Engine** | High concurrent write contention under WAL mode | Retries transactions with busy handler timeout; dynamic `PRAGMA cache_size` prevents memory overflow. | `tests/unit/test_schema_drift.py` |
| **Web PWA Client** | Connection drop during active E2EE exchange | Socket.IO client auto-reconnects over WebSocket/Polling; offline messages queued in encrypted IndexedDB. | `web/src/test/core.test.ts` |

---

## 4. Execution Manual & Command Reference

### A. Python Backend Test Suite (`pytest`)
Run all unit, integration, and contract tests excluding legacy deprecated suites:
```bash
venv\Scripts\python.exe -m pytest tests/unit tests/integration -m "not legacy"
```

Run specific subsystem tests:
```bash
# Cryptographic Known Answer Tests
venv\Scripts\python.exe -m pytest tests/unit/test_kat_crypto.py

# TreeKEM MLS Group Management
venv\Scripts\python.exe -m pytest tests/unit/test_mls_groups.py

# Hardware Capability Tier Detection
venv\Scripts\python.exe -m pytest tests/unit/test_capability_tiers.py

# Schema Drift Verification (SQLAlchemy ORM vs Alembic)
venv\Scripts\python.exe -m pytest tests/unit/test_schema_drift.py

# API Contract v3 Integration Tests
venv\Scripts\python.exe -m pytest tests/integration/test_contract_v3.py
```

### B. Python Linter & Code Formatting
```bash
# Check code style and imports
venv\Scripts\python.exe -m ruff check .

# Check formatting
venv\Scripts\python.exe -m ruff format --check .
```

### C. Rust Cryptographic Core (`core/rust/`)
```bash
# Run cargo tests
cargo test

# Check formatting
cargo fmt --check

# Check clippy warnings
cargo clippy --all-targets -- -D warnings
```

### D. Web Frontend Client (`web/`)
```bash
# Type check TypeScript codebase
npx tsc -b --noEmit

# Run Vitest unit tests
npm test

# Build WASM core bindings
npm run wasm:build

# Generate production PWA bundle
npm run build
```

---

## 5. Continuous Integration (CI) Verification

All pull requests and commits to `main` must pass the complete set of 10 GitHub Actions workflows:

1. `python.yml` — Python Linting, Type Checking, and Pytest Suite.
2. `web.yml` — Web Type Checking, Vitest, WASM, and PWA Build.
3. `rust.yml` — Rust Core Formatting, Clippy, and Cargo Tests.
4. `android.yml` — Android Native Preflight and Kotlin Unit Tests.
5. `ios.yml` — iOS SwiftUI Preflight Validation.
6. `js.yml` — TypeScript SDK Preflight Validation.
7. `ci-health.yml` — Actionlint & Yamllint Workflow Integrity Checks.
8. `codeql.yml` — GitHub CodeQL Static Security Analysis.
9. `semgrep.yml` — Semgrep SAST Vulnerability Scanning.
10. `sbom.yml` — CycloneDX Software Bill of Materials Generation.
