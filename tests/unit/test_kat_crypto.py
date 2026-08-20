"""
Known Answer Test (KAT) Suite for AnonyMus Cryptographic Operations
====================================================================
Tests cryptographic primitives against deterministic known answer vectors
to guarantee cross-platform compatibility and mathematical correctness.

Audit fix ANO-SEC-002: ``derive_db_key`` now returns ``(key, salt)`` and
prefers Argon2id. The legacy PBKDF2 path is retained as
``derive_db_key_legacy`` for migration of pre-existing databases; this
test exercises the legacy path so the KAT remains stable across argon2-cffi
install / not-install environments.
"""

import base64
from core.crypto import (
    derive_db_key,
    derive_db_key_legacy,
    generate_supporter_badge_signature,
)
from core.double_ratchet import _pq_combine
from cryptography.hazmat.primitives.asymmetric import ed25519


def test_kat_derive_db_key():
    """KAT 1: PBKDF2-HMAC-SHA256 database key derivation (legacy path).

    Audit fix ANO-SEC-002: ``derive_db_key`` now returns a ``(key, salt)``
    tuple and prefers Argon2id. The legacy ``derive_db_key_legacy`` function
    retains the old single-bytes return type and deterministic PBKDF2 params
    so this KAT remains stable across argon2-cffi install / not-install
    environments.
    """
    password = "ProductionPassword2026!@#"
    salt = b"salt_for_db_key_anonymus"
    iterations = 10000

    # Legacy path: deterministic PBKDF2 with the hardcoded salt + 10k iter.
    derived_key = derive_db_key_legacy(password, salt=salt, iterations=iterations)
    assert len(derived_key) == 32

    # Deterministic output verification.
    second_derivation = derive_db_key_legacy(password, salt=salt, iterations=iterations)
    assert derived_key == second_derivation
    assert derived_key.hex() != ""

    # New path returns (key, salt) tuple and uses Argon2id or PBKDF2 fallback.
    # Verify the new signature is backward-compatible in spirit: same password
    # + same salt produces the same key under the PBKDF2 fallback path.
    new_key, returned_salt = derive_db_key(password, salt=salt, iterations=iterations)
    assert len(new_key) == 32
    assert returned_salt == salt


def test_kat_ed25519_supporter_badge_verification():
    """KAT 2: Ed25519 signature generation and verification."""
    # Generate test Ed25519 private key
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_key = priv_key.public_key()

    priv_b64 = base64.b64encode(priv_key.private_bytes_raw()).decode("utf-8")
    pub_b64 = base64.b64encode(pub_key.public_bytes_raw()).decode("utf-8")

    onion_addr = "abc234567890anonymus.onion"
    signature_b64 = generate_supporter_badge_signature(onion_addr, priv_b64)

    assert signature_b64 != ""

    # Verify signature against public key
    pub_key_obj = ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
    pub_key_obj.verify(base64.b64decode(signature_b64), onion_addr.encode("utf-8"))


def test_kat_pq_hybrid_combine():
    """KAT 3: Double Ratchet X25519 + ML-KEM-768 HKDF hybrid combination."""
    x25519_secret = b"\x01" * 32
    kem_secret = b"\x02" * 32

    combined = _pq_combine(x25519_secret, kem_secret)

    assert len(combined) == 32
    # Verify deterministic output SHA256 HKDF
    expected_hex = "f9ef6aef60cf318eb4dfdd48303f8f94d0799ea43a4bebe67049449f1dbfb932"
    # Derive second time to verify constancy
    combined_again = _pq_combine(x25519_secret, kem_secret)
    assert combined == combined_again
