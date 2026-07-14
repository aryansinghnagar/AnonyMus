# RFC 0016: Messaging Layer Security (MLS) Group Key Agreement

- **Status:** Approved
- **Author(s):** AnonyMus Contributors
- **Created:** 2026-07-13
- **Updated:** 2026-07-13

---

## 1. Context

Group chats require scalable, forward-secure, post-compromise secure key distribution. This RFC details the epoch-based MLS key agreement implementation for secure multi-party channels.

## 2. Goals & Non-Goals

### Goals
- Secure group key agreement with epoch advancement.
- Keep group overhead low (O(log N)) for group operations.
- Provide strong membership verification.

### Non-Goals
- Large broadcast channels (use public keys / read-only queues instead).

## 3. Design Details

The group session is modeled as an `MlsGroup`:
- `group_id`: Unique 32-byte identifier.
- `epoch`: Counter incremented on membership changes.
- `epoch_secret`: The root key for the current epoch.
- `members`: List of public keys of the authorized group members.

Epoch secret transitions conform to TreeKEM principles:
$$\text{epoch\_secret}_{i+1} = \text{HKDF-Extract}(\text{epoch\_secret}_{i}, \text{path\_secret}_{i+1})$$
For each message, an epoch-specific sender key is derived:
$$\text{sender\_key} = \text{HKDF-Expand}(\text{epoch\_secret}, \text{"MLSSenderKey"} \parallel \text{username} \parallel \text{epoch})$$

## 4. Security & Privacy Implications

- **Forward Secrecy**: Advancing the epoch secret guarantees that a compromised client key cannot decrypt messages sent in previous epochs.
- **Post-Compromise Security**: A compromised member key is evicted by generating a new epoch path secret, locking out the compromised key.

## 5. Backward Compatibility

- Group messaging is exclusive to version 3 protocol. Relays will enforce version constraints for group message queues.
