import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def derive_db_key(
    password: str, salt: bytes = b"salt_for_db_key_anonymus", iterations: int = 10000
) -> bytes:
    """
    Derives a 256-bit database decryption key from password using PBKDF2-HMAC-SHA256.
    """
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


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

DEVELOPER_PUBLIC_KEY_B64 = "HO/h+Ogyso5N4QGTd5AhBIOuX2PQx7mj39dhwk4U1hU="


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
