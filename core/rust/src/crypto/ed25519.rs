//! Ed25519 digital signature verification.
//!
//! Used for:
//! - Supporter badge verification (root developer key).
//! - Identity key binding proofs.

use ed25519_dalek::{Signature, SigningKey, VerifyingKey, Signer, Verifier};

use crate::{AnonymusError, Result};

pub const PUBLIC_KEY_LEN: usize = 32;
pub const PRIVATE_KEY_LEN: usize = 32;
pub const SIGNATURE_LEN: usize = 64;

/// An Ed25519 signing keypair.
pub struct SigningKeypair {
    inner: SigningKey,
}

impl SigningKeypair {
    pub fn generate() -> Self {
        Self {
            inner: SigningKey::generate(&mut rand_core::OsRng),
        }
    }

    pub fn from_bytes(bytes: &[u8; PRIVATE_KEY_LEN]) -> Self {
        Self {
            inner: SigningKey::from_bytes(bytes),
        }
    }

    pub fn public_bytes(&self) -> [u8; PUBLIC_KEY_LEN] {
        self.inner.verifying_key().to_bytes()
    }

    pub fn sign(&self, message: &[u8]) -> [u8; SIGNATURE_LEN] {
        self.inner.sign(message).to_bytes()
    }
}

/// Verify a detached Ed25519 `signature` over `message` using `public_key`.
pub fn verify(
    public_key: &[u8; PUBLIC_KEY_LEN],
    message: &[u8],
    signature: &[u8; SIGNATURE_LEN],
) -> Result<()> {
    let vk = VerifyingKey::from_bytes(public_key)
        .map_err(|e| AnonymusError::InvalidKey(e.to_string()))?;
    let sig = Signature::from_bytes(signature);
    vk.verify(message, &sig)
        .map_err(|_| AnonymusError::BadSignature)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sign_and_verify() {
        let kp = SigningKeypair::generate();
        let msg = b"AnonyMus supporter badge";
        let sig = kp.sign(msg);
        assert!(verify(&kp.public_bytes(), msg, &sig).is_ok());
    }

    #[test]
    fn wrong_message_fails() {
        let kp = SigningKeypair::generate();
        let sig = kp.sign(b"original");
        assert!(verify(&kp.public_bytes(), b"tampered", &sig).is_err());
    }

    #[test]
    fn wrong_key_fails() {
        let kp = SigningKeypair::generate();
        let other = SigningKeypair::generate();
        let sig = kp.sign(b"message");
        assert!(verify(&other.public_bytes(), b"message", &sig).is_err());
    }
}
