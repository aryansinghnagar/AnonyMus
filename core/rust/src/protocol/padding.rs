//! Variable-length padding.
//!
//! Pads messages to constant block boundaries to hide exact payload size
//! and resist traffic analysis attacks.

use crate::{AnonymusError, Result};

/// Pad a message payload to the next multiple of `block_size` using PKCS#7 padding.
pub fn pad(payload: &[u8], block_size: usize) -> Result<Vec<u8>> {
    if block_size == 0 || block_size > 256 {
        return Err(AnonymusError::Internal(format!(
            "invalid block size: {block_size}. Must be in 1..=256"
        )));
    }
    let pad_len = block_size - (payload.len() % block_size);
    let mut padded = payload.to_vec();
    padded.resize(payload.len() + pad_len, pad_len as u8);
    Ok(padded)
}

/// Unpad a message payload, removing the PKCS#7 padding.
pub fn unpad(padded: &[u8], block_size: usize) -> Result<Vec<u8>> {
    if padded.is_empty() {
        return Err(AnonymusError::Decrypt("padded payload is empty".into()));
    }
    if block_size == 0 || block_size > 256 {
        return Err(AnonymusError::Internal(format!(
            "invalid block size: {block_size}. Must be in 1..=256"
        )));
    }
    if padded.len() % block_size != 0 {
        return Err(AnonymusError::Decrypt(format!(
            "payload length {} is not a multiple of block size {}",
            padded.len(),
            block_size
        )));
    }

    let pad_len = *padded.last().unwrap() as usize;
    if pad_len == 0 || pad_len > block_size {
        return Err(AnonymusError::Decrypt(format!(
            "invalid padding length value: {pad_len}"
        )));
    }

    // Verify all padding bytes match pad_len
    let start_idx = padded.len() - pad_len;
    for &byte in &padded[start_idx..] {
        if byte as usize != pad_len {
            return Err(AnonymusError::Decrypt("invalid PKCS#7 padding bytes".into()));
        }
    }

    Ok(padded[..start_idx].to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn padding_roundtrip() {
        let block_size = 128;
        let msg = b"Hello, this is a secret message!";

        let padded = pad(msg, block_size).unwrap();
        assert_eq!(padded.len() % block_size, 0);
        assert!(padded.len() > msg.len());

        let unpadded = unpad(&padded, block_size).unwrap();
        assert_eq!(unpadded, msg);
    }

    #[test]
    fn exact_block_adds_full_padding_block() {
        let block_size = 16;
        let msg = vec![0u8; 16]; // exactly 1 block
        let padded = pad(&msg, block_size).unwrap();
        assert_eq!(padded.len(), 32); // should add 16 bytes of padding

        let unpadded = unpad(&padded, block_size).unwrap();
        assert_eq!(unpadded, msg);
    }

    #[test]
    fn invalid_padding_fails() {
        let block_size = 16;
        let mut padded = pad(b"test", block_size).unwrap();

        // Corrupt the padding byte
        let idx = padded.len() - 1;
        padded[idx] = 99;

        assert!(unpad(&padded, block_size).is_err());
    }
}
