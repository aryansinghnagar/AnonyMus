"""
core/pq_kem.py — Post-Quantum Key Encapsulation (ML-KEM-768 / Kyber768)

Wraps the Open Quantum Safe `liboqs-python` library's ML-KEM-768 implementation.
Gracefully degrades to None if liboqs is not available — callers must handle the
None case by falling back to X25519-only mode.

ML-KEM-768 (NIST FIPS 203) parameters:
  Public key:       1184 bytes
  Private key:      2400 bytes
  Ciphertext:       1088 bytes
  Shared secret:    32 bytes

Usage:
    # Key generation (Bob, receiver)
    pk, sk = generate_ml_kem_keypair()

    # Encapsulation (Alice, sender)
    ct, ss_alice = encapsulate(pk)

    # Decapsulation (Bob)
    ss_bob = decapsulate(ct, sk)
    assert ss_alice == ss_bob  # Both have the same 32-byte shared secret
"""

import base64
import logging
import os

log = logging.getLogger(__name__)

# Feature flag — set ANONYMUS_PQ_HYBRID=1 to enable hybrid X25519 + ML-KEM mode
PQ_HYBRID_ENABLED: bool = os.environ.get("ANONYMUS_PQ_HYBRID", "0") == "1"

# The algorithm name used in liboqs (Kyber768 == ML-KEM-768 per NIST FIPS 203)
_KEM_ALG = "Kyber768"

# Attempt to load liboqs at import time.
# liboqs-python requires a pre-compiled native liboqs.so/.dll.
# On Windows without cmake the auto-installer will fail; we catch that gracefully.
_oqs = None
if not os.environ.get("ANONYMUS_PQ_DISABLE"):
    try:
        import oqs as _oqs_module  # type: ignore

        # Eagerly probe the native lib so we fail fast, not on first call
        _probe = _oqs_module.KeyEncapsulation(_KEM_ALG)
        _probe.generate_keypair()
        del _probe
        _oqs = _oqs_module
        log.info("liboqs loaded — ML-KEM-768 (Kyber768) available")
    except (Exception, SystemExit) as e:
        log.warning("liboqs not available — PQ hybrid mode disabled: %s", e)
        _oqs = None


def is_available() -> bool:
    """Returns True if liboqs is installed and ML-KEM-768 is usable."""
    return _oqs is not None


def generate_ml_kem_keypair() -> tuple[bytes, bytes] | None:
    """
    Generates an ML-KEM-768 key pair.

    Returns:
        (public_key_bytes, private_key_bytes) — 1184 and 2400 bytes respectively.
        Returns None if liboqs is not available.
    """
    if _oqs is None:
        return None
    kem = _oqs.KeyEncapsulation(_KEM_ALG)
    pk = kem.generate_keypair()
    sk = kem.export_secret_key()
    return pk, sk


def encapsulate(recipient_public_key_bytes: bytes) -> tuple[bytes, bytes] | None:
    """
    Encapsulates a shared secret for the given recipient public key.

    Args:
        recipient_public_key_bytes: 1184-byte ML-KEM-768 public key

    Returns:
        (ciphertext_bytes, shared_secret_bytes) — 1088 and 32 bytes respectively.
        Returns None if liboqs is not available.
    """
    if _oqs is None:
        return None
    kem = _oqs.KeyEncapsulation(_KEM_ALG)
    ciphertext, shared_secret = kem.encap_secret(recipient_public_key_bytes)
    return ciphertext, shared_secret


def decapsulate(ciphertext_bytes: bytes, private_key_bytes: bytes) -> bytes | None:
    """
    Decapsulates a shared secret from the given ciphertext and private key.

    Args:
        ciphertext_bytes:   1088-byte ML-KEM-768 ciphertext
        private_key_bytes:  2400-byte ML-KEM-768 private key

    Returns:
        32-byte shared secret, or None if liboqs is not available or decapsulation fails.
    """
    if _oqs is None:
        return None
    try:
        kem = _oqs.KeyEncapsulation(_KEM_ALG, private_key_bytes)
        return kem.decap_secret(ciphertext_bytes)
    except Exception as e:
        log.error("ML-KEM-768 decapsulation failed: %s", e)
        return None


def encode_public_key(pk_bytes: bytes) -> str:
    """Base64-encodes an ML-KEM-768 public key for JSON transport."""
    return base64.b64encode(pk_bytes).decode("utf-8")


def decode_public_key(pk_b64: str) -> bytes:
    """Decodes a base64-encoded ML-KEM-768 public key."""
    return base64.b64decode(pk_b64)


def encode_ciphertext(ct_bytes: bytes) -> str:
    """Base64-encodes an ML-KEM-768 ciphertext for JSON transport."""
    return base64.b64encode(ct_bytes).decode("utf-8")


def decode_ciphertext(ct_b64: str) -> bytes:
    """Decodes a base64-encoded ML-KEM-768 ciphertext."""
    return base64.b64decode(ct_b64)
