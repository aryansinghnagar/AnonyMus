#!/usr/bin/env python3
"""
AnonyMus Client Launcher
========================
Bootstraps local node services:
1. Validates Tor SOCKS5 proxy connectivity.
2. Runs Alembic database schema migrations.
3. Launches FastAPI app_v3 server on port 5001 via Uvicorn.
4. Opens default web browser to local web client interface.
"""

import os
import sys
import time
import socket
import signal
import subprocess
import webbrowser
from pathlib import Path

# Base Directory Setup
BASE_DIR = Path(__file__).resolve().parent


def check_tor_socks(
    host: str = "127.0.0.1", port: int = 9050, timeout: float = 3.0
) -> bool:
    """Verifies that the local Tor daemon SOCKS5 port is accessible."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def run_migrations():
    """Applies pending Alembic migrations to the SQLite database."""
    print("[*] Running Alembic database schema migrations...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[!] Migration Warning / Notice:\n{result.stderr or result.stdout}")
    else:
        print("[+] Database schema is up to date.")


def main():
    print("=" * 60)
    print("      AnonyMus Production Client Node Launcher")
    print("=" * 60)

    # 1. Tor SOCKS5 Proxy Check
    tor_host = os.environ.get("TOR_SOCKS_HOST", "127.0.0.1")
    tor_port = int(os.environ.get("TOR_SOCKS_PORT", "9050"))

    print(f"[*] Verifying Tor SOCKS5 proxy on {tor_host}:{tor_port}...")
    if not check_tor_socks(tor_host, tor_port):
        print(
            f"[!] WARNING: Tor SOCKS5 proxy is not accessible at {tor_host}:{tor_port}."
        )
        print(
            "    Tor P2P and Onion relay routing will be unavailable until Tor is started."
        )
        print("    Continuing boot in local-only / LAN mDNS mode...")
    else:
        print(f"[+] Tor SOCKS5 proxy verified on {tor_host}:{tor_port}.")

    # 2. Database Migrations
    run_migrations()

    # 3. Start FastAPI Server
    port = int(os.environ.get("PORT", "5001"))
    host = os.environ.get("HOST", "127.0.0.1")

    print(f"[*] Booting AnonyMus FastAPI Server on http://{host}:{port}...")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "transports.p2p.app_v3:app",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        "info",
    ]

    proc = subprocess.Popen(cmd, cwd=BASE_DIR)

    # Give server 1.5s to start
    time.sleep(1.5)

    # 4. Open Web Interface
    web_url = f"http://{host}:{port}/index.html"
    print(f"[+] Launching web browser: {web_url}")
    try:
        webbrowser.open(web_url)
    except Exception as e:
        print(f"[!] Failed to open browser automatically: {e}")
        print(f"    Please manually open: {web_url}")

    print("\n[+] AnonyMus node running. Press Ctrl+C to stop.\n")

    def signal_handler(sig, frame):
        print("\n[*] Shutting down AnonyMus node...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[+] Node stopped cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        proc.wait()
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
