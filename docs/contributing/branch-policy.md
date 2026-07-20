# AnonyMus Branch Policy & Merge Strategy

This document establishes the official branch topology, pull request merge criteria, and release workflow for the AnonyMus codebase.

---

## 1. Primary Branches

| Branch | Purpose | Protection & Rules |
|---|---|---|
| `main` | Production-ready stable release trunk. | Protected: Requires 1 approval, green CI suite, linear history. |
| `dev` | Integration trunk for active feature development. | Protected: Requires green CI suite before merging into `main`. |
| `release/vX.Y.Z` | Release candidate stabilization. | Tagged and signed before deployment. |

---

## 2. Dependabot & Dependency Upgrades

- **Patch & Minor Updates**: Grouped weekly by ecosystem (`pip`, `cargo`, `npm`, `gradle`, `github-actions`).
- **Major Version Upgrades**: Isolated in explicit feature branches (e.g. `feature/pyo3-upgrade`) and validated via integration suites before merging to `dev`.

---

## 3. Release Lifecycle

1. Development lands on `dev` via feature PRs.
2. Cut `release/vX.Y.Z` branch from `dev` when feature-complete.
3. Perform security audit checks and KAT suite validation.
4. Merge `release/vX.Y.Z` into `main`, tag version `vX.Y.Z`, and trigger release artifact pipeline.
