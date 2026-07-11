//! X25519 Elliptic-Curve Diffie-Hellman key exchange.
//!
//! Used in X3DH pre-key bundles and Double Ratchet DH ratchet steps.

use x25519_dalek::{EphemeralSecret, PublicKey, StaticSecret};

use crate::{AnonymusError, Result};

pub const PUBLIC_KEY_LEN: usize = 32;
pub const PRIVATE_KEY_LEN: usize = 32;
pub const SHARED_SECRET_LEN: usize = 32;

/// An X25519 keypair backed by a **static** (storable) private key.
pub struct StaticKeypair {
    pub private: StaticSecret,
    pub public: PublicKey,
}

impl StaticKeypair {
    /// Generate a fresh keypair using OS RNG.
    pub fn generate() -> Self {
        let private = StaticSecret::random_from_rng(rand_core::OsRng);
        let public = PublicKey::from(&private);
        Self { private, public }
    }

    /// Restore from raw 32-byte private key bytes (e.g. loaded from encrypted DB).
    pub fn from_bytes(bytes: [u8; PRIVATE_KEY_LEN]) -> Self {
        let private = StaticSecret::from(bytes);
        let public = PublicKey::from(&private);
        Self { private, public }
    }

    /// Export the private key bytes (to be stored in encrypted storage).
    pub fn private_bytes(&self) -> [u8; PRIVATE_KEY_LEN] {
        self.private.to_bytes()
    }

    /// Export the public key bytes (sent to peers / published in pre-key bundle).
    pub fn public_bytes(&self) -> [u8; PUBLIC_KEY_LEN] {
        *self.public.as_bytes()
    }

    /// Perform DH with a peer's public key; returns the 32-byte shared secret.
    pub fn dh(&self, peer_public: &[u8; PUBLIC_KEY_LEN]) -> Result<[u8; SHARED_SECRET_LEN]> {
        let peer = PublicKey::from(*peer_public);
        Ok(*self.private.diffie_hellman(&peer).as_bytes())
    }
}

/// Generate an ephemeral keypair for a single use (X3DH initiator EK).
/// The private key is consumed after the DH step.
pub struct EphemeralKeypair {
    secret: Option<EphemeralSecret>,
    pub public: PublicKey,
}

impl EphemeralKeypair {
    pub fn generate() -> Self {
        let secret = EphemeralSecret::random_from_rng(rand_core::OsRng);
        let public = PublicKey::from(&secret);
        Self {
            secret: Some(secret),
            public,
        }
    }

    pub fn public_bytes(&self) -> [u8; PUBLIC_KEY_LEN] {
        *self.public.as_bytes()
    }

    /// Consume the ephemeral private key performing a DH step.
    /// Panics if called twice (enforces single-use).
    pub fn dh(mut self, peer_public: &[u8; PUBLIC_KEY_LEN]) -> Result<[u8; SHARED_SECRET_LEN]> {
        let secret = self
            .secret
            .take()
            .ok_or_else(|| AnonymusError::InvalidKey("ephemeral key already consumed".into()))?;
        let peer = PublicKey::from(*peer_public);
        Ok(*secret.diffie_hellman(&peer).as_bytes())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dh_is_commutative() {
        let alice = StaticKeypair::generate();
        let bob = StaticKeypair::generate();

        let alice_shared = alice.dh(&bob.public_bytes()).unwrap();
        let bob_shared = bob.dh(&alice.public_bytes()).unwrap();
        assert_eq!(alice_shared, bob_shared);
    }

    #[test]
    fn static_keypair_roundtrip() {
        let kp = StaticKeypair::generate();
        let bytes = kp.private_bytes();
        let restored = StaticKeypair::from_bytes(bytes);
        assert_eq!(kp.public_bytes(), restored.public_bytes());
    }

    #[test]
    fn ephemeral_keypair_dh() {
        let eph = EphemeralKeypair::generate();
        let static_kp = StaticKeypair::generate();
        let eph_pub = eph.public_bytes();

        let eph_shared = eph.dh(&static_kp.public_bytes()).unwrap();
        let static_shared = static_kp.dh(&eph_pub).unwrap();
        assert_eq!(eph_shared, static_shared);
    }
}
