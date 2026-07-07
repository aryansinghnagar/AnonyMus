import unittest
import base64
import struct
from core import protocol
from core.double_ratchet import DoubleRatchetSession
from core.queue_cryptobox import QueueCryptobox


class TestCryptographicProtocol(unittest.TestCase):

    def test_key_generation_and_export_import(self):
        """X25519 keys export as 32-byte raw values (not uncompressed P-256 points)."""
        priv, pub = protocol.generate_key_pair()
        exported = protocol.export_public_key(pub)

        # Verify it is a valid base64 string that decodes to exactly 32 bytes
        decoded = base64.b64decode(exported)
        self.assertEqual(len(decoded), 32, "X25519 public key must be exactly 32 bytes")

        # Re-import key and re-export — must be identical
        imported_pub = protocol.import_public_key(exported)
        re_exported = protocol.export_public_key(imported_pub)
        self.assertEqual(exported, re_exported)

    def test_x25519_dh_shared_secret_symmetry(self):
        """Both sides must derive the same shared secret via X25519 DH exchange."""
        alice_priv, alice_pub = protocol.generate_key_pair()
        bob_priv, bob_pub = protocol.generate_key_pair()

        alice_secret = protocol.derive_shared_secret(alice_priv, bob_pub)
        bob_secret = protocol.derive_shared_secret(bob_priv, alice_pub)

        self.assertEqual(alice_secret, bob_secret, "X25519 DH shared secret must be symmetric")
        self.assertEqual(len(alice_secret), 32, "Shared secret must be 32 bytes")

    def test_double_ratchet_encrypt_decrypt_roundtrip(self):
        """Full Double Ratchet + NaCl Cryptobox round-trip between Alice and Bob."""
        # Key generation
        alice_priv, alice_pub = protocol.generate_key_pair()
        bob_priv, bob_pub = protocol.generate_key_pair()

        alice_pub_b64 = protocol.export_public_key(alice_pub)
        bob_pub_b64 = protocol.export_public_key(bob_pub)

        shared_secret = protocol.derive_shared_secret(alice_priv, bob_pub)

        # Raw private key bytes for NaCl box (last 32 bytes of DER-encoded private key)
        from cryptography.hazmat.primitives import serialization
        alice_priv_der = alice_priv.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        bob_priv_der = bob_priv.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        alice_pub_raw = base64.b64decode(alice_pub_b64)
        bob_pub_raw = base64.b64decode(bob_pub_b64)

        # Initialize DR sessions
        alice_session = DoubleRatchetSession.init_alice(shared_secret, bob_pub_raw)
        bob_session = DoubleRatchetSession.init_bob(shared_secret, bob_priv_der)

        session_id = "test-session-abc"
        plaintext = "Hello from Alice to Bob via Double Ratchet!"

        # Alice encrypts
        payload = protocol.encrypt_message_v2(
            alice_session, plaintext, "A", session_id,
            alice_priv_der, bob_pub_raw
        )
        self.assertIn("nacl_ciphertext", payload)
        self.assertIn("nacl_nonce", payload)
        self.assertIn("dr_dh_public", payload)
        self.assertIn("dr_seq", payload)
        self.assertIn("dr_pn", payload)

        # Bob decrypts
        decrypted = protocol.decrypt_message_v2(
            bob_session, payload, "A", session_id,
            bob_priv_der, alice_pub_raw
        )
        self.assertEqual(decrypted, plaintext)

    def test_double_ratchet_multi_message(self):
        """Verify the ratchet advances correctly across multiple messages."""
        alice_priv, alice_pub = protocol.generate_key_pair()
        bob_priv, bob_pub = protocol.generate_key_pair()

        from cryptography.hazmat.primitives import serialization
        alice_priv_raw = alice_priv.private_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        bob_priv_raw = bob_priv.private_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        alice_pub_raw = base64.b64decode(protocol.export_public_key(alice_pub))
        bob_pub_raw = base64.b64decode(protocol.export_public_key(bob_pub))

        shared_secret = protocol.derive_shared_secret(alice_priv, bob_pub)
        alice_session = DoubleRatchetSession.init_alice(shared_secret, bob_pub_raw)
        bob_session = DoubleRatchetSession.init_bob(shared_secret, bob_priv_raw)

        messages = ["Message 1", "Message 2", "Message 3"]
        for i, msg in enumerate(messages):
            payload = protocol.encrypt_message_v2(
                alice_session, msg, "A", f"sess-{i}",
                alice_priv_raw, bob_pub_raw
            )
            decrypted = protocol.decrypt_message_v2(
                bob_session, payload, "A", f"sess-{i}",
                bob_priv_raw, alice_pub_raw
            )
            self.assertEqual(decrypted, msg)

    def test_safety_number_computation(self):
        pub1 = "AlicePublicKeyBase64PlaceholderStringHere="
        pub2 = "BobPublicKeyBase64PlaceholderStringHere="

        num1 = protocol.compute_safety_number(pub1, pub2)
        num2 = protocol.compute_safety_number(pub2, pub1)

        # Order independence
        self.assertEqual(num1, num2)

        # Format check: 12 groups of 5 decimal digits separated by spaces
        groups = num1.split(" ")
        self.assertEqual(len(groups), 12, f"Expected 12 groups, got: {num1}")
        for group in groups:
            self.assertEqual(len(group), 5, f"Expected 5-digit group, got: {group}")
            self.assertTrue(group.isdigit(), f"Expected all digits, got: {group}")

    def test_padding_structure(self):
        text = "Hello world! Test message."
        padded = protocol.pad_plaintext(text)

        # Length check
        self.assertEqual(len(padded), protocol.PADDED_SIZE)

        # Extraction
        extracted_len = struct.unpack('>I', padded[:4])[0]
        self.assertEqual(extracted_len, len(text))

        extracted_text = padded[4:4+extracted_len].decode('utf-8')
        self.assertEqual(extracted_text, text)

    def test_large_message_padding(self):
        # Message longer than PADDED_SIZE
        large_text = "A" * (protocol.PADDED_SIZE + 100)
        padded = protocol.pad_plaintext(large_text)

        self.assertEqual(len(padded), protocol.PADDED_SIZE * 2)

    def test_nacl_cryptobox_tamper_detection(self):
        """NaCl box must reject tampered ciphertexts."""
        alice_priv, alice_pub = protocol.generate_key_pair()
        bob_priv, bob_pub = protocol.generate_key_pair()

        from cryptography.hazmat.primitives import serialization
        alice_priv_raw = alice_priv.private_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        bob_priv_raw = bob_priv.private_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        alice_pub_raw = base64.b64decode(protocol.export_public_key(alice_pub))
        bob_pub_raw = base64.b64decode(protocol.export_public_key(bob_pub))

        plaintext = b"Secret message for NaCl box test"
        box_ct, box_nonce = QueueCryptobox.encrypt(plaintext, alice_priv_raw, bob_pub_raw)

        # Tamper the ciphertext
        tampered = bytearray(box_ct)
        tampered[0] ^= 0xFF
        with self.assertRaises(Exception):
            QueueCryptobox.decrypt(bytes(tampered), box_nonce, alice_pub_raw, bob_priv_raw)


# ---------------------------------------------------------------------------
# PQ KEM Tests (skipped if liboqs native library is not installed)
# ---------------------------------------------------------------------------

import os
os.environ.setdefault("ANONYMUS_PQ_DISABLE", "1")  # Suppress cmake auto-installer during tests
from core import pq_kem

_PQ_AVAILABLE = pq_kem.is_available()


@unittest.skipIf(not _PQ_AVAILABLE, "liboqs not installed — skipping PQ tests (install cmake + run: pip install liboqs-python)")
class TestPQKEM(unittest.TestCase):

    def test_ml_kem_768_keypair_sizes(self):
        """ML-KEM-768 key pair must have canonical sizes: 1184-byte pk, 2400-byte sk."""
        result = pq_kem.generate_ml_kem_keypair()
        self.assertIsNotNone(result, "generate_ml_kem_keypair returned None")
        pk, sk = result
        self.assertEqual(len(pk), 1184, f"ML-KEM-768 public key must be 1184 bytes, got {len(pk)}")
        self.assertEqual(len(sk), 2400, f"ML-KEM-768 private key must be 2400 bytes, got {len(sk)}")

    def test_ml_kem_768_encapsulate_sizes(self):
        """Encapsulation must produce a 1088-byte ciphertext and 32-byte shared secret."""
        pk, sk = pq_kem.generate_ml_kem_keypair()
        result = pq_kem.encapsulate(pk)
        self.assertIsNotNone(result, "encapsulate returned None")
        ct, ss = result
        self.assertEqual(len(ct), 1088, f"ML-KEM-768 ciphertext must be 1088 bytes, got {len(ct)}")
        self.assertEqual(len(ss), 32, f"ML-KEM-768 shared secret must be 32 bytes, got {len(ss)}")

    def test_ml_kem_768_roundtrip(self):
        """Encapsulated and decapsulated shared secrets must be equal (Alice == Bob)."""
        pk, sk = pq_kem.generate_ml_kem_keypair()
        ct, ss_alice = pq_kem.encapsulate(pk)
        ss_bob = pq_kem.decapsulate(ct, sk)
        self.assertIsNotNone(ss_bob, "decapsulate returned None")
        self.assertEqual(ss_alice, ss_bob, "ML-KEM-768 shared secrets must match")

    def test_ml_kem_768_wrong_key_decapsulation(self):
        """Decapsulating with the wrong private key must return a different shared secret."""
        pk1, sk1 = pq_kem.generate_ml_kem_keypair()
        pk2, sk2 = pq_kem.generate_ml_kem_keypair()
        ct, ss_alice = pq_kem.encapsulate(pk1)
        # Decapsulate with wrong key — ML-KEM spec says this returns pseudorandom (not an exception)
        ss_wrong = pq_kem.decapsulate(ct, sk2)
        # Must not equal the correct secret
        self.assertNotEqual(ss_alice, ss_wrong, "Wrong-key decapsulation must not produce the correct secret")

    def test_pq_combine_deterministic(self):
        """_pq_combine must be a deterministic pure function."""
        from core.double_ratchet import _pq_combine
        x25519_secret = bytes(range(32))
        kem_secret = bytes(range(32, 64))
        result1 = _pq_combine(x25519_secret, kem_secret)
        result2 = _pq_combine(x25519_secret, kem_secret)
        self.assertEqual(result1, result2, "_pq_combine must be deterministic")
        self.assertEqual(len(result1), 32, "_pq_combine must produce 32 bytes")

    def test_pq_combine_different_from_x25519_only(self):
        """Combined secret must differ from the X25519-only secret."""
        from core.double_ratchet import _pq_combine
        x25519_secret = bytes(range(32))
        kem_secret = bytes(range(32, 64))
        combined = _pq_combine(x25519_secret, kem_secret)
        self.assertNotEqual(combined, x25519_secret, "Hybrid secret must differ from X25519-only secret")


@unittest.skipIf(not _PQ_AVAILABLE, "liboqs not installed — skipping hybrid DR tests")
class TestHybridDoubleRatchet(unittest.TestCase):

    def test_hybrid_dr_roundtrip_pq(self):
        """Full Double Ratchet encrypt/decrypt with PQ hybrid KDF must roundtrip."""
        from core.cryptography_helpers import derive_shared_secret_bytes  # use raw DH
        from cryptography.hazmat.primitives.asymmetric import x25519

        # Generate X25519 + ML-KEM-768 keys for both parties
        alice_dh_priv_key = x25519.X25519PrivateKey.generate()
        bob_dh_priv_key = x25519.X25519PrivateKey.generate()

        alice_dh_pub_bytes = alice_dh_priv_key.public_key().public_bytes(
            encoding=__import__('cryptography').hazmat.primitives.serialization.Encoding.Raw,
            format=__import__('cryptography').hazmat.primitives.serialization.PublicFormat.Raw
        )
        bob_dh_pub_bytes = bob_dh_priv_key.public_key().public_bytes(
            encoding=__import__('cryptography').hazmat.primitives.serialization.Encoding.Raw,
            format=__import__('cryptography').hazmat.primitives.serialization.PublicFormat.Raw
        )
        bob_dh_priv_bytes = bob_dh_priv_key.private_bytes(
            encoding=__import__('cryptography').hazmat.primitives.serialization.Encoding.Raw,
            format=__import__('cryptography').hazmat.primitives.serialization.PrivateFormat.Raw,
            encryption_algorithm=__import__('cryptography').hazmat.primitives.serialization.NoEncryption()
        )

        # Generate ML-KEM-768 keys for Bob
        bob_kem_pk, bob_kem_sk = pq_kem.generate_ml_kem_keypair()

        # Shared X25519 base secret (from initial key exchange)
        shared_secret = alice_dh_priv_key.exchange(bob_dh_priv_key.public_key())

        # Alice: init with PQ hybrid → encapsulates KEM secret for Bob
        alice_session = DoubleRatchetSession.init_alice_pq(shared_secret, bob_dh_pub_bytes, bob_kem_pk)
        self.assertIsNotNone(alice_session.kem_ciphertext_b64, "Alice must produce a KEM ciphertext")

        kem_ciphertext = base64.b64decode(alice_session.kem_ciphertext_b64)

        # Bob: init with PQ hybrid → decapsulates KEM secret
        bob_session = DoubleRatchetSession.init_bob_pq(shared_secret, bob_dh_priv_bytes, bob_kem_sk, kem_ciphertext)

        # Alice encrypts, Bob decrypts — multiple messages
        for i in range(3):
            msg_key_a, pub_a, seq_a, pn_a = alice_session.encrypt()
            msg_key_b = bob_session.decrypt(pub_a, seq_a, pn_a)
            self.assertEqual(msg_key_a, msg_key_b, f"Message keys must match for send #{i}")

    def test_hybrid_dr_fallback_without_pq(self):
        """init_alice_pq / init_bob_pq must fall back gracefully when liboqs is absent."""
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives import serialization

        # Use placeholder KEM keys — the test overrides _pq.is_available to return False
        import core.pq_kem as _pq_mod
        original_available = _pq_mod.is_available

        try:
            _pq_mod.is_available = lambda: False

            alice_priv = x25519.X25519PrivateKey.generate()
            bob_priv = x25519.X25519PrivateKey.generate()
            bob_pub_bytes = bob_priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
            )
            bob_priv_bytes = bob_priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            shared_secret = alice_priv.exchange(bob_priv.public_key())

            # Fake KEM key (256 bytes of zeros — not valid, but fallback ignores it)
            fake_kem_pk = b'\x00' * 1184
            alice_session = DoubleRatchetSession.init_alice_pq(shared_secret, bob_pub_bytes, fake_kem_pk)
            # When liboqs absent, kem_ciphertext_b64 must be None
            self.assertIsNone(alice_session.kem_ciphertext_b64, "Fallback mode must produce no KEM ciphertext")

            bob_session = DoubleRatchetSession.init_bob_pq(shared_secret, bob_priv_bytes, b'', b'')
            # Both should work as plain X25519-only DR
            msg_key_a, pub_a, seq_a, pn_a = alice_session.encrypt()
            msg_key_b = bob_session.decrypt(pub_a, seq_a, pn_a)
            self.assertEqual(msg_key_a, msg_key_b, "Fallback DR must still produce matching keys")
        finally:
            _pq_mod.is_available = original_available


if __name__ == '__main__':
    unittest.main()
