//! Argon2id password-based key derivation.
//!
//! Used to derive the SQLCipher database encryption key from the user's password.
//! Parameters match OWASP 2024 recommendations for interactive logins.

use argon2::{Algorithm, Argon2, Params, Version};

use crate::{AnonymusError, Result};

pub const KEY_LEN: usize = 32;

// OWASP 2024 interactive parameters
const M_COST: u32 = 65536; // 64 MiB
const T_COST: u32 = 3; // iterations
const P_COST: u32 = 4; // parallelism

/// Derive a 32-byte key from `password` and `salt` (should be 16+ random bytes).
/// This is deliberately slow — do NOT call on the hot path.
pub fn derive_key(password: &[u8], salt: &[u8]) -> Result<[u8; KEY_LEN]> {
    let params = Params::new(M_COST, T_COST, P_COST, Some(KEY_LEN))
        .map_err(|e| AnonymusError::Kdf(e.to_string()))?;
    let argon2 = Argon2::new(Algorithm::Argon2id, Version::V0x13, params);

    let mut out = [0u8; KEY_LEN];
    argon2
        .hash_password_into(password, salt, &mut out)
        .map_err(|e| AnonymusError::Kdf(e.to_string()))?;
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deterministic_given_same_inputs() {
        let pw = b"correct horse battery staple";
        let salt = [0x42u8; 16];
        let k1 = derive_key(pw, &salt).unwrap();
        let k2 = derive_key(pw, &salt).unwrap();
        assert_eq!(k1, k2);
    }

    #[test]
    fn different_passwords_different_keys() {
        let salt = [0x01u8; 16];
        let k1 = derive_key(b"password1", &salt).unwrap();
        let k2 = derive_key(b"password2", &salt).unwrap();
        assert_ne!(k1, k2);
    }

    #[test]
    fn different_salts_different_keys() {
        let pw = b"same-password";
        let k1 = derive_key(pw, &[0u8; 16]).unwrap();
        let k2 = derive_key(pw, &[1u8; 16]).unwrap();
        assert_ne!(k1, k2);
    }
}
