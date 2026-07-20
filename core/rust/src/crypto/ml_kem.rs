//! ML-KEM-768 (FIPS 203) post-quantum key encapsulation.
//!
//! Used in PQXDH (X3DH + ML-KEM hybrid) and the amortised PQ ratchet step.
//!
//! ML-KEM-768 provides ~180-bit post-quantum security (NIST PQ Level 3).

use ml_kem::kem::{Decapsulate, Encapsulate};
use ml_kem::{Encoded, EncodedSizeUser};
use ml_kem::{KemCore, MlKem768};

use crate::{AnonymusError, Result};

pub const SS_LEN: usize = 32;

/// Holds an ML-KEM-768 keypair as raw byte vectors.
pub struct MlKemKeypair {
    /// Encapsulation key bytes (send to peer / publish in pre-key bundle).
    pub ek_bytes: Vec<u8>,
    /// Decapsulation key bytes (keep secret, store encrypted).
    dk_bytes: Vec<u8>,
}

impl MlKemKeypair {
    /// Generate a fresh keypair using OS randomness.
    pub fn generate() -> Self {
        let (dk, ek) = MlKem768::generate(&mut rand_core::OsRng);
        Self {
            ek_bytes: ek.as_bytes().to_vec(),
            dk_bytes: dk.as_bytes().to_vec(),
        }
    }

    /// Restore a keypair from raw bytes (loaded from encrypted storage).
    pub fn from_bytes(ek_bytes: Vec<u8>, dk_bytes: Vec<u8>) -> Self {
        Self { ek_bytes, dk_bytes }
    }

    /// Returns a reference to the decapsulation key bytes (private).
    pub fn dk_bytes(&self) -> &[u8] {
        &self.dk_bytes
    }

    /// Decapsulate a ciphertext, returning a 32-byte shared secret.
    pub fn decapsulate(&self, ct_bytes: &[u8]) -> Result<[u8; SS_LEN]> {
        use ml_kem::MlKem768Params;

        type Dk = ml_kem::kem::DecapsulationKey<MlKem768Params>;
        type Ct = ml_kem::Ciphertext<MlKem768>;

        let dk_encoded = Encoded::<Dk>::try_from(self.dk_bytes.as_slice())
            .map_err(|_| AnonymusError::InvalidKey("dk length/format mismatch".into()))?;
        let dk = Dk::from_bytes(&dk_encoded);

        let ct = Ct::try_from(ct_bytes)
            .map_err(|_| AnonymusError::InvalidKey("ct length mismatch".into()))?;

        let ss = dk
            .decapsulate(&ct)
            .map_err(|_| AnonymusError::Decrypt("decapsulation failed".into()))?;
        let ss_bytes: [u8; SS_LEN] = ss[..SS_LEN]
            .try_into()
            .expect("shared secret length guaranteed");
        Ok(ss_bytes)
    }
}

/// Encapsulate a shared secret to the holder of `ek_bytes`.
/// Returns `(shared_secret_32_bytes, ciphertext_bytes)`.
pub fn encapsulate(ek_bytes: &[u8]) -> Result<([u8; SS_LEN], Vec<u8>)> {
    use ml_kem::MlKem768Params;

    type Ek = ml_kem::kem::EncapsulationKey<MlKem768Params>;

    let ek_encoded = Encoded::<Ek>::try_from(ek_bytes)
        .map_err(|_| AnonymusError::InvalidKey("ek length/format mismatch".into()))?;
    let ek = Ek::from_bytes(&ek_encoded);

    let (ct, ss) = ek
        .encapsulate(&mut rand_core::OsRng)
        .map_err(|e| AnonymusError::Kdf(format!("{e:?}")))?;

    let ss_bytes: [u8; SS_LEN] = ss[..SS_LEN]
        .try_into()
        .expect("shared secret length guaranteed");
    Ok((ss_bytes, ct.to_vec()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn encap_decap_roundtrip() {
        let kp = MlKemKeypair::generate();
        let (alice_ss, ct) = encapsulate(&kp.ek_bytes).unwrap();
        let bob_ss = kp.decapsulate(&ct).unwrap();
        assert_eq!(alice_ss, bob_ss);
    }

    #[test]
    fn wrong_dk_gives_different_secret() {
        let kp = MlKemKeypair::generate();
        let other_kp = MlKemKeypair::generate();
        let (_ss, ct) = encapsulate(&kp.ek_bytes).unwrap();
        // ML-KEM uses implicit rejection: decapsulation never fails, just returns a random value.
        let ss_wrong = other_kp.decapsulate(&ct).unwrap();
        let ss_right = kp.decapsulate(&ct).unwrap();
        assert_ne!(ss_wrong, ss_right);
    }
}
