# ADR-0003: Signal Protocol Double Ratchet + SPQR PQ Extension

**Date:** 2026-07-11  
**Status:** Accepted  
**Deciders:** AnonyMus Core Team

## Context

AnonyMus v1.0 used a custom, ad-hoc symmetric encryption scheme (`AES-256-CBC` + static key per conversation). This provided no forward secrecy: compromising a single session key exposed the entire conversation history.

## Decision

Implement the **Signal Protocol Double Ratchet Algorithm** (`core/rust/src/protocol/double_ratchet.rs`) as the session encryption layer for all P2P messages, extended with the **SPQR (Stateful Post-Quantum Ratchet)** layer (`pq_ratchet.rs`) that mixes ML-KEM-768 shared secrets into the chain key every N messages.

### Why Signal Protocol Double Ratchet?

| Property | Double Ratchet | v1.0 static key |
|---|---|---|
| Forward secrecy | ✅ Per-message | ❌ None |
| Break-in recovery | ✅ Every DH step | ❌ None |
| Out-of-order delivery | ✅ Skip-key cache | ❌ Ordering required |
| Well-studied | ✅ Signal, WhatsApp, Wire | — |

### Why SPQR (amortised PQ)?

Full per-message ML-KEM overhead (1,088-byte ciphertext × every message) is prohibitive on Tor. The SPQR approach amortises this:

- Every 10 messages, the sender encapsulates a fresh ML-KEM-768 shared secret and includes the 1,088-byte ciphertext in the message.
- The 9 intermediate messages use only Curve25519 + AES-256-GCM (≈72 bytes overhead).
- Result: PQ-hardened forward secrecy at **~10% bandwidth overhead** vs. the non-PQ baseline.

## Consequences

### Positive
- Full forward secrecy from message 1.
- Break-in recovery after every DH ratchet step (every message in a typical conversation).
- Post-quantum harvest-now-decrypt-later attacks require breaking ML-KEM-768 (~180-bit PQ security).
- The Rust implementation is unit-tested with 8 tests covering: single-message roundtrip, multi-message in-order, out-of-order delivery, bidirectional conversation, ciphertext tampering, header tampering, header encode/decode.

### Negative
- Session state (`Session` struct) must be persisted in the encrypted SQLite store across page reloads (fixes the v1.0 key-loss bug when combined with IndexedDB in the web client).
- Out-of-order message buffer is bounded to `MAX_SKIP = 1000` messages to prevent memory exhaustion DoS.

## Implementation Notes

- `Session::init_sender` / `init_receiver` take a 32-byte shared secret from X3DH.
- Headers are authenticated as AAD in the AES-256-GCM tag — tampering the header invalidates the ciphertext.
- `ZeroizeOnDrop` is implemented on `Session`, `RootKey`, `ChainKey`, and `MessageKey` to wipe key material from memory on drop.
