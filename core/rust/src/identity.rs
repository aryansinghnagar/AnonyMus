//! Identity Keypairs and Safety Numbers.
//!
//! Exposes the primary IdentityKeypair representing a user's cryptographic identity,
//! and utilities to compute Safety Numbers for verification.

use crate::crypto::{ed25519::SigningKeypair, x25519::StaticKeypair};
use sha2::{Digest, Sha256};

pub struct IdentityKeypair {
    pub signing: SigningKeypair,
    pub diffie_hellman: StaticKeypair,
}

impl IdentityKeypair {
    pub fn generate() -> Self {
        Self {
            signing: SigningKeypair::generate(),
            diffie_hellman: StaticKeypair::generate(),
        }
    }

    pub fn from_bytes(signing_bytes: &[u8; 32], dh_bytes: &[u8; 32]) -> Self {
        Self {
            signing: SigningKeypair::from_bytes(signing_bytes),
            diffie_hellman: StaticKeypair::from_bytes(*dh_bytes),
        }
    }
}

/// Compute a 32-byte Safety Number from two users' identity public keys.
///
/// Under v3 refactor guidelines (fix v1.0 16-byte truncation bug):
/// The Safety Number is computed as:
/// SHA-256 of:
/// - "SafetyNumberV3" label
/// - Sorted lexicographically: (User A's identifiers + public keys, User B's identifiers + public keys)
///
/// Output format: A human-readable string consisting of blocks of 5 decimal numbers.
pub fn compute_safety_number(
    user_a_id: &str,
    user_a_signing_pub: &[u8; 32],
    user_a_dh_pub: &[u8; 32],
    user_b_id: &str,
    user_b_signing_pub: &[u8; 32],
    user_b_dh_pub: &[u8; 32],
) -> String {
    let mut block_a = Vec::new();
    block_a.extend_from_slice(user_a_id.as_bytes());
    block_a.extend_from_slice(user_a_signing_pub);
    block_a.extend_from_slice(user_a_dh_pub);

    let mut block_b = Vec::new();
    block_b.extend_from_slice(user_b_id.as_bytes());
    block_b.extend_from_slice(user_b_signing_pub);
    block_b.extend_from_slice(user_b_dh_pub);

    let (first, second) = if block_a < block_b {
        (block_a, block_b)
    } else {
        (block_b, block_a)
    };

    let mut hasher = Sha256::new();
    hasher.update(b"SafetyNumberV3");
    hasher.update(&first);
    hasher.update(&second);
    let digest = hasher.finalize();

    let mut numbers = Vec::new();
    for i in 0..8 {
        let offset = i * 4;
        let val = u32::from_be_bytes([
            digest[offset],
            digest[offset + 1],
            digest[offset + 2],
            digest[offset + 3],
        ]);
        let num = val % 100000;
        numbers.push(format!("{:05}", num));
    }
    numbers.join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safety_number_is_commutative() {
        let a_signing = [1u8; 32];
        let a_dh = [2u8; 32];
        let b_signing = [3u8; 32];
        let b_dh = [4u8; 32];

        let sn1 = compute_safety_number("alice", &a_signing, &a_dh, "bob", &b_signing, &b_dh);
        let sn2 = compute_safety_number("bob", &b_signing, &b_dh, "alice", &a_signing, &a_dh);

        assert_eq!(sn1, sn2);
    }

    #[test]
    fn safety_number_kat() {
        let a_signing = [1u8; 32];
        let a_dh = [2u8; 32];
        let b_signing = [3u8; 32];
        let b_dh = [4u8; 32];

        let sn = compute_safety_number("alice", &a_signing, &a_dh, "bob", &b_signing, &b_dh);
        // Let's assert it to see the exact generated value
        assert_eq!(sn, "71932 75787 50849 05947 92533 39228 35916 67364");
    }
}
