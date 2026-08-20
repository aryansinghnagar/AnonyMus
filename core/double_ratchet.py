import base64
import json
import os
import threading
from collections import OrderedDict
from typing import Callable, Awaitable, TYPE_CHECKING

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core import pq_kem as _pq  # graceful fallback if liboqs absent

if TYPE_CHECKING:
    # Forward-reference only — avoids the circular reference at runtime
    # because DRSessionCache is defined BEFORE DoubleRatchetSession.
    pass


# ============================================================================
# Perf fix P3: LRU cache for recently-used Double Ratchet sessions.
# ============================================================================
#
# The DR session state is stored in the database (Contact.dr_state column)
# and (de)serialised via DoubleRatchetSession.to_json / from_json on every
# incoming/outgoing message. This adds ~5-20 ms of JSON parsing + key
# reconstruction per message, which dominates the message-processing budget
# for high-frequency conversation.
#
# The LRU cache below holds the most recently used sessions in memory keyed
# by peer onion address, eliminating the DB lookup + JSON parse on cache hit.
# Writes are still persisted back to the DB by the caller (via save_session)
# so a process restart does not lose session state.


class DRSessionCache:
    """Thread-safe LRU cache of Double Ratchet sessions keyed by peer onion.

    Perf fix P3: avoids a DB lookup + JSON parse on every message. Sessions
    that fall out of the cache are transparently re-loaded by the caller.
    """

    def __init__(self, capacity: int | None = None) -> None:
        if capacity is None:
            capacity = int(os.environ.get("ANONYMUS_DR_CACHE_SIZE", "50"))
        self.capacity = max(1, capacity)
        # Values are DoubleRatchetSession instances; typed as Any at the
        # OrderedDict level to avoid a forward-reference cycle (the class
        # is defined below this one).
        self._entries: "OrderedDict[str, object]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, peer_onion: str):
        with self._lock:
            session = self._entries.get(peer_onion)
            if session is not None:
                # Mark as most-recently-used.
                self._entries.move_to_end(peer_onion)
            return session

    def put(self, peer_onion: str, session: object) -> None:
        with self._lock:
            self._entries[peer_onion] = session
            self._entries.move_to_end(peer_onion)
            while len(self._entries) > self.capacity:
                # Pop least-recently-used entry.
                self._entries.popitem(last=False)

    def invalidate(self, peer_onion: str) -> None:
        with self._lock:
            self._entries.pop(peer_onion, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


# Module-level singleton. Importing modules can call ``dr_cache.get(...)`` /
# ``dr_cache.put(...)`` directly. Tests can call ``dr_cache.clear()`` between
# runs to avoid cross-test contamination.
dr_cache = DRSessionCache()


# ============================================================================
# Audit fix ANO-SEC-013 (B8): Sealed sender contact verification.
# ============================================================================
#
# Sealed sender (RFC 0014) allows a peer to send a message without revealing
# their identity in the envelope. The recipient decrypts the message and then
# *resolves* the sender's identity post-hoc by matching the ephemeral public
# key against known contacts. This is a useful anonymity feature, but in
# strict mode we want to reject sealed-sender messages from unknown / unverified
# contacts to mitigate spam and impersonation via fresh-identity abuse.
#
# The check is opt-in via the ``ANONYMUS_SEALED_SENDER_STRICT`` env var (or
# the ``sealed_sender_strict`` setting). When enabled, the recipient's
# message-ingestion pipeline calls ``verify_sealed_sender_known_contact``
# before processing the decrypted payload. If the sender is not a known AND
# verified contact, the message is dropped.


def sealed_sender_strict_mode_enabled() -> bool:
    """Return True if "verified contacts only" sealed-sender mode is enabled.

    Opt-in via ``ANONYMUS_SEALED_SENDER_STRICT=1`` env var. When enabled,
    sealed-sender messages from unknown or unverified contacts are rejected
    (audit fix ANO-SEC-013 / B8).
    """
    val = os.environ.get("ANONYMUS_SEALED_SENDER_STRICT", "0").strip().lower()
    return val in ("1", "true", "yes", "on")


async def verify_sealed_sender_known_contact(
    sender_onion: str,
    *,
    lookup_contact: Callable[[str], Awaitable[object | None]] | None = None,
) -> bool:
    """Verify that ``sender_onion`` is a known, verified contact.

    Audit fix ANO-SEC-013 (B8): when strict sealed-sender mode is enabled,
    the message-ingestion pipeline calls this helper before accepting a
    sealed-sender payload. The caller passes a ``lookup_contact`` coroutine
    that returns a Contact ORM object (or None) for the given onion address.

    Returns True iff:
      - strict mode is DISABLED (default -- backward compatible), OR
      - strict mode is enabled AND the lookup returns a Contact whose
        ``verified`` attribute is truthy.

    Returns False (reject) when strict mode is enabled and the lookup returns
    None or an unverified contact. The caller should drop the message and
    log at INFO level (not WARNING -- this is the normal spam path).
    """
    if not sealed_sender_strict_mode_enabled():
        return True  # opt-in feature is OFF; accept all sealed-sender messages
    if lookup_contact is None:
        # No lookup provided -- fail closed in strict mode.
        return False
    try:
        contact = await lookup_contact(sender_onion)
    except Exception:
        return False
    if contact is None:
        return False
    # Contact objects may use either a `verified` boolean or a
    # `status` string ("accepted" / "verified"). Accept either.
    verified_attr = getattr(contact, "verified", None)
    if verified_attr is True:
        return True
    status_attr = getattr(contact, "status", None)
    return status_attr in ("verified", "accepted")


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
        salt=b"\x00" * 32,
        info=b"AnonyMus-DR-Hybrid",
    )
    return hkdf.derive(ikm)


class DoubleRatchetSession:
    def __init__(self):
        self.dh_private: x25519.X25519PrivateKey | None = None
        self.dh_remote: x25519.X25519PublicKey | None = None
        self.root_key: bytes | None = None
        self.sending_chain_key: bytes | None = None
        self.receiving_chain_key: bytes | None = None
        self.seq_send = 0
        self.seq_recv = 0
        self.prev_chain_length = 0
        self.skipped_message_keys: dict[
            str, str
        ] = {}  # { "peer_dh_b64_seq": "key_hex" }
        self.kem_ciphertext_b64: str | None = None

    @classmethod
    def init_alice(cls, shared_secret: bytes, peer_dh_pub_bytes: bytes):
        session = cls()
        session.dh_private = x25519.X25519PrivateKey.generate()
        session.dh_remote = x25519.X25519PublicKey.from_public_bytes(peer_dh_pub_bytes)

        # Initial root ratchet step
        dh_out = session.dh_private.exchange(session.dh_remote)

        rk_hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=shared_secret,
            info=b"AnonyMus-DR-RootRatchet",
        )
        derived = rk_hkdf.derive(dh_out)
        session.root_key = derived[:32]
        session.sending_chain_key = derived[32:]
        session.receiving_chain_key = None
        return session

    @classmethod
    def init_bob(cls, shared_secret: bytes, my_dh_priv_bytes: bytes):
        session = cls()
        session.dh_private = x25519.X25519PrivateKey.from_private_bytes(
            my_dh_priv_bytes
        )
        session.dh_remote = None
        session.root_key = shared_secret
        session.sending_chain_key = None
        session.receiving_chain_key = None
        return session

    # ------------------------------------------------------------------
    # PQ Hybrid factories (X25519 + ML-KEM-768)
    # ------------------------------------------------------------------

    @classmethod
    def init_alice_pq(
        cls, shared_secret: bytes, peer_dh_pub_bytes: bytes, peer_kem_pub_bytes: bytes
    ) -> "DoubleRatchetSession":
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
            base64.b64encode(kem_ciphertext).decode("utf-8") if kem_ciphertext else None
        )
        return session

    @classmethod
    def init_bob_pq(
        cls,
        shared_secret: bytes,
        my_dh_priv_bytes: bytes,
        my_kem_priv_bytes: bytes,
        kem_ciphertext_bytes: bytes,
    ) -> "DoubleRatchetSession":
        """
        Bob role with PQ hybrid: decapsulates the ML-KEM-768 shared secret
        from Alice's ciphertext, then combines X25519 + KEM secrets via HKDF.

        Falls back to X25519-only if liboqs is unavailable or ciphertext is None.
        """
        if my_kem_priv_bytes and kem_ciphertext_bytes and _pq.is_available():
            kem_secret = _pq.decapsulate(kem_ciphertext_bytes, my_kem_priv_bytes)
            combined = (
                _pq_combine(shared_secret, kem_secret) if kem_secret else shared_secret
            )
        else:
            combined = shared_secret

        return cls.init_bob(combined, my_dh_priv_bytes)

    def to_json(self) -> str:
        priv_bytes = (
            self.dh_private.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            if self.dh_private
            else None
        )

        pub_remote_bytes = (
            self.dh_remote.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            if self.dh_remote
            else None
        )

        data = {
            "dh_private_b64": base64.b64encode(priv_bytes).decode("utf-8")
            if priv_bytes
            else None,
            "dh_remote_b64": base64.b64encode(pub_remote_bytes).decode("utf-8")
            if pub_remote_bytes
            else None,
            "root_key_hex": self.root_key.hex() if self.root_key else None,
            "sending_chain_key_hex": self.sending_chain_key.hex()
            if self.sending_chain_key
            else None,
            "receiving_chain_key_hex": self.receiving_chain_key.hex()
            if self.receiving_chain_key
            else None,
            "seq_send": self.seq_send,
            "seq_recv": self.seq_recv,
            "prev_chain_length": self.prev_chain_length,
            "skipped_message_keys": self.skipped_message_keys,
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
            session.dh_private = x25519.X25519PrivateKey.from_private_bytes(
                base64.b64decode(priv_b64)
            )

        pub_b64 = data.get("dh_remote_b64")
        if pub_b64:
            session.dh_remote = x25519.X25519PublicKey.from_public_bytes(
                base64.b64decode(pub_b64)
            )

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
        if self.dh_private is None or self.sending_chain_key is None:
            raise ValueError("Session keys not initialized")

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=self.sending_chain_key,
            info=b"AnonyMus-DR-ChainRatchet",
        )
        derived = hkdf.derive(b"\x00" * 32)
        message_key = derived[:32]
        self.sending_chain_key = derived[32:]

        my_pub_bytes = self.dh_private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )

        seq = self.seq_send
        self.seq_send += 1
        return message_key, my_pub_bytes, seq, self.prev_chain_length

    def decrypt(self, peer_dh_pub_bytes: bytes, seq: int, prev_chain_len: int) -> bytes:
        """
        Decrypts message, stepping DH ratchet if peer key changed.
        """
        peer_dh_b64 = base64.b64encode(peer_dh_pub_bytes).decode("utf-8")
        skip_key = f"{peer_dh_b64}_{seq}"

        if skip_key in self.skipped_message_keys:
            key_hex = self.skipped_message_keys.pop(skip_key)
            return bytes.fromhex(key_hex)

        peer_dh_pub = x25519.X25519PublicKey.from_public_bytes(peer_dh_pub_bytes)

        if (
            not self.dh_remote
            or self.dh_remote.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            != peer_dh_pub_bytes
        ):
            self._skip_messages(prev_chain_len)

            self.dh_remote = peer_dh_pub
            if self.dh_private is None or self.root_key is None:
                raise ValueError("Keys not initialized for ratchet step")
            dh_out1 = self.dh_private.exchange(self.dh_remote)

            rk_hkdf1 = HKDF(
                algorithm=hashes.SHA256(),
                length=64,
                salt=self.root_key,
                info=b"AnonyMus-DR-RootRatchet",
            )
            derived1 = rk_hkdf1.derive(dh_out1)
            self.root_key = derived1[:32]
            self.receiving_chain_key = derived1[32:]

            self.dh_private = x25519.X25519PrivateKey.generate()
            dh_out2 = self.dh_private.exchange(self.dh_remote)

            rk_hkdf2 = HKDF(
                algorithm=hashes.SHA256(),
                length=64,
                salt=self.root_key,
                info=b"AnonyMus-DR-RootRatchet",
            )
            derived2 = rk_hkdf2.derive(dh_out2)
            self.root_key = derived2[:32]
            self.sending_chain_key = derived2[32:]

            self.prev_chain_length = self.seq_send
            self.seq_send = 0
            self.seq_recv = 0

        self._skip_messages(seq)

        if self.receiving_chain_key is None:
            raise ValueError("Receiving chain key not initialized")

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=self.receiving_chain_key,
            info=b"AnonyMus-DR-ChainRatchet",
        )
        derived = hkdf.derive(b"\x00" * 32)
        message_key = derived[:32]
        self.receiving_chain_key = derived[32:]
        self.seq_recv += 1

        return message_key

    def _skip_messages(self, until_seq: int):
        if not self.receiving_chain_key or self.dh_remote is None:
            return
        if self.seq_recv + 100 < until_seq:
            raise ValueError("Too many skipped messages, refusing to ratchet.")

        while self.seq_recv < until_seq:
            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=64,
                salt=self.receiving_chain_key,
                info=b"AnonyMus-DR-ChainRatchet",
            )
            derived = hkdf.derive(b"\x00" * 32)
            msg_key = derived[:32]
            self.receiving_chain_key = derived[32:]

            peer_pub_bytes = self.dh_remote.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            peer_b64 = base64.b64encode(peer_pub_bytes).decode("utf-8")
            skip_key = f"{peer_b64}_{self.seq_recv}"
            self.skipped_message_keys[skip_key] = msg_key.hex()
            self.seq_recv += 1
