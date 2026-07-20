//! UniFFI Swift bindings for anonymus-core.

#![cfg(feature = "swift")]

use crate::crypto;

#[derive(uniffi::Record)]
pub struct Keypair {
    pub private_key: Vec<u8>,
    pub public_key: Vec<u8>,
}

#[derive(uniffi::Record)]
pub struct PqxdhInitiatorResult {
    pub shared_secret: Vec<u8>,
    pub alice_ephemeral_pub: Vec<u8>,
    pub ml_kem_ciphertext: Vec<u8>,
}

#[derive(uniffi::Record)]
pub struct SealedSenderPayload {
    pub sender_username: String,
    pub sender_signing_pub: Vec<u8>,
    pub sender_dh_pub: Vec<u8>,
    pub inner_message: Vec<u8>,
}

// ── AEAD ───────────────────────────────────────────────────────────────────────

#[uniffi::export]
pub fn aead_encrypt(key: Vec<u8>, plaintext: Vec<u8>) -> Result<Vec<u8>, String> {
    let key_arr: [u8; 32] = key
        .try_into()
        .map_err(|_| "key must be 32 bytes".to_string())?;
    crypto::aead::encrypt(&key_arr, &plaintext).map_err(|e| e.to_string())
}

#[uniffi::export]
pub fn aead_decrypt(key: Vec<u8>, blob: Vec<u8>) -> Result<Vec<u8>, String> {
    let key_arr: [u8; 32] = key
        .try_into()
        .map_err(|_| "key must be 32 bytes".to_string())?;
    crypto::aead::decrypt(&key_arr, &blob).map_err(|e| e.to_string())
}

// ── HKDF ───────────────────────────────────────────────────────────────────────

#[uniffi::export]
pub fn hkdf_derive(
    ikm: Vec<u8>,
    info: Vec<u8>,
    output_len: u32,
    salt: Option<Vec<u8>>,
) -> Result<Vec<u8>, String> {
    crypto::hkdf::derive(&ikm, salt.as_deref(), &info, output_len as usize)
        .map_err(|e| e.to_string())
}

// ── X25519 ─────────────────────────────────────────────────────────────────────

#[uniffi::export]
pub fn x25519_generate() -> Keypair {
    let kp = crypto::x25519::StaticKeypair::generate();
    Keypair {
        private_key: kp.private_bytes().to_vec(),
        public_key: kp.public_bytes().to_vec(),
    }
}

#[uniffi::export]
pub fn x25519_dh(private_key: Vec<u8>, peer_public_key: Vec<u8>) -> Result<Vec<u8>, String> {
    let priv_arr: [u8; 32] = private_key
        .try_into()
        .map_err(|_| "private key must be 32 bytes".to_string())?;
    let pub_arr: [u8; 32] = peer_public_key
        .try_into()
        .map_err(|_| "public key must be 32 bytes".to_string())?;
    let kp = crypto::x25519::StaticKeypair::from_bytes(priv_arr);
    kp.dh(&pub_arr)
        .map(|ss| ss.to_vec())
        .map_err(|e| e.to_string())
}

// ── Ed25519 ────────────────────────────────────────────────────────────────────

#[uniffi::export]
pub fn ed25519_verify(
    public_key: Vec<u8>,
    message: Vec<u8>,
    signature: Vec<u8>,
) -> Result<(), String> {
    let pk_arr: [u8; 32] = public_key
        .try_into()
        .map_err(|_| "public key must be 32 bytes".to_string())?;
    let sig_arr: [u8; 64] = signature
        .try_into()
        .map_err(|_| "signature must be 64 bytes".to_string())?;
    ed25519_verify_internal(&pk_arr, &message, &sig_arr)
}

fn ed25519_verify_internal(
    public_key: &[u8; 32],
    message: &[u8],
    signature: &[u8; 64],
) -> Result<(), String> {
    crypto::ed25519::verify(public_key, message, signature).map_err(|e| e.to_string())
}

// ── Argon2id ───────────────────────────────────────────────────────────────────

#[uniffi::export]
pub fn argon2_derive_key(password: Vec<u8>, salt: Vec<u8>) -> Result<Vec<u8>, String> {
    crypto::argon2::derive_key(&password, &salt)
        .map(|k| k.to_vec())
        .map_err(|e| e.to_string())
}

// ── Phase 5 Primitives ──────────────────────────────────────────────────────────

#[uniffi::export]
pub fn compute_safety_number(
    user_a_id: String,
    user_a_signing_pub: Vec<u8>,
    user_a_dh_pub: Vec<u8>,
    user_b_id: String,
    user_b_signing_pub: Vec<u8>,
    user_b_dh_pub: Vec<u8>,
) -> Result<String, String> {
    let a_sign: [u8; 32] = user_a_signing_pub
        .try_into()
        .map_err(|_| "user_a_signing_pub must be 32 bytes".to_string())?;
    let a_dh: [u8; 32] = user_a_dh_pub
        .try_into()
        .map_err(|_| "user_a_dh_pub must be 32 bytes".to_string())?;
    let b_sign: [u8; 32] = user_b_signing_pub
        .try_into()
        .map_err(|_| "user_b_signing_pub must be 32 bytes".to_string())?;
    let b_dh: [u8; 32] = user_b_dh_pub
        .try_into()
        .map_err(|_| "user_b_dh_pub must be 32 bytes".to_string())?;

    Ok(crate::identity::compute_safety_number(
        &user_a_id, &a_sign, &a_dh, &user_b_id, &b_sign, &b_dh,
    ))
}

#[uniffi::export]
pub fn pqxdh_initiate(
    alice_identity_priv: Vec<u8>,
    bob_identity_pub: Vec<u8>,
    bob_signed_prekey_pub: Vec<u8>,
    bob_one_time_prekey_pub: Option<Vec<u8>>,
    bob_pq_signed_prekey_ek: Vec<u8>,
) -> Result<PqxdhInitiatorResult, String> {
    let alice_priv_arr: [u8; 32] = alice_identity_priv
        .try_into()
        .map_err(|_| "alice_identity_priv must be 32 bytes".to_string())?;
    let alice_identity = crypto::x25519::StaticKeypair::from_bytes(alice_priv_arr);

    let bob_id_arr: [u8; 32] = bob_identity_pub
        .try_into()
        .map_err(|_| "bob_identity_pub must be 32 bytes".to_string())?;
    let bob_spk_arr: [u8; 32] = bob_signed_prekey_pub
        .try_into()
        .map_err(|_| "bob_signed_prekey_pub must be 32 bytes".to_string())?;

    let bob_otk_arr: Option<[u8; 32]> = match bob_one_time_prekey_pub {
        Some(otk) => Some(
            otk.try_into()
                .map_err(|_| "bob_one_time_prekey_pub must be 32 bytes".to_string())?,
        ),
        None => None,
    };

    let res = crate::protocol::x3dh::pqxdh_initiate(
        &alice_identity,
        &bob_id_arr,
        &bob_spk_arr,
        bob_otk_arr.as_ref(),
        &bob_pq_signed_prekey_ek,
    )
    .map_err(|e| e.to_string())?;

    Ok(PqxdhInitiatorResult {
        shared_secret: res.shared_secret.to_vec(),
        alice_ephemeral_pub: res.alice_ephemeral_pub.to_vec(),
        ml_kem_ciphertext: res.ml_kem_ciphertext,
    })
}

#[uniffi::export]
pub fn pqxdh_respond(
    bob_identity_priv: Vec<u8>,
    bob_signed_prekey_priv: Vec<u8>,
    bob_one_time_prekey_priv: Option<Vec<u8>>,
    bob_pq_signed_prekey_dk: Vec<u8>,
    alice_identity_pub: Vec<u8>,
    alice_ephemeral_pub: Vec<u8>,
    ml_kem_ciphertext: Vec<u8>,
) -> Result<Vec<u8>, String> {
    let bob_id_arr: [u8; 32] = bob_identity_priv
        .try_into()
        .map_err(|_| "bob_identity_priv must be 32 bytes".to_string())?;
    let bob_identity = crypto::x25519::StaticKeypair::from_bytes(bob_id_arr);

    let bob_spk_arr: [u8; 32] = bob_signed_prekey_priv
        .try_into()
        .map_err(|_| "bob_signed_prekey_priv must be 32 bytes".to_string())?;
    let bob_signed_prekey = crypto::x25519::StaticKeypair::from_bytes(bob_spk_arr);

    let bob_otk = match bob_one_time_prekey_priv {
        Some(otk) => {
            let otk_arr: [u8; 32] = otk
                .try_into()
                .map_err(|_| "bob_one_time_prekey_priv must be 32 bytes".to_string())?;
            Some(crypto::x25519::StaticKeypair::from_bytes(otk_arr))
        }
        None => None,
    };

    let bob_pq_dk = crypto::ml_kem::MlKemKeypair::from_bytes(Vec::new(), bob_pq_signed_prekey_dk);

    let alice_id_arr: [u8; 32] = alice_identity_pub
        .try_into()
        .map_err(|_| "alice_identity_pub must be 32 bytes".to_string())?;
    let alice_eph_arr: [u8; 32] = alice_ephemeral_pub
        .try_into()
        .map_err(|_| "alice_ephemeral_pub must be 32 bytes".to_string())?;

    let ss = crate::protocol::x3dh::pqxdh_respond(
        &bob_identity,
        &bob_signed_prekey,
        bob_otk.as_ref(),
        &bob_pq_dk,
        &alice_id_arr,
        &alice_eph_arr,
        &ml_kem_ciphertext,
    )
    .map_err(|e| e.to_string())?;

    Ok(ss.to_vec())
}

#[uniffi::export]
pub fn sealed_sender_seal(
    recipient_queue_id: String,
    sealed_sender_key: Vec<u8>,
    sender_username: String,
    sender_signing_pub: Vec<u8>,
    sender_dh_pub: Vec<u8>,
    inner_message: Vec<u8>,
) -> Result<Vec<u8>, String> {
    let key: [u8; 32] = sealed_sender_key
        .try_into()
        .map_err(|_| "sealed_sender_key must be 32 bytes".to_string())?;
    let signing_pub: [u8; 32] = sender_signing_pub
        .try_into()
        .map_err(|_| "sender_signing_pub must be 32 bytes".to_string())?;
    let dh_pub: [u8; 32] = sender_dh_pub
        .try_into()
        .map_err(|_| "sender_dh_pub must be 32 bytes".to_string())?;

    let payload = crate::protocol::sealed_sender::SealedSenderPayload {
        sender_username,
        sender_signing_pub: signing_pub,
        sender_dh_pub: dh_pub,
        inner_message,
    };

    let envelope = crate::protocol::sealed_sender::SealedSenderEnvelope::seal(
        &recipient_queue_id,
        &key,
        &payload,
    )
    .map_err(|e| e.to_string())?;

    serde_json::to_vec(&envelope).map_err(|e| format!("failed to serialize envelope: {e}"))
}

#[uniffi::export]
pub fn sealed_sender_unseal(
    envelope_bytes: Vec<u8>,
    sealed_sender_key: Vec<u8>,
) -> Result<SealedSenderPayload, String> {
    let key: [u8; 32] = sealed_sender_key
        .try_into()
        .map_err(|_| "sealed_sender_key must be 32 bytes".to_string())?;

    let envelope: crate::protocol::sealed_sender::SealedSenderEnvelope =
        serde_json::from_slice(&envelope_bytes)
            .map_err(|e| format!("failed to parse envelope: {e}"))?;

    let payload = envelope.unseal(&key).map_err(|e| e.to_string())?;

    Ok(SealedSenderPayload {
        sender_username: payload.sender_username,
        sender_signing_pub: payload.sender_signing_pub.to_vec(),
        sender_dh_pub: payload.sender_dh_pub.to_vec(),
        inner_message: payload.inner_message,
    })
}

#[uniffi::export]
pub fn padding_pad(message: Vec<u8>, block_size: u32) -> Result<Vec<u8>, String> {
    crate::protocol::padding::pad(&message, block_size as usize).map_err(|e| e.to_string())
}

#[uniffi::export]
pub fn padding_unpad(padded: Vec<u8>, block_size: u32) -> Result<Vec<u8>, String> {
    crate::protocol::padding::unpad(&padded, block_size as usize).map_err(|e| e.to_string())
}
