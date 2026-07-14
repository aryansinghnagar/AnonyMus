# RFC 0012: Post-Quantum Extended Triple Diffie-Hellman (PQXDH)

- **Status:** Approved
- **Author(s):** AnonyMus Contributors
- **Created:** 2026-07-13
- **Updated:** 2026-07-13

---

## 1. Context

This RFC details the key agreement protocol designed to replace classical X3DH with a hybrid Post-Quantum version (PQXDH). This protects asynchronous session setup against harvest-now-decrypt-later attacks using a combination of X25519 and ML-KEM-768.

## 2. Goals & Non-Goals

### Goals
- Secure asynchronous key agreement between two peers (Alice and Bob).
- Combine classical X25519 security with ML-KEM-768 post-quantum confidentiality.
- Defend against a quantum-capable passive adversary.

### Non-Goals
- Real-time/interactive session upgrades (use PQ Double Ratchet instead).

## 3. Design Details

The protocol requires Bob to publish a prekey bundle containing:
- An X25519 Identity Key ($IK_B$).
- An X25519 Signed Prekey ($SPK_B$).
- An ML-KEM-768 Ephemeral Public Key ($PQ\_SPK_B$).
- An X25519 One-Time Prekey ($OPK_B$) (optional).

Alice initiates by generating an ephemeral X25519 key ($EK_A$) and performing:
1. Classical DH operations ($DH_1 = IK_A \cdot SPK_B$, $DH_2 = EK_A \cdot IK_B$, $DH_3 = EK_A \cdot SPK_B$, $DH_4 = EK_A \cdot OPK_B$).
2. ML-KEM encapsulation ($SS_{PQ}, CT_{PQ}) = \text{Encapsulate}(PQ\_SPK_B$).
3. Derive the master shared secret:
   $$SS_{master} = \text{HKDF-Extract}(DH_1 \parallel DH_2 \parallel DH_3 \parallel DH_4 \parallel SS_{PQ})$$

## 4. Security & Privacy Implications

- **Hybrid Confidentiality**: If either X25519 or ML-KEM-768 is compromised, the remaining algorithm guarantees confidentiality.
- **Forward Secrecy**: Ephemeral KEM parameters and OPKs guarantee session key forward secrecy.

## 5. Backward Compatibility

- Old clients that do not support protocol version 3 cannot parse the hybrid ML-KEM-768 parameters. Relays will verify compatibility via API version headers (`/v3/`).
