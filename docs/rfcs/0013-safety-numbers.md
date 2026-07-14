# RFC 0013: Per-Connection Safety Numbers (v3 Truncation Fix)

- **Status:** Approved
- **Author(s):** AnonyMus Contributors
- **Created:** 2026-07-13
- **Updated:** 2026-07-13

---

## 1. Context

This RFC describes the safety number calculation for verified connections. The v3 refactor replaces the legacy 16-byte truncation mechanism with a full 32-byte hash bound to Additional Associated Data (AAD), mitigating collision risks.

## 2. Goals & Non-Goals

### Goals
- Allow out-of-band verification of key continuity.
- Prevent active Man-in-the-Middle (MITM) attacks.
- Format the output as a human-readable series of decimal blocks.

### Non-Goals
- Automated identity updates (verification remains out-of-band/QR-based).

## 3. Design Details

The Safety Number is calculated as:
1. Sort the public keys of User A and User B lexicographically to guarantee determinism regardless of who calculates it.
2. Concatenate: `"SafetyNumberV3" || UserA_ID || UserA_SigningKey || UserA_DHKey || UserB_ID || UserB_SigningKey || UserB_DHKey`.
3. Compute SHA-256 over this payload.
4. Extract 8 blocks of 5-digit decimal strings from the resulting 32-byte digest.

```rust
let digest = Sha256::digest(payload);
let mut sn = String::new();
for i in 0..8 {
    let offset = i * 4;
    let val = u32::from_be_bytes(digest[offset..offset+4]);
    sn.push_str(&format!("{:05} ", val % 100000));
}
```

## 4. Security & Privacy Implications

- **Collision Resistance**: By utilizing the full SHA-256 digest and including usernames, we defend against malicious collision attacks.
- **AAD Binding**: Binds identity public keys directly to the session context.

## 5. Backward Compatibility

- Legacy v1.0 / v2.0 clients used a truncated 16-byte safety number. The v3 protocol will enforce the new 32-byte safety number when `protocolVersion >= 3` is negotiated.
