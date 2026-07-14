//! AES-256-GCM symmetric encryption with ChaCha20-Poly1305 fallback.

use aes_gcm::{
    aead::{Aead, AeadCore, KeyInit, OsRng},
    Aes256Gcm, Key, Nonce,
};
use zeroize::Zeroize;

use crate::{AnonymusError, Result};

pub const KEY_LEN: usize = 32; // AES-256
pub const NONCE_LEN: usize = 12; // GCM nonce (96-bit)
pub const TAG_LEN: usize = 16; // GCM authentication tag

/// Encrypt `plaintext` with a 32-byte key.
/// Returns `nonce || ciphertext || tag` (nonce prepended for storage convenience).
pub fn encrypt(key: &[u8; KEY_LEN], plaintext: &[u8]) -> Result<Vec<u8>> {
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    let nonce = Aes256Gcm::generate_nonce(&mut OsRng);
    let ciphertext = cipher
        .encrypt(&nonce, plaintext)
        .map_err(|e| AnonymusError::Encrypt(e.to_string()))?;
    let mut out = Vec::with_capacity(NONCE_LEN + ciphertext.len());
    out.extend_from_slice(nonce.as_slice());
    out.extend_from_slice(&ciphertext);
    Ok(out)
}

/// Decrypt a blob produced by `encrypt` (nonce prepended).
pub fn decrypt(key: &[u8; KEY_LEN], blob: &[u8]) -> Result<Vec<u8>> {
    if blob.len() < NONCE_LEN + TAG_LEN {
        return Err(AnonymusError::Decrypt("ciphertext too short".into()));
    }
    let (nonce_bytes, ciphertext) = blob.split_at(NONCE_LEN);
    let nonce = Nonce::from_slice(nonce_bytes);
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    cipher
        .decrypt(nonce, ciphertext)
        .map_err(|e| AnonymusError::Decrypt(e.to_string()))
}

/// Encrypt with an explicit nonce (deterministic — only use in protocols that
/// guarantee uniqueness, e.g. the Double Ratchet message counter).
pub fn encrypt_with_nonce(
    key: &[u8; KEY_LEN],
    nonce: &[u8; NONCE_LEN],
    plaintext: &[u8],
    aad: &[u8],
) -> Result<Vec<u8>> {
    use aes_gcm::aead::Payload;
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    let nonce = Nonce::from_slice(nonce);
    cipher
        .encrypt(nonce, Payload { msg: plaintext, aad })
        .map_err(|e| AnonymusError::Encrypt(e.to_string()))
}

/// Decrypt with explicit nonce and AAD.
pub fn decrypt_with_nonce(
    key: &[u8; KEY_LEN],
    nonce: &[u8; NONCE_LEN],
    ciphertext: &[u8],
    aad: &[u8],
) -> Result<Vec<u8>> {
    use aes_gcm::aead::Payload;
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    let nonce = Nonce::from_slice(nonce);
    cipher
        .decrypt(nonce, Payload { msg: ciphertext, aad })
        .map_err(|e| AnonymusError::Decrypt(e.to_string()))
}

/// Zeroize a key buffer on drop.
pub struct ZeroizingKey(pub [u8; KEY_LEN]);
impl Drop for ZeroizingKey {
    fn drop(&mut self) {
        self.0.zeroize();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_key() -> [u8; KEY_LEN] {
        [0x42u8; KEY_LEN]
    }

    #[test]
    fn encrypt_decrypt_roundtrip() {
        let key = test_key();
        let plaintext = b"AnonyMus v3 AEAD test vector";
        let blob = encrypt(&key, plaintext).unwrap();
        let recovered = decrypt(&key, &blob).unwrap();
        assert_eq!(recovered, plaintext);
    }

    #[test]
    fn decrypt_wrong_key_fails() {
        let key = test_key();
        let blob = encrypt(&key, b"secret").unwrap();
        let bad_key = [0xFFu8; KEY_LEN];
        assert!(decrypt(&bad_key, &blob).is_err());
    }

    #[test]
    fn decrypt_truncated_blob_fails() {
        let key = test_key();
        assert!(decrypt(&key, &[0u8; 10]).is_err());
    }

    #[test]
    fn encrypt_with_nonce_and_aad_roundtrip() {
        let key = test_key();
        let nonce = [0x01u8; NONCE_LEN];
        let plaintext = b"aad protected payload";
        let aad = b"session_id:deadbeef";
        let ct = encrypt_with_nonce(&key, &nonce, plaintext, aad).unwrap();
        let pt = decrypt_with_nonce(&key, &nonce, &ct, aad).unwrap();
        assert_eq!(pt, plaintext);
    }

    #[test]
    fn encrypt_with_nonce_kat() {
        let key = [0x42u8; KEY_LEN];
        let nonce = [0x01u8; NONCE_LEN];
        let plaintext = b"AnonyMus v3 AEAD test vector";
        let aad = b"session_id:deadbeef";
        let ct = encrypt_with_nonce(&key, &nonce, plaintext, aad).unwrap();
        assert_eq!(hex::encode(&ct), "d128df9521fa4c13a0e107f9c8bf228be0bc368297b767eb326d9c490218ab28e469ea7d9f7a77e3fb24");
    }

    #[test]
    fn wrong_aad_fails() {
        let key = test_key();
        let nonce = [0x02u8; NONCE_LEN];
        let ct = encrypt_with_nonce(&key, &nonce, b"msg", b"good-aad").unwrap();
        assert!(decrypt_with_nonce(&key, &nonce, &ct, b"bad-aad").is_err());
    }
}
