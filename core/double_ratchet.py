import base64
import json
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from core import pq_kem as _pq  # graceful fallback if liboqs absent


def _pq_combine(x25519_secret: bytes, kem_secret: bytes) -> bytes:
    """
    Combines X25519 and ML-KEM-768 shared secrets into a single 32-byte value
    via HKDF-SHA256. This is the hybrid KDF step (matching the NIST SP 800-227
    KEM/KDF hybrid construction):
        combined = HKDF(IKM = x25519_secret || kem_secret,
                        info = "AnonyMus-DR-Hybrid", salt = 0x00*32)
    """
    ikm = x25519_secret + kem_secret
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'\x00' * 32,
        info=b"AnonyMus-DR-Hybrid"
    )
    return hkdf.derive(ikm)


class DoubleRatchetSession:
    def __init__(self):
        self.dh_private = None
        self.dh_remote = None
        self.root_key = None
        self.sending_chain_key = None
        self.receiving_chain_key = None
        self.seq_send = 0
        self.seq_recv = 0
        self.prev_chain_length = 0
        self.skipped_message_keys = {}  # { "peer_dh_b64_seq": "key_hex" }

    @classmethod
    def init_alice(cls, shared_secret: bytes, peer_dh_pub_bytes: bytes):
        session = cls()
        session.dh_private = x25519.X25519PrivateKey.generate()
        session.dh_remote = x25519.X25519PublicKey.from_public_bytes(peer_dh_pub_bytes)
        
        # Initial root ratchet step
        dh_out = session.dh_private.exchange(session.dh_remote)
        
        rk_hkdf = HKDF(algorithm=hashes.SHA256(), length=64, salt=shared_secret, info=b"AnonyMus-DR-RootRatchet")
        derived = rk_hkdf.derive(dh_out)
        session.root_key = derived[:32]
        session.sending_chain_key = derived[32:]
        session.receiving_chain_key = None
        return session

    @classmethod
    def init_bob(cls, shared_secret: bytes, my_dh_priv_bytes: bytes):
        session = cls()
        session.dh_private = x25519.X25519PrivateKey.from_private_bytes(my_dh_priv_bytes)
        session.dh_remote = None
        session.root_key = shared_secret
        session.sending_chain_key = None
        session.receiving_chain_key = None
        return session

    # ------------------------------------------------------------------
    # PQ Hybrid factories (X25519 + ML-KEM-768)
    # ------------------------------------------------------------------

    @classmethod
    def init_alice_pq(cls, shared_secret: bytes, peer_dh_pub_bytes: bytes,
                      peer_kem_pub_bytes: bytes) -> 'DoubleRatchetSession':
        """
        Alice role with PQ hybrid: encapsulates an ML-KEM-768 shared secret
        against Bob's KEM public key, then combines X25519 + KEM secrets via HKDF.

        Falls back to X25519-only if liboqs is unavailable.

        Returns the session and the KEM ciphertext (to be sent to Bob).
        The ciphertext is stored on the session as ``kem_ciphertext_b64``.
        """
        result = _pq.encapsulate(peer_kem_pub_bytes)
        if result is not None:
            kem_ciphertext, kem_secret = result
            combined = _pq_combine(shared_secret, kem_secret)
        else:
            kem_ciphertext = None
            combined = shared_secret

        session = cls.init_alice(combined, peer_dh_pub_bytes)
        session.kem_ciphertext_b64 = (
            base64.b64encode(kem_ciphertext).decode('utf-8') if kem_ciphertext else None
        )
        return session

    @classmethod
    def init_bob_pq(cls, shared_secret: bytes, my_dh_priv_bytes: bytes,
                    my_kem_priv_bytes: bytes, kem_ciphertext_bytes: bytes) -> 'DoubleRatchetSession':
        """
        Bob role with PQ hybrid: decapsulates the ML-KEM-768 shared secret
        from Alice's ciphertext, then combines X25519 + KEM secrets via HKDF.

        Falls back to X25519-only if liboqs is unavailable or ciphertext is None.
        """
        if my_kem_priv_bytes and kem_ciphertext_bytes and _pq.is_available():
            kem_secret = _pq.decapsulate(kem_ciphertext_bytes, my_kem_priv_bytes)
            combined = _pq_combine(shared_secret, kem_secret) if kem_secret else shared_secret
        else:
            combined = shared_secret

        return cls.init_bob(combined, my_dh_priv_bytes)

    def to_json(self) -> str:
        priv_bytes = self.dh_private.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        ) if self.dh_private else None
        
        pub_remote_bytes = self.dh_remote.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        ) if self.dh_remote else None
        
        data = {
            "dh_private_b64": base64.b64encode(priv_bytes).decode('utf-8') if priv_bytes else None,
            "dh_remote_b64": base64.b64encode(pub_remote_bytes).decode('utf-8') if pub_remote_bytes else None,
            "root_key_hex": self.root_key.hex() if self.root_key else None,
            "sending_chain_key_hex": self.sending_chain_key.hex() if self.sending_chain_key else None,
            "receiving_chain_key_hex": self.receiving_chain_key.hex() if self.receiving_chain_key else None,
            "seq_send": self.seq_send,
            "seq_recv": self.seq_recv,
            "prev_chain_length": self.prev_chain_length,
            "skipped_message_keys": self.skipped_message_keys
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str):
        if not json_str:
            return None
        data = json.loads(json_str)
        session = cls()
        
        priv_b64 = data.get("dh_private_b64")
        if priv_b64:
            session.dh_private = x25519.X25519PrivateKey.from_private_bytes(base64.b64decode(priv_b64))
            
        pub_b64 = data.get("dh_remote_b64")
        if pub_b64:
            session.dh_remote = x25519.X25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
            
        rk_hex = data.get("root_key_hex")
        if rk_hex:
            session.root_key = bytes.fromhex(rk_hex)
            
        sck_hex = data.get("sending_chain_key_hex")
        if sck_hex:
            session.sending_chain_key = bytes.fromhex(sck_hex)
            
        rck_hex = data.get("receiving_chain_key_hex")
        if rck_hex:
            session.receiving_chain_key = bytes.fromhex(rck_hex)
            
        session.seq_send = data.get("seq_send", 0)
        session.seq_recv = data.get("seq_recv", 0)
        session.prev_chain_length = data.get("prev_chain_length", 0)
        session.skipped_message_keys = data.get("skipped_message_keys", {})
        return session

    def encrypt(self) -> tuple:
        """
        Derives message key and increments sending sequence number.
        Returns:
            (message_key: bytes, my_dh_public_bytes: bytes, seq: int, prev_chain_len: int)
        """
        hkdf = HKDF(algorithm=hashes.SHA256(), length=64, salt=self.sending_chain_key, info=b"AnonyMus-DR-ChainRatchet")
        derived = hkdf.derive(b"\x00" * 32)
        message_key = derived[:32]
        self.sending_chain_key = derived[32:]
        
        my_pub_bytes = self.dh_private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        seq = self.seq_send
        self.seq_send += 1
        return message_key, my_pub_bytes, seq, self.prev_chain_length

    def decrypt(self, peer_dh_pub_bytes: bytes, seq: int, prev_chain_len: int) -> bytes:
        """
        Decrypts message, stepping DH ratchet if peer key changed.
        """
        peer_dh_b64 = base64.b64encode(peer_dh_pub_bytes).decode('utf-8')
        skip_key = f"{peer_dh_b64}_{seq}"
        
        if skip_key in self.skipped_message_keys:
            key_hex = self.skipped_message_keys.pop(skip_key)
            return bytes.fromhex(key_hex)
            
        peer_dh_pub = x25519.X25519PublicKey.from_public_bytes(peer_dh_pub_bytes)
        
        if not self.dh_remote or self.dh_remote.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        ) != peer_dh_pub_bytes:
            self._skip_messages(prev_chain_len)
            
            self.dh_remote = peer_dh_pub
            dh_out1 = self.dh_private.exchange(self.dh_remote)
            
            rk_hkdf1 = HKDF(algorithm=hashes.SHA256(), length=64, salt=self.root_key, info=b"AnonyMus-DR-RootRatchet")
            derived1 = rk_hkdf1.derive(dh_out1)
            self.root_key = derived1[:32]
            self.receiving_chain_key = derived1[32:]
            
            self.dh_private = x25519.X25519PrivateKey.generate()
            dh_out2 = self.dh_private.exchange(self.dh_remote)
            
            rk_hkdf2 = HKDF(algorithm=hashes.SHA256(), length=64, salt=self.root_key, info=b"AnonyMus-DR-RootRatchet")
            derived2 = rk_hkdf2.derive(dh_out2)
            self.root_key = derived2[:32]
            self.sending_chain_key = derived2[32:]
            
            self.prev_chain_length = self.seq_send
            self.seq_send = 0
            self.seq_recv = 0
            
        self._skip_messages(seq)
        
        hkdf = HKDF(algorithm=hashes.SHA256(), length=64, salt=self.receiving_chain_key, info=b"AnonyMus-DR-ChainRatchet")
        derived = hkdf.derive(b"\x00" * 32)
        message_key = derived[:32]
        self.receiving_chain_key = derived[32:]
        self.seq_recv += 1
        
        return message_key

    def _skip_messages(self, until_seq: int):
        if not self.receiving_chain_key:
            return
        if self.seq_recv + 100 < until_seq:
            raise ValueError("Too many skipped messages, refusing to ratchet.")
            
        while self.seq_recv < until_seq:
            hkdf = HKDF(algorithm=hashes.SHA256(), length=64, salt=self.receiving_chain_key, info=b"AnonyMus-DR-ChainRatchet")
            derived = hkdf.derive(b"\x00" * 32)
            msg_key = derived[:32]
            self.receiving_chain_key = derived[32:]
            
            peer_pub_bytes = self.dh_remote.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            peer_b64 = base64.b64encode(peer_pub_bytes).decode('utf-8')
            skip_key = f"{peer_b64}_{self.seq_recv}"
            self.skipped_message_keys[skip_key] = msg_key.hex()
            self.seq_recv += 1
