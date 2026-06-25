# Setup & Deployment Guide (Centralized Architecture)

This document provides technical instructions to set up, configure, and execute the centralized server relay and compile the Android client.

---

## 1. System Requirements

### Backend Relay
- **Python**: Version 3.11 or newer
- **Operating System**: Linux, macOS, or Windows (10/11)
- **Containerization (Optional)**: Docker Engine & Docker Compose

### Android Client
- **JDK**: Version 17
- **Android SDK**: API level 34 (Android 14) compile SDK, API level 26 (Android 8.0) minimum SDK

---

## 2. Server Deployment (Virtual Environment)

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

Configure the environment variables:
- `FLASK_SECRET_KEY`: High-entropy key used to secure Flask sessions.
- `DISABLE_SSL`: Set to `True` only when running behind a local reverse proxy or Tor Hidden Service where SSL is terminated externally. Set to `False` in production.
- `DATABASE_URL`: Set to a PostgreSQL connection URI (e.g., `postgresql://user:pass@host:5432/db`) to switch from SQLite to PostgreSQL. Leave empty to use SQLite (`users.db`).
- `REDIS_URL`: Connection string for Redis session/limiter caching (e.g., `redis://localhost:6379`). Leave empty to use in-memory caching.
- `CORS_ORIGINS`: Comma-separated list of allowed client origins.

### C. Run the Relay Server
To run the server locally:
```bash
python server.py
```
By default, the server runs on `http://127.0.0.1:5000`.

---

## 3. Server Deployment (Docker Containerization)

To spin up the centralized relay using Docker Compose (which configures the Flask server, PostgreSQL database, and Redis cache):
```bash
docker-compose up --build -d
```
The Flask relay will expose port `5000` to the host machine.

---

## 4. Running Automated Tests

A comprehensive suite of unit and integration tests is included. To execute backend unit tests:
```bash
python -m unittest discover tests
```

---

## 5. Android Client Compilation

The Android client is built using Gradle.

1. Open the `AnonyMus_android/` directory in Android Studio.
2. Ensure you have JDK 17 configured as the Gradle JDK.
3. Build the project or execute tests via the command line:
   ```bash
   cd AnonyMus_android
   # Linux / macOS
   ./gradlew test assembleDebug
   # Windows
   .\gradlew.bat test assembleDebug
   ```
4. The generated APK will be available under `app/build/outputs/apk/debug/`.
