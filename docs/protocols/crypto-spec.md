# Cryptographic Specification & Security Architecture (v3.0)

This specification defines the cryptographic primitives, key derivation functions, ratchet state transitions, envelope formats, and at-rest storage mechanisms implemented in AnonyMus v3.0.

---

## 1. Cryptographic Primitives & Parameters

| Primitive Role | Algorithm / Standard | Parameters / Key Sizes |
|---|---|---|
| **Classical Key Exchange** | X25519 (RFC 7748) | Curve25519 ECDH, 32-byte public/private keys |
| **Post-Quantum Key Exchange** | ML-KEM-768 (NIST FIPS 203) | Kyber768, 1184-byte public key, 1088-byte ciphertext |
| **Digital Signatures** | Ed25519 (RFC 8032) | 32-byte public key, 64-byte signature |
| **Symmetric Encryption (AEAD)** | AES-256-GCM (NIST SP 800-38D) | 256-bit key, 12-byte IV, 16-byte authentication tag |
| **Alternative Cipher** | ChaCha20-Poly1305 (RFC 8439) | 256-bit key, 12-byte nonce, 16-byte tag |
| **Key Derivation Function** | HKDF-SHA256 (RFC 5869) | SHA-256 extract & expand with contextual info strings |
| **At-Rest Key Derivation** | Argon2id & PBKDF2-HMAC-SHA256 | Argon2id ($t=3, m=65536, p=4$) / PBKDF2 (600,000 iter, 16B salt) |
| **Password Storage** | bcrypt | Work factor 12 |

---

## 2. Post-Quantum Hybrid Key Encapsulation (PQXDH)

AnonyMus protects against harvest-now-decrypt-later attacks by combining classical Diffie-Hellman with quantum-resistant lattice encapsulation:

### A. Prekey Bundles & Pool Replenishment
Each node generates and publishes prekey bundles comprising:
- **Identity Key**: Long-term Ed25519/X25519 keypair ($IK$).
- **Signed Prekey**: Medium-term X25519 keypair ($SPK$) signed with $IK$.
- **One-Time Prekeys**: Ephemeral X25519 keypairs ($OPK$).
- **Post-Quantum Prekey**: NIST FIPS 203 ML-KEM-768 keypair ($PQ\_PK$).

The background worker (`core/prekey_pool.py`) continuously tracks active prekey pools and automatically generates new bundles whenever available one-time keys fall below configured thresholds.

### B. Shared Secret Derivation
The sender initiates a session by generating ephemeral keypair $EK$ and encapsulating against the recipient's $PQ\_PK$:
$$(\text{kem\_ct}, \text{kem\_ss}) = \text{ML-KEM-768.Encaps}(PQ\_PK)$$
$$\text{DH}_1 = \text{X25519}(IK_A, SPK_B), \quad \text{DH}_2 = \text{X25519}(EK_A, IK_B)$$
$$\text{DH}_3 = \text{X25519}(EK_A, SPK_B), \quad \text{DH}_4 = \text{X25519}(EK_A, OPK_B)$$
$$\text{Classical\_Secret} = \text{DH}_1 \parallel \text{DH}_2 \parallel \text{DH}_3 \parallel \text{DH}_4$$
$$\text{Master\_Secret} = \text{HKDF-SHA256}(\text{Classical\_Secret} \parallel \text{kem\_ss}, \text{salt}=\text{"AnonyMus-PQXDH-v3"}, \text{info}=\text{"SessionMasterKey"})$$

---

## 3. Double Ratchet & Authenticated Decryption

### A. Ratchet Mechanics
Each session maintains symmetric sending and receiving chain keys alongside an asynchronous Diffie-Hellman ratchet:
1. **Symmetric Step**: Advancing the sending/receiving chain produces a unique 32-byte message key ($MK$) and the next chain key.
2. **DH Ratchet Step**: Whenever a message with a new ephemeral DH public key is received, a new DH secret is computed and mixed into the root key via HKDF-SHA256.

### B. Strict v2 Associated Authenticated Data (`ANO-SEC-017`)
To prevent session splicing and downgrade attacks, encryption strictly binds the v2 AAD header:
$$\text{AAD} = \text{SHA256}(\text{session\_id})[:16] \parallel \text{role\_byte} \parallel \text{uint32\_be}(\text{seq\_num}) \parallel \text{0x02}$$
*Legacy v1 AAD fallback has been eliminated to protect against downgrade forgery.*

### C. Uniform Message Padding
Before encryption, plaintexts are padded to uniform 2 KB block boundaries with pseudo-random byte jitter (`core/rust/src/protocol/padding.rs`), mitigating traffic-analysis side-channel leakage.

---

## 4. Rejection-Sampling Safety Numbers (`ANO-CODE-009`)

Safety numbers allow out-of-band verification of participant identity keys:
1. Participant public keys are sorted lexicographically: $\text{data} = \text{sort}(PK_A, PK_B)$.
2. SHA-256 hash chains generate 32-bit candidate integers.
3. Candidate values are filtered with strict rejection sampling ($\text{val} < 4,294,900,000$).
4. Accepted values are reduced modulo $100,000$ to produce 12 groups of 5-digit decimal strings with **zero modulo bias**.

---

## 5. Metadata Protection & Envelope Privacy

- **Sealed-Sender Routing (`ANO-SEC-013`)**: Inner payloads encrypt sender identity. In strict mode (`ANONYMUS_SEALED_SENDER_STRICT=1`), messages from unverified contacts are dropped before reaching internal state stores.
- **Signed XFTP Chunk Transfer (`ANO-SEC-004`)**: File uploads are partitioned into 10 MB chunks and signed with the uploader's Ed25519 key, preventing cross-uploader cache poisoning and quota exhaustion.
- **Relay Node Verification (`ANO-SEC-005`)**: Node registration on blind relays requires Ed25519 signature proof over timestamped onion challenges.

---

## 6. Storage Encryption & Anti-Forensics

- **SQLCipher Integration (`ANO-SEC-008`)**: Databases use AES-256-GCM page encryption. In production, missing database keys trigger immediate startup termination.
- **Argon2id Key Derivation (`ANO-SEC-002`)**: Passphrases derive encryption keys via Argon2id ($t=3, m=65536, p=4$) with a per-database cryptographically random 16-byte salt (`generate_db_salt()`).
- **Emergency Zeroization (`obliviate`)**: Duress codes trigger multi-pass cryptographic zeroing (`os.urandom`) over local database files and key stores.
