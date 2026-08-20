# Setup & Deployment Guide (Unified Architecture)

This document provides technical instructions to set up, configure, and execute the unified AnonyMus messaging application. It details deployment instructions for both **Centralized Relay** and **Decentralized P2P** modes.

---

## 1. System Requirements

### Backend Relay / Node
- **Python**: Version 3.11 or newer
- **Operating System**: Linux, macOS, or Windows (10/11)
- **Tor (For P2P Mode)**:
  - **Windows**: The P2P transport automatically orchestrates, downloads, and runs the embedded Tor Expert Bundle.
  - **Linux / macOS**: Requires a local Tor service installed and running on default SOCKS5 port 9050.
- **Containerization (Optional)**: Docker Engine & Docker Compose (used primarily for Centralized Relay deployment).

### Android Client
- **JDK**: Version 17
- **Android SDK**: API level 34 (Android 14) compile SDK, API level 26 (Android 8.0) minimum SDK.

---

## 2. Server & Node Deployment (Virtual Environment)

### A. Clone and Setup Environment
Clone the repository:
```bash
git clone https://github.com/aryansinghnagar/AnonyMus.git
cd AnonyMus
```

Create a Python virtual environment and activate it:
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

Install application dependencies:
```bash
pip install -r requirements.txt
```

### B. Configuration
Create a `.env` file from the template:
```bash
cp .env.example .env
```

Configure the environment variables in `.env`:
- `ANONYMUS_MODE`: Boot mode of the application. Set to `p2p` (peer-to-peer Tor mode) or `relay` (centralized relay mode). Defaults to `p2p`.
- `SECRET_KEY`: High-entropy 64-character hex secret used for session tokens and challenge validation.
- `DB_KEY`: 64-character hex encryption key for the SQLCipher at-rest database (mandatory in production environments).
- `ANONYMUS_METRICS_TOKEN`: Optional bearer token for authenticating access to the `/metrics` endpoint (`ANO-SEC-007`).
- `DISABLE_SSL`: Set to `True` when running behind a local reverse proxy or Tor Hidden Service.
- `DATABASE_URL`: Optional PostgreSQL connection URI (e.g., `postgresql+asyncpg://user:pass@host:5432/db`) for relay mode.
- `REDIS_URL`: Connection string for Redis session/limiter caching (e.g., `redis://localhost:6379`).

---

## 3. Running the Application

### A. Turnkey Launcher (Recommended)
Boot the application, initialize local keys, verify Tor proxy connectivity, and open the web interface in one step:
```bash
python anonymus-launcher.py
```
By default, the client node serves the web interface on `http://127.0.0.1:5001/index.html`.

### B. Direct ASGI Server Startup
To start the FastAPI v3 ASGI server directly:
```bash
python server.py
```
- If `ANONYMUS_MODE=p2p`, it starts the local node, loads the encrypted database, and connects to the Tor Control Port (`9051`) to publish an ephemeral v3 onion service.
- If `ANONYMUS_MODE=relay`, it boots the blind relay server on the configured port.

### C. Desktop Service Launcher (GUI)
The repository includes a desktop launcher utility to manage node lifecycles and monitor connection status:
```bash
python launcher/launcher.py
```

---

## 4. Containerized Deployment (Docker)

To deploy the production blind relay stack with Caddy auto-TLS, Redis, and Coturn TURN:

1. Configure `.env` with `SECRET_KEY`, `RELAY_DOMAIN`, `COTURN_USER`, and `COTURN_PASSWORD`.
2. Start the services from the repository root:
   ```bash
   docker compose up -d
   ```

---

## 5. Running Automated Tests

Run backend unit and integration test suites:

```bash
# Python Unit & Cryptographic KAT Suite
python -m pytest tests/unit -v

# FastAPI Integration & Contract Suite
python -m pytest tests/integration/test_fastapi_v3.py tests/integration/test_contract_v3.py -v

# Code Quality & Linting
ruff check .
ruff format --check .
```

---

## 6. Android Client Compilation

The native Android client source resides in the `android/` directory and is built using Gradle.

1. Open the [android/](file:///c:/Users/Aryan/OneDrive/Desktop/Coding%20Projects/1-Custom%20Chat%20App/AnonyMus/android) directory in Android Studio.
2. Ensure you have JDK 17 configured as the Gradle JDK.
3. Build the project or execute tests via the command line:
   ```bash
   cd android
   # Linux / macOS
   ./gradlew test assembleDebug
   # Windows
   .\gradlew.bat test assembleDebug
   ```
4. The generated APK will be available under `app/build/outputs/apk/debug/`.
