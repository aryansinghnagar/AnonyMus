# Setup & Compilation Guide (Decentralized P2P Architecture)

This document provides technical instructions to set up the development environment, run the P2P and Client-Server daemons manually, run unit tests, and compile the disguised installer executable.

---

## 1. System Prerequisites

- **Python**: Version 3.11 or newer
- **Tor**: The application automatically downloads and extracts the **Tor Expert Bundle (v15.0.16)** for Windows, macOS, or Linux on first run. No manual Tor installation is required.
- **Inno Setup 6**: Required on Windows only if you intend to compile the standalone installer executable (`NetworkDiagnosticsInstaller.exe`).

---

## 2. Local Manual Setup

### A. Clone and Setup Virtual Environment
```bash
git clone https://github.com/aryansinghnagar/AnonyMus.git
cd AnonyMus
```

Create a virtual environment and install dependencies:
```bash
# Create venv
python -m venv venv

# Activate venv (Windows)
.\venv\Scripts\activate

# Activate venv (Linux/macOS)
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### B. Configuration
Create a `.env` file from the template at the root of the repository:
```bash
cp .env.example .env
```
The local GUI launcher dynamically overrides session keys and debugging variables, but a `.env` template is provided for manual development customization.

---

## 3. Running the Control Utility

To launch the disguised GUI administrative control panel (Windows Network Diagnostics Disguise):
```bash
python launcher.py
```
From the GUI, you can:
1. Configure active ports.
2. Select between P2P node mode (which provisions the Tor hidden service) or Centralized Client-Server relay client mode.
3. Start/stop the background daemons.
4. Launch the local web dashboard browser instance.

---

## 4. Standalone Executable Compilation

The repository includes scripts to bundle the entire project into a single, professional Windows installer.

1. Install Inno Setup 6 on your Windows system (default installation path: `C:\Program Files (x86)\Inno Setup 6\`).
2. Activate your virtual environment and install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
3. Run the automated build script:
   ```bash
   python build.py
   ```
4. The script will:
   - Run PyInstaller on `launcher.py` to compile a folder-based binary bundle under `dist/NetworkDiagnostics/`.
   - Embed the `app_main/` and `app_p2p/` packages inside the binary bundle.
   - Run the Inno Setup compiler to pack everything into a secure, single-file installer: `output/NetworkDiagnosticsInstaller.exe`.

---

## 5. Running Automated Tests

Both the client-server and P2P code packages include separate automated test suites.

To run the client-server (main) unit and integration tests:
```bash
python -m unittest discover app_main/tests
```

To run the decentralized P2P unit and integration tests:
```bash
python -m unittest discover app_p2p/tests
```

To run the end-to-end browser smoke test (requires Playwright):
```bash
# Install Playwright and chromium browser
pip install playwright
playwright install chromium

# Run the smoke test suite
python -m unittest app_main/tests/test_smoke.py
```

---

## 6. Troubleshooting & Security Notes

### A. Port Assignment Conventions
* **Centralized Server**: By default, the centralized relay server (`app_main/server.py`) binds to port `5000` (consistent with Docker, Docker Compose, and default Gunicorn settings).
* **Decentralized P2P UI**: In P2P mode, the local launcher GUI utility binds the web control panel to port `8080`. If port `8080` is in use, it will scan sequentially for the next available port.

### B. Clipboard Auto-Clear Behavior
* For security, the browser UI attempts to auto-clear the chat session invite link from the clipboard 30 seconds after copying.
* Modern browsers restrict clipboard reading to secure contexts and require user approval. If clipboard read permissions are denied, the auto-clear script will log a warning to the developer console and fail silently without disrupting the application flow.

### C. Self-Signed SSL Certificates & Android TOFU (Trust-On-First-Use)
* When running the centralized server in production/local secure modes, the backend generates a self-signed RSA-2048 certificate (`cert.pem`/`key.pem`) on startup if one is not present.
* The native Android client employs a Trust-On-First-Use (TOFU) pinning protocol. If you delete the server's certificate files and generate new ones, the client will block the WebSocket connection due to the fingerprint mismatch.
* **Resolution**: Clear the Android app's storage/cache in System settings to reset the TOFU certificate cache, or manually distribute/trust the new root CA/certificate.

### D. Local Multicast DNS (mDNS) Discovery
* The centralized server broadcasts its local IP address over LAN using the service descriptor `_anonymus._tcp.local.`.
* If local adapter discovery fails, verify that your host machine's firewall allows inbound UDP traffic on port `5353` (mDNS standard port) and that your local network router supports multicast packet routing.
