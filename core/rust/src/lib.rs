//! anonymus-core — unified cryptographic and protocol core for AnonyMus v3.
//!
//! All platform clients (Python/PyO3, Web/WASM, Android/JNI, iOS/UniFFI)
//! bind against this single audited code path.

pub mod crypto;
pub mod ffi;

use thiserror::Error;

/// Semantic protocol version. Bumped on breaking wire-format changes.
pub const PROTOCOL_VERSION: u32 = 3;

/// Unified crate error type.
#[derive(Error, Debug)]
pub enum AnonymusError {
    #[error("encryption failed: {0}")]
    Encrypt(String),
    #[error("decryption failed: {0}")]
    Decrypt(String),
    #[error("key derivation failed: {0}")]
    Kdf(String),
    #[error("invalid key material: {0}")]
    InvalidKey(String),
    #[error("signature verification failed")]
    BadSignature,
    #[error("internal error: {0}")]
    Internal(String),
}

pub type Result<T> = std::result::Result<T, AnonymusError>;

/// Must be called once per process to verify the runtime environment.
pub fn init() -> Result<()> {
    // Future: FIPS self-test, entropy check, etc.
    Ok(())
}
