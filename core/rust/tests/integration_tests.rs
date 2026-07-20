//! Integration tests — exercises public API of anonymus-core.
//! Loads KAT vectors from tests/kat/v3-vectors.json and verifies each primitive.

use serde_json::Value;
use std::fs;

fn hex(s: &str) -> Vec<u8> {
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
        .collect()
}

fn load_vectors() -> Value {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/kat/v3-vectors.json");
    let raw = fs::read_to_string(path).expect("KAT vector file missing");
    serde_json::from_str(&raw).expect("invalid JSON")
}

#[test]
fn kat_hkdf_rfc5869_tc1() {
    use anonymus_core::crypto::hkdf;

    let vecs = load_vectors();
    let v = &vecs["vectors"][0]; // hkdf-1

    let ikm = hex(v["ikm"].as_str().unwrap());
    let salt = hex(v["salt"].as_str().unwrap());
    let info = hex(v["info"].as_str().unwrap());
    let expected = hex(v["okm"].as_str().unwrap());
    let output_len = v["output_len"].as_u64().unwrap() as usize;

    let derived = hkdf::derive(&ikm, Some(&salt), &info, output_len).unwrap();
    assert_eq!(derived, expected, "HKDF KAT failed for {}", v["id"]);
}

#[test]
fn kat_x25519_rfc7748_tc1() {
    use anonymus_core::crypto::x25519::StaticKeypair;

    let vecs = load_vectors();
    let v = vecs["vectors"]
        .as_array()
        .unwrap()
        .iter()
        .find(|v| v["id"] == "x25519-1")
        .expect("x25519-1 vector missing");

    let alice_priv: [u8; 32] = hex(v["alice_private"].as_str().unwrap())
        .try_into()
        .unwrap();
    let bob_pub: [u8; 32] = hex(v["bob_public"].as_str().unwrap()).try_into().unwrap();
    let expected: Vec<u8> = hex(v["shared_secret"].as_str().unwrap());

    let alice_kp = StaticKeypair::from_bytes(alice_priv);
    let ss = alice_kp.dh(&bob_pub).unwrap();
    assert_eq!(&ss[..], &expected[..], "X25519 KAT failed");
}

#[test]
fn kat_aead_roundtrip() {
    use anonymus_core::crypto::aead;

    let key = [0u8; 32];
    let nonce = [0u8; 12];
    let plaintext = hex("416e6f6e794d75732076332061656164207465737420766563746f72");
    let aad = b"";

    let ct = aead::encrypt_with_nonce(&key, &nonce, &plaintext, aad).unwrap();
    let pt = aead::decrypt_with_nonce(&key, &nonce, &ct, aad).unwrap();
    assert_eq!(pt, plaintext, "AEAD round-trip KAT failed");
}

#[test]
fn protocol_version_is_3() {
    assert_eq!(anonymus_core::PROTOCOL_VERSION, 3);
}
