//! SPQR: Stateful Post-Quantum Ratchet.
//!
//! Extends the Double Ratchet with amortised ML-KEM-768 ratchet steps.
//! Every N messages (configurable, default=10), the sender encapsulates a
//! fresh ML-KEM shared secret and includes the ciphertext in the message header.
//! The receiver decapsulates and feeds it into the root KDF alongside the DH output.
//!
//! This provides post-quantum forward secrecy without per-message KEM overhead.
//! Reference: <https://eprint.iacr.org/2023/hybrid>

use crate::crypto::{hkdf, ml_kem};
use crate::{AnonymusError, Result};

/// How many messages between PQ ratchet steps.
pub const PQ_RATCHET_PERIOD: u32 = 10;

/// The current PQ ratchet state for one session direction.
pub struct PqRatchetState {
    /// Our current ML-KEM-768 keypair (used for receiving the next encapsulation).
    pub keypair: ml_kem::MlKemKeypair,
    /// Peer's current ML-KEM-768 encapsulation key.
    pub peer_ek: Option<Vec<u8>>,
    /// Shared secret from the last successful decapsulation (mixed into chain key).
    pub last_ss: Option<[u8; 32]>,
    /// Message counter — triggers a ratchet step every `PQ_RATCHET_PERIOD` messages.
    pub counter: u32,
}

impl PqRatchetState {
    /// Create a fresh PQ ratchet state.
    pub fn new() -> Self {
        Self {
            keypair: ml_kem::MlKemKeypair::generate(),
            peer_ek: None,
            last_ss: None,
            counter: 0,
        }
    }

    /// Check whether it is time to perform a PQ ratchet step.
    pub fn should_ratchet(&self) -> bool {
        self.counter % PQ_RATCHET_PERIOD == 0 && self.counter > 0
    }

    /// Advance the counter and optionally generate an encapsulation for the peer.
    ///
    /// Returns `Some((ciphertext, new_ss))` when a ratchet step is triggered.
    pub fn step_send(&mut self) -> Result<Option<(Vec<u8>, [u8; 32])>> {
        self.counter += 1;
        if !self.should_ratchet() {
            return Ok(None);
        }
        let peer_ek = self
            .peer_ek
            .as_ref()
            .ok_or_else(|| AnonymusError::Internal("PQ peer EK not set".into()))?;
        let (ss, ct) = ml_kem::encapsulate(peer_ek)?;
        Ok(Some((ct, ss)))
    }

    /// Decapsulate an incoming PQ ratchet ciphertext.
    pub fn step_receive(&mut self, ct: &[u8]) -> Result<[u8; 32]> {
        let ss = self.keypair.decapsulate(ct)?;
        self.last_ss = Some(ss);
        // Rotate our keypair so future sessions start fresh.
        self.keypair = ml_kem::MlKemKeypair::generate();
        Ok(ss)
    }

    /// Mix a PQ shared secret into a chain key using HKDF.
    pub fn mix_into_chain(&self, chain_key: &[u8; 32]) -> Result<[u8; 32]> {
        let ss = self
            .last_ss
            .as_ref()
            .ok_or_else(|| AnonymusError::Internal("no PQ SS to mix".into()))?;
        hkdf::derive_32(
            ss,
            Some(chain_key),
            b"AnonyMus v3 SPQR chain mix",
        )
    }
}

impl Default for PqRatchetState {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pq_ratchet_period() {
        let mut state = PqRatchetState::new();
        for i in 1..PQ_RATCHET_PERIOD {
            state.counter = i;
            assert!(!state.should_ratchet(), "should not ratchet at {i}");
        }
        state.counter = PQ_RATCHET_PERIOD;
        assert!(state.should_ratchet());
    }

    #[test]
    fn encap_decap_pq_ratchet() {
        let mut sender = PqRatchetState::new();
        let mut receiver = PqRatchetState::new();

        // Exchange public keys
        sender.peer_ek = Some(receiver.keypair.ek_bytes.clone());
        receiver.peer_ek = Some(sender.keypair.ek_bytes.clone());

        // Trigger a send-side ratchet step
        sender.counter = PQ_RATCHET_PERIOD;
        let result = sender.step_send().unwrap();
        assert!(result.is_some(), "should generate ratchet ciphertext");

        let (ct, sender_ss) = result.unwrap();
        let receiver_ss = receiver.step_receive(&ct).unwrap();
        assert_eq!(sender_ss, receiver_ss);
    }

    #[test]
    fn mix_into_chain_deterministic() {
        let mut state = PqRatchetState::new();
        state.last_ss = Some([0x42u8; 32]);
        let ck = [0x11u8; 32];
        let a = state.mix_into_chain(&ck).unwrap();
        let b = state.mix_into_chain(&ck).unwrap();
        assert_eq!(a, b);
    }
}
