//! Sealed Sender Envelope.
//!
//! Encrypts and hides the sender's identity from intermediate relay servers
//! using a symmetric sealed-sender key.

use crate::crypto::aead;
use crate::{AnonymusError, Result};
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
pub struct SealedSenderPayload {
    pub sender_username: String,
    pub sender_signing_pub: [u8; 32],
    pub sender_dh_pub: [u8; 32],
    pub inner_message: Vec<u8>, // Double Ratchet payload/ciphertext
}

#[derive(Serialize, Deserialize)]
pub struct SealedSenderEnvelope {
    pub recipient_queue_id: String,
    pub encrypted_payload: Vec<u8>, // Contains nonce + ciphertext + tag from aead::encrypt
}

impl SealedSenderEnvelope {
    /// Encrypt a SealedSenderPayload into a SealedSenderEnvelope.
    pub fn seal(
        recipient_queue_id: &str,
        sealed_sender_key: &[u8; 32],
        payload: &SealedSenderPayload,
    ) -> Result<Self> {
        let serialized = serde_json::to_vec(payload)
            .map_err(|e| AnonymusError::Encrypt(format!("serialization failed: {e}")))?;

        let encrypted_payload = aead::encrypt(sealed_sender_key, &serialized)?;
        Ok(Self {
            recipient_queue_id: recipient_queue_id.to_string(),
            encrypted_payload,
        })
    }

    /// Decrypt a SealedSenderEnvelope to recover the SealedSenderPayload.
    pub fn unseal(&self, sealed_sender_key: &[u8; 32]) -> Result<SealedSenderPayload> {
        let decrypted = aead::decrypt(sealed_sender_key, &self.encrypted_payload)?;
        let payload: SealedSenderPayload = serde_json::from_slice(&decrypted)
            .map_err(|e| AnonymusError::Decrypt(format!("deserialization failed: {e}")))?;
        Ok(payload)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn seal_and_unseal_roundtrip() {
        let key = [9u8; 32];
        let payload = SealedSenderPayload {
            sender_username: "alice".to_string(),
            sender_signing_pub: [1u8; 32],
            sender_dh_pub: [2u8; 32],
            inner_message: vec![3, 4, 5],
        };

        let env = SealedSenderEnvelope::seal("bob-queue-id", &key, &payload).unwrap();
        assert_eq!(env.recipient_queue_id, "bob-queue-id");

        let decrypted = env.unseal(&key).unwrap();
        assert_eq!(decrypted.sender_username, "alice");
        assert_eq!(decrypted.sender_signing_pub, [1u8; 32]);
        assert_eq!(decrypted.sender_dh_pub, [2u8; 32]);
        assert_eq!(decrypted.inner_message, vec![3, 4, 5]);
    }
}
