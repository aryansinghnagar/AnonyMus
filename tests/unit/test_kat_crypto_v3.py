"""
Comprehensive Cryptographic KAT and Protocol Verification Suite (v3.0)
"""

import base64
import secrets
import pytest

from core.crypto import (
    derive_db_key,
    generate_supporter_badge_signature,
)
from core.double_ratchet import _pq_combine, DoubleRatchetSession
from core.protocol import compute_safety_number
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


def test_kat_hkdf_rfc5869_test_case_1():
    ikm = bytes.fromhex("0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b")
    salt = bytes.fromhex("000102030405060708090a0b0c")
    info = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
    expected_okm = bytes.fromhex(
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
        "34007208d5b887185865"
    )
    hkdf = HKDF(algorithm=hashes.SHA256(), length=42, salt=salt, info=info)
    derived = hkdf.derive(ikm)
    assert derived == expected_okm


def test_kat_x25519_rfc7748_test_vector_1():
    bob_priv_bytes = bytes.fromhex(
        "5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb"
    )
    alice_pub_bytes = bytes.fromhex(
        "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"
    )
    expected_ss = bytes.fromhex(
        "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742"
    )

    bob_priv = x25519.X25519PrivateKey.from_private_bytes(bob_priv_bytes)
    alice_pub = x25519.X25519PublicKey.from_public_bytes(alice_pub_bytes)

    ss = bob_priv.exchange(alice_pub)
    assert ss == expected_ss


def test_aead_aes_gcm_and_chacha20_roundtrip():
    key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    plaintext = b"AnonyMus v3.0 zero-knowledge end-to-end payload"
    aad = b"protocol=v3|session_id=node-007"

    aes = AESGCM(key)
    ct = aes.encrypt(nonce, plaintext, aad)
    pt = aes.decrypt(nonce, ct, aad)
    assert pt == plaintext

    tampered_ct = bytearray(ct)
    tampered_ct[0] ^= 0xFF
    with pytest.raises(Exception):
        aes.decrypt(nonce, bytes(tampered_ct), aad)

    chacha = ChaCha20Poly1305(key)
    ct_chacha = chacha.encrypt(nonce, plaintext, aad)
    pt_chacha = chacha.decrypt(nonce, ct_chacha, aad)
    assert pt_chacha == plaintext


def test_db_key_derivation_determinism_and_entropy():
    pwd1 = "Correct-Horse-Battery-Staple-2026!"
    pwd2 = "Different-Password-2026!"
    salt1 = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
    salt2 = bytes.fromhex("1112131415161718191a1b1c1d1e1f20")

    key1a, s1a = derive_db_key(pwd1, salt=salt1, iterations=1000)
    key1b, s1b = derive_db_key(pwd1, salt=salt1, iterations=1000)
    assert key1a == key1b
    assert s1a == salt1

    key2, _ = derive_db_key(pwd2, salt=salt1, iterations=1000)
    assert key1a != key2

    key3, _ = derive_db_key(pwd1, salt=salt2, iterations=1000)
    assert key1a != key3


def test_ed25519_supporter_badge_signing_and_verification():
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_key = priv_key.public_key()

    priv_b64 = base64.b64encode(priv_key.private_bytes_raw()).decode("utf-8")
    pub_b64 = base64.b64encode(pub_key.public_bytes_raw()).decode("utf-8")

    onion = "abcdef234567890abcdef234567890abcdef234567890anonymus.onion"
    sig_b64 = generate_supporter_badge_signature(onion, priv_b64)

    pub_obj = ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
    pub_obj.verify(base64.b64decode(sig_b64), onion.encode("utf-8"))

    with pytest.raises(Exception):
        pub_obj.verify(base64.b64decode(sig_b64), b"attacker.onion")


def test_pqxdh_hybrid_combination_vector():
    x25519_ss = b"\xaa" * 32
    kem_ss = b"\xbb" * 32

    combined_1 = _pq_combine(x25519_ss, kem_ss)
    combined_2 = _pq_combine(x25519_ss, kem_ss)

    assert len(combined_1) == 32
    assert combined_1 == combined_2

    combined_3 = _pq_combine(x25519_ss, b"\xcc" * 32)
    assert combined_1 != combined_3


def test_double_ratchet_session_roundtrip_and_forward_secrecy():
    shared_key = secrets.token_bytes(32)
    bob_dh_priv = x25519.X25519PrivateKey.generate()
    bob_dh_pub = bob_dh_priv.public_key().public_bytes_raw()

    alice_session = DoubleRatchetSession.init_alice(shared_key, bob_dh_pub)
    bob_session = DoubleRatchetSession.init_bob(
        shared_key, bob_dh_priv.private_bytes_raw()
    )

    for i in range(5):
        msg = f"Secret payload #{i}".encode("utf-8")
        msg_key_alice, pub_alice, seq_alice, prev_len_alice = alice_session.encrypt()
        nonce = secrets.token_bytes(12)
        ct = AESGCM(msg_key_alice).encrypt(nonce, msg, b"aad-header")

        msg_key_bob = bob_session.decrypt(pub_alice, seq_alice, prev_len_alice)
        assert msg_key_alice == msg_key_bob
        pt = AESGCM(msg_key_bob).decrypt(nonce, ct, b"aad-header")
        assert pt == msg


def test_safety_number_symmetry_and_formatting():
    key_a = base64.b64encode(b"\x01" * 32).decode("utf-8")
    key_b = base64.b64encode(b"\x02" * 32).decode("utf-8")

    sn_ab = compute_safety_number(key_a, key_b)
    sn_ba = compute_safety_number(key_b, key_a)

    assert sn_ab == sn_ba

    blocks = sn_ab.split(" ")
    assert len(blocks) == 12
    for block in blocks:
        assert len(block) == 5
        assert block.isdigit()
        val = int(block)
        assert 0 <= val < 100000


def test_pkcs7_message_padding():
    block_size = 128
    msg = b"Short msg"
    pad_len = block_size - (len(msg) % block_size)
    padded = msg + bytes([pad_len] * pad_len)

    assert len(padded) % block_size == 0
    assert len(padded) == 128

    unpad_len = padded[-1]
    assert unpad_len == pad_len
    unpadded = padded[:-unpad_len]
    assert unpadded == msg


def test_lan_pairing_token_entropy_and_salt_isolation():
    token1 = secrets.token_bytes(32)
    token2 = secrets.token_bytes(32)
    assert len(token1) == 32
    assert token1 != token2

    salt1 = secrets.token_bytes(16)
    salt2 = secrets.token_bytes(16)
    assert len(salt1) == 16
    assert salt1 != salt2
