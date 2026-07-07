# RFC 0003: Tor Egress Routing for Client Metadata Privacy

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

In decentralized networks, direct peer-to-peer IP connections leak physical location and internet service provider (ISP) metadata. To prevent de-anonymization, all outbound connections to peers must be routed through the Tor network.

## 2. Goals & Non-Goals

### Goals
- Secure client IP addresses from discovery by contacts or relays.
- Tunnel all outgoing HTTP and WebSocket traffic through local Tor SOCKS5 proxies.
- Validate and package Tor Expert Bundle dependencies automatically on first setup.

### Non-Goals
- Routing local-only configuration or diagnostic loopback (`127.0.0.1`) API traffic through Tor.

## 3. Design Details

The client system incorporates a SOCKS5 socks-wrapper (such as SOCKSProxy configured via the `requests[socks]` library or local environment proxy variables).

When the transport starts:
1. `tor_manager.py` checks for the presence of the Tor binary locally.
2. If absent, it downloads and verifies the official Tor Expert Bundle against SHA-256 hashes.
3. It spins up a background Tor daemon listening on port `9050` (or dynamic configuration).
4. All peer-to-peer traffic is routed via `socks5h://127.0.0.1:9050` ensuring that DNS resolutions also happen on the Tor exit node.

```
+------------+          +---------------+          +------------+
| AnonyMus   |  SOCKS5  | Local Tor     |  Onion   | Peer Tor   |
| Client App +--------->+ Daemon (9050) +--------->+ Service    |
+------------+          +---------------+          +------------+
```

## 4. Security & Privacy Implications

- **DNS Leaks:** Using `socks5h` instead of standard `socks5` forces domain resolution to occur inside the Tor network, preventing local DNS leaks.
- **Tor Bootstrapping Attacks:** An adversary can monitor Tor bootstrap logs to detect that a user is running a privacy client.

## 5. Backward Compatibility

Compatible with standard Tor network routing rules and V3 onion address structures.
