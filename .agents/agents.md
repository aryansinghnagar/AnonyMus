# AnonyMus Repository Rules & Agent Operating Guidance

This document defines the mandatory engineering constraints, quality standards, and operating rules for all autonomous AI agent sessions working within the AnonyMus codebase.

---

## 1. Core Operating Doctrine

1. **Fail-Closed Security**: Cryptographic operations (Double Ratchet, PQ-KEM ML-KEM-768, TreeKEM MLS, Sealed Sender) must fail safely and explicitly. Never swallow cryptographic exceptions or emit partial plaintexts.
2. **Dual-Stack Hygiene**: Maintain strict code quality, type safety, and lint compliance across both the **Python** backend (`core/`, `transports/`) and **JavaScript/TypeScript** client (`web/`, `packages/typescript-sdk/`).
3. **No Breaking Changes**: Preserve existing API contracts, database schemas (SQLite WAL/SQLAlchemy/Alembic), and transport protocols.

---

## 2. Code Hygiene & Static Analysis

### Python (`pyproject.toml` / `requirements.txt`)
- **Linting & Formatting**: Enforce zero linter errors with `ruff check .` and formatting with `ruff format --check .`.
- **Type Checking**: Pass static type analysis with `pyright`.
- **Imports & Dead Code**: Remove all unused imports (`F401`), unreferenced variables, and dead code before committing.
- **Exception Handling**: Never catch generic `Exception` silently without logging or re-raising.

### JavaScript / TypeScript (`web/` & `packages/typescript-sdk/`)
- **Type Safety**: Strictly adhere to TypeScript annotations (`tsc -b --noEmit`). No arbitrary `any` casting without documented rationale.
- **Linting & Formatting**: Clean code structure validated via `biome check ./src`.
- **Bundle Optimization**: Avoid unnecessary dynamic `import()` calls inside frequently invoked handlers; maintain static top-level imports to optimize Vite bundle chunking.

---

## 3. Algorithmic Complexity & Performance

1. **Lookup Optimization**: Prefer $O(1)$ Hash Map / Set lookups over $O(N)$ list iterations for entity indexing (e.g., active ratchets, contact sessions, message stores).
2. **Non-Blocking Async Loops**: Never perform blocking I/O (e.g., `time.sleep()`, synchronous `requests.get()`, or blocking disk writes) on main asyncio event loops or UI threads.
3. **Resource Scaling**: Respect hardware capability tiers (`core/capability_tiers.py`) for scaling PBKDF2 iterations, SQLite cache sizes (`PRAGMA cache_size`), and concurrency limits.

---

## 4. Test Coverage & Verification Requirements

1. **Python Unit & Integration Tests**:
   - All backend modifications must be covered by `pytest` test suites under `tests/unit/` and `tests/integration/`.
   - Maintain coverage checks (`pytest --cov=core --cov=transports --cov-report=xml`).
   - Run tests excluding legacy deprecated Flask endpoints (`-m "not legacy"`).

2. **Web Client Tests**:
   - Component, store, and crypto utilities must be verified via Vitest (`npm test` inside `web/`).
   - Ensure production build passes (`npm run build`).

3. **Rust Cryptographic Core**:
   - Any FFI or core Rust primitive modifications require `cargo check --lib` inside `core/rust/` and cryptographic verification via `pytest tests/unit/test_kat_crypto.py`.

---

## 5. Continuous Improvement & Dependency Ecosystem

- **Dependabot Integration**: All package ecosystems (`npm` for `web/` & `packages/typescript-sdk/`, `pip` for root Python environment, `cargo` for Rust core, `github-actions` for CI workflows) must be tracked for daily/weekly security updates via `.github/dependabot.yml`.
- **CI/CD Enforcement**: All commits must pass the automated GitHub Actions pipeline (`python.yml`, `web.yml`, `js.yml`, `ci.yml`) before merging.
