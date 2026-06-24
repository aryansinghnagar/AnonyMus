/**
 * crypto.js — End-to-end encryption for the Zero-Knowledge Chat App.
 */

// ---------------------------------------------------------------------------
// Helpers — binary <-> base64 conversion
// ---------------------------------------------------------------------------

function toBase64(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = '';
  const len = bytes.byteLength;
  const chunk_size = 0x8000;
  for (let i = 0; i < len; i += chunk_size) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk_size));
  }
  return btoa(binary);
}

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

async function generateKeyPair() {
  const keyPair = await crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' },
    true,
    ['deriveKey', 'deriveBits']
  );
  return { publicKey: keyPair.publicKey, privateKey: keyPair.privateKey };
}

// ---------------------------------------------------------------------------
// 2. Public key export / import
// ---------------------------------------------------------------------------

async function exportPublicKey(publicKey) {
  const rawKey = await crypto.subtle.exportKey('raw', publicKey);
  return toBase64(rawKey);
}

async function importPublicKey(base64String) {
  const rawKey = fromBase64(base64String);
  return await crypto.subtle.importKey(
    'raw',
    rawKey,
    { name: 'ECDH', namedCurve: 'P-256' },
    true,
    []
  );
}

// ---------------------------------------------------------------------------
// 3. ECDH — deriving the shared secret
// ---------------------------------------------------------------------------

function constructAAD(role, seqNum) {
  const aad = new Uint8Array(5);
  aad[0] = role.charCodeAt(0);
  const view = new DataView(aad.buffer);
  view.setUint32(1, seqNum, false); // Length as 32-bit big-endian
  return aad;
}

async function deriveSessionKeys(myPrivateKey, theirPublicKey, myPubKeyB64, theirPubKeyB64) {
  const sharedSecretBits = await crypto.subtle.deriveBits(
    { name: 'ECDH', public: theirPublicKey },
    myPrivateKey,
    256
  );

  const hkdfKey = await crypto.subtle.importKey(
    'raw',
    sharedSecretBits,
    { name: 'HKDF' },
    false,
    ['deriveKey']
  );

  const salt = new Uint8Array(32); // 32 zero bytes
  const labelClient = new TextEncoder().encode("AnonyMus-Client-To-Server-Key");
  const labelServer = new TextEncoder().encode("AnonyMus-Server-To-Client-Key");

  const clientKey = await crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: salt,
      info: labelClient
    },
    hkdfKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );

  const serverKey = await crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: salt,
      info: labelServer
    },
    hkdfKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );

  const isAlice = myPubKeyB64 < theirPubKeyB64;
  return {
    writeKey: isAlice ? clientKey : serverKey,
    readKey: isAlice ? serverKey : clientKey
  };
}

// ---------------------------------------------------------------------------
// 4. Safety Number Derivation (Phase 2)
// ---------------------------------------------------------------------------

async function computeSafetyNumber(myPubKeyB64, theirPubKeyB64) {
  // Sort them to ensure both parties compute the exact same hash
  const sorted = [myPubKeyB64, theirPubKeyB64].sort();
  const data = new TextEncoder().encode(sorted[0] + sorted[1]);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  
  // Use all 256 bits formatted as hex chunks
  const hex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  let chunks = [];
  for (let i = 0; i < hex.length; i += 8) {
    chunks.push(hex.slice(i, i + 8));
  }
  return chunks.join('-');
}

// ---------------------------------------------------------------------------
// 5. AES-GCM — encrypting and decrypting messages with Length-Prefixed Padding
// ---------------------------------------------------------------------------

const BLOCK_SIZE = 512;

async function encryptMessage(key, plaintext, role, seqNum) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const textBytes = new TextEncoder().encode(plaintext);
  const textLen = textBytes.length;
  
  // Padding logic: pad to nearest multiple of BLOCK_SIZE with random bytes
  let paddedLength = Math.ceil((textLen + 4) / BLOCK_SIZE) * BLOCK_SIZE;
  const paddedBuffer = new Uint8Array(paddedLength);
  
  const view = new DataView(paddedBuffer.buffer);
  view.setUint32(0, textLen, false); // Length as 32-bit big-endian
  
  paddedBuffer.set(textBytes, 4);
  
  // Add random padding
  if (paddedLength > textLen + 4) {
    const paddingBytes = new Uint8Array(paddedLength - textLen - 4);
    crypto.getRandomValues(paddingBytes);
    paddedBuffer.set(paddingBytes, textLen + 4);
  }

  const aad = constructAAD(role, seqNum);

  const encryptedBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: aad },
    key,
    paddedBuffer
  );

  return {
    iv: toBase64(iv),
    ciphertext: toBase64(encryptedBuffer)
  };
}

async function decryptMessage(key, ivBase64, ciphertextBase64, role, seqNum) {
  try {
    const iv = fromBase64(ivBase64);
    const ciphertext = fromBase64(ciphertextBase64);
    const aad = constructAAD(role, seqNum);

    const decryptedBuffer = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv, additionalData: aad },
      key,
      ciphertext
    );

    const view = new DataView(decryptedBuffer);
    const textLen = view.getUint32(0, false);
    
    // Safety check to prevent out-of-bounds error
    if (textLen > decryptedBuffer.byteLength - 4) {
      return null;
    }
    
    const textBytes = new Uint8Array(decryptedBuffer, 4, textLen);
    return new TextDecoder().decode(textBytes);
  } catch (err) {
    console.error('decryptMessage: decryption failed', err);
    return null;
  }
}
