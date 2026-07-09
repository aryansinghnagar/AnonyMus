# AnonyMus v1.0.0 — Zero-Knowledge Metadata-Private Messenger Released

We are proud to announce the official stable release of **AnonyMus v1.0.0**, a decentralized, metadata-private communications network built from the ground up to protect user identity and relationship graphs.

Most modern secure messaging applications protect the *content* of messages using End-to-End Encryption (E2EE), but leak the *metadata*—who is talking to whom, when, and how often. AnonyMus utilizes a unique queue-routing and P2P architecture to ensure that relationship graphs remain completely invisible to network observers, relay operators, and third parties.

---

## 🚀 Key Features in v1.0.0

### 1. Dual Routing Modes (Relay & P2P)
*   **Centralized Relay Mode:** Ephemeral, zero-knowledge in-memory message routing queues. Relays can be deployed onion-only (via `RELAY_AS_ONION=true`) to shield servers from clearnet IP mapping.
*   **Decentralized P2P Mode:** Direct node-to-node routing over Tor hidden services with no central points of failure.

### 2. Quantum-Resistant End-to-End Security
*   **X25519 Double Ratchet:** Ephemeral session ratchets providing forward secrecy and post-compromise security.
*   **Hybrid PQ-KEM (Kyber-768):** Integrated post-quantum key encapsulation to protect historic traffic from harvest-now-decrypt-later adversaries.

### 3. Absolute Metadata Privacy
*   **Pairwise Pseudonyms:** Every connection uses a distinct, randomly generated queue and public key. Users have no global profiles or persistent identity strings.
*   **Tor Integration:** Automatic Tor SOCKS5 routing to hide client IP locations and network presence.

### 4. Interactive & Collaborative UI
*   **Decentralized Groups:** Decentralized multi-user chat rooms using connection fan-outs and E2EE.
*   **WebRTC Voice/Video Notes:** Lazily loaded, chunked audio and video capturing (via Web XFTP transfer) and inline playback behind coturn TURN allocation.
*   **Disappearing & Live Messages:** Custom message auto-deletion TTLs and live-updating draft indicators.
*   **Multiple & Hidden Profiles:** Multiple isolated local contact folders with hidden profiles protected by decoy passphrases.

### 5. Third-Party Integrations
*   **TypeScript SDK:** `@anonymus/client` is published to let developers build automated bridges, bots, and alternative UI layouts.

---

## 🛠️ Getting Started

### Local Node Setup
Run the unified WSGI dispatcher to boot the controller panel locally:
```bash
venv\Scripts\python.exe server.py
```
Visit `http://127.0.0.1:8080` in your browser to launch the web client dashboard.

---

## 🛡️ Trust & Auditing
AnonyMus v1.0.0 incorporates an evolution of independent security reviews. We have published our [transparency declaration](file:///docs/security/transparency.md) outlining metadata zero-knowledge guarantees and zero law-enforcement compliance stats.
