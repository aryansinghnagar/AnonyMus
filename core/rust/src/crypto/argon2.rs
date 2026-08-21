//! Argon2id password-based key derivation.
//!
//! Used to derive the SQLCipher database encryption key from the user's password.
//! Parameters match OWASP 2024 recommendations for interactive logins.

use argon2::{Algorithm, Argon2, Params, Version};

use crate::{AnonymusError, Result};

pub const KEY_LEN: usize = 32;

// OWASP 2024 interactive parameters for production
#[cfg(not(test))]
const M_COST: u32 = 65536; // 64 MiB
#[cfg(not(test))]
const T_COST: u32 = 3; // iterations
#[cfg(not(test))]
const P_COST: u32 = 4; // parallelism

// Fast parameters for unit tests to prevent thread starvation, memory spikes, and CPU freezing
#[cfg(test)]
const M_COST: u32 = 1024; // 1 MiB
#[cfg(test)]
const T_COST: u32 = 1; // 1 iteration
#[cfg(test)]
const P_COST: u32 = 1; // 1 thread

/// Derive a 32-byte key from `password` and `salt` using custom Argon2id parameters.
pub fn derive_key_with_params(
    password: &[u8],
    salt: &[u8],
    m_cost: u32,
    t_cost: u32,
    p_cost: u32,
) -> Result<[u8; KEY_LEN]> {
    let params = Params::new(m_cost, t_cost, p_cost, Some(KEY_LEN))
        .map_err(|e| AnonymusError::Kdf(e.to_string()))?;
    let argon2 = Argon2::new(Algorithm::Argon2id, Version::V0x13, params);

    let mut out = [0u8; KEY_LEN];
    argon2
        .hash_password_into(password, salt, &mut out)
        .map_err(|e| AnonymusError::Kdf(e.to_string()))?;
    Ok(out)
}

/// Derive a 32-byte key from `password` and `salt` (should be 16+ random bytes).
/// In production, uses OWASP memory-hard parameters. In test mode, uses lightweight parameters.
pub fn derive_key(password: &[u8], salt: &[u8]) -> Result<[u8; KEY_LEN]> {
    derive_key_with_params(password, salt, M_COST, T_COST, P_COST)
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
