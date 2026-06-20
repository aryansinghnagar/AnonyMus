/**
 * crypto.js — End-to-end encryption for the chat app.
 *
 * Built entirely on the browser's native Web Crypto API. No external
 * JavaScript libraries.
 *
 * THE FLOW
 * --------
 *   1. On page load, each client calls generateKeyPair() once. The private
 *      key is kept only in memory in this client and is never sent anywhere.
 *   2. Each client exports its public key with exportPublicKey() and sends
 *      the resulting base64 string to the other party over SocketIO.
 *   3. Each client imports the other party's public key with
 *      importPublicKey(), then calls deriveSharedSecret(myPrivateKey,
 *      theirPublicKey). Both sides land on the exact same AES-GCM secret —
 *      the secret itself is never transmitted (this is the ECDH magic).
 *   4. Outgoing messages are run through encryptMessage(sharedSecret, text)
 *      before being sent. Incoming messages are run through
 *      decryptMessage(sharedSecret, iv, ciphertext) after being received.
 *
 * Everything here is async because every Web Crypto operation returns a
 * Promise — callers should `await` these functions.
 */

// ---------------------------------------------------------------------------
// Helpers — binary <-> base64 conversion
// ---------------------------------------------------------------------------
// SocketIO sends text, not raw bytes, so every ArrayBuffer that needs to
// travel over the network (public keys, IVs, ciphertext) gets base64-encoded
// first and decoded back to bytes on the other end.

/**
 * Converts an ArrayBuffer (or typed array) into a base64 string.
 * @param {ArrayBuffer} arrayBuffer
 * @returns {string} base64-encoded string
 */
function toBase64(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Converts a base64 string back into a Uint8Array of raw bytes.
 * @param {string} base64String
 * @returns {Uint8Array}
 */
function fromBase64(base64String) {
  const binary = atob(base64String);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

// ---------------------------------------------------------------------------
// 1. Key pair generation
// ---------------------------------------------------------------------------

/**
 * Generates a fresh ECDH key pair on the P-256 curve.
 * Call this once when the chat page loads. Keep the returned privateKey in
 * a variable that never leaves this client (e.g. don't log it, don't send
 * it, don't store it anywhere persistent).
 *
 * @returns {Promise<{publicKey: CryptoKey, privateKey: CryptoKey}>}
 */
async function generateKeyPair() {
  const keyPair = await crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' },
    true,              // extractable — the public key needs to be exportable
    ['deriveKey']       // this key pair will only ever be used to derive a shared secret
  );
  return { publicKey: keyPair.publicKey, privateKey: keyPair.privateKey };
}

// ---------------------------------------------------------------------------
// 2. Public key export / import (for sending over SocketIO as plain text)
// ---------------------------------------------------------------------------

/**
 * Exports a public CryptoKey to a base64 string so it can be sent as a
 * normal text field in a SocketIO event.
 * @param {CryptoKey} publicKey
 * @returns {Promise<string>} base64-encoded raw public key
 */
async function exportPublicKey(publicKey) {
  const rawKey = await crypto.subtle.exportKey('raw', publicKey);
  return toBase64(rawKey);
}

/**
 * Imports a base64-encoded public key (received from the other party over
 * SocketIO) back into a usable CryptoKey object.
 * @param {string} base64String
 * @returns {Promise<CryptoKey>}
 */
async function importPublicKey(base64String) {
  const rawKey = fromBase64(base64String);
  return await crypto.subtle.importKey(
    'raw',
    rawKey,
    { name: 'ECDH', namedCurve: 'P-256' },
    true,   // extractable
    []      // a public key isn't used to derive on its own — no usages needed
  );
}

// ---------------------------------------------------------------------------
// 3. ECDH — deriving the shared secret
// ---------------------------------------------------------------------------

/**
 * Combines my private key with their public key to derive the shared
 * AES-GCM secret. Run with the roles reversed on the other client and the
 * result is mathematically identical — without the secret ever crossing
 * the network.
 *
 * @param {CryptoKey} myPrivateKey   - my own private key (from generateKeyPair)
 * @param {CryptoKey} theirPublicKey - the other party's public key (from importPublicKey)
 * @returns {Promise<CryptoKey>} an AES-GCM CryptoKey, ready to encrypt/decrypt with
 */
async function deriveSharedSecret(myPrivateKey, theirPublicKey) {
  return await crypto.subtle.deriveKey(
    { name: 'ECDH', public: theirPublicKey },
    myPrivateKey,
    { name: 'AES-GCM', length: 256 },
    false,                  // not extractable — the raw secret should never leave this CryptoKey
    ['encrypt', 'decrypt']
  );
}

// ---------------------------------------------------------------------------
// 4. AES-GCM — encrypting and decrypting messages
// ---------------------------------------------------------------------------

/**
 * Encrypts a plaintext chat message with the shared secret.
 * A fresh random IV is generated for every single message — this is
 * required for AES-GCM to stay secure (never reuse an IV with the same key).
 *
 * @param {CryptoKey} sharedSecret - AES-GCM key from deriveSharedSecret
 * @param {string} plaintext       - the chat message to encrypt
 * @returns {Promise<{iv: string, ciphertext: string}>} both fields base64-encoded, safe to send over SocketIO
 */
async function encryptMessage(sharedSecret, plaintext) {
  const iv = crypto.getRandomValues(new Uint8Array(12)); // 12 bytes is the standard AES-GCM IV length
  const encodedText = new TextEncoder().encode(plaintext);

  const encryptedBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    sharedSecret,
    encodedText
  );

  return {
    iv: toBase64(iv),
    ciphertext: toBase64(encryptedBuffer)
  };
}

/**
 * Decrypts a message that was encrypted with encryptMessage(), using the
 * same shared secret.
 *
 * Never throws — if decryption fails for any reason (wrong key, tampered
 * ciphertext, corrupted data), it returns null so the chat page never
 * crashes on a bad message.
 *
 * @param {CryptoKey} sharedSecret    - AES-GCM key from deriveSharedSecret
 * @param {string} ivBase64           - the IV that was sent alongside the ciphertext
 * @param {string} ciphertextBase64   - the encrypted message
 * @returns {Promise<string|null>} the original plaintext, or null on failure
 */
async function decryptMessage(sharedSecret, ivBase64, ciphertextBase64) {
  try {
    const iv = fromBase64(ivBase64);
    const ciphertext = fromBase64(ciphertextBase64);

    const decryptedBuffer = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv },
      sharedSecret,
      ciphertext
    );

    return new TextDecoder().decode(decryptedBuffer);
  } catch (err) {
    console.error('decryptMessage: decryption failed', err);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Optional CommonJS export — only activates under Node (e.g. for testing).
// In the browser, `module` is undefined, this block is skipped, and all the
// functions above simply live as globals on the page, as intended.
// ---------------------------------------------------------------------------
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    toBase64,
    fromBase64,
    generateKeyPair,
    exportPublicKey,
    importPublicKey,
    deriveSharedSecret,
    encryptMessage,
    decryptMessage
  };
}
