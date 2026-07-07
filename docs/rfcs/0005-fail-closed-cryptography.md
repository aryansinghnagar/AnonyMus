# RFC 0005: Fail-Closed Cryptography Design

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

In cryptographic systems, failing open or silently swallowing errors is a critical vulnerability. If an encryption helper fails and returns plaintext or default values, it can lead to accidental unencrypted message transmission or information disclosure.

## 2. Goals & Non-Goals

### Goals
- Ensure all cryptographic operations propagate exceptions immediately on failure.
- Prevent default or fall-through plaintext transmissions when encryption errors occur.
- Isolate stack trace outputs to prevent side-channel info leaks.

### Non-Goals
- Attempting automatic cryptographic key recoveries on failure (the session is aborted).

## 3. Design Details

The cryptography module `core/crypto.py` exposes `encrypt_secret` and `decrypt_secret`. If the GCM tag authentication fails, or if data is corrupt, standard cryptography exceptions (`InvalidTag`, `InvalidKey`) are raised and bubble up, rather than returning the raw input or empty strings.

```python
# Code snippet from core/crypto.py showing exception raising
def decrypt_secret(enc_str, key):
    try:
        # Decryption operations...
        # If decryption fails:
    except Exception as e:
        logger.error("Decryption failed")
        raise e  # Must propagate the error
```

## 4. Security & Privacy Implications

- **Side-Channel Protections:** Stack traces and error messages are redacted or sanitized in logs via logging filters to prevent exposing internal buffer parameters or key sizes.
- **Fail-Closed Guarantees:** Assures that any invalid network payloads, replay attempts, or key discrepancies immediately terminate the request.

## 5. Backward Compatibility

Any client receiving a fail-closed response is redirected to the authentication route to reset the key state.
