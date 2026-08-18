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
| **Physical Device Seizure** | Unauthorized offline database analysis | SQLite database encryption via AES-256-GCM + Argon2id key derivation + Duress PIN wipe capability. |
| **LAN Eavesdropping / Hijacking** | Malicious database injection during device sync | Mutual 6-digit SAS PIN authentication and HKDF key derivation over X25519 ephemeral key exchange. |
| **Memory Exhaustion (DoS)** | Excessive chunk uploads exhausting RAM | Bounded disk-backed XFTP chunk cache with a 500 MB quota and 15-minute TTL eviction. |
| **XSS / Desktop Injection** | Host code execution via web client | Strict Content Security Policy (CSP) in Tauri desktop wrapper and solid client input sanitization. |

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
