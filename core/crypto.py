import base64
import hashlib
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ── Argon2id parameters ──────────────────────────────────────────────────────
#
# Audit fix ANO-SEC-002: previously ``derive_db_key`` used PBKDF2-HMAC-SHA256
# with a hardcoded constant salt (``b"salt_for_db_key_anonymus"``) and only
# 10,000 iterations. SECURITY.md line 28 promises "Argon2id (t=3, m=65536,
# p=4)" — the actual implementation used neither Argon2 nor per-user salts.
#
# OWASP recommends PBKDF2-HMAC-SHA256 with at least 600,000 iterations for
# password hashing (2023 guidance), and NIST SP 800-132 mandates per-password
# random salts. Argon2id with m=65536 (64 MB memory) limits an attacker to
# ~1-10 guesses/second on commodity GPU hardware, vs 100,000+/second for
# PBKDF2 with 10,000 iterations.
#
# The implementation below prefers Argon2id (via the ``argon2-cffi`` package
# when available) and falls back to PBKDF2 with 600,000 iterations if Argon2
# is not installed. The salt is always per-user random 16 bytes, generated
# at registration time and stored alongside the password hash.

ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # 64 MB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = 32
PBKDF2_FALLBACK_ITERATIONS = 600_000  # OWASP 2023 minimum


def _argon2_available() -> bool:
    """Return True if the ``argon2-cffi`` package is importable."""
    try:
        import argon2  # type: ignore[import-untyped]  # noqa: F401

        return True
    except ImportError:
        return False


def derive_db_key(
    password: str,
    salt: bytes | None = None,
    iterations: int | None = None,
) -> tuple[bytes, bytes]:
    """Derive a 256-bit database key from a password.

    Audit fix ANO-SEC-002: this function now uses Argon2id (the memory-hard
    variant recommended by OWASP and the RFC 9106 spec) when the
    ``argon2-cffi`` package is available, and falls back to PBKDF2 with
    600,000 iterations otherwise. The salt is per-user random 16 bytes,
    generated if not provided, and returned alongside the derived key so the
    caller can persist it.

    Args:
        password: The user's password.
        salt: Optional 16-byte random salt. If None, a fresh salt is generated.
        iterations: Optional iteration count (PBKDF2 fallback only). Defaults
            to ``PBKDF2_FALLBACK_ITERATIONS`` (600,000).

    Returns:
        Tuple of ``(derived_key, salt)``. The caller MUST persist the salt
        alongside the password hash so the same key can be re-derived on
        subsequent logins.

    Migration note: existing databases that were encrypted with the legacy
        ``derive_db_key(password, salt=b"salt_for_db_key_anonymus", iterations=10000)``
        call cannot be re-derived with the new parameters. A migration script
        is required to re-encrypt existing databases on next login.
    """
    if salt is None:
        salt = os.urandom(16)
    if iterations is None:
        iterations = PBKDF2_FALLBACK_ITERATIONS

    if _argon2_available():
        # Use the low-level Argon2id hash via argon2-cffi.
        from argon2.low_level import hash_secret_raw, Type

        key = hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=ARGON2_TIME_COST,
            memory_cost=ARGON2_MEMORY_COST,
            parallelism=ARGON2_PARALLELISM,
            hash_len=ARGON2_HASH_LEN,
            type=Type.ID,  # Argon2id (hybrid)
        )
        return key, salt

    # Fallback: PBKDF2 with 600,000 iterations (was 10,000).
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return key, salt


def derive_db_key_legacy(
    password: str, salt: bytes = b"salt_for_db_key_anonymus", iterations: int = 10000
) -> bytes:
    """Legacy PBKDF2 key derivation — retained for migration of old databases only.

    Audit fix ANO-SEC-002: this function is kept ONLY to support one-shot
    re-encryption of databases that were encrypted with the old parameters.
    New code MUST use ``derive_db_key`` (Argon2id + per-user salt) instead.
    """
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def generate_db_salt() -> bytes:
    """Generate a fresh 16-byte random salt for DB key derivation.

    Audit fix ANO-SEC-002: the previous implementation used a hardcoded
    constant salt, which meant rainbow tables precomputed for that salt
    would decrypt every user's database with the same password.
    """
    return secrets.token_bytes(16)


def encrypt_secret(plaintext_b64: str, db_key_hex: str) -> str:
    """
    Encrypts a shared secret using AES-GCM. Raises exceptions on failure.
    """
    if not plaintext_b64:
        return plaintext_b64
    if not db_key_hex:
        raise ValueError("Missing database key for encryption.")
    key = bytes.fromhex(db_key_hex)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext_b64.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("utf-8")


def decrypt_secret(ciphertext_b64: str, db_key_hex: str) -> str:
    """
    Decrypts a shared secret using AES-GCM. Raises exceptions on failure.
    """
    if not ciphertext_b64:
        return ciphertext_b64
    if not db_key_hex:
        raise ValueError("Missing database key for decryption.")
    data = base64.b64decode(ciphertext_b64)
    if len(data) < 12:
        raise ValueError("Ciphertext too short.")
    nonce = data[:12]
    ct = data[12:]
    key = bytes.fromhex(db_key_hex)
    aesgcm = AESGCM(key)
    pt = aesgcm.decrypt(nonce, ct, None)
    return pt.decode("utf-8")


from cryptography.hazmat.primitives.asymmetric import ed25519

# Audit fix ANO-CODE-001 / ANO-SEC-023: hardcoded developer public key.
# This is retained for backward compatibility with existing supporter
# badges, but new badges should use a rotating key managed via the
# SUPPORTER_BADGE_PUBLIC_KEY environment variable. See AUDIT_REMEDIATION.md
# for the migration path.
_DEVELOPER_PUBLIC_KEY_B64_DEFAULT = "HO/h+Ogyso5N4QGTd5AhBIOuX2PQx7mj39dhwk4U1hU="
DEVELOPER_PUBLIC_KEY_B64 = os.environ.get(
    "SUPPORTER_BADGE_PUBLIC_KEY",
    _DEVELOPER_PUBLIC_KEY_B64_DEFAULT,
)


def verify_supporter_badge(onion_address: str, signature_b64: str) -> bool:
    """
    Verifies a supporter badge signature locally.
    The message signed is the user's onion_address.
    """
    try:
        pub_key_bytes = base64.b64decode(DEVELOPER_PUBLIC_KEY_B64)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_key_bytes)
        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, onion_address.encode("utf-8"))
        return True
    except Exception:
        return False


def generate_supporter_badge_signature(onion_address: str, priv_key_b64: str) -> str:
    """
    Helper function to generate a supporter badge signature.
    """
    priv_key_bytes = base64.b64decode(priv_key_b64)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_key_bytes)
    signature = private_key.sign(onion_address.encode("utf-8"))
    return base64.b64encode(signature).decode("utf-8")
