# AnonyMus v3.0

> **Decentralized, Post-Quantum Resilient, Metadata-Resistant Communications**

[![CI Status](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/python.yml/badge.svg)](https://github.com/aryansinghnagar/AnonyMus/actions)
[![Rust Core](https://img.shields.io/badge/Rust_Core-anonymus__core-orange.svg)](core/rust)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Post-Quantum Ready](https://img.shields.io/badge/PQ_KEM-ML--KEM--768-success)](core/pq_kem.py)
[![Tor v3 Onion](https://img.shields.io/badge/Transport-Tor_v3_P2P-purple)](transports/p2p)

---

## What is AnonyMus?

**AnonyMus** is an open-source, metadata-resistant instant messaging and secure communication suite. Built from the ground up to protect user identity and content against surveillance, traffic analysis, and future quantum adversaries, AnonyMus combines:

1. **Tor v3 Onion Services**: Direct peer-to-peer routing with zero central servers or phone number requirements.
2. **Post-Quantum Hybrid Cryptography**: Double Ratchet forward secrecy augmented with NIST FIPS 203 **ML-KEM-768 (Kyber768)** key encapsulation.
3. **Hardware & Capability Optimization**: Dynamic profile detection (`detect_capability_tier()`) adjusting cryptographic complexity and cache footprints to match low-end and high-end devices alike.
4. **Coercion-Resistant Duress Wipes**: Duress PIN codes for instant panic database shredding.
5. **Layman-Friendly Zero-Config Launcher**: 1-click startup with embedded Tor proxy detection and web/desktop GUI.

---

## Quickstart (For Layman Users)

No terminal expertise required!

### Windows
1. Double-click `install.ps1` (or run `./install.ps1` in PowerShell).
2. The setup wizard will automatically prepare the environment and launch AnonyMus in your default web browser.

### Linux / macOS
```bash
./install.sh
python3 anonymus-launcher.py
```

---

## Key Features

- **Zero-Knowledge Identity**: No email, phone number, or central directory registration required. Your cryptographic onion address is your public identity.
- **End-to-End Encryption**: Signal-grade Double Ratchet + ML-KEM-768 hybrid key exchange.
- **Disappearing & Ephemeral Messages**: Configurable TTL auto-burn timers with secure SQLite page zeroing.
- **Multi-Device Synchronization**: Mutual 6-digit SAS PIN-verified LAN device pairing.
- **Encrypted File Transfer (XFTP)**: Chunked, bounded disk-backed encrypted media transfer with automatic TTL pruning.
- **Decoy Profiles & Plausible Deniability**: Multiple sandboxed contact profiles behind independent unlock codes.

---

## Architectural Overview

```
 ┌────────────────────────────────────────────────────────┐
 │            Solid.js Web / Tauri Desktop UI             │
 └──────────────────────────┬─────────────────────────────┘
                            │ ASGI / REST / WebSockets
 ┌──────────────────────────▼─────────────────────────────┐
 │               FastAPI v3 Async Node                    │
 │  ┌─────────────────┐ ┌───────────────┐ ┌────────────┐  │
 │  │ Auth / Profiles │ │ Contacts & DB │ │ Push Relay │  │
 │  └─────────────────┘ └───────────────┘ └────────────┘  │
 └─────────────┬───────────────────────────┬──────────────┘
               │                           │
 ┌─────────────▼───────────────┐ ┌─────────▼──────────────┐
 │     Cryptographic Core      │ │    Transport Layer     │
 │  - Rust `anonymus_core`     │ │  - Tor v3 SOCKS5 Pool  │
 │  - Double Ratchet + ML-KEM  │ │  - Authenticated Sync  │
 │  - Argon2id / AES-256-GCM   │ │  - Local mDNS Beacon   │
 └─────────────────────────────┘ └────────────────────────┘
```

---

## Documentation Suite

- [User Quickstart Guide](QUICKSTART.md) — Comprehensive guide on creating identities, adding contacts, and pairing devices.
- [System Architecture](ARCHITECTURE.md) — In-depth architectural blueprint, protocol specifications, and database schema.
- [Security Policy & Threat Model](SECURITY.md) — Cryptographic parameters, vulnerability disclosure, and threat analysis.
- [Testing & Verification Guide](TESTING.md) — Master test suite and CI verification instructions.

---

## Verification & Testing

Run the full automated test suite locally:

```powershell
# Python Unit & Cryptographic KAT Suite
python -m pytest tests/unit -v

# FastAPI Integration & Contract Suite
python -m pytest tests/integration/test_fastapi_v3.py tests/integration/test_contract_v3.py -v

# Rust Core Verification
cargo check --lib --manifest-path core/rust/Cargo.toml
```

---

## License

AnonyMus is open-source software licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See [LICENSE](LICENSE) for details.
