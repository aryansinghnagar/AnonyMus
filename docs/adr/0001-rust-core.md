# ADR-0001: Extract Cryptographic Core to Rust (`anonymus-core`)

**Date:** 2026-07-09
**Status:** Accepted
**Deciders:** AnonyMus Core Team

## Context

AnonyMus v1.0 maintains **four parallel cryptographic implementations**:

| Platform | Files |
|---|---|
| Python backend | `core/protocol.py`, `core/double_ratchet.py`, `core/queue_cryptobox.py`, `core/pq_kem.py` |
| Web (JS) | `web/static/crypto.js` (inline Double Ratchet) |
| Android (Kotlin/JVM) | `JceCryptoProvider.kt`, `TinkCryptoProvider.kt`, `DoubleRatchetSession.kt`, `CryptoUtils.kt` |
| iOS (Swift) | Reference implementation in `examples/ios/` |

This divergence produces real bugs today:

- **Padding mismatch**: Python uses `PADDED_SIZE = 16384`; JS uses 512. Decryption fails cross-platform.
- **AAD truncation**: Python sends an 8-byte safety number as AAD; Android and JS use different lengths. The authentication tag covers different data on each platform.
- **Audit cost**: Four audit targets × four languages = ~4× the cost of a single Rust audit.
- **Crypto update tax**: Every fix requires four PRs tested independently.

## Decision

Extract **all cryptographic and protocol logic** into a single Rust crate: `anonymus-core` (at `core/rust/`).

The crate is exposed to each platform shell via:

| Platform | Binding | Build |
|---|---|---|
| Python | PyO3 (`feature = "python"`) | `maturin build --features python` |
| Web | wasm-bindgen (`feature = "wasm"`) | `wasm-pack build --features wasm` |
| Android | JNI (`feature = "android"`) | cross-compiled via `cargo-ndk` |
| iOS | UniFFI (`feature = "ios"`) | `cargo build --target aarch64-apple-ios` |
| Desktop | native rlib | standard `cargo build --release` |

## Consequences

### Positive
- **One audited code path.** Trail of Bits / Cure53 audit covers the Rust crate; all platforms inherit the result via FFI.
- **Cross-platform KAT parity is structural.** All platforms share `tests/kat/v3-vectors.json` and fail CI if any diverge.
- **Performance.** Rust `aes-gcm` is ≈5× faster than Python `cryptography`. Eliminates GIL contention on the relay.
- **Memory safety.** No use-after-free, no buffer overflows in the crypto path. `zeroize` on all key material.
- **Fungible fixes.** One PR to fix a crypto bug ships to all platforms in the next release.

### Negative
- **Rust learning curve** — mitigated by comprehensive inline docs, skill files, and pair-programming.
- **FFI build matrix complexity** — mitigated by CI matrix and `scripts/ci-preflight.sh` skipping targets not yet scaffolded.
- **Temporary dual-stack** — legacy Python/JS/Kotlin implementations coexist until Phase 2d (week 20-24). All new protocol sessions use the Rust path.

## Rejected Alternatives

| Alternative | Reason rejected |
|---|---|
| Keep four parallel implementations | Maintains the structural liability. Audit cost remains 4×. |
| Python C extension (CFFI) | Loses type safety; harder to audit than Rust. |
| Haskell core (SimpleX model) | Smaller ecosystem; fewer FFI generators; smaller talent pool. |
| Go shared library | No zero-cost WASM; CGO overhead on Android. |
