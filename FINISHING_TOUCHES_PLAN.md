# Finishing Touches Plan
## AnonyMus: The Self-Improving Metadata-Resistant Messenger
**Status:** Alpha Release Handoff & Hardening Plan
**Target Date:** Q3 2026
**Guiding Doctrine:** `agent.md` (Systems-first, verified execution, absolute transparency)

---

## 1. Executive Summary & Architecture Overview

AnonyMus has undergone a successful migration from its legacy Flask/SQLite stack (v1.0/v2.0 baseline) to a modern, structured **FastAPI v3 architecture** backed by **SQLAlchemy asynchronous engines (WAL mode)**, **Alembic migration versioning**, and a **SolidJS + Vite + TypeScript** frontend bundle.

This document serves as the **Finishing Touches Plan** to transition the current codebase into a production-grade, alpha-ready release. It outlines:
1. **The Remaining Deliverables Matrix** across the original plan, v2.0 improvements, and v3.0 refactoring.
2. **A Systematic Integration Plan** mapping these tasks into the current architecture.
3. **An Alpha User Release Preparation Guide** detailing Tor configs, launchers, and self-hosted relay setups.
4. **A Remaining Bug & Issue Register** with concrete technical mitigations.

### Current System Topology
```mermaid
flowchart TB
    subgraph Client Node (Local Host)
        UI[SolidJS Web Frontend] <-->|HTTP/WS localhost:5001| FastAPI[FastAPI v3 Core]
        FastAPI <-->|asyncio / aiosqlite| DB[(SQLite WAL DB)]
        FastAPI <-->|SOCKS5 Proxy| TorLocal[Tor Daemon Local]
    end

    subgraph Public Internet
        TorLocal <-->|Tor Onion Circuit| RelayServer[AnonyMus Relay Server]
        TorLocal <-->|Direct Tor P2P| RemoteNode[Remote Peer Client Node]
    end
```

---

## 2. Remaining Deliverables Matrix

The table below lists all pending and partially completed items that must be addressed prior to the formal Alpha user release.

| ID | Phase | Feature / Task | Current Status | Description & Target Architecture |
| :--- | :--- | :--- | :--- | :--- |
| **D-01** | v3.0 Refactor | Deprecate Flask `server.py` | **Partial** | Remove legacy routes in `server.py`. Ensure all client processes, tests, and launchers boot the FastAPI app in `app_v3.py` on port 5001. |
| **D-02** | v3.0 Refactor | SDK & CLI Route Update | **Pending** | Port [core/sdk.py](file:///c:/Users/Aryan/OneDrive/Desktop/Coding%20Projects/1-Custom%20Chat%20App/AnonyMus/core/sdk.py) and [cli.py](file:///c:/Users/Aryan/OneDrive/Desktop/Coding%20Projects/1-Custom%20Chat%20App/AnonyMus/cli.py) from legacy `/api/` Flask endpoints to target `/v3/` FastAPI routes, or implement a compatibility redirection middleware in FastAPI. |
| **D-03** | v2.0 Crypto | Sealed-Sender Envelopes | **Pending** | Encrypt sender identities under recipient's public identity keys so that Relays cannot enumerate the social graph or identify message originators. |
| **D-04** | v2.0 Crypto | Fixed-Size Payload Padding | **Pending** | Implement pad-to-2KB blocks (with random jitter) on all outgoing E2EE envelopes to thwart side-channel traffic-size analysis. |
| **D-05** | Original Plan | mDNS LAN Discovery | **Partial** | Standardize multicast DNS peer discovery for offline local area network chat scenarios when Tor is unavailable. |
| **D-06** | Original Plan | Obliviate Panic Wipe | **Partial** | Hard-wire the UI button/command to execute a zeroization wipe of SQLite files, local storage keys, and credentials on demand. |
| **D-07** | v2.0 Features | WebRTC Calls over Tor | **Pending** | Route WebRTC signaling over the local Tor loop and force turn/stun routing to prevent local IP leaks during voice/video connections. |

---

## 3. Systematic Integration Plan

To integrate the remaining deliverables cleanly into the existing architecture, the following build steps will be executed:

```
[Phase A: Compatibility & Cleanup] -> [Phase B: Traffic & Size Obfuscation] -> [Phase C: LAN & Panic Features]
```

### Phase A: Compatibility & Deprecation (D-01, D-02)
1. **Redirection Layer in FastAPI**:
   To prevent immediate breakage of existing CLI or custom scripting clients, implement an API compatibility router in FastAPI that redirects `/api/{path}` to `/v3/{path}` with equivalent JSON payload mapping.
2. **SDK Route Alignment**:
   Modify [core/sdk.py](file:///c:/Users/Aryan/OneDrive/Desktop/Coding%20Projects/1-Custom%20Chat%20App/AnonyMus/core/sdk.py) variables to use the `/v3/` endpoint prefix.
3. **Flask Removal**:
   Retire `server.py` by renaming it to `server.py.deprecated` and removing its references in testing runners.

### Phase B: Sealed-Sender & Padding Integration (D-03, D-04)
1. **Sealed-Sender Envelope**:
   Add a second layer of encryption on P2P routes:
   - Outer envelope is encrypted under the recipient's identity key.
   - Only the recipient can decrypt the outer layer to view the sender's onion address and verification signature.
   - The relay server receives only generic routing tokens, leaving it completely blind to who is talking to whom.
2. **Padding Helper (`core/crypto.py`)**:
   Implement a padding utility:
   ```python
   def pad_payload(payload: bytes, target_size: int = 2048) -> bytes:
       # Add padding to exactly 2048 bytes with PKCS#7 or custom padding
       pass
   ```

### Phase C: Offline LAN & Panic Wipe (D-05, D-06)
1. **Local mDNS Daemon**:
   Mount a background Zeroconf listener in [app_v3.py](file:///c:/Users/Aryan/OneDrive/Desktop/Coding%20Projects/1-Custom%20Chat%20App/AnonyMus/transports/p2p/app_v3.py) that advertises the user's local peer port to other nodes on the same network.
2. **Panic Wipe Controller**:
   Expose `POST /v3/node/obliviate` to wipe the DB:
   ```python
   @router.post("/obliviate")
   async def obliviate(session: AsyncSession = Depends(get_session)):
       # Overwrite SQLite WAL files with random bytes, truncate, and exit process
       pass
   ```

---

## 4. Alpha User Release Preparation Guide

This guide describes how to configure, boot, and package the AnonyMus client and relay servers for alpha testers.

### 4.1 Client Node Configuration

#### 1. Tor Daemon Configuration (`torrc`)
Alpha users must run a local Tor daemon. Provide this standard configuration in `launcher/torrc`:
```text
SocksPort 9050
ControlPort 9051
CookieAuthentication 1
HiddenServiceDir ./hidden_service/
HiddenServicePort 80 127.0.0.1:5001
```

#### 2. Local Environment Setup (`.env`)
Instruct users to copy `.env.example` to `.env` in the project root:
```ini
# Production environment configurations
FLASK_SECRET_KEY=generate-a-secure-32-byte-token
DATABASE_URL=sqlite+aiosqlite:///./anonymus.db
TOR_CONTROL_PORT=9051
TOR_SOCKS_PORT=9050
TOR_ONION_DIR=./hidden_service
RELAY_ONION_ADDRESS=http://examplepayloadrelay.onion
```

#### 3. Client Bootstrap Script (`anonymus-launcher.py`)
Create a simple startup script `anonymus-launcher.py` in the root directory that handles dependencies and launch orchestration:
```python
import subprocess
import sys
import os
import time

def check_tor():
    # Attempt connecting to SOCKS5 port 9050
    import socket
    s = socket.socket()
    try:
        s.connect(("127.0.0.1", 9050))
        return True
    except Exception:
        return False

def main():
    print("[*] Checking Tor SOCKS5 daemon...")
    if not check_tor():
        print("[!] Tor is not running on port 9050. Please start Tor first.")
        sys.exit(1)

    print("[*] Running Alembic migrations...")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"])

    print("[*] Starting AnonyMus Local Server (FastAPI)...")
    # Boot Uvicorn on port 5001 (accessible only locally)
    subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        "transports.p2p.app_v3:app",
        "--host", "127.0.0.1",
        "--port", "5001"
    ])

    print("[*] Booting web interface...")
    # Instruct user to open browser, or auto-open
    import webbrowser
    webbrowser.open("http://127.0.0.1:5001/index.html")

if __name__ == "__main__":
    main()
```

### 4.2 Self-Hosted Relay Server Setup

For alpha users who want to host their own sealed-sender relay, provide the following Docker Compose stack.

#### 1. Relay Dockerfile (`Dockerfile.relay`)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY transports/relay /app/transports/relay
COPY core /app/core
EXPOSE 5001
ENV PORT=5001
CMD ["python", "-m", "uvicorn", "transports.relay.app_relay:app", "--host", "0.0.0.0", "--port", "5001"]
```

#### 2. Caddy Reverse Proxy Configuration (`Caddyfile`)
This configures Caddy to automatically fetch Let's Encrypt TLS certificates:
```text
relay.yourdomain.com {
    reverse_proxy anonymus-relay:5001

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-XSS-Protection "1; mode=block"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "no-referrer"
    }
}
```

#### 3. Orchestration Configuration (`docker-compose.yml`)
```yaml
version: '3.8'
services:
  anonymus-relay:
    build:
      context: .
      dockerfile: Dockerfile.relay
    environment:
      - DATABASE_URL=sqlite:///./relay.db
    volumes:
      - ./data:/app/data
    restart: always

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - anonymus-relay
    restart: always

volumes:
  caddy_data:
  caddy_config:
```

---

## 5. Remaining Bugs, Issues & Mitigation Register

The following register tracks known vulnerabilities, race conditions, or architecture defects, and details their mitigations.

### 5.1 Eventlet Pipe Selection Deadlock on Windows
* **Problem:** In legacy scripts, `eventlet` is loaded. Eventlet intercepts and patches socket functions. On Windows, this leads to deadlocks when launching background subprocesses using `subprocess.PIPE` because Eventlet's select loop fails to poll Windows pipes correctly.
* **Mitigation:**
  1. Ban the use of `eventlet` in the FastAPI v3 service (`app_v3.py`). Use standard asyncio and `uvicorn` which do not perform aggressive monkey-patching.
  2. For test cases that execute subprocesses, write outputs to temporary file wrappers (`tempfile.TemporaryFile`) instead of using `subprocess.PIPE` to bypass Windows pipe polling limitations.

### 5.2 Tor SOCKS5 Boot Race Condition
* **Problem:** If a client node starts and attempts to send pending messages over SOCKS5 immediately, it may crash or raise `ConnectionError` because the local Tor service is still building circuit tunnels.
* **Mitigation:**
  - Implement SOCKS5 connection pooling with retry loops inside [messages.py](file:///c:/Users/Aryan/OneDrive/Desktop/Coding%20Projects/1-Custom Chat App/AnonyMus/transports/p2p/routers/messages.py):
  ```python
  async def transmit_p2p_message_with_retry(recipient_onion: str, payload: dict, retries: int = 5):
      for attempt in range(retries):
          try:
              await transmit_p2p_message(recipient_onion, payload)
              return
          except Exception as e:
              # Wait with exponential backoff (e.g. 2, 4, 8 seconds)
              await asyncio.sleep(2 ** attempt)
      logger.error("transmission_aborted_permanently", target=recipient_onion)
  ```

### 5.3 Web Cryptography Production Fallback Vulnerability
* **Problem:** If WebAssembly loads slowly or fails in the browser, the frontend fallback stubs in `core.ts` provide mock cryptography (insecure keys and plaintexts). This is highly dangerous in production.
* **Mitigation:**
  - Implement a strict production check. In `web/src/lib/core.ts`, assert that the crypto engine is initialized using real WebAssembly:
  ```typescript
  if (import.meta.env.PROD && isUsingCryptoStub()) {
      showHardErrorScreen("Cryptographic Engine Failed to Initialize. Chat is disabled to prevent security compromise.");
      throw new Error("WASM Crypto failure in production.");
  }
  ```
  - The TopBar warning badge we added should remain as a secondary visual aid.

### 5.4 Database Schema Migration Version Skew
* **Problem:** Users updating their client might have a database matching a past version (e.g., missing columns in `contacts` or `groups`). A direct, unshielded migration might crash if columns were already manually added by other custom modules.
* **Mitigation:**
  - Standardize database checks on startup. The Alembic upgrade scripts must use `sa.inspect` (as in [698e812f0dfc_add_profiles_abuse_and_supporter_badges.py](file:///c:/Users/Aryan/OneDrive/Desktop/Coding%20Projects/1-Custom%20Chat%20App/AnonyMus/alembic/versions/698e812f0dfc_add_profiles_abuse_and_supporter_badges.py)) to conditionally add tables and columns only if they do not exist.
