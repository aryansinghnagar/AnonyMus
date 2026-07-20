#![cfg(feature = "android")]

use jni::objects::{JClass, JString};
use jni::sys::{jbyteArray, jstring};
use jni::JNIEnv;
use rand_core::{OsRng, RngCore};

use crate::crypto::{aead, hkdf, ml_kem, x25519};

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_generateKeypairNative(
    mut env: JNIEnv,
    _class: JClass,
) -> jbyteArray {
    let kp = x25519::StaticKeypair::generate();
    let mut out = [0u8; 64];
    out[0..32].copy_from_slice(kp.private_bytes());
    out[32..64].copy_from_slice(kp.public_bytes());
    env.byte_array_from_slice(&out)
        .map(|arr| arr.into_raw())
        .unwrap_or(std::ptr::null_mut())
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_x25519DhNative(
    mut env: JNIEnv,
    _class: JClass,
    private_key: jbyteArray,
    peer_public_key: jbyteArray,
) -> jbyteArray {
    let priv_bytes = match env.convert_byte_array(private_key) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let pub_bytes = match env.convert_byte_array(peer_public_key) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let priv_arr: [u8; 32] = match priv_bytes.try_into() {
        Ok(arr) => arr,
        Err(_) => return std::ptr::null_mut(),
    };
    let pub_arr: [u8; 32] = match pub_bytes.try_into() {
        Ok(arr) => arr,
        Err(_) => return std::ptr::null_mut(),
    };

    let kp = x25519::StaticKeypair::from_bytes(priv_arr);
    match kp.dh(&pub_arr) {
        Ok(ss) => env
            .byte_array_from_slice(&ss)
            .map(|arr| arr.into_raw())
            .unwrap_or(std::ptr::null_mut()),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_aeadEncryptNative(
    mut env: JNIEnv,
    _class: JClass,
    key: jbyteArray,
    plaintext: jbyteArray,
    aad: jbyteArray,
) -> jbyteArray {
    let key_bytes = match env.convert_byte_array(key) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let key_arr: [u8; 32] = match key_bytes.try_into() {
        Ok(arr) => arr,
        Err(_) => return std::ptr::null_mut(),
    };
    let pt = match env.convert_byte_array(plaintext) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let aad_bytes = match env.convert_byte_array(aad) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };

    let mut nonce = [0u8; 12];
    OsRng.fill_bytes(&mut nonce);

    match aead::encrypt_with_nonce(&key_arr, &nonce, &pt, &aad_bytes) {
        Ok(ct) => {
            let mut out = Vec::with_capacity(12 + ct.len());
            out.extend_from_slice(&nonce);
            out.extend_from_slice(&ct);
            env.byte_array_from_slice(&out)
                .map(|arr| arr.into_raw())
                .unwrap_or(std::ptr::null_mut())
        }
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_aeadDecryptNative(
    mut env: JNIEnv,
    _class: JClass,
    key: jbyteArray,
    blob: jbyteArray,
    aad: jbyteArray,
) -> jbyteArray {
    let key_bytes = match env.convert_byte_array(key) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let key_arr: [u8; 32] = match key_bytes.try_into() {
        Ok(arr) => arr,
        Err(_) => return std::ptr::null_mut(),
    };
    let blob_bytes = match env.convert_byte_array(blob) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let aad_bytes = match env.convert_byte_array(aad) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };

    if blob_bytes.len() < 12 {
        return std::ptr::null_mut();
    }
    let (nonce, ct) = blob_bytes.split_at(12);
    let nonce_arr: &[u8; 12] = match nonce.try_into() {
        Ok(arr) => arr,
        Err(_) => return std::ptr::null_mut(),
    };

    match aead::decrypt_with_nonce(&key_arr, nonce_arr, ct, &aad_bytes) {
        Ok(pt) => env
            .byte_array_from_slice(&pt)
            .map(|arr| arr.into_raw())
            .unwrap_or(std::ptr::null_mut()),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_hkdfDeriveNative(
    mut env: JNIEnv,
    _class: JClass,
    ikm: jbyteArray,
    info: jbyteArray,
    salt: jbyteArray,
    output_len: jni::sys::jint,
) -> jbyteArray {
    let ikm_bytes = match env.convert_byte_array(ikm) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let info_bytes = match env.convert_byte_array(info) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let salt_bytes = match env.convert_byte_array(salt) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };

    let len = output_len as usize;
    let mut okm = vec![0u8; len];
    let salt_opt = if salt_bytes.is_empty() {
        None
    } else {
        Some(salt_bytes.as_slice())
    };

    match hkdf::derive(salt_opt, &ikm_bytes, &info_bytes, &mut okm) {
        Ok(_) => env
            .byte_array_from_slice(&okm)
            .map(|arr| arr.into_raw())
            .unwrap_or(std::ptr::null_mut()),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_computeSafetyNumberNative(
    mut env: JNIEnv,
    _class: JClass,
    our_identity: jbyteArray,
    their_identity: jbyteArray,
) -> jstring {
    let our_bytes = match env.convert_byte_array(our_identity) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let their_bytes = match env.convert_byte_array(their_identity) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let our_arr: [u8; 32] = match our_bytes.try_into() {
        Ok(arr) => arr,
        Err(_) => return std::ptr::null_mut(),
    };
    let their_arr: [u8; 32] = match their_bytes.try_into() {
        Ok(arr) => arr,
        Err(_) => return std::ptr::null_mut(),
    };

    let sn = crate::identity::compute_safety_number(&our_arr, &their_arr);
    env.new_string(sn)
        .map(|s| s.into_raw())
        .unwrap_or(std::ptr::null_mut())
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_pqxdhInitiateNative(
    mut env: JNIEnv,
    _class: JClass,
    alice_identity_priv: jbyteArray,
    bob_identity_pub: jbyteArray,
    bob_signed_prekey_pub: jbyteArray,
    bob_one_time_prekey_pub: jbyteArray,
    bob_pq_signed_prekey_ek: jbyteArray,
) -> jbyteArray {
    let alice_priv = match env.convert_byte_array(alice_identity_priv) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_id = match env.convert_byte_array(bob_identity_pub) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_spk = match env.convert_byte_array(bob_signed_prekey_pub) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_otk = match env.convert_byte_array(bob_one_time_prekey_pub) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_pq_ek = match env.convert_byte_array(bob_pq_signed_prekey_ek) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };

    let alice_priv_arr: [u8; 32] = match alice_priv.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let alice_identity = x25519::StaticKeypair::from_bytes(alice_priv_arr);

    let bob_id_arr: [u8; 32] = match bob_id.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_spk_arr: [u8; 32] = match bob_spk.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    let bob_otk_arr: Option<[u8; 32]> = if bob_otk.is_empty() {
        None
    } else {
        match bob_otk.try_into() {
            Ok(a) => Some(a),
            Err(_) => return std::ptr::null_mut(),
        }
    };

    match crate::protocol::x3dh::pqxdh_initiate(
        &alice_identity,
        &bob_id_arr,
        &bob_spk_arr,
        bob_otk_arr.as_ref(),
        &bob_pq_ek,
    ) {
        Ok(res) => {
            let mut out = [0u8; 32 + 32 + 1088];
            out[0..32].copy_from_slice(&res.shared_secret);
            out[32..64].copy_from_slice(&res.alice_ephemeral_pub);
            out[64..1152].copy_from_slice(&res.ml_kem_ciphertext);
            env.byte_array_from_slice(&out)
                .map(|arr| arr.into_raw())
                .unwrap_or(std::ptr::null_mut())
        }
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_pqxdhRespondNative(
    mut env: JNIEnv,
    _class: JClass,
    bob_identity_priv: jbyteArray,
    bob_signed_prekey_priv: jbyteArray,
    bob_one_time_prekey_priv: jbyteArray,
    bob_pq_signed_prekey_dk: jbyteArray,
    alice_identity_pub: jbyteArray,
    alice_ephemeral_pub: jbyteArray,
    ml_kem_ciphertext: jbyteArray,
) -> jbyteArray {
    let bob_id = match env.convert_byte_array(bob_identity_priv) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_spk = match env.convert_byte_array(bob_signed_prekey_priv) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_otk = match env.convert_byte_array(bob_one_time_prekey_priv) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_pq_dk_bytes = match env.convert_byte_array(bob_pq_signed_prekey_dk) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let alice_id = match env.convert_byte_array(alice_identity_pub) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let alice_eph = match env.convert_byte_array(alice_ephemeral_pub) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let ct = match env.convert_byte_array(ml_kem_ciphertext) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };

    let bob_id_arr: [u8; 32] = match bob_id.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_identity = x25519::StaticKeypair::from_bytes(bob_id_arr);

    let bob_spk_arr: [u8; 32] = match bob_spk.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let bob_signed_prekey = x25519::StaticKeypair::from_bytes(bob_spk_arr);

    let bob_otk_kp = if bob_otk.is_empty() {
        None
    } else {
        let otk_arr: [u8; 32] = match bob_otk.try_into() {
            Ok(a) => a,
            Err(_) => return std::ptr::null_mut(),
        };
        Some(x25519::StaticKeypair::from_bytes(otk_arr))
    };

    let bob_pq_dk = ml_kem::MlKemKeypair::from_bytes(Vec::new(), bob_pq_dk_bytes);

    let alice_id_arr: [u8; 32] = match alice_id.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let alice_eph_arr: [u8; 32] = match alice_eph.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    match crate::protocol::x3dh::pqxdh_respond(
        &bob_identity,
        &bob_signed_prekey,
        bob_otk_kp.as_ref(),
        &bob_pq_dk,
        &alice_id_arr,
        &alice_eph_arr,
        &ct,
    ) {
        Ok(ss) => env
            .byte_array_from_slice(&ss)
            .map(|arr| arr.into_raw())
            .unwrap_or(std::ptr::null_mut()),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_sealedSenderSealNative(
    mut env: JNIEnv,
    _class: JClass,
    recipient_queue_id: jstring,
    sealed_sender_key: jbyteArray,
    sender_username: jstring,
    sender_signing_pub: jbyteArray,
    sender_dh_pub: jbyteArray,
    inner_message: jbyteArray,
) -> jbyteArray {
    let q_id: String = match env.get_string(&recipient_queue_id.into()) {
        Ok(s) => s.into(),
        Err(_) => return std::ptr::null_mut(),
    };
    let key_bytes = match env.convert_byte_array(sealed_sender_key) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let username: String = match env.get_string(&sender_username.into()) {
        Ok(s) => s.into(),
        Err(_) => return std::ptr::null_mut(),
    };
    let signing_pub = match env.convert_byte_array(sender_signing_pub) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let dh_pub = match env.convert_byte_array(sender_dh_pub) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let msg = match env.convert_byte_array(inner_message) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };

    let key_arr: [u8; 32] = match key_bytes.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let signing_arr: [u8; 32] = match signing_pub.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let dh_arr: [u8; 32] = match dh_pub.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    let payload = crate::protocol::sealed_sender::SealedSenderPayload {
        sender_username: username,
        sender_signing_pub: signing_arr,
        sender_dh_pub: dh_arr,
        inner_message: msg,
    };

    match crate::protocol::sealed_sender::SealedSenderEnvelope::seal(&q_id, &key_arr, &payload) {
        Ok(env_struct) => {
            if let Ok(serialized) = serde_json::to_vec(&env_struct) {
                env.byte_array_from_slice(&serialized)
                    .map(|arr| arr.into_raw())
                    .unwrap_or(std::ptr::null_mut())
            } else {
                std::ptr::null_mut()
            }
        }
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_sealedSenderUnsealNative(
    mut env: JNIEnv,
    _class: JClass,
    envelope_bytes: jbyteArray,
    sealed_sender_key: jbyteArray,
) -> jbyteArray {
    let env_bytes = match env.convert_byte_array(envelope_bytes) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let key_bytes = match env.convert_byte_array(sealed_sender_key) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let key_arr: [u8; 32] = match key_bytes.try_into() {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    let envelope: crate::protocol::sealed_sender::SealedSenderEnvelope =
        match serde_json::from_slice(&env_bytes) {
            Ok(e) => e,
            Err(_) => return std::ptr::null_mut(),
        };

    match envelope.unseal(&key_arr) {
        Ok(payload) => {
            if let Ok(serialized) = serde_json::to_vec(&payload) {
                env.byte_array_from_slice(&serialized)
                    .map(|arr| arr.into_raw())
                    .unwrap_or(std::ptr::null_mut())
            } else {
                std::ptr::null_mut()
            }
        }
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_paddingPadNative(
    mut env: JNIEnv,
    _class: JClass,
    message: jbyteArray,
    block_size: jni::sys::jint,
) -> jbyteArray {
    let msg = match env.convert_byte_array(message) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    let padded = crate::protocol::padding::pad(&msg, block_size as usize);
    env.byte_array_from_slice(&padded)
        .map(|arr| arr.into_raw())
        .unwrap_or(std::ptr::null_mut())
}

#[no_mangle]
pub extern "system" fn Java_com_anonymus_app_data_JniCryptoProvider_paddingUnpadNative(
    mut env: JNIEnv,
    _class: JClass,
    padded: jbyteArray,
    block_size: jni::sys::jint,
) -> jbyteArray {
    let pad_bytes = match env.convert_byte_array(padded) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    match crate::protocol::padding::unpad(&pad_bytes, block_size as usize) {
        Ok(unpadded) => env
            .byte_array_from_slice(&unpadded)
            .map(|arr| arr.into_raw())
            .unwrap_or(std::ptr::null_mut()),
        Err(_) => std::ptr::null_mut(),
    }
}
