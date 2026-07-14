# RFC 0015: Message Padding & Size Disguise

- **Status:** Approved
- **Author(s):** AnonyMus Contributors
- **Created:** 2026-07-13
- **Updated:** 2026-07-13

---

## 1. Context

Varying packet lengths allow passive network eavesdroppers to infer the contents of a message using size fingerprinting. This RFC defines standard PKCS#7 message padding rules to eliminate length leaks.

## 2. Goals & Non-Goals

### Goals
- Pad message payloads to constant block boundaries before encryption.
- Obfuscate conversational message sizes.

### Non-Goals
- Hide network packet count (mitigated via cover traffic / dummy messaging).

## 3. Design Details

The client applies PKCS#7 padding before passing the plaintext to the AEAD layer:
1. Determine the block boundaries (default: nearest multiple of 128 or 256 bytes).
2. Calculate `pad_len = block_size - (payload.len() % block_size)`.
3. Append `pad_len` bytes, each carrying the value of `pad_len`.
4. Decryption removes these trailing padding bytes by checking the final byte value.

## 4. Security & Privacy Implications

- **Traffic Analysis Resistance**: Since all messages are rounded to identical block boundaries (e.g. 128 bytes, 256 bytes), eavesdroppers cannot distinguish small text messages, reactions, or emojis based on length.

## 5. Backward Compatibility

- Handled internally by the client wrapper before encryption and after decryption. Plaintext length is preserved.
