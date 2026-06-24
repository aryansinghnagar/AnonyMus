# Setup & Compilation Guide (Decentralized P2P Architecture)

This document provides technical instructions to set up the development environment, run the P2P daemon manually, run unit tests, and compile the disguised installer executable.

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
1. View active ports and settings.
2. Initialize Onion routing and boot the background daemon.
3. Launch the local web dashboard browser instance.

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
   - Embed the `app_p2p/` package inside the binary bundle.
   - Run the Inno Setup compiler to pack everything into a secure, single-file installer: `output/NetworkDiagnosticsInstaller.exe`.

---

## 5. Running Automated Tests

To run the decentralized P2P unit and integration tests:
```bash
python -m unittest discover app_p2p/tests
```

---

## 6. Troubleshooting & Security Notes

### A. Port Assignment Conventions
* **Decentralized P2P UI**: In P2P mode, the local launcher GUI utility binds the web control panel to a dynamic port index starting at `8080`. If port `8080` is in use, it will scan sequentially for the next available free port.

### B. Clipboard Auto-Clear Behavior
* For security, the browser UI attempts to auto-clear the chat session invite link from the clipboard 30 seconds after copying.
* Modern browsers restrict clipboard reading to secure contexts and require user approval. If clipboard read permissions are denied, the auto-clear script will log a warning to the developer console and fail silently without disrupting the application flow.
