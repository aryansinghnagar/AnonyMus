# RFC 0001: AnonyMus Dual-Mode Architecture Overview

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

AnonyMus is designed to support two distinct operational environments using a single application bundle:
1. **Centralized Relay Mode:** Optimized for fast, low-latency, real-time message exchange over a centralized coordinator utilizing WebSockets (via Flask-SocketIO).
2. **Decentralized P2P Mode:** Optimized for maximal metadata protection, using peer-to-peer Tor V3 onion hidden services for end-to-end direct routing.

The runtime mode must be switchable on-the-fly without restarting the main system process or exposing duplicate state.

## 2. Goals & Non-Goals

### Goals
- Support dynamic switching of runtime network transport layers via a single localhost dispatcher endpoint `/api/mode`.
- Maintain discrete database separation and transport server life-cycles for P2P and Relay modes.
- Abstract the transport layer logic through a unified `TransportRegistry` and `BaseTransportAdapter` interface.

### Non-Goals
- Real-time handoff of active socket frames without connection drops. Users are expected to reconnect when modes switch.

## 3. Design Details

The switching logic is orchestrated by `core/transport_registry.py`. The active transport listens to control signals and boots the standby transport server before shutting down the active one (atomic switching).

```
          +-----------------------------------------+
          |           WSGI Dispatcher               |
          |       (server.py / mode router)         |
          +-------------------+---------------------+
                              |
                     [switch_mode event]
                              |
            +-----------------+-----------------+
            |                                   |
            v                                   v
   +--------+--------+                 +--------+--------+
   |  Relay Transport |                 |  P2P Transport  |
   | (Flask+SocketIO)|                 | (Tor V3 Service)|
   +-----------------+                 +-----------------+
```

## 4. Security & Privacy Implications

- **Mode Swapping Exposure:** The `/api/mode` endpoint is unauthenticated by default. In production, it must be restricted to localhost (`127.0.0.1` and `[::1]`) and validated against `ANONYMUS_ADMIN_SECRET` to prevent remote attackers from switching the transport mode.
- **Relay Social Graph:** Centralized relay servers record user registrations and active socket connections, presenting a metadata leakage vector. P2P mode mitigates this by eliminating centralized registration.

## 5. Backward Compatibility

This architecture preserves compatibility with client APIs by maintaining common frontend endpoint structures, allowing client apps to switch server modes transparently.
