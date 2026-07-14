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
// Phase 5 Primitives
// ──────────────────────────────────────────────────────────────────────────────

/// Compute a commutative 32-byte safety number for verified connections.
#[pyfunction]
fn compute_safety_number(our_identity: &[u8], their_identity: &[u8]) -> PyResult<String> {
    let our_id: [u8; 32] = our_identity
        .try_into()
        .map_err(|_| PyValueError::new_err("our identity must be 32 bytes"))?;
    let their_id: [u8; 32] = their_identity
        .try_into()
        .map_err(|_| PyValueError::new_err("their identity must be 32 bytes"))?;
    Ok(crate::identity::compute_safety_number(&our_id, &their_id))
}

/// Initiate PQXDH key exchange as Alice. Returns `(shared_secret, alice_ephemeral_pub, ml_kem_ciphertext)`.
#[pyfunction]
fn pqxdh_initiate(
    alice_identity_priv: &[u8],
    bob_identity_pub: &[u8],
    bob_signed_prekey_pub: &[u8],
    bob_one_time_prekey_pub: Option<&[u8]>,
    bob_pq_signed_prekey_ek: &[u8],
) -> PyResult<(Vec<u8>, Vec<u8>, Vec<u8>)> {
    let alice_priv_arr: [u8; 32] = alice_identity_priv
        .try_into()
        .map_err(|_| PyValueError::new_err("alice_identity_priv must be 32 bytes"))?;
    let alice_identity = crypto::x25519::StaticKeypair::from_bytes(alice_priv_arr);

    let bob_id_arr: [u8; 32] = bob_identity_pub
        .try_into()
        .map_err(|_| PyValueError::new_err("bob_identity_pub must be 32 bytes"))?;
    let bob_spk_arr: [u8; 32] = bob_signed_prekey_pub
        .try_into()
        .map_err(|_| PyValueError::new_err("bob_signed_prekey_pub must be 32 bytes"))?;

    let bob_otk_arr: Option<[u8; 32]> = match bob_one_time_prekey_pub {
        Some(otk) => Some(
            otk.try_into()
                .map_err(|_| PyValueError::new_err("bob_one_time_prekey_pub must be 32 bytes"))?,
        ),
        None => None,
    };

    let res = crate::protocol::x3dh::pqxdh_initiate(
        &alice_identity,
        &bob_id_arr,
        &bob_spk_arr,
        bob_otk_arr.as_ref(),
        bob_pq_signed_prekey_ek,
    )
    .map_err(|e| PyValueError::new_err(e.to_string()))?;

    Ok((
        res.shared_secret.to_vec(),
        res.alice_ephemeral_pub.to_vec(),
        res.ml_kem_ciphertext,
    ))
}

/// Respond to PQXDH key exchange as Bob. Returns `shared_secret`.
#[pyfunction]
fn pqxdh_respond(
    bob_identity_priv: &[u8],
    bob_signed_prekey_priv: &[u8],
    bob_one_time_prekey_priv: Option<&[u8]>,
    bob_pq_signed_prekey_dk: &[u8],
    alice_identity_pub: &[u8],
    alice_ephemeral_pub: &[u8],
    ml_kem_ciphertext: &[u8],
) -> PyResult<Vec<u8>> {
    let bob_id_arr: [u8; 32] = bob_identity_priv
        .try_into()
        .map_err(|_| PyValueError::new_err("bob_identity_priv must be 32 bytes"))?;
    let bob_identity = crypto::x25519::StaticKeypair::from_bytes(bob_id_arr);

    let bob_spk_arr: [u8; 32] = bob_signed_prekey_priv
        .try_into()
        .map_err(|_| PyValueError::new_err("bob_signed_prekey_priv must be 32 bytes"))?;
    let bob_signed_prekey = crypto::x25519::StaticKeypair::from_bytes(bob_spk_arr);

    let bob_otk = match bob_one_time_prekey_priv {
        Some(otk) => {
            let otk_arr: [u8; 32] = otk
                .try_into()
                .map_err(|_| PyValueError::new_err("bob_one_time_prekey_priv must be 32 bytes"))?;
            Some(crypto::x25519::StaticKeypair::from_bytes(otk_arr))
        }
        None => None,
    };

    let bob_pq_dk = crypto::ml_kem::MlKemKeypair::from_bytes(Vec::new(), bob_pq_signed_prekey_dk.to_vec());

    let alice_id_arr: [u8; 32] = alice_identity_pub
        .try_into()
        .map_err(|_| PyValueError::new_err("alice_identity_pub must be 32 bytes"))?;
    let alice_eph_arr: [u8; 32] = alice_ephemeral_pub
        .try_into()
        .map_err(|_| PyValueError::new_err("alice_ephemeral_pub must be 32 bytes"))?;

    let ss = crate::protocol::x3dh::pqxdh_respond(
        &bob_identity,
        &bob_signed_prekey,
        bob_otk.as_ref(),
        &bob_pq_dk,
        &alice_id_arr,
        &alice_eph_arr,
        ml_kem_ciphertext,
    )
    .map_err(|e| PyValueError::new_err(e.to_string()))?;

    Ok(ss.to_vec())
}

/// Seal a payload into a Sealed Sender envelope.
#[pyfunction]
fn sealed_sender_seal(
    recipient_queue_id: &str,
    sealed_sender_key: &[u8],
    sender_username: &str,
    sender_signing_pub: &[u8],
    sender_dh_pub: &[u8],
    inner_message: &[u8],
) -> PyResult<Vec<u8>> {
    let key: [u8; 32] = sealed_sender_key
        .try_into()
        .map_err(|_| PyValueError::new_err("sealed_sender_key must be 32 bytes"))?;
    let signing_pub: [u8; 32] = sender_signing_pub
        .try_into()
        .map_err(|_| PyValueError::new_err("sender_signing_pub must be 32 bytes"))?;
    let dh_pub: [u8; 32] = sender_dh_pub
        .try_into()
        .map_err(|_| PyValueError::new_err("sender_dh_pub must be 32 bytes"))?;

    let payload = crate::protocol::sealed_sender::SealedSenderPayload {
        sender_username: sender_username.to_string(),
        sender_signing_pub: signing_pub,
        sender_dh_pub: dh_pub,
        inner_message: inner_message.to_vec(),
    };

    let envelope = crate::protocol::sealed_sender::SealedSenderEnvelope::seal(
        recipient_queue_id,
        &key,
        &payload,
    )
    .map_err(|e| PyValueError::new_err(e.to_string()))?;

    serde_json::to_vec(&envelope)
        .map_err(|e| PyValueError::new_err(format!("failed to serialize envelope: {e}")))
}

/// Unseal a Sealed Sender envelope. Returns `(sender_username, sender_signing_pub, sender_dh_pub, inner_message)`.
#[pyfunction]
fn sealed_sender_unseal(
    envelope_bytes: &[u8],
    sealed_sender_key: &[u8],
) -> PyResult<(String, Vec<u8>, Vec<u8>, Vec<u8>)> {
    let key: [u8; 32] = sealed_sender_key
        .try_into()
        .map_err(|_| PyValueError::new_err("sealed_sender_key must be 32 bytes"))?;

    let envelope: crate::protocol::sealed_sender::SealedSenderEnvelope = serde_json::from_slice(envelope_bytes)
        .map_err(|e| PyValueError::new_err(format!("failed to parse envelope: {e}")))?;

    let payload = envelope.unseal(&key)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;

    Ok((
        payload.sender_username,
        payload.sender_signing_pub.to_vec(),
        payload.sender_dh_pub.to_vec(),
        payload.inner_message,
    ))
}

/// Pad a message to a constant block boundary.
#[pyfunction]
fn padding_pad(message: &[u8], block_size: usize) -> PyResult<Vec<u8>> {
    Ok(crate::protocol::padding::pad(message, block_size))
}

/// Unpad a message to recover original content.
#[pyfunction]
fn padding_unpad(padded: &[u8], block_size: usize) -> PyResult<Vec<u8>> {
    crate::protocol::padding::unpad(padded, block_size)
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
    m.add_function(wrap_pyfunction!(compute_safety_number, m)?)?;
    m.add_function(wrap_pyfunction!(pqxdh_initiate, m)?)?;
    m.add_function(wrap_pyfunction!(pqxdh_respond, m)?)?;
    m.add_function(wrap_pyfunction!(sealed_sender_seal, m)?)?;
    m.add_function(wrap_pyfunction!(sealed_sender_unseal, m)?)?;
    m.add_function(wrap_pyfunction!(padding_pad, m)?)?;
    m.add_function(wrap_pyfunction!(padding_unpad, m)?)?;
    m.add("PROTOCOL_VERSION", crate::PROTOCOL_VERSION)?;
    Ok(())
}
