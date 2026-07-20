# AnonyMus Security Audit Readiness Specification

**Target Scope:** External Third-Party Cryptographic & Architecture Audit (Trail of Bits / Cure53)
**Document Version:** 1.0.0
**Target Release:** v3.0 Production Launch Gate 1

---

## 1. Executive Audit Overview

This document provides external security auditors with a comprehensive reference map of the AnonyMus cryptographic implementation, network protocol handshakes, threat model boundaries, and automated test harnesses.

AnonyMus is a metadata-resistant, privacy-preserving instant messenger operating over a dual-mode centralized relay or decentralized Tor P2P transport network.

---

## 2. Cryptographic Primitive Inventory

| Primitive / Subsystem | Implementation File | Standard / Specification | Key Sizes & Parameters |
| :--- | :--- | :--- | :--- |
| **Classical Key Exchange** | `core/protocol.py` | X25519 (Curve25519) | 256-bit private / 32-byte public |
| **Post-Quantum KEM** | `core/pq_kem.py` | ML-KEM-768 (NIST FIPS 203 / Kyber768) | 1184-byte PK, 2400-byte SK, 1088-byte CT |
| **Double Ratchet** | `core/double_ratchet.py` | Signal Double Ratchet Spec | KDF: HKDF-SHA256, AEAD: AES-256-GCM |
| **Sealed-Sender Envelope** | `core/crypto.py`, `routers/messages.py` | ECIES Outer Envelope | Ephemeral X25519 + AES-256-GCM |
| **Payload Padding** | `core/crypto.py` | PKCS#7 + Random Byte Jitter | Fixed 2048-byte uniform block size |
| **Identity Signatures** | `core/crypto.py` | Ed25519 | 64-byte signature, 32-byte public key |
| **Local DB Key KDF** | `core/crypto.py` | PBKDF2-HMAC-SHA256 | 10,000 iterations, 256-bit key |

---

## 3. Threat Model & Security Boundaries

### 3.1 In-Scope Adversaries
1. **Malicious / Compromised Pairwise Relay**: The relay node may attempt to log connection IP addresses, observe message metadata, enumerate social graphs, or forge messages.
   - *Mitigation*: Ephemeral un-linkable queue tokens, Sealed-Sender ECIES outer envelopes, uniform 2KB payload padding.
2. **Harvest-Now-Decrypt-Later (Quantum Adversary)**: Passive adversaries recording ciphertext streams to decrypt when quantum computers arrive.
   - *Mitigation*: ML-KEM-768 post-quantum key encapsulation combined with X25519 via HKDF-SHA256 hybrid derivation (`_pq_combine`).
3. **Local Workstation / Coercion Adversary**: Physical seizure or inspection of user devices.
   - *Mitigation*: Zeroization panic wipe (`obliviate`), PBKDF2-encrypted local database, non-functional cover launcher.

### 3.2 Out-of-Scope / Non-Goals
- Global traffic analysis covering all Tor entry/exit guard nodes across the public internet.
- Physical hardware compromise of active CPU memory during un-locked runtime.

---

## 4. Entry Points & Attack Surface Map

```
┌──────────────────────────────────────────────────────────────────┐
│                      Client UI (SolidJS)                         │
└─────────────────────────────────┬────────────────────────────────┘
                                  │ HTTP / WS (localhost:5001)
┌─────────────────────────────────▼────────────────────────────────┐
│              FastAPI Backend (app_v3.py / Uvicorn)               │
├──────────────────────────────────┬───────────────────────────────┤
│ Routers:                         │ Security Controls:            │
│  - /v3/auth/                     │  - CORS Local Restrict        │
│  - /v3/messages/                 │  - Rate Limiter Middleware    │
│  - /v3/contacts/                 │  - Strict Payload Validation  │
│  - /v3/p2p/                      │  - Sealed-Sender Resolver     │
│  - /v3/node/obliviate            │  - Eventlet Isolation         │
└──────────────────────────────────┴───────────────────────────────┘
```

---

## 5. Audit Harness & Test Vector Execution

Auditors can execute the complete cryptographic test harness using:

```bash
# 1. Execute Known Answer Test (KAT) Vectors
python -m pytest tests/unit/test_kat_crypto.py -v

# 2. Execute Full Cryptographic Unit Test Suite
python -m pytest tests/unit/p2p/test_protocol.py -v

# 3. Execute Schema Drift and SQL Injection Verification
python -m pytest tests/unit/test_schema_drift.py -v
```
