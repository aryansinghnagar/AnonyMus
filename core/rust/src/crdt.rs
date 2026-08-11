//! Offline-First Chat Sync via CRDTs (Yrs)
//! Implements conflict-free replicated state for peer message document merging.

use yrs::updates::decoder::Decode;
use yrs::updates::encoder::Encode;
use yrs::{Doc, GetString, StateVector, Text, Transact, Update};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum CrdtError {
    #[error("CRDT encoding failed: {0}")]
    EncodingFailed(String),
    #[error("CRDT merge failed: {0}")]
    MergeFailed(String),
}

/// Managed CRDT document store for chat history synchronization
pub struct ChatDocument {
    doc: Doc,
}

impl Default for ChatDocument {
    fn default() -> Self {
        Self::new()
    }
}

impl ChatDocument {
    pub fn new() -> Self {
        Self { doc: Doc::new() }
    }

    /// Insert or append text content to a key in the document
    pub fn append_message(&self, text_key: &str, content: &str) -> Result<(), CrdtError> {
        let mut txn = self.doc.transact_mut();
        let text = txn.get_or_insert_text(text_key);
        text.push(&mut txn, content);
        Ok(())
    }

    /// Read the complete text state for a given key
    pub fn get_messages(&self, text_key: &str) -> String {
        let txn = self.doc.transact();
        if let Some(text) = txn.get_text(text_key) {
            text.get_string(&txn)
        } else {
            String::new()
        }
    }

    /// Encode local document update delta relative to a remote state vector
    pub fn encode_update(&self, remote_sv: Option<&[u8]>) -> Result<Vec<u8>, CrdtError> {
        let txn = self.doc.transact();
        let sv = if let Some(bytes) = remote_sv {
            StateVector::decode_v1(bytes)
                .map_err(|e| CrdtError::EncodingFailed(e.to_string()))?
        } else {
            StateVector::default()
        };
        let update = txn.encode_update_v1(&sv);
        Ok(update)
    }

    /// Merge an incoming remote CRDT update payload
    pub fn apply_update(&self, update_bytes: &[u8]) -> Result<(), CrdtError> {
        let update = Update::decode_v1(update_bytes)
            .map_err(|e| CrdtError::MergeFailed(e.to_string()))?;
        let mut txn = self.doc.transact_mut();
        txn.apply_update(update)
            .map_err(|e| CrdtError::MergeFailed(e.to_string()))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_crdt_offline_sync() {
        let doc1 = ChatDocument::new();
        let doc2 = ChatDocument::new();

        doc1.append_message("chat_room_1", "Hello from Peer A! ").unwrap();

        // Encode update from doc1 and apply to doc2
        let update = doc1.encode_update(None).unwrap();
        doc2.apply_update(&update).unwrap();

        assert_eq!(doc2.get_messages("chat_room_1"), "Hello from Peer A! ");

        // Peer B appends locally
        doc2.append_message("chat_room_1", "Hi Peer A!").unwrap();

        // Sync doc2 update back to doc1
        let update2 = doc2.encode_update(None).unwrap();
        doc1.apply_update(&update2).unwrap();

        assert_eq!(doc1.get_messages("chat_room_1"), "Hello from Peer A! Hi Peer A!");
        assert_eq!(doc2.get_messages("chat_room_1"), "Hello from Peer A! Hi Peer A!");
    }
}
