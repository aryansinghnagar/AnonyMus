//! Hybrid Post-Quantum Key Exchange (X25519 + ML-KEM-1024)
//! Combines classical ECDH and Post-Quantum KEM via HKDF to ensure
//! zero-trust resilience against cryptanalytic breaks.

use crate::crypto::{hkdf as hkdf_util, ml_kem, x25519};
use crate::Result;

pub const HYBRID_SS_LEN: usize = 32;

/// Hybrid Keypair containing both X25519 and ML-KEM keys
pub struct HybridKeypair {
    pub x25519_kp: x25519::StaticKeypair,
    pub ml_kem_kp: ml_kem::MlKemKeypair,
}

impl Default for HybridKeypair {
    fn default() -> Self {
        Self::generate()
    }
}

impl HybridKeypair {
    pub fn generate() -> Self {
        let x25519_kp = x25519::StaticKeypair::generate();
        let ml_kem_kp = ml_kem::MlKemKeypair::generate();
        Self {
            x25519_kp,
            ml_kem_kp,
        }
    }

    /// Perform hybrid decapsulation given peer's X25519 public key bytes and ML-KEM ciphertext
    pub fn decapsulate_hybrid(
        &self,
        peer_x25519_pub: &[u8; 32],
        ml_kem_ct: &[u8],
    ) -> Result<[u8; HYBRID_SS_LEN]> {
        // 1. Classical X25519 Diffie-Hellman
        let ecdh_ss = self.x25519_kp.dh(peer_x25519_pub)?;

        // 2. Post-Quantum ML-KEM Decapsulation
        let pq_ss = self.ml_kem_kp.decapsulate(ml_kem_ct)?;

        // 3. HKDF Combine (ECDH_SS || PQ_SS) -> Hybrid Shared Secret
        let mut combined_ikm = Vec::with_capacity(64);
        combined_ikm.extend_from_slice(&ecdh_ss);
        combined_ikm.extend_from_slice(&pq_ss);

        hkdf_util::derive_32(&combined_ikm, None, b"AnonyMus-v3-Hybrid-PQ-KeyExchange")
    }
}

/// Perform hybrid encapsulation to recipient's hybrid public key
pub fn encapsulate_hybrid(
    peer_x25519_pub: &[u8; 32],
    peer_ml_kem_ek: &[u8],
) -> Result<([u8; HYBRID_SS_LEN], [u8; 32], Vec<u8>)> {
    // 1. Generate ephemeral X25519 keypair for classical ECDH
    let eph_kp = x25519::EphemeralKeypair::generate();
    let eph_pub = eph_kp.public_bytes();
    let ecdh_ss = eph_kp.dh(peer_x25519_pub)?;

    // 2. Encapsulate ML-KEM secret
    let (pq_ss, ml_kem_ct) = ml_kem::encapsulate(peer_ml_kem_ek)?;

    // 3. HKDF Combine (ECDH_SS || PQ_SS) -> Hybrid Shared Secret
    let mut combined_ikm = Vec::with_capacity(64);
    combined_ikm.extend_from_slice(&ecdh_ss);
    combined_ikm.extend_from_slice(&pq_ss);

    let hybrid_ss = hkdf_util::derive_32(&combined_ikm, None, b"AnonyMus-v3-Hybrid-PQ-KeyExchange")?;

    Ok((hybrid_ss, eph_pub, ml_kem_ct))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hybrid_pq_roundtrip() {
        let recipient_kp = HybridKeypair::generate();
        let recipient_x25519_pub = recipient_kp.x25519_kp.public_bytes();

        let (sender_ss, eph_pub, ml_kem_ct) =
            encapsulate_hybrid(&recipient_x25519_pub, &recipient_kp.ml_kem_kp.ek_bytes).unwrap();

        let recipient_ss = recipient_kp
            .decapsulate_hybrid(&eph_pub, &ml_kem_ct)
            .unwrap();

        assert_eq!(sender_ss, recipient_ss);
    }
}
