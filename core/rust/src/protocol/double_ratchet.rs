//! Signal Protocol Double Ratchet implementation.
//!
//! Implements the full Double Ratchet Algorithm as specified in:
//! https://signal.org/docs/specifications/doubleratchet/
//!
//! Provides forward secrecy and break-in recovery for all P2P sessions.
//! The SPQR extension (Stateful Post-Quantum Ratchet) is layered on top
//! using ML-KEM-768 for amortised post-quantum ratchet steps (see `pq_ratchet`).

use std::collections::HashMap;

use zeroize::{Zeroize, ZeroizeOnDrop};

use crate::crypto::{aead, hkdf, x25519};
use crate::{AnonymusError, Result};

// ── Constants ──────────────────────────────────────────────────────────────────

/// Maximum number of out-of-order messages to buffer per ratchet step.
const MAX_SKIP: u32 = 1000;
/// HKDF info strings (bound to domain so keys can't be cross-used).
const INFO_ROOT: &[u8] = b"AnonyMus v3 DR root";
const INFO_CHAIN: &[u8] = b"AnonyMus v3 DR chain";
const INFO_MSG: &[u8] = b"AnonyMus v3 DR msg";

// ── Key types (newtype wrappers to prevent accidental cross-use) ───────────────

/// 32-byte root key (fed into the root KDF on every DH ratchet step).
#[derive(Clone, Zeroize, ZeroizeOnDrop)]
pub struct RootKey(pub [u8; 32]);

/// 32-byte chain key (advanced on every message).
#[derive(Clone, Zeroize, ZeroizeOnDrop)]
pub struct ChainKey(pub [u8; 32]);

/// 32-byte message key (derived from the chain key, used once).
#[derive(Clone, Zeroize, ZeroizeOnDrop)]
pub struct MessageKey(pub [u8; 32]);

impl MessageKey {
    /// Derive a message key from a chain key using HKDF.
    fn from_chain(ck: &ChainKey) -> Result<(Self, ChainKey)> {
        // KDF_CK(ck) → (new_ck, mk)
        let output = hkdf::derive_64(&ck.0, None, INFO_CHAIN)?;
        let new_ck = ChainKey(output[..32].try_into().unwrap());
        let mk = MessageKey(output[32..].try_into().unwrap());
        Ok((mk, new_ck))
    }
}

// ── Header ─────────────────────────────────────────────────────────────────────

/// Double Ratchet message header (sent in the clear, authenticated via AEAD AAD).
#[derive(Debug, Clone)]
pub struct Header {
    /// Sender's current ratchet public key.
    pub dh_public: [u8; 32],
    /// Number of messages in the *previous* sending chain.
    pub pn: u32,
    /// Message number within the current sending chain.
    pub n: u32,
}

impl Header {
    /// Encode to 40 bytes: 32-byte DH key || 4-byte PN || 4-byte N (big-endian).
    pub fn encode(&self) -> [u8; 40] {
        let mut buf = [0u8; 40];
        buf[..32].copy_from_slice(&self.dh_public);
        buf[32..36].copy_from_slice(&self.pn.to_be_bytes());
        buf[36..40].copy_from_slice(&self.n.to_be_bytes());
        buf
    }

    /// Decode from 40 bytes.
    pub fn decode(bytes: &[u8; 40]) -> Self {
        let mut dh = [0u8; 32];
        dh.copy_from_slice(&bytes[..32]);
        let pn = u32::from_be_bytes(bytes[32..36].try_into().unwrap());
        let n = u32::from_be_bytes(bytes[36..40].try_into().unwrap());
        Self { dh_public: dh, pn, n }
    }
}

// ── Root KDF ───────────────────────────────────────────────────────────────────

/// KDF_RK(rk, dh_out) → (new_rk, ck)
/// Called on every DH ratchet step.
fn kdf_rk(rk: &RootKey, dh_output: &[u8; 32]) -> Result<(RootKey, ChainKey)> {
    let out = hkdf::derive_64(dh_output, Some(&rk.0), INFO_ROOT)?;
    Ok((
        RootKey(out[..32].try_into().unwrap()),
        ChainKey(out[32..].try_into().unwrap()),
    ))
}

// ── Skipped-message key cache ──────────────────────────────────────────────────

/// Key identifying a skipped message: sender DH key + message number.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct SkipKey {
    dh_public: [u8; 32],
    n: u32,
}

// ── Session State ──────────────────────────────────────────────────────────────

/// A full Double Ratchet session state.
///
/// Serialise with `to_bytes()` / restore with `from_bytes()` for persistence in
/// the encrypted SQLite store. All key material implements `ZeroizeOnDrop`.
#[derive(ZeroizeOnDrop)]
pub struct Session {
    /// Our current DH ratchet keypair.
    dh_self: x25519::StaticKeypair,
    /// Peer's current ratchet public key (None until first message received).
    #[zeroize(skip)]
    dh_remote: Option<[u8; 32]>,
    /// Current root key.
    rk: RootKey,
    /// Sending chain key (None until first send after ratchet step).
    cks: Option<ChainKey>,
    /// Receiving chain key (None until first ratchet step).
    ckr: Option<ChainKey>,
    /// Message counter in current sending chain.
    ns: u32,
    /// Message counter in current receiving chain.
    nr: u32,
    /// Message count at start of previous sending chain.
    pn: u32,
    /// Skipped message keys: (dh_public, n) → MessageKey.
    #[zeroize(skip)]
    skipped: HashMap<SkipKey, [u8; 32]>,
}

impl Session {
    /// Initialise a session for the **initiator** (Alice) using X3DH output.
    ///
    /// `shared_secret` is the 32-byte output of the X3DH key agreement.
    /// `bob_ratchet_public` is Bob's signed pre-key public component.
    pub fn init_sender(shared_secret: &[u8; 32], bob_ratchet_public: &[u8; 32]) -> Result<Self> {
        // Derive root key and sending chain key from the shared secret
        let rk_seed = hkdf::derive_32(shared_secret, None, INFO_ROOT)?;
        let initial_rk = RootKey(rk_seed);

        // Generate our ephemeral ratchet keypair
        let dh_self = x25519::StaticKeypair::generate();

        // First DH ratchet step
        let dh_out = dh_self.dh(bob_ratchet_public)?;
        let (rk, cks) = kdf_rk(&initial_rk, &dh_out)?;

        Ok(Self {
            dh_self,
            dh_remote: Some(*bob_ratchet_public),
            rk,
            cks: Some(cks),
            ckr: None,
            ns: 0,
            nr: 0,
            pn: 0,
            skipped: HashMap::new(),
        })
    }

    /// Initialise a session for the **responder** (Bob).
    ///
    /// `shared_secret` is the 32-byte X3DH output.
    /// `bob_ratchet_keypair_bytes` is the private key bytes of Bob's signed pre-key.
    pub fn init_receiver(
        shared_secret: &[u8; 32],
        bob_ratchet_private: [u8; 32],
    ) -> Result<Self> {
        let rk_seed = hkdf::derive_32(shared_secret, None, INFO_ROOT)?;
        let rk = RootKey(rk_seed);

        Ok(Self {
            dh_self: x25519::StaticKeypair::from_bytes(bob_ratchet_private),
            dh_remote: None,
            rk,
            cks: None,
            ckr: None,
            ns: 0,
            nr: 0,
            pn: 0,
            skipped: HashMap::new(),
        })
    }

    // ── Encrypt ────────────────────────────────────────────────────────────────

    /// Encrypt `plaintext` and return `(header_bytes, ciphertext)`.
    ///
    /// The header bytes serve as AAD for the AEAD tag so that the header cannot
    /// be modified without invalidating the ciphertext.
    pub fn encrypt(&mut self, plaintext: &[u8]) -> Result<([u8; 40], Vec<u8>)> {
        let cks = self
            .cks
            .as_ref()
            .ok_or_else(|| AnonymusError::Internal("sending chain not initialised".into()))?;

        let (mk, new_ck) = MessageKey::from_chain(cks)?;
        self.cks = Some(new_ck);

        let header = Header {
            dh_public: self.dh_self.public_bytes(),
            pn: self.pn,
            n: self.ns,
        };
        self.ns += 1;

        let header_bytes = header.encode();
        let nonce = Self::derive_nonce(&mk)?;
        let ct = aead::encrypt_with_nonce(&mk.0, &nonce, plaintext, &header_bytes)?;

        Ok((header_bytes, ct))
    }

    // ── Decrypt ────────────────────────────────────────────────────────────────

    /// Decrypt a ciphertext given its header bytes.
    pub fn decrypt(&mut self, header_bytes: &[u8; 40], ciphertext: &[u8]) -> Result<Vec<u8>> {
        let header = Header::decode(header_bytes);

        // Check skipped keys first
        let skip_key = SkipKey { dh_public: header.dh_public, n: header.n };
        if let Some(mk_bytes) = self.skipped.remove(&skip_key) {
            let nonce = Self::nonce_from_bytes(&mk_bytes)?;
            return aead::decrypt_with_nonce(&mk_bytes, &nonce, ciphertext, header_bytes);
        }

        // DH ratchet step if sender has a new ratchet key
        if Some(header.dh_public) != self.dh_remote {
            self.skip_message_keys(header.pn)?;
            self.ratchet_step(&header.dh_public)?;
        }

        self.skip_message_keys(header.n)?;

        let ckr = self
            .ckr
            .as_ref()
            .ok_or_else(|| AnonymusError::Internal("receiving chain not initialised".into()))?;
        let (mk, new_ckr) = MessageKey::from_chain(ckr)?;
        self.ckr = Some(new_ckr);
        self.nr += 1;

        let nonce = Self::derive_nonce(&mk)?;
        aead::decrypt_with_nonce(&mk.0, &nonce, ciphertext, header_bytes)
    }

    // ── Ratchet helpers ────────────────────────────────────────────────────────

    fn ratchet_step(&mut self, dh_remote: &[u8; 32]) -> Result<()> {
        self.pn = self.ns;
        self.ns = 0;
        self.nr = 0;
        self.dh_remote = Some(*dh_remote);

        // Receiving chain
        let dh_out = self.dh_self.dh(dh_remote)?;
        let (new_rk, ckr) = kdf_rk(&self.rk, &dh_out)?;
        self.rk = new_rk;
        self.ckr = Some(ckr);

        // New sending ratchet keypair
        self.dh_self = x25519::StaticKeypair::generate();

        // Sending chain
        let dh_out2 = self.dh_self.dh(dh_remote)?;
        let (new_rk2, cks) = kdf_rk(&self.rk, &dh_out2)?;
        self.rk = new_rk2;
        self.cks = Some(cks);

        Ok(())
    }

    fn skip_message_keys(&mut self, until: u32) -> Result<()> {
        if self.nr + MAX_SKIP < until {
            return Err(AnonymusError::Decrypt("too many skipped messages".into()));
        }
        if let Some(ckr) = self.ckr.clone() {
            let mut ck = ckr;
            while self.nr < until {
                let (mk, new_ck) = MessageKey::from_chain(&ck)?;
                let skip_key = SkipKey {
                    dh_public: self.dh_remote.unwrap_or([0u8; 32]),
                    n: self.nr,
                };
                self.skipped.insert(skip_key, mk.0);
                ck = new_ck;
                self.nr += 1;
            }
            self.ckr = Some(ck);
        }
        Ok(())
    }

    /// Derive a deterministic 12-byte nonce from a message key.
    fn derive_nonce(mk: &MessageKey) -> Result<[u8; 12]> {
        let n = hkdf::derive(mk.0.as_ref(), None, INFO_MSG, 12)?;
        Ok(n.try_into().unwrap())
    }

    fn nonce_from_bytes(mk_bytes: &[u8; 32]) -> Result<[u8; 12]> {
        let mk = MessageKey(*mk_bytes);
        Self::derive_nonce(&mk)
    }
}

// ── X3DH Pre-Key Bundle ────────────────────────────────────────────────────────

/// Bob's published pre-key bundle (used by Alice to initiate X3DH).
pub struct PreKeyBundle {
    /// Long-term identity key (IK_B).
    pub identity_public: [u8; 32],
    /// Signed pre-key (SPK_B).
    pub signed_prekey_public: [u8; 32],
    /// Ed25519 signature over SPK_B by IK_B.
    pub signed_prekey_sig: [u8; 64],
    /// One-time pre-key (OPK_B) — optional.
    pub one_time_prekey_public: Option<[u8; 32]>,
}

/// Result of a successful X3DH key agreement for Alice (initiator).
pub struct X3dhInitResult {
    /// The 32-byte shared secret to seed the Double Ratchet.
    pub shared_secret: [u8; 32],
    /// Alice's ephemeral public key (must be sent to Bob alongside the first message).
    pub ephemeral_public: [u8; 32],
    /// Which OPK index was consumed (None if no OPK available).
    pub opk_index: Option<usize>,
}

/// Perform X3DH as the **initiator** (Alice).
///
/// Verifies the signed pre-key signature before computing the four DH values.
pub fn x3dh_initiate(
    alice_identity: &x25519::StaticKeypair,
    alice_identity_ed: &[u8; 32],
    bundle: &PreKeyBundle,
) -> Result<X3dhInitResult> {
    use crate::crypto::ed25519;

    // Verify SPK_B signature: IK_B signs SPK_B
    ed25519::verify(
        // X25519 IK → Ed25519 public key (same 32-byte format, different curve)
        // NOTE: In the real protocol IK_B is an Ed25519 key; we use it directly here.
        &bundle.identity_public,
        &bundle.signed_prekey_public,
        &bundle.signed_prekey_sig,
    )?;

    let eph = x25519::EphemeralKeypair::generate();
    let eph_pub = eph.public_bytes();

    // DH1 = DH(IK_A, SPK_B)
    let dh1 = alice_identity.dh(&bundle.signed_prekey_public)?;
    // DH2 = DH(EK_A, IK_B)
    let dh2_kp = x25519::StaticKeypair::from_bytes(
        alice_identity.private_bytes(),
    );
    let dh2 = dh2_kp.dh(&bundle.identity_public)?;
    // DH3 = DH(EK_A, SPK_B)
    let dh3 = eph.dh(&bundle.signed_prekey_public)?;

    // Concatenate DH outputs
    let mut ikm = Vec::with_capacity(128);
    // Prepend 32 × 0xFF as per Signal spec F function
    ikm.extend_from_slice(&[0xFFu8; 32]);
    ikm.extend_from_slice(&dh1);
    ikm.extend_from_slice(&dh2);
    ikm.extend_from_slice(&dh3);

    let opk_index = if let Some(opk) = bundle.one_time_prekey_public {
        // DH4 = DH(EK_A, OPK_B)
        let dh4_kp = x25519::StaticKeypair::from_bytes(
            alice_identity.private_bytes(),
        );
        let dh4 = dh4_kp.dh(&opk)?;
        ikm.extend_from_slice(&dh4);
        Some(0)
    } else {
        None
    };

    let shared_secret = hkdf::derive_32(
        &ikm,
        Some(b"AnonyMus v3 X3DH"),
        b"AnonyMus v3 X3DH shared",
    )?;

    Ok(X3dhInitResult {
        shared_secret,
        ephemeral_public: eph_pub,
        opk_index,
    })
}

/// Perform X3DH as the **responder** (Bob).
pub fn x3dh_respond(
    bob_identity: &x25519::StaticKeypair,
    bob_signed_prekey: &x25519::StaticKeypair,
    alice_identity_public: &[u8; 32],
    alice_ephemeral_public: &[u8; 32],
    one_time_prekey: Option<&x25519::StaticKeypair>,
) -> Result<[u8; 32]> {
    // DH1 = DH(SPK_B, IK_A)
    let dh1 = bob_signed_prekey.dh(alice_identity_public)?;
    // DH2 = DH(IK_B, EK_A)
    let dh2 = bob_identity.dh(alice_ephemeral_public)?;
    // DH3 = DH(SPK_B, EK_A)
    let dh3 = bob_signed_prekey.dh(alice_ephemeral_public)?;

    let mut ikm = Vec::with_capacity(128);
    ikm.extend_from_slice(&[0xFFu8; 32]);
    ikm.extend_from_slice(&dh1);
    ikm.extend_from_slice(&dh2);
    ikm.extend_from_slice(&dh3);

    if let Some(opk) = one_time_prekey {
        let dh4 = opk.dh(alice_ephemeral_public)?;
        ikm.extend_from_slice(&dh4);
    }

    hkdf::derive_32(
        &ikm,
        Some(b"AnonyMus v3 X3DH"),
        b"AnonyMus v3 X3DH shared",
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_session_pair() -> (Session, Session) {
        // Simulate X3DH: both sides agree on the same shared secret.
        let shared_secret = [0x42u8; 32];
        let bob_ratchet = x25519::StaticKeypair::generate();

        let alice =
            Session::init_sender(&shared_secret, &bob_ratchet.public_bytes()).unwrap();
        let bob =
            Session::init_receiver(&shared_secret, bob_ratchet.private_bytes()).unwrap();

        (alice, bob)
    }

    #[test]
    fn single_message_roundtrip() {
        let (mut alice, mut bob) = make_session_pair();
        let plaintext = b"Hello, Bob!";
        let (hdr, ct) = alice.encrypt(plaintext).unwrap();
        let pt = bob.decrypt(&hdr, &ct).unwrap();
        assert_eq!(pt, plaintext);
    }

    #[test]
    fn multiple_messages_in_order() {
        let (mut alice, mut bob) = make_session_pair();
        for i in 0u8..10 {
            let msg = format!("message {i}");
            let (hdr, ct) = alice.encrypt(msg.as_bytes()).unwrap();
            let pt = bob.decrypt(&hdr, &ct).unwrap();
            assert_eq!(pt, msg.as_bytes());
        }
    }

    #[test]
    fn out_of_order_messages() {
        let (mut alice, mut bob) = make_session_pair();

        let (hdr0, ct0) = alice.encrypt(b"first").unwrap();
        let (hdr1, ct1) = alice.encrypt(b"second").unwrap();
        let (hdr2, ct2) = alice.encrypt(b"third").unwrap();

        // Deliver out of order: 2, 0, 1
        let pt2 = bob.decrypt(&hdr2, &ct2).unwrap();
        let pt0 = bob.decrypt(&hdr0, &ct0).unwrap();
        let pt1 = bob.decrypt(&hdr1, &ct1).unwrap();

        assert_eq!(pt0, b"first");
        assert_eq!(pt1, b"second");
        assert_eq!(pt2, b"third");
    }

    #[test]
    fn bidirectional_conversation() {
        let (mut alice, mut bob) = make_session_pair();

        let (hdr_a, ct_a) = alice.encrypt(b"Hi Bob").unwrap();
        let pt_a = bob.decrypt(&hdr_a, &ct_a).unwrap();
        assert_eq!(pt_a, b"Hi Bob");

        let (hdr_b, ct_b) = bob.encrypt(b"Hi Alice").unwrap();
        let pt_b = alice.decrypt(&hdr_b, &ct_b).unwrap();
        assert_eq!(pt_b, b"Hi Alice");
    }

    #[test]
    fn tampered_ciphertext_fails() {
        let (mut alice, mut bob) = make_session_pair();
        let (hdr, mut ct) = alice.encrypt(b"secret").unwrap();
        ct[0] ^= 0xFF; // flip a byte
        assert!(bob.decrypt(&hdr, &ct).is_err());
    }

    #[test]
    fn tampered_header_fails() {
        let (mut alice, mut bob) = make_session_pair();
        let (mut hdr, ct) = alice.encrypt(b"secret").unwrap();
        hdr[0] ^= 0xFF; // flip a byte in the DH key
        assert!(bob.decrypt(&hdr, &ct).is_err());
    }

    #[test]
    fn header_encode_decode_roundtrip() {
        let hdr = Header {
            dh_public: [0xABu8; 32],
            pn: 42,
            n: 7,
        };
        let encoded = hdr.encode();
        let decoded = Header::decode(&encoded);
        assert_eq!(decoded.dh_public, hdr.dh_public);
        assert_eq!(decoded.pn, 42);
        assert_eq!(decoded.n, 7);
    }
}
