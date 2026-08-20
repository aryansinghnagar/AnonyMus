# AnonyMus Security Policy & Threat Model

## 1. Security Philosophy

AnonyMus treats user privacy and metadata resistance as fundamental human rights. Our security engineering doctrine mandates:
1. **Zero Knowledge**: Servers and relays must never possess plaintext message keys, contact graphs, or identity maps.
2. **Post-Quantum Defense-in-Depth**: All asymmetric handshakes must utilize hybrid classical + quantum-resistant encapsulation (ML-KEM-768).
3. **Plausible Deniability & Anti-Forensics**: Sensitive records must support automatic shredding and coercion duress zeroization.

---

## 2. Threat Model & Mitigations

| Threat Vector | Potential Impact | AnonyMus Mitigation |
| :--- | :--- | :--- |
| **ISP / Network Surveillance** | Traffic metadata analysis & peer identity discovery | All peer communications are routed over Tor v3 hidden services with onion routing. |
| **Future Quantum Decryption** | "Harvest now, decrypt later" attacks against historical traffic | Post-quantum ML-KEM-768 hybrid key encapsulation integrated into X3DH / Double Ratchet. |
| **Physical Device Seizure** | Unauthorized offline database analysis | SQLite database encryption via SQLCipher (AES-256-GCM) + Argon2id key derivation (`t=3, m=65536, p=4`) + Duress PIN wipe capability. **Audit fix ANO-SEC-008**: the database engine now refuses to start in production with `DB_KEY` unset, and automatically swaps to `sqlite+sqlcipher://` when `sqlcipher3` is installed. **Audit fix ANO-SEC-002**: the key-derivation function uses Argon2id with per-user random 16-byte salts (was PBKDF2 with 10,000 iterations and a hardcoded constant salt). |
| **LAN Eavesdropping / Hijacking** | Malicious database injection during device sync | Mutual 256-bit random pairing token (base32-encoded) authentication and HKDF key derivation over X25519 ephemeral key exchange, with a fresh per-pairing random 16-byte HKDF salt. **Audit fix ANO-SEC-001**: the previous 6-digit numeric PIN was brute-forceable in seconds against the GCM authentication tag; it is now a 256-bit random token with per-IP rate limiting (5 attempts / 60s, 30-minute cooldown after 10 failures). |
| **Memory Exhaustion (DoS)** | Excessive chunk uploads exhausting RAM | Bounded disk-backed XFTP chunk cache with a 500 MB quota and 15-minute TTL eviction. **Audit fix ANO-SEC-004**: the P2P upload endpoint now requires an Ed25519 signature from the uploader (verified against the public key encoded in their v3 onion address) and enforces per-uploader rate limiting (50 chunks / 5 minutes). |
| **XSS / Desktop Injection** | Host code execution via web client | Strict Content Security Policy (CSP) in Tauri desktop wrapper and solid client input sanitization. |
| **Relay Directory Pollution** | Attacker registers fake onion addresses, redirecting clients to attacker-controlled nodes | **Audit fix ANO-SEC-005**: the `/nodes/register` and `/nodes/heartbeat` endpoints now require an Ed25519 signature over `(onion_address || timestamp)` from the requester, verified against the 32-byte Ed25519 public key encoded in the v3 onion address. |
| **Prometheus Metrics Exposure** | Information disclosure (which onion addresses are active, message counts, etc.) | **Audit fix ANO-SEC-007**: the `/metrics` endpoint now requires either loopback access or a bearer token matching `ANONYMUS_METRICS_TOKEN` (compared with `secrets.compare_digest`). |
| **Hardcoded TURN Credentials** | Anyone with repo read access could use the TURN server | **Audit fix ANO-SEC-003**: Coturn credentials are now read from `COTURN_USER` / `COTURN_PASSWORD` environment variables; the compose file fails fast if either is unset. |
| **AAD Downgrade Attack** | Adversary forces fallback to legacy unauthenticated AAD format | **Audit fix ANO-SEC-017**: strict v2 AAD validation is enforced; silent v1 downgrade fallback in `decrypt_message` has been eliminated. |
| **Modulo Bias in Safety Numbers** | Skewed distribution leaving 34% of codespace unreachable | **Audit fix ANO-CODE-009**: safety number derivation utilizes SHA-256 hash chains with 32-bit window rejection sampling for provably uniform distribution. |
| **Sealed-Sender Spam / Abuse** | Anonymous senders flooding mailboxes with unverified traffic | **Audit fix ANO-SEC-013**: opt-in `ANONYMUS_SEALED_SENDER_STRICT` mode validates sender onion against the recipient's verified contact store before ingestion. |

---

## 3. Cryptographic Primitives & Parameters

- **Symmetric Cipher**: AES-256-GCM (NIST SP 800-38D) / ChaCha20-Poly1305 (RFC 8439)
- **Key Derivation**: Argon2id (`t=3, m=65536, p=4`) & HKDF-SHA256 (RFC 5869)
- **Classical Key Exchange**: Curve25519 (X25519, RFC 7748)
- **Post-Quantum KEM**: ML-KEM-768 (NIST FIPS 203)
- **Signatures**: Ed25519 (RFC 8032)
- **Password Storage**: bcrypt (work factor 12)

---

## 4. Reporting Security Vulnerabilities

We welcome security audits and responsible vulnerability reports from the research community.

If you discover a vulnerability or security flaw, please do NOT file a public issue. Instead, report it securely via:
- **Email**: `security@anonymus.internal` (PGP Key Fingerprint: `9F82 4B12 3C89 E5A1 D42B`)
- **Bug Bounty / Disclosure**: We aim to acknowledge receipt within 24 hours and provide a remediation timeline within 72 hours.
