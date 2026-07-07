import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def derive_db_key(password: str, salt: bytes = b'salt_for_db_key_anonymus', iterations: int = 10000) -> bytes:
    """
    Derives a 256-bit database decryption key from password using PBKDF2-HMAC-SHA256.
    """
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)

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
    ct = aesgcm.encrypt(nonce, plaintext_b64.encode('utf-8'), None)
    return base64.b64encode(nonce + ct).decode('utf-8')

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
    return pt.decode('utf-8')

