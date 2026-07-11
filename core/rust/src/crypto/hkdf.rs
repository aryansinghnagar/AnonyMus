//! HKDF-SHA256 key derivation.
//!
//! Used throughout the protocol to derive sub-keys from shared secrets.

use hkdf::Hkdf;
use sha2::Sha256;

use crate::{AnonymusError, Result};

pub const MAX_OUTPUT_LEN: usize = 255 * 32; // HKDF-SHA256 max output

/// Derive `output_len` bytes from `ikm` (input keying material) using optional `salt` and `info`.
pub fn derive(ikm: &[u8], salt: Option<&[u8]>, info: &[u8], output_len: usize) -> Result<Vec<u8>> {
    if output_len == 0 || output_len > MAX_OUTPUT_LEN {
        return Err(AnonymusError::Kdf(format!(
            "output_len must be in 1..={MAX_OUTPUT_LEN}, got {output_len}"
        )));
    }
    let hk = Hkdf::<Sha256>::new(salt, ikm);
    let mut out = vec![0u8; output_len];
    hk.expand(info, &mut out)
        .map_err(|e| AnonymusError::Kdf(e.to_string()))?;
    Ok(out)
}

/// Convenience: derive exactly 32 bytes into a fixed-size array.
pub fn derive_32(ikm: &[u8], salt: Option<&[u8]>, info: &[u8]) -> Result<[u8; 32]> {
    let vec = derive(ikm, salt, info, 32)?;
    Ok(vec.try_into().expect("length guaranteed"))
}

/// Convenience: derive exactly 64 bytes (two chained keys).
pub fn derive_64(ikm: &[u8], salt: Option<&[u8]>, info: &[u8]) -> Result<[u8; 64]> {
    let vec = derive(ikm, salt, info, 64)?;
    Ok(vec.try_into().expect("length guaranteed"))
}

#[cfg(test)]
mod tests {
    use super::*;

    // RFC 5869 Test Case 1 (truncated to 42 bytes — we only check first 32 here)
    #[test]
    fn rfc5869_test_case_1_first_32_bytes() {
        let ikm = hex::decode("0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b").unwrap();
        let salt = hex::decode("000102030405060708090a0b0c").unwrap();
        let info = hex::decode("f0f1f2f3f4f5f6f7f8f9").unwrap();
        let okm = derive(&ikm, Some(&salt), &info, 32).unwrap();
        // First 32 bytes of RFC 5869 TC1 OKM
        let expected =
            hex::decode("3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf")
                .unwrap();
        assert_eq!(okm, expected);
    }

    #[test]
    fn no_salt_deterministic() {
        let a = derive_32(b"shared-secret", None, b"AnonyMus v3 root key").unwrap();
        let b = derive_32(b"shared-secret", None, b"AnonyMus v3 root key").unwrap();
        assert_eq!(a, b);
    }

    #[test]
    fn different_info_different_output() {
        let a = derive_32(b"ikm", None, b"chain-key").unwrap();
        let b = derive_32(b"ikm", None, b"message-key").unwrap();
        assert_ne!(a, b);
    }

    #[test]
    fn zero_output_len_errors() {
        assert!(derive(b"ikm", None, b"", 0).is_err());
    }
}
