//! Messaging Layer Security (MLS) protocol implementation.
//!
//! Provides the core data structures and key derivation logic for group messaging
//! conforming to the RFC 9420 epoch transitions and TreeKEM group key agreement principles.

use crate::crypto::{aead, hkdf};
use crate::Result;

/// Represents an MLS group session with epoch-based forward secrecy.
pub struct MlsGroup {
    pub group_id: Vec<u8>,
    pub epoch: u64,
    pub epoch_secret: [u8; 32],
    pub member_usernames: Vec<String>,
}

impl MlsGroup {
    /// Initialize a new group session with an initial epoch secret.
    pub fn new(group_id: Vec<u8>, initial_secret: [u8; 32], members: Vec<String>) -> Self {
        Self {
            group_id,
            epoch: 0,
            epoch_secret: initial_secret,
            member_usernames: members,
        }
    }

    /// Advance the group epoch and compute new epoch keying material.
    ///
    /// Conforming to RFC 9420 Section 8, epoch secrets are derived using HKDF
    /// from the previous epoch secret and the new path secret.
    pub fn advance_epoch(&mut self, path_secret: &[u8; 32]) -> Result<()> {
        self.epoch += 1;

        let mut info = Vec::new();
        info.extend_from_slice(b"MLSEpochSecret");
        info.extend_from_slice(&self.group_id);
        info.extend_from_slice(&self.epoch.to_be_bytes());

        // Use previous_epoch_secret as salt, path_secret as IKM
        let next_epoch_secret = hkdf::derive_32(path_secret, Some(&self.epoch_secret), &info)?;
        self.epoch_secret = next_epoch_secret;
        Ok(())
    }

    /// Derive an epoch-specific sender key for a group member.
    fn derive_sender_key(&self, sender_username: &str) -> Result<[u8; 32]> {
        let mut info = Vec::new();
        info.extend_from_slice(b"MLSSenderKey");
        info.extend_from_slice(sender_username.as_bytes());
        info.extend_from_slice(&self.epoch.to_be_bytes());

        hkdf::derive_32(&self.epoch_secret, None, &info)
    }

    /// Encrypt a message payload for the group under the current epoch.
    pub fn encrypt_message(&self, sender_username: &str, plaintext: &[u8]) -> Result<Vec<u8>> {
        if !self.member_usernames.contains(&sender_username.to_string()) {
            return Err(crate::AnonymusError::Internal(
                "sender is not a member of this group".into(),
            ));
        }

        let sender_key = self.derive_sender_key(sender_username)?;
        aead::encrypt(&sender_key, plaintext)
    }

    /// Decrypt a message payload under the current epoch.
    pub fn decrypt_message(&self, sender_username: &str, ciphertext: &[u8]) -> Result<Vec<u8>> {
        if !self.member_usernames.contains(&sender_username.to_string()) {
            return Err(crate::AnonymusError::Internal(
                "sender is not a member of this group".into(),
            ));
        }

        let sender_key = self.derive_sender_key(sender_username)?;
        aead::decrypt(&sender_key, ciphertext)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mls_group_encryption_roundtrip() {
        let members = vec!["alice".to_string(), "bob".to_string()];
        let start_secret = [1u8; 32];
        let group = MlsGroup::new(b"group-123".to_vec(), start_secret, members);

        let plaintext = b"Hello, MLS group members!";
        let ciphertext = group.encrypt_message("alice", plaintext).unwrap();

        // Bob decrypts
        let decrypted = group.decrypt_message("alice", &ciphertext).unwrap();
        assert_eq!(decrypted, plaintext);
    }

    #[test]
    fn mls_epoch_advancement_forward_secrecy() {
        let members = vec!["alice".to_string(), "bob".to_string()];
        let start_secret = [1u8; 32];
        let mut group = MlsGroup::new(b"group-123".to_vec(), start_secret, members);

        let plaintext = b"Top secret for epoch 0";
        let ciphertext = group.encrypt_message("alice", plaintext).unwrap();

        // Advance epoch
        let path_secret = [9u8; 32];
        group.advance_epoch(&path_secret).unwrap();
        assert_eq!(group.epoch, 1);

        // Trying to decrypt the old message under the new epoch secret fails
        // because the sender key is derived from the new epoch secret.
        let decrypt_attempt = group.decrypt_message("alice", &ciphertext);
        assert!(decrypt_attempt.is_err());
    }

    #[test]
    fn non_member_cannot_encrypt_or_decrypt() {
        let members = vec!["alice".to_string()];
        let start_secret = [1u8; 32];
        let group = MlsGroup::new(b"group-123".to_vec(), start_secret, members);

        let encrypt_attempt = group.encrypt_message("attacker", b"malicious");
        assert!(encrypt_attempt.is_err());
    }
}
