//! wasm-bindgen bindings for the AnonyMus web client.
//!
//! Exposes a minimal, high-level TypeScript-friendly API so the Solid.js
//! client can call into the Rust core without touching raw crypto.
//!
//! Build with:
//!   wasm-pack build core/rust --target web --features wasm --out-dir web/src/pkg
//!
//! Enabled with: `cargo build --features wasm`

#![cfg(feature = "wasm")]

use wasm_bindgen::prelude::*;

use crate::crypto::{aead, hkdf, x25519, ed25519, ml_kem};

// ── Utilities ──────────────────────────────────────────────────────────────────

fn js_err(e: impl ToString) -> JsValue {
    JsValue::from_str(&e.to_string())
}

// ── Identity / Key Generation ──────────────────────────────────────────────────

/// Generate a new X25519 identity keypair.
/// Returns `{ privateKey: Uint8Array, publicKey: Uint8Array }`.
#[wasm_bindgen(js_name = generateIdentityKeypair)]
pub fn generate_identity_keypair() -> Result<js_sys::Object, JsValue> {
    let kp = x25519::StaticKeypair::generate();
    let obj = js_sys::Object::new();
    js_sys::Reflect::set(&obj, &"privateKey".into(), &js_sys::Uint8Array::from(kp.private_bytes().as_ref()))?;
    js_sys::Reflect::set(&obj, &"publicKey".into(), &js_sys::Uint8Array::from(kp.public_bytes().as_ref()))?;
    Ok(obj)
}

// ── ECDH ───────────────────────────────────────────────────────────────────────

/// Perform X25519 DH. Returns a 32-byte shared secret.
#[wasm_bindgen(js_name = x25519Dh)]
pub fn x25519_dh(private_key: &[u8], peer_public_key: &[u8]) -> Result<Vec<u8>, JsValue> {
    let priv_arr: [u8; 32] = private_key.try_into().map_err(|_| js_err("private key must be 32 bytes"))?;
    let pub_arr: [u8; 32] = peer_public_key.try_into().map_err(|_| js_err("peer public key must be 32 bytes"))?;
    let kp = x25519::StaticKeypair::from_bytes(priv_arr);
    kp.dh(&pub_arr).map(|ss| ss.to_vec()).map_err(|e| js_err(e))
}

// ── AEAD ───────────────────────────────────────────────────────────────────────

/// Encrypt plaintext with a 32-byte key. Returns `nonce || ciphertext`.
#[wasm_bindgen(js_name = aeadEncrypt)]
pub fn aead_encrypt(key: &[u8], plaintext: &[u8]) -> Result<Vec<u8>, JsValue> {
    let key: [u8; 32] = key.try_into().map_err(|_| js_err("key must be 32 bytes"))?;
    aead::encrypt(&key, plaintext).map_err(|e| js_err(e))
}

/// Decrypt a blob produced by `aeadEncrypt`.
#[wasm_bindgen(js_name = aeadDecrypt)]
pub fn aead_decrypt(key: &[u8], blob: &[u8]) -> Result<Vec<u8>, JsValue> {
    let key: [u8; 32] = key.try_into().map_err(|_| js_err("key must be 32 bytes"))?;
    aead::decrypt(&key, blob).map_err(|e| js_err(e))
}

// ── HKDF ───────────────────────────────────────────────────────────────────────

/// Derive `outputLen` bytes via HKDF-SHA256.
#[wasm_bindgen(js_name = hkdfDerive)]
pub fn hkdf_derive(
    ikm: &[u8],
    info: &[u8],
    output_len: usize,
    salt: Option<Vec<u8>>,
) -> Result<Vec<u8>, JsValue> {
    hkdf::derive(ikm, salt.as_deref(), info, output_len).map_err(|e| js_err(e))
}

// ── Ed25519 ────────────────────────────────────────────────────────────────────

/// Verify an Ed25519 signature. Throws on failure.
#[wasm_bindgen(js_name = ed25519Verify)]
pub fn ed25519_verify(public_key: &[u8], message: &[u8], signature: &[u8]) -> Result<(), JsValue> {
    let pk: [u8; 32] = public_key.try_into().map_err(|_| js_err("public key must be 32 bytes"))?;
    let sig: [u8; 64] = signature.try_into().map_err(|_| js_err("signature must be 64 bytes"))?;
    ed25519::verify(&pk, message, &sig).map_err(|e| js_err(e))
}

// ── Phase 5 Primitives ──────────────────────────────────────────────────────────

/// Compute safety number for verified connections.
#[wasm_bindgen(js_name = computeSafetyNumber)]
pub fn compute_safety_number(our_identity: &[u8], their_identity: &[u8]) -> Result<String, JsValue> {
    let our_id: [u8; 32] = our_identity.try_into().map_err(|_| js_err("our identity must be 32 bytes"))?;
    let their_id: [u8; 32] = their_identity.try_into().map_err(|_| js_err("their identity must be 32 bytes"))?;
    Ok(crate::identity::compute_safety_number(&our_id, &their_id))
}

/// Initiate PQXDH key exchange as Alice.
/// Returns `{ sharedSecret: Uint8Array, aliceEphemeralPub: Uint8Array, mlKemCiphertext: Uint8Array }`.
#[wasm_bindgen(js_name = pqxdhInitiate)]
pub fn pqxdh_initiate(
    alice_identity_priv: &[u8],
    bob_identity_pub: &[u8],
    bob_signed_prekey_pub: &[u8],
    bob_one_time_prekey_pub: Option<Vec<u8>>,
    bob_pq_signed_prekey_ek: &[u8],
) -> Result<js_sys::Object, JsValue> {
    let alice_priv_arr: [u8; 32] = alice_identity_priv.try_into().map_err(|_| js_err("alice_identity_priv must be 32 bytes"))?;
    let alice_identity = x25519::StaticKeypair::from_bytes(alice_priv_arr);

    let bob_id_arr: [u8; 32] = bob_identity_pub.try_into().map_err(|_| js_err("bob_identity_pub must be 32 bytes"))?;
    let bob_spk_arr: [u8; 32] = bob_signed_prekey_pub.try_into().map_err(|_| js_err("bob_signed_prekey_pub must be 32 bytes"))?;

    let bob_otk_arr: Option<[u8; 32]> = match bob_one_time_prekey_pub {
        Some(otk) => Some(otk.as_slice().try_into().map_err(|_| js_err("bob_one_time_prekey_pub must be 32 bytes"))?),
        None => None,
    };

    let res = crate::protocol::x3dh::pqxdh_initiate(
        &alice_identity,
        &bob_id_arr,
        &bob_spk_arr,
        bob_otk_arr.as_ref(),
        bob_pq_signed_prekey_ek,
    )
    .map_err(|e| js_err(e))?;

    let obj = js_sys::Object::new();
    js_sys::Reflect::set(&obj, &"sharedSecret".into(), &js_sys::Uint8Array::from(res.shared_secret.as_ref()))?;
    js_sys::Reflect::set(&obj, &"aliceEphemeralPub".into(), &js_sys::Uint8Array::from(res.alice_ephemeral_pub.as_ref()))?;
    js_sys::Reflect::set(&obj, &"mlKemCiphertext".into(), &js_sys::Uint8Array::from(res.ml_kem_ciphertext.as_ref()))?;

    Ok(obj)
}

/// Respond to PQXDH key exchange as Bob. Returns a 32-byte shared secret.
#[wasm_bindgen(js_name = pqxdhRespond)]
pub fn pqxdh_respond(
    bob_identity_priv: &[u8],
    bob_signed_prekey_priv: &[u8],
    bob_one_time_prekey_priv: Option<Vec<u8>>,
    bob_pq_signed_prekey_dk: &[u8],
    alice_identity_pub: &[u8],
    alice_ephemeral_pub: &[u8],
    ml_kem_ciphertext: &[u8],
) -> Result<Vec<u8>, JsValue> {
    let bob_id_arr: [u8; 32] = bob_identity_priv.try_into().map_err(|_| js_err("bob_identity_priv must be 32 bytes"))?;
    let bob_identity = x25519::StaticKeypair::from_bytes(bob_id_arr);

    let bob_spk_arr: [u8; 32] = bob_signed_prekey_priv.try_into().map_err(|_| js_err("bob_signed_prekey_priv must be 32 bytes"))?;
    let bob_signed_prekey = x25519::StaticKeypair::from_bytes(bob_spk_arr);

    let bob_otk = match bob_one_time_prekey_priv {
        Some(otk) => {
            let otk_arr: [u8; 32] = otk.as_slice().try_into().map_err(|_| js_err("bob_one_time_prekey_priv must be 32 bytes"))?;
            Some(x25519::StaticKeypair::from_bytes(otk_arr))
        }
        None => None,
    };

    let bob_pq_dk = ml_kem::MlKemKeypair::from_bytes(Vec::new(), bob_pq_signed_prekey_dk.to_vec());

    let alice_id_arr: [u8; 32] = alice_identity_pub.try_into().map_err(|_| js_err("alice_identity_pub must be 32 bytes"))?;
    let alice_eph_arr: [u8; 32] = alice_ephemeral_pub.try_into().map_err(|_| js_err("alice_ephemeral_pub must be 32 bytes"))?;

    let ss = crate::protocol::x3dh::pqxdh_respond(
        &bob_identity,
        &bob_signed_prekey,
        bob_otk.as_ref(),
        &bob_pq_dk,
        &alice_id_arr,
        &alice_eph_arr,
        ml_kem_ciphertext,
    )
    .map_err(|e| js_err(e))?;

    Ok(ss.to_vec())
}

/// Seal a payload into a Sealed Sender envelope.
#[wasm_bindgen(js_name = sealedSenderSeal)]
pub fn sealed_sender_seal(
    recipient_queue_id: &str,
    sealed_sender_key: &[u8],
    sender_username: &str,
    sender_signing_pub: &[u8],
    sender_dh_pub: &[u8],
    inner_message: &[u8],
) -> Result<Vec<u8>, JsValue> {
    let key: [u8; 32] = sealed_sender_key.try_into().map_err(|_| js_err("sealed_sender_key must be 32 bytes"))?;
    let signing_pub: [u8; 32] = sender_signing_pub.try_into().map_err(|_| js_err("sender_signing_pub must be 32 bytes"))?;
    let dh_pub: [u8; 32] = sender_dh_pub.try_into().map_err(|_| js_err("sender_dh_pub must be 32 bytes"))?;

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
    .map_err(|e| js_err(e))?;

    serde_json::to_vec(&envelope)
        .map_err(|e| js_err(format!("failed to serialize envelope: {e}")))
}

/// Unseal a Sealed Sender envelope.
/// Returns `{ senderUsername: string, senderSigningPub: Uint8Array, senderDhPub: Uint8Array, innerMessage: Uint8Array }`.
#[wasm_bindgen(js_name = sealedSenderUnseal)]
pub fn sealed_sender_unseal(
    envelope_bytes: &[u8],
    sealed_sender_key: &[u8],
) -> Result<js_sys::Object, JsValue> {
    let key: [u8; 32] = sealed_sender_key.try_into().map_err(|_| js_err("sealed_sender_key must be 32 bytes"))?;

    let envelope: crate::protocol::sealed_sender::SealedSenderEnvelope = serde_json::from_slice(envelope_bytes)
        .map_err(|e| js_err(format!("failed to parse envelope: {e}")))?;

    let payload = envelope.unseal(&key).map_err(|e| js_err(e))?;

    let obj = js_sys::Object::new();
    js_sys::Reflect::set(&obj, &"senderUsername".into(), &JsValue::from_str(&payload.sender_username))?;
    js_sys::Reflect::set(&obj, &"senderSigningPub".into(), &js_sys::Uint8Array::from(payload.sender_signing_pub.as_ref()))?;
    js_sys::Reflect::set(&obj, &"senderDhPub".into(), &js_sys::Uint8Array::from(payload.sender_dh_pub.as_ref()))?;
    js_sys::Reflect::set(&obj, &"innerMessage".into(), &js_sys::Uint8Array::from(payload.inner_message.as_ref()))?;

    Ok(obj)
}

/// Pad a message to a constant block boundary.
#[wasm_bindgen(js_name = paddingPad)]
pub fn padding_pad(message: &[u8], block_size: usize) -> Vec<u8> {
    crate::protocol::padding::pad(message, block_size)
}

/// Unpad a message to recover original content.
#[wasm_bindgen(js_name = paddingUnpad)]
pub fn padding_unpad(padded: &[u8], block_size: usize) -> Result<Vec<u8>, JsValue> {
    crate::protocol::padding::unpad(padded, block_size).map_err(|e| js_err(e))
}

// ── Protocol version ────────────────────────────────────────────────────────────

/// Returns the protocol version number (3).
#[wasm_bindgen(js_name = protocolVersion)]
pub fn protocol_version() -> u32 {
    crate::PROTOCOL_VERSION
}
