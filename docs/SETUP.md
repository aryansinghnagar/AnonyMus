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
- `ANONYMUS_MODE`: Boot mode of the application. Set to `relay` (for centralized relay mode) or `p2p` (for peer-to-peer Tor mode). Defaults to `relay`.
- `FLASK_SECRET_KEY`: High-entropy key used to secure Flask sessions and sign cookies.
- `DISABLE_SSL`: Set to `True` only when running behind a local reverse proxy or when hosting as a Tor Hidden Service in P2P mode. Set to `False` in production relay environments.
- `DATABASE_URL`: Set to a PostgreSQL connection URI (e.g., `postgresql://user:pass@host:5432/db`) to switch from SQLite to PostgreSQL in Centralized Relay mode. Leave empty to use standard SQLite (`users.db`).
- `REDIS_URL`: Connection string for Redis session/limiter caching (e.g., `redis://localhost:6379`). Leave empty to use in-memory caching.

---

## 3. Running the Application

The unified system can be started via the Command Line Interface (CLI) or the Graphical User Interface (GUI) launcher.

### A. CLI Mode Startup
To start the application server using the configuration specified in `.env`:
```bash
python server.py
```
By default, the unified server runs on `http://127.0.0.1:5000`. 
- If `ANONYMUS_MODE=relay`, it boots the centralized relay Flask app.
- If `ANONYMUS_MODE=p2p`, it starts the local peer node and establishes a Tor Hidden Service.

### B. Graphical Desktop Launcher (Windows)
The repository includes a disguised Tkinter utility that manages the server lifecycle, performs diagnostic checks (DNS, Tor status), and provides runtime mode switching.
To run the launcher:
```bash
python launcher/launcher.py
```
- By default, it operates as the "Windows Network Diagnostics & Adapter Utility".
- Users can switch between Centralized Relay and Peer-to-Peer Tor modes directly inside the graphical interface.

---

## 4. Containerized Deployment (Docker)

To spin up the centralized relay stack (Flask server, PostgreSQL database, and Redis cache) using Docker Compose, execute the following from the repository root:

1. Build the Docker image:
   ```bash
   docker build -t anonymus -f build/Dockerfile .
   ```
2. Start the services:
   ```bash
   docker-compose -f build/docker-compose.yml up -d
   ```
The Flask relay will expose port `5000` to the host machine.

---

## 5. Running Automated Tests

The test suite covers shared core primitives, centralized relay logic, and P2P node components. To run all backend unit and integration tests:

Using virtual environment Python:
```bash
.\venv\Scripts\python.exe tests/run_tests.py
```

Or using system Python:
```bash
python tests/run_tests.py
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
