# AnonyMus Relay Transparency Report

This document contains statistics regarding information requests from law enforcement agencies, government entities, or third parties, and the responsive data provided by this AnonyMus relay operator.

> [!NOTE]
> Because AnonyMus is a fully decentralized, zero-knowledge metadata routing network, the relay has no access to user identities, shared keys, or decrypted message content. Furthermore, since the relay is a pure in-memory message queue with short-lived ephemeral chunk buffers, it has no persistent history of message routing metadata.

---

## 1. Information Requests Summary (Annual)

| Reporting Period | Country of Request | Number of Requests | Responsive Data Provided | Rationale |
|---|---|---|---|---|
| **2026 (YTD)** | All Countries | 0 | 0 | No user data or metadata exists on the relay server. |
| **2025** | All Countries | 0 | 0 | No user data or metadata exists on the relay server. |

---

## 2. Zero-Knowledge Rationale

This relay is mathematically and architecturally incapable of complying with data disclosure requests:
1. **No User Registration:** No email addresses, phone numbers, public keys, or usernames are stored.
2. **Ephemeral In-Memory Queues:** Messages are temporarily stored in volatile memory and deleted immediately upon recipient download.
3. **Double-Ratchet Encryption:** All messages are end-to-end encrypted (E2EE). The relay operator has no access to private key material.
4. **Onion Routing NAT Traversal:** Traffic is routed through Tor onion services, masking the IP addresses of both the sender and the recipient.

---

## 3. Warrant Canary

As of the date of this report:
1. The operator has not received any secret national security letters, gag orders, or FISA court warrants.
2. No backdoors have been introduced into the relay routing engine or cryptographic wrappers.
3. The server integrity has not been compromised.

---

## 4. Operator Template (For Self-Hosters)

If you are self-hosting an AnonyMus relay, copy this file to your repository and customize Section 1 and Section 3 to accurately reflect requests received by your node.
