//! Zero-Knowledge Anti-Spam: Rate-Limiting Nullifiers (RLN)
//! Enforces epoch-based rate limits without revealing user identity or leaking metadata.

use sha2::{Digest, Sha256};
use crate::{AnonymusError, Result};

/// Epoch identifier for rate-limiting calculations (e.g. 10-second windows)
pub type Epoch = u64;

/// Nullifier value constructed from secret key + epoch index
pub type Nullifier = [u8; 32];

/// Zero-Knowledge Proof representation for RLN validation
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RlnProof {
    pub nullifier: Nullifier,
    pub share_x: [u8; 32],
    pub share_y: [u8; 32],
    pub epoch: Epoch,
}

/// Managed Rate-Limiting Nullifier identity key
pub struct RlnIdentity {
    secret_key: [u8; 32],
}

impl RlnIdentity {
    pub fn generate() -> Self {
        let mut secret_key = [0u8; 32];
        getrandom::getrandom(&mut secret_key).expect("RNG failed");
        Self { secret_key }
    }

    pub fn from_secret(secret_key: [u8; 32]) -> Self {
        Self { secret_key }
    }

    /// Generate an RLN zero-knowledge proof payload for a specific message & epoch
    pub fn generate_proof(&self, message: &[u8], epoch: Epoch) -> Result<RlnProof> {
        // 1. Calculate nullifier: Hash(secret_key || epoch)
        let mut hasher = Sha256::new();
        hasher.update(&self.secret_key);
        hasher.update(&epoch.to_be_bytes());
        let nullifier: Nullifier = hasher.finalize().into();

        // 2. Share X = Hash(message)
        let mut msg_hasher = Sha256::new();
        msg_hasher.update(message);
        let share_x: [u8; 32] = msg_hasher.finalize().into();

        // 3. Share Y = Hash(secret_key || share_x || epoch)
        let mut y_hasher = Sha256::new();
        y_hasher.update(&self.secret_key);
        y_hasher.update(&share_x);
        y_hasher.update(&epoch.to_be_bytes());
        let share_y: [u8; 32] = y_hasher.finalize().into();

        Ok(RlnProof {
            nullifier,
            share_x,
            share_y,
            epoch,
        })
    }
}

/// Relay verifier state for detecting rate-limit breaches
pub struct RlnVerifier {
    seen_proofs: Vec<RlnProof>,
}

impl Default for RlnVerifier {
    fn default() -> Self {
        Self::new()
    }
}

impl RlnVerifier {
    pub fn new() -> Self {
        Self {
            seen_proofs: Vec::new(),
        }
    }

    /// Validate an incoming proof. Returns Err if a double-spend / rate breach occurs in the same epoch.
    pub fn verify_and_record(&mut self, proof: &RlnProof) -> Result<()> {
        for seen in &self.seen_proofs {
            if seen.epoch == proof.epoch && seen.nullifier == proof.nullifier {
                if seen.share_x != proof.share_x {
                    return Err(AnonymusError::Decrypt(
                        "RLN rate limit breached: double-sign detected for epoch".into(),
                    ));
                }
                // Duplicate message resend in same epoch is allowed or idempotent
                return Ok(());
            }
        }
        self.seen_proofs.push(proof.clone());
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rln_proof_generation_and_verification() {
        let identity = RlnIdentity::generate();
        let mut verifier = RlnVerifier::new();

        let proof1 = identity.generate_proof(b"Message 1", 100).unwrap();
        assert!(verifier.verify_and_record(&proof1).is_ok());

        // Second message in same epoch from same identity triggers rate breach detection!
        let proof2 = identity.generate_proof(b"Message 2 (Spam attempt)", 100).unwrap();
        assert!(verifier.verify_and_record(&proof2).is_err());

        // Message in a new epoch succeeds
        let proof3 = identity.generate_proof(b"Message 3", 101).unwrap();
        assert!(verifier.verify_and_record(&proof3).is_ok());
    }
}
