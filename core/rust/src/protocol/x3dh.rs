//! Post-Quantum Extended Triple Diffie-Hellman (PQXDH).
//!
//! Synthesizes X25519 DH steps with ML-KEM-768 key encapsulation.

use crate::crypto::{hkdf, ml_kem, x25519::StaticKeypair};
use crate::Result;

pub struct PqxdhInitiatorResult {
    pub shared_secret: [u8; 32],
    pub alice_ephemeral_pub: [u8; 32],
    pub ml_kem_ciphertext: Vec<u8>,
}

/// Initiate PQXDH exchange as Alice.
pub fn pqxdh_initiate(
    alice_identity: &StaticKeypair,
    bob_identity_pub: &[u8; 32],
    bob_signed_prekey_pub: &[u8; 32],
    bob_one_time_prekey_pub: Option<&[u8; 32]>,
    bob_pq_signed_prekey_ek: &[u8],
) -> Result<PqxdhInitiatorResult> {
    // Generate Alice's ephemeral key as a one-time StaticKeypair
    let alice_ephemeral = StaticKeypair::generate();
    let alice_ephemeral_pub = alice_ephemeral.public_bytes();

    // DH1 = DH(AliceIdentity, BobSignedPreKey)
    let dh1 = alice_identity.dh(bob_signed_prekey_pub)?;

    // DH2 = DH(AliceEphemeral, BobIdentity)
    let dh2 = alice_ephemeral.dh(bob_identity_pub)?;

    // DH3 = DH(AliceEphemeral, BobSignedPreKey)
    let dh3 = alice_ephemeral.dh(bob_signed_prekey_pub)?;

    // DH4 = DH(AliceEphemeral, BobOneTimePreKey) (optional)
    let mut ikm = Vec::new();
    ikm.extend_from_slice(&dh1);
    ikm.extend_from_slice(&dh2);
    ikm.extend_from_slice(&dh3);

    if let Some(otk) = bob_one_time_prekey_pub {
        let dh4 = alice_ephemeral.dh(otk)?;
        ikm.extend_from_slice(&dh4);
    }

    // Post-Quantum KEM step
    let (pq_secret, ct) = ml_kem::encapsulate(bob_pq_signed_prekey_ek)?;
    ikm.extend_from_slice(&pq_secret);

    // Derive final master key via HKDF
    let shared_secret = hkdf::derive_32(&ikm, None, b"PQXDHMasterSecret")?;

    Ok(PqxdhInitiatorResult {
        shared_secret,
        alice_ephemeral_pub,
        ml_kem_ciphertext: ct,
    })
}

/// Respond to PQXDH exchange as Bob.
pub fn pqxdh_respond(
    bob_identity: &StaticKeypair,
    bob_signed_prekey: &StaticKeypair,
    bob_one_time_prekey: Option<&StaticKeypair>,
    bob_pq_signed_prekey_dk: &ml_kem::MlKemKeypair,
    alice_identity_pub: &[u8; 32],
    alice_ephemeral_pub: &[u8; 32],
    ml_kem_ciphertext: &[u8],
) -> Result<[u8; 32]> {
    // DH1 = DH(BobSignedPreKey, AliceIdentity)
    let dh1 = bob_signed_prekey.dh(alice_identity_pub)?;

    // DH2 = DH(BobIdentity, AliceEphemeral)
    let dh2 = bob_identity.dh(alice_ephemeral_pub)?;

    // DH3 = DH(BobSignedPreKey, AliceEphemeral)
    let dh3 = bob_signed_prekey.dh(alice_ephemeral_pub)?;

    let mut ikm = Vec::new();
    ikm.extend_from_slice(&dh1);
    ikm.extend_from_slice(&dh2);
    ikm.extend_from_slice(&dh3);

    if let Some(otk) = bob_one_time_prekey {
        let dh4 = otk.dh(alice_ephemeral_pub)?;
        ikm.extend_from_slice(&dh4);
    }

    // Post-Quantum KEM step (decapsulate)
    let pq_secret = bob_pq_signed_prekey_dk.decapsulate(ml_kem_ciphertext)?;
    ikm.extend_from_slice(&pq_secret);

    // Derive final master key via HKDF
    let shared_secret = hkdf::derive_32(&ikm, None, b"PQXDHMasterSecret")?;
    Ok(shared_secret)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pqxdh_roundtrip_no_otk() {
        let alice_identity = StaticKeypair::generate();
        let bob_identity = StaticKeypair::generate();
        let bob_signed_prekey = StaticKeypair::generate();
        let bob_pq_signed_prekey = ml_kem::MlKemKeypair::generate();

        // Alice initiates
        let alice_res = pqxdh_initiate(
            &alice_identity,
            &bob_identity.public_bytes(),
            &bob_signed_prekey.public_bytes(),
            None,
            &bob_pq_signed_prekey.ek_bytes,
        )
        .unwrap();

        // Bob responds
        let bob_secret = pqxdh_respond(
            &bob_identity,
            &bob_signed_prekey,
            None,
            &bob_pq_signed_prekey,
            &alice_identity.public_bytes(),
            &alice_res.alice_ephemeral_pub,
            &alice_res.ml_kem_ciphertext,
        )
        .unwrap();

        assert_eq!(alice_res.shared_secret, bob_secret);
    }

    #[test]
    fn pqxdh_roundtrip_with_otk() {
        let alice_identity = StaticKeypair::generate();
        let bob_identity = StaticKeypair::generate();
        let bob_signed_prekey = StaticKeypair::generate();
        let bob_one_time_prekey = StaticKeypair::generate();
        let bob_pq_signed_prekey = ml_kem::MlKemKeypair::generate();

        // Alice initiates
        let alice_res = pqxdh_initiate(
            &alice_identity,
            &bob_identity.public_bytes(),
            &bob_signed_prekey.public_bytes(),
            Some(&bob_one_time_prekey.public_bytes()),
            &bob_pq_signed_prekey.ek_bytes,
        )
        .unwrap();

        // Bob responds
        let bob_secret = pqxdh_respond(
            &bob_identity,
            &bob_signed_prekey,
            Some(&bob_one_time_prekey),
            &bob_pq_signed_prekey,
            &alice_identity.public_bytes(),
            &alice_res.alice_ephemeral_pub,
            &alice_res.ml_kem_ciphertext,
        )
        .unwrap();

        assert_eq!(alice_res.shared_secret, bob_secret);
    }
}
