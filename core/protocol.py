"""
Core Cryptographic Protocol Module for AnonyMus (Parity with Web Client).
Implements X25519 key exchange, Double Ratchet E2EE (v2), NaCl Cryptobox (v2),
PQ Hybrid KEM (ML-KEM-768, optional), safety numbers derivation, and
AES-256-GCM message encryption.
"""

import base64
import hashlib
import os
import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core import pq_kem
from core.queue_cryptobox import QueueCryptobox

PADDED_SIZE = 16384

# ---------------------------------------------------------------------------
# Post-Quantum KEM helpers (thin wrappers over core.pq_kem)
# ---------------------------------------------------------------------------


def generate_kem_keypair() -> tuple[bytes, bytes] | None:
    """
    Generates an ML-KEM-768 key pair.
    Returns (public_key_bytes, private_key_bytes) or None if liboqs unavailable.
    """
    return pq_kem.generate_ml_kem_keypair()


def kem_encapsulate(recipient_pub_bytes: bytes) -> tuple[bytes, bytes] | None:
    """
    Encapsulates a shared secret for recipient.
    Returns (ciphertext_bytes, shared_secret_bytes) or None if liboqs unavailable.
    """
    return pq_kem.encapsulate(recipient_pub_bytes)


def kem_decapsulate(ciphertext_bytes: bytes, private_key_bytes: bytes) -> bytes | None:
    """
    Decapsulates shared secret from ciphertext.
    Returns 32-byte shared secret or None if liboqs unavailable.
    """
    return pq_kem.decapsulate(ciphertext_bytes, private_key_bytes)


def generate_key_pair():
    """Generates a new X25519 private/public key pair."""
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def export_public_key(public_key) -> str:
    """Exports a public key as a base64-encoded raw byte string."""
    raw_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw_bytes).decode("utf-8")


def import_public_key(pub_b64: str):
    """Imports a public key from a base64-encoded raw byte string."""
    raw_bytes = base64.b64decode(pub_b64)
    return x25519.X25519PublicKey.from_public_bytes(raw_bytes)


def export_private_key_pem(private_key) -> str:
    """Exports a private key as an unencrypted PEM PKCS8 string."""
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_bytes.decode("utf-8")


def import_private_key_pem(pem_str: str):
    """Imports a private key from an unencrypted PEM PKCS8 string."""
    return serialization.load_pem_private_key(pem_str.encode("utf-8"), password=None)


def derive_shared_secret(my_private_key, their_public_key) -> bytes:
    """Computes X25519 shared secret."""
    return my_private_key.exchange(their_public_key)


def hkdf_derive(ikm: bytes, info: bytes, salt: bytes = b"\x00" * 32) -> bytes:
    """Derives a 256-bit key from input keying material using HKDF-SHA256."""
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info)
    return hkdf.derive(ikm)


def compute_safety_number(pubkey1_b64: str, pubkey2_b64: str) -> str:
    """
    Computes a human-verifiable safety number as 12 groups of 5 decimal digits.
    """
    sorted_keys = sorted([pubkey1_b64, pubkey2_b64])
    data = (sorted_keys[0] + sorted_keys[1]).encode("utf-8")
    h = hashlib.sha256(data).digest()

    groups = []
    indices = [int(i * 2.5) for i in range(12)]
    for idx in indices:
        val = (h[idx] << 8) | h[idx + 1]
        groups.append(str(val % 100000).zfill(5))
    return " ".join(groups)


def construct_aad(
    role: str, seq_num: int, session_id: str, protocol_version: int = 2
) -> bytes:
    """Constructs authenticated additional data payload."""
    role_byte = role.encode("utf-8")[0:1]
    if protocol_version == 1:
        return role_byte + struct.pack(">I", seq_num)

    session_hash = hashlib.sha256(session_id.encode("utf-8")).digest()
    truncated_session = session_hash[:16]
    return (
        role_byte
        + struct.pack(">I", seq_num)
        + truncated_session
        + bytes([protocol_version])
    )


def pad_plaintext(text: str) -> bytes:
    """Pads plaintext with a 4-byte length prefix and random trailing noise."""
    text_bytes = text.encode("utf-8")
    text_len = len(text_bytes)

    padded_len = PADDED_SIZE
    if text_len + 4 > padded_len:
        padded_len = ((text_len + 4 + PADDED_SIZE - 1) // PADDED_SIZE) * PADDED_SIZE

    padded_buffer = bytearray(padded_len)
    struct.pack_into(">I", padded_buffer, 0, text_len)
    padded_buffer[4 : 4 + text_len] = text_bytes

    if padded_len > text_len + 4:
        padded_buffer[4 + text_len :] = os.urandom(padded_len - text_len - 4)
    return bytes(padded_buffer)


def encrypt_message_v2(
    dr_session,
    plaintext: str,
    role: str,
    session_id: str,
    my_private_key_bytes: bytes,
    peer_public_key_bytes: bytes,
) -> dict:
    """
    Layered E2E Encryption (v2):
    1. Inner Layer: Double Ratchet AES-256-GCM.
    2. Outer Layer: Queue NaCl Cryptobox.
    """
    msg_key, dr_pub_bytes, dr_seq, dr_pn = dr_session.encrypt()

    iv = os.urandom(12)
    padded_data = pad_plaintext(plaintext)
    aad = construct_aad(role, dr_seq, session_id, 2)

    aesgcm = AESGCM(msg_key)
    inner_ciphertext = aesgcm.encrypt(iv, padded_data, aad)
    inner_payload = iv + inner_ciphertext

    box_ciphertext, box_nonce = QueueCryptobox.encrypt(
        inner_payload, my_private_key_bytes, peer_public_key_bytes
    )

    return {
        "nacl_nonce": base64.b64encode(box_nonce).decode("utf-8"),
        "nacl_ciphertext": base64.b64encode(box_ciphertext).decode("utf-8"),
        "dr_dh_public": base64.b64encode(dr_pub_bytes).decode("utf-8"),
        "dr_seq": dr_seq,
        "dr_pn": dr_pn,
    }


def decrypt_message_v2(
    dr_session,
    payload: dict,
    role: str,
    session_id: str,
    my_private_key_bytes: bytes,
    peer_public_key_bytes: bytes,
) -> str:
    """
    Layered E2E Decryption (v2):
    1. Outer Layer: Decrypt NaCl Cryptobox.
    2. Double Ratchet Step to retrieve Message Key.
    3. Inner Layer: Decrypt AES-256-GCM.
    """
    box_nonce = base64.b64decode(payload["nacl_nonce"])
    box_ciphertext = base64.b64decode(payload["nacl_ciphertext"])
    dr_pub_bytes = base64.b64decode(payload["dr_dh_public"])
    dr_seq = int(payload["dr_seq"])
    dr_pn = int(payload["dr_pn"])

    inner_payload = QueueCryptobox.decrypt(
        box_ciphertext, box_nonce, peer_public_key_bytes, my_private_key_bytes
    )

    iv = inner_payload[:12]
    inner_ciphertext = inner_payload[12:]

    msg_key = dr_session.decrypt(dr_pub_bytes, dr_seq, dr_pn)

    aad = construct_aad(role, dr_seq, session_id, 2)
    aesgcm = AESGCM(msg_key)
    decrypted = aesgcm.decrypt(iv, inner_ciphertext, aad)

    text_len = struct.unpack(">I", decrypted[:4])[0]
    if text_len > len(decrypted) - 4:
        raise ValueError("Decrypted length header exceeds message buffer bounds.")
    return decrypted[4 : 4 + text_len].decode("utf-8")


def decrypt_message(
    key_or_session,
    iv_b64: str,
    ct_b64: str,
    role: str,
    seq_num: int,
    session_id: str,
    my_private_key_bytes: bytes = None,
    peer_public_key_bytes: bytes = None,
    payload: dict = None,
) -> str:
    """
    Decrypts a message, automatically choosing v2 Double Ratchet/Cryptobox or v1 fallback.
    """
    if payload and "nacl_ciphertext" in payload:
        return decrypt_message_v2(
            key_or_session,  # dr_session
            payload,
            role,
            session_id,
            my_private_key_bytes,
            peer_public_key_bytes,
        )
    else:
        # Fallback to old v1 decryption
        iv = base64.b64decode(iv_b64)
        ciphertext = base64.b64decode(ct_b64)
        aesgcm = AESGCM(key_or_session)

        try:
            aad = construct_aad(role, seq_num, session_id, 2)
            decrypted = aesgcm.decrypt(iv, ciphertext, aad)
        except Exception:
            aad = construct_aad(role, seq_num, session_id, 1)
            decrypted = aesgcm.decrypt(iv, ciphertext, aad)

        text_len = struct.unpack(">I", decrypted[:4])[0]
        if text_len > len(decrypted) - 4:
            raise ValueError("Decrypted length header exceeds message bounds.")
        return decrypted[4 : 4 + text_len].decode("utf-8")
