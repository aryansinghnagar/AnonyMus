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

PADDED_SIZE = 2048

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


def derive_chain_keys(chain_key: bytes) -> dict[str, bytes]:
    """
    Derives next chain key and message key from current chain key using HKDF-SHA256.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=chain_key,
        info=b"AnonyMus-DR-ChainRatchet",
    )
    derived = hkdf.derive(b"\x00" * 32)
    return {
        "message_key": derived[:32],
        "next_chain_key": derived[32:],
    }


def compute_safety_number(pubkey1_b64: str, pubkey2_b64: str) -> str:
    """Compute a human-verifiable safety number as 12 groups of 5 decimal digits.

    Audit fix ANO-CODE-009 (C4): the previous implementation extracted 2 bytes
    per group and used ``val % 100000``. Since 2 bytes (16 bits, range 0..65535)
    only spans 65536 values but the modulus is 100000, the modulo wraps so
    that buckets 65536..99999 are *never* hit -- i.e., 34% of the 5-digit
    codespace was structurally unreachable, and the remaining buckets had
    double probability (1/65536 instead of 1/100000). This is a textbook
    modulo-bias vulnerability.

    The new implementation:
      1. Generates enough keying material via a SHA-256 hash chain
         (counter-prepended re-hashing) so we have 4 bytes per group
         (32 bits, range 0..4294967295).
      2. Applies rejection sampling: each 32-bit window is accepted only if
         ``val < floor(2**32 / 100000) * 100000 = 4_294_900_000``. Values
         in the rejection window ``[4_294_900_000, 4_294_967_295]`` are
         discarded and the next 4-byte window is consumed.
      3. ``2**32 mod 100000 = 67296``, so the rejection rate is
         ``67296 / 2**32 ~= 0.00157%`` -- effectively never, but the
         resulting distribution is provably uniform over [0, 100000).

    The output format (12 groups of 5-digit decimal numbers, space-separated,
    order-independent wrt the two input keys) is preserved so existing UIs
    that render safety numbers continue to work without modification.
    """
    sorted_keys = sorted([pubkey1_b64, pubkey2_b64])
    data = (sorted_keys[0] + sorted_keys[1]).encode("utf-8")

    MODULUS = 100_000  # 5-digit groups (00000..99999)
    BYTES_PER_GROUP = 4  # 32-bit window for low rejection rate
    # Pre-compute the largest multiple of MODULUS that fits in a 32-bit uint.
    MAX_ACCEPTED = (2**32 // MODULUS) * MODULUS  # = 4_294_900_000

    groups: list[str] = []
    counter = 0
    # Hash chain: H(data || counter) produces 32 bytes per iteration,
    # yielding 8 candidate 4-byte windows per hash (32/4 = 8).
    while len(groups) < 12:
        h = hashlib.sha256(data + counter.to_bytes(4, "big")).digest()
        for i in range(0, 32, BYTES_PER_GROUP):
            val = int.from_bytes(h[i : i + BYTES_PER_GROUP], "big")
            if val < MAX_ACCEPTED:
                groups.append(str(val % MODULUS).zfill(5))
                if len(groups) == 12:
                    break
        counter += 1
        # Defensive bound: ~10 rejections per group is astronomically unlikely
        # (probability ~ (10^-4)^12 = 10^-48). Cap at 1000 iterations.
        if counter > 1000:
            # Fall back to biased sampling (only triggers if the hash function
            # is broken; should never happen in practice).
            while len(groups) < 12:
                h = hashlib.sha256(data + counter.to_bytes(4, "big")).digest()
                for i in range(0, 32, BYTES_PER_GROUP):
                    val = int.from_bytes(h[i : i + BYTES_PER_GROUP], "big")
                    groups.append(str(val % MODULUS).zfill(5))
                    if len(groups) == 12:
                        break
                counter += 1
            break

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


def encrypt_message(
    message_key: bytes,
    plaintext: str,
    role: str,
    seq_num: int,
    session_id: str,
) -> dict:
    """
    Encrypts a message (v1 format) with length prefix and padding.
    """
    padded_data = pad_plaintext(plaintext)
    iv = os.urandom(12)
    aad = construct_aad(role, seq_num, session_id, 2)
    aesgcm = AESGCM(message_key)
    ciphertext = aesgcm.encrypt(iv, padded_data, aad)
    return {
        "iv": base64.b64encode(iv).decode("utf-8"),
        "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
    }


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
    my_private_key_bytes: bytes | None = None,
    peer_public_key_bytes: bytes | None = None,
    payload: dict | None = None,
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
            my_private_key_bytes or b"",
            peer_public_key_bytes or b"",
        )
    else:
        # Fallback to old v1 decryption (no Double Ratchet payload).
        iv = base64.b64decode(iv_b64)
        ciphertext = base64.b64decode(ct_b64)
        aesgcm = AESGCM(key_or_session)

        # Audit fix ANO-SEC-017 (C5): the previous code silently fell back
        # to the v1 AAD format when v2 decryption failed. This is a
        # downgrade attack vector -- an attacker who can forge a v1-AAD
        # ciphertext could force the recipient to accept messages without
        # the session-binding protection of the v2 AAD (which includes a
        # truncated session_id hash + protocol version byte). The fallback
        # is now REMOVED: we attempt only v2 AAD decryption, and raise on
        # any failure. Legacy v1 messages will be rejected; callers that
        # legitimately need to decrypt historical v1 messages must
        # explicitly construct a v1 AAD and call aesgcm.decrypt directly.
        aad = construct_aad(role, seq_num, session_id, 2)
        decrypted = aesgcm.decrypt(iv, ciphertext, aad)

        text_len = struct.unpack(">I", decrypted[:4])[0]
        if text_len > len(decrypted) - 4:
            raise ValueError("Decrypted length header exceeds message bounds.")
        return decrypted[4 : 4 + text_len].decode("utf-8")
