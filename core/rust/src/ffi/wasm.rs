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

use crate::crypto::{aead, hkdf, x25519, ed25519};

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

// ── Protocol version ────────────────────────────────────────────────────────────

/// Returns the protocol version number (3).
#[wasm_bindgen(js_name = protocolVersion)]
pub fn protocol_version() -> u32 {
    crate::PROTOCOL_VERSION
}
