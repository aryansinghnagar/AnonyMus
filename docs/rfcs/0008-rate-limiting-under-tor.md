# RFC 0008: Tor-Aware Rate Limiting Key Extraction

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

In Tor hidden service P2P networks, all incoming requests show the origin IP as loopback (`127.0.0.1` or `[::1]`) because connections transit the local Tor daemon. Standard rate-limiters matching on client IP will globally throttle all peers if a single peer floods the node.

## 2. Goals & Non-Goals

### Goals
- Isolate rate-limiting quotas per peer when operating over Tor.
- Extract individual peer identifiers from incoming HTTP request structures.
- Prevent loopback-address collision rate throttling.

### Non-Goals
- Attempting to extract remote WAN IP addresses (unresolvable over Tor).

## 3. Design Details

The application implements a custom rate-limiting key generator `get_p2p_rate_limit_key()` registered with Flask-Limiter:
1. **P2P Identifier Extraction:** For public P2P endpoints (e.g. `/p2p/message`), the helper inspects incoming JSON parameters for the peer's `sender` or `onion_address`.
2. **Fallback:** If parameters are missing, it falls back to standard client IP logging, which handles non-Tor loopback testing.
3. **Storage:** The rate-limiting hits are stored in the server's in-memory store.

```python
# Rate limiting key selector
def get_p2p_rate_limit_key():
    data = request.get_json(silent=True) or {}
    peer = data.get('sender') or data.get('onion_address')
    if peer:
        return f"tor_peer:{peer}"
    return get_remote_address()
```

## 4. Security & Privacy Implications

- **Symmetric Flooding Defenses:** Peers attempting to flood the hidden service route will be blocked individually, keeping the service responsive for other contacts.
- **Spoofing Mitigation:** Peer identifiers must map to registered contacts; requests claiming a fake identifier are rejected before executing rate-limiting rules.

## 5. Backward Compatibility

All P2P transport adapters must supply the correct `sender` parameters in outbound JSON requests to prevent rate limit hits.
