//! PyO3 Python bindings for anonymus-core.
//!
//! Exposes a minimal high-level API so the FastAPI backend can call into
//! the Rust core without touching raw crypto primitives.
//!
//! Enable with: `cargo build --release --features python`
//! Install with: `maturin develop --features python`

#![cfg(feature = "python")]

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

use crate::crypto;

// ──────────────────────────────────────────────────────────────────────────────
// AEAD
// ──────────────────────────────────────────────────────────────────────────────

/// Encrypt `plaintext` with a 32-byte `key`. Returns `nonce || ciphertext`.
#[pyfunction]
fn aead_encrypt(key: &[u8], plaintext: &[u8]) -> PyResult<Vec<u8>> {
    let key: [u8; 32] = key
        .try_into()
        .map_err(|_| PyValueError::new_err("key must be exactly 32 bytes"))?;
    crypto::aead::encrypt(&key, plaintext)
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

/// Decrypt a blob produced by `aead_encrypt`.
#[pyfunction]
fn aead_decrypt(key: &[u8], blob: &[u8]) -> PyResult<Vec<u8>> {
    let key: [u8; 32] = key
        .try_into()
        .map_err(|_| PyValueError::new_err("key must be exactly 32 bytes"))?;
    crypto::aead::decrypt(&key, blob)
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

// ──────────────────────────────────────────────────────────────────────────────
// HKDF
// ──────────────────────────────────────────────────────────────────────────────

/// Derive `output_len` bytes via HKDF-SHA256.
#[pyfunction]
#[pyo3(signature = (ikm, info, output_len, salt=None))]
fn hkdf_derive(ikm: &[u8], info: &[u8], output_len: usize, salt: Option<&[u8]>) -> PyResult<Vec<u8>> {
    crypto::hkdf::derive(ikm, salt, info, output_len)
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

// ──────────────────────────────────────────────────────────────────────────────
// X25519
// ──────────────────────────────────────────────────────────────────────────────

/// Generate an X25519 static keypair. Returns `(private_bytes, public_bytes)`.
#[pyfunction]
fn x25519_generate() -> PyResult<(Vec<u8>, Vec<u8>)> {
    let kp = crypto::x25519::StaticKeypair::generate();
    Ok((kp.private_bytes().to_vec(), kp.public_bytes().to_vec()))
}

/// Perform X25519 DH. Returns 32-byte shared secret.
#[pyfunction]
fn x25519_dh(private_bytes: &[u8], peer_public_bytes: &[u8]) -> PyResult<Vec<u8>> {
    let priv_arr: [u8; 32] = private_bytes
        .try_into()
        .map_err(|_| PyValueError::new_err("private key must be 32 bytes"))?;
    let pub_arr: [u8; 32] = peer_public_bytes
        .try_into()
        .map_err(|_| PyValueError::new_err("public key must be 32 bytes"))?;
    let kp = crypto::x25519::StaticKeypair::from_bytes(priv_arr);
    let ss = kp.dh(&pub_arr).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(ss.to_vec())
}

// ──────────────────────────────────────────────────────────────────────────────
// Ed25519
// ──────────────────────────────────────────────────────────────────────────────

/// Verify an Ed25519 signature. Raises ValueError on failure.
#[pyfunction]
fn ed25519_verify(public_key: &[u8], message: &[u8], signature: &[u8]) -> PyResult<()> {
    let pk: [u8; 32] = public_key
        .try_into()
        .map_err(|_| PyValueError::new_err("public key must be 32 bytes"))?;
    let sig: [u8; 64] = signature
        .try_into()
        .map_err(|_| PyValueError::new_err("signature must be 64 bytes"))?;
    crypto::ed25519::verify(&pk, message, &sig)
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

// ──────────────────────────────────────────────────────────────────────────────
// Argon2id
// ──────────────────────────────────────────────────────────────────────────────

/// Derive a 32-byte database key from `password` and `salt`.
#[pyfunction]
fn argon2_derive_key(password: &[u8], salt: &[u8]) -> PyResult<Vec<u8>> {
    crypto::argon2::derive_key(password, salt)
        .map(|k| k.to_vec())
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

// ──────────────────────────────────────────────────────────────────────────────
// Module registration
// ──────────────────────────────────────────────────────────────────────────────

#[pymodule]
pub fn anonymus_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(aead_encrypt, m)?)?;
    m.add_function(wrap_pyfunction!(aead_decrypt, m)?)?;
    m.add_function(wrap_pyfunction!(hkdf_derive, m)?)?;
    m.add_function(wrap_pyfunction!(x25519_generate, m)?)?;
    m.add_function(wrap_pyfunction!(x25519_dh, m)?)?;
    m.add_function(wrap_pyfunction!(ed25519_verify, m)?)?;
    m.add_function(wrap_pyfunction!(argon2_derive_key, m)?)?;
    m.add("PROTOCOL_VERSION", crate::PROTOCOL_VERSION)?;
    Ok(())
}
