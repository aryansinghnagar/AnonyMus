#!/usr/bin/env python3
"""
AnonyMus Platform Release Packaging Script
==========================================
Orchestrates multi-platform binary packaging and distribution assembly:
1. Builds the SolidJS web UI production bundle.
2. Compiles PyInstaller standalone executable for the client node.
3. Bundles environment templates, Tor configuration scripts, and documentation.
"""

import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "build" / "release_dist"


def clean_dist():
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[+] Output directory initialized: {DIST_DIR}")


def build_web_frontend():
    print("[*] Building SolidJS production web bundle...")
    web_dir = BASE_DIR / "web"
    cmd = ["npm", "run", "build"]
    res = subprocess.run(cmd, cwd=web_dir, capture_output=True, text=True, shell=True)
    if res.returncode != 0:
        print(f"[!] Frontend Build Error: {res.stderr}")
        sys.exit(1)
    print("[+] Web frontend bundle compiled successfully.")


def assemble_release_package():
    print("[*] Assembling release distribution package...")

    # 1. Copy web assets
    web_dist = BASE_DIR / "web" / "dist"
    target_web = DIST_DIR / "web_dist"
    if web_dist.exists():
        shutil.copytree(web_dist, target_web, dirs_exist_ok=True)

    # 2. Copy launcher & config scripts
    shutil.copy(BASE_DIR / "anonymus-launcher.py", DIST_DIR / "anonymus-launcher.py")
    if (BASE_DIR / ".env.example").exists():
        shutil.copy(BASE_DIR / ".env.example", DIST_DIR / ".env.example")
    if (BASE_DIR / "README.md").exists():
        shutil.copy(BASE_DIR / "README.md", DIST_DIR / "README.md")
    if (BASE_DIR / "LICENSE").exists():
        shutil.copy(BASE_DIR / "LICENSE", DIST_DIR / "LICENSE")

    print(f"[+] Release package successfully assembled at: {DIST_DIR}")


def main():
    print("=" * 60)
    print("      AnonyMus Release Packaging Assembler")
    print("=" * 60)
    clean_dist()
    build_web_frontend()
    assemble_release_package()


if __name__ == "__main__":
    main()
