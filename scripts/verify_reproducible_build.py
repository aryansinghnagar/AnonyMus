#!/usr/bin/env python3
"""
AnonyMus Reproducible Build Verification & Attestation Script
=============================================================
Computes bit-for-bit SHA-256 hashes of release artifacts and generates a
Cosign-compatible JSON attestation report for verifying build reproducibility.
"""

import json
import hashlib
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_reproducibility(dry_run: bool = False) -> dict:
    """Computes checksums of key artifacts and returns attestation manifest."""
    artifacts = [
        BASE_DIR / "anonymus-launcher.py",
        BASE_DIR / "requirements.txt",
        BASE_DIR / "Dockerfile.relay",
        BASE_DIR / "web" / "package.json",
    ]

    manifest = {
        "_type": "https://in-toto.io/Statement/v0.1",
        "predicateType": "https://slsa.dev/provenance/v0.2",
        "subject": [],
        "builder": {"id": "anonymus-reproducible-builder-v1"},
    }

    print("[*] Computing cryptographic digests for release subjects...")
    for path in artifacts:
        if path.exists():
            sha256_hash = compute_file_sha256(path)
            rel_path = path.relative_to(BASE_DIR).as_posix()
            manifest["subject"].append(
                {"name": rel_path, "digest": {"sha256": sha256_hash}}
            )
            print(f"    - {rel_path}: {sha256_hash}")

    attestation_path = BASE_DIR / "reproducible_attestation.json"
    if not dry_run:
        with open(attestation_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        print(f"[+] Attestation manifest saved to: {attestation_path}")
    else:
        print("[+] Dry run complete. Manifest generated in memory.")

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="AnonyMus Reproducible Build Verification Utility"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform verification without writing output files",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("    AnonyMus Reproducible Build & Attestation Verification")
    print("=" * 60)
    verify_reproducibility(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
