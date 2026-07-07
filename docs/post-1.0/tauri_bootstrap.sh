#!/bin/bash
# ==============================================================================
# tauri_bootstrap.sh — Setup template for AnonyMus Desktop Client (v1.0.0+)
# ==============================================================================
# This script initializes the Rust-based Tauri wrapper and copies front-end SDK
# build assets for desktop packaging.
#

set -e

DESKTOP_DIR="packages/desktop-client"

echo "=== 1. Checking rustc and cargo installation ==="
if ! command -v cargo &> /dev/null; then
    echo "ERROR: Rust compiler 'cargo' is not installed. Please visit https://rustup.rs/."
    exit 1
fi

echo "=== 2. Creating Tauri app directory ==="
mkdir -p "$DESKTOP_DIR"
cd "$DESKTOP_DIR"

echo "=== 3. Initializing Node/TS Web Frontend ==="
npm init -y
npm install --save-dev typescript tauri @tauri-apps/cli @tauri-apps/api
npm install socket.io-client

# Copy TypeScript SDK compiled JS/d.ts into node_modules for local linking
echo "=== 4. Linking @anonymus/client SDK ==="
mkdir -p node_modules/@anonymus/client/dist
cp -r ../typescript-sdk/dist/* node_modules/@anonymus/client/dist/
cp ../typescript-sdk/package.json node_modules/@anonymus/client/

echo "=== 5. Running Tauri Initialization ==="
# Initialize Tauri Rust backend non-interactively
npx tauri init \
  --app-name "AnonyMus" \
  --window-title "AnonyMus Secure Messenger" \
  --dist-dir "../dist" \
  --dev-path "http://localhost:5173" \
  --before-dev-command "npm run dev" \
  --before-build-command "npm run build"

echo "=== 6. Packaging Embedded Tor Expert Bundle ==="
# Note: For production builds, Tor binaries must be placed in src-tauri/bin/
# so they are packed as sidecar executables.
mkdir -p src-tauri/bin
echo "[Tauri Setup] Please copy platform-specific tor binary (e.g. tor-x86_64-pc-windows-msvc) to src-tauri/bin/"

echo "=== Tauri environment bootstrapped successfully! ==="
