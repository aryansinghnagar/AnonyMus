/**
 * crypto.js — End-to-end encryption for AnonyMus (v2 Unified Architecture).
 * Supports X25519 Double Ratchet and tweetnacl.js queue cryptobox.
 */

// ---------------------------------------------------------------------------
// Helpers — binary <-> base64 <-> hex conversion
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

function toHex(arrayBuffer) {
  return Array.prototype.map.call(new Uint8Array(arrayBuffer), x => ('00' + x.toString(16)).slice(-2)).join('');
}

function fromHex(hexString) {
  const bytes = new Uint8Array(hexString.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hexString.substr(i * 2, 2), 16);
  }
  return bytes;
}

function equals(a, b) {
  if (a.byteLength !== b.byteLength) return false;
  for (let i = 0; i < a.byteLength; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function getRawPrivateKey(pkcs8) {
  const arr = new Uint8Array(pkcs8);
  return arr.slice(-32);
}

// ---------------------------------------------------------------------------
// 1. Key pair generation
// ---------------------------------------------------------------------------

async function generateKeyPair() {
  const keyPair = await crypto.subtle.generateKey(
    { name: 'X25519' },
    true,
    ['deriveKey', 'deriveBits']
  );
  return { publicKey: keyPair.publicKey, privateKey: keyPair.privateKey };
}

// ---------------------------------------------------------------------------
// 2. Public / Private key export / import
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
    { name: 'X25519' },
    true,
    []
  );
}

async function computeDH(privateKey, publicKey) {
  return await crypto.subtle.deriveBits(
    { name: 'X25519', public: publicKey },
    privateKey,
    256
  );
}

async function hkdfDerive512(ikm, info, salt = new Uint8Array(32)) {
  const hkdfKey = await crypto.subtle.importKey(
    'raw',
    ikm,
    { name: 'HKDF' },
    false,
    ['deriveKey', 'deriveBits']
  );
  return await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: salt,
      info: info
    },
    hkdfKey,
    512
  );
}

// ---------------------------------------------------------------------------
// 3. Double Ratchet Implementation
// ---------------------------------------------------------------------------

class DoubleRatchetSession {
  constructor() {
    this.dhPrivateKey = null;
    this.dhPublicKey = null;
    this.dhRemotePublicKey = null;
    this.rootKey = null;
    this.sendingChainKey = null;
    this.receivingChainKey = null;
    this.seqSend = 0;
    this.seqRecv = 0;
    this.prevChainLength = 0;
    this.skippedMessageKeys = {}; // { "peer_dh_b64_seq": "key_hex" }
  }

  static async initAlice(sharedSecret, peerDhPubBytes) {
    const session = new DoubleRatchetSession();
    const keyPair = await generateKeyPair();
    session.dhPrivateKey = keyPair.privateKey;
    session.dhPublicKey = keyPair.publicKey;
    session.dhRemotePublicKey = await crypto.subtle.importKey(
      'raw',
      peerDhPubBytes,
      { name: 'X25519' },
      true,
      []
    );
    
    const dhOut = await computeDH(session.dhPrivateKey, session.dhRemotePublicKey);
    const derived = await hkdfDerive512(dhOut, new TextEncoder().encode("AnonyMus-DR-RootRatchet"), sharedSecret);
    
    session.rootKey = new Uint8Array(derived.slice(0, 32));
    session.sendingChainKey = new Uint8Array(derived.slice(32, 64));
    session.receivingChainKey = null;
    return session;
  }

  static async initBob(sharedSecret, myDhPrivBytes) {
    const session = new DoubleRatchetSession();
    session.dhPrivateKey = await crypto.subtle.importKey(
      'pkcs8',
      myDhPrivBytes,
      { name: 'X25519' },
      true,
      ['deriveKey', 'deriveBits']
    );
    session.dhRemotePublicKey = null;
    session.rootKey = sharedSecret;
    session.sendingChainKey = null;
    session.receivingChainKey = null;
    return session;
  }

  async encrypt() {
    const derived = await hkdfDerive512(new Uint8Array(32), new TextEncoder().encode("AnonyMus-DR-ChainRatchet"), this.sendingChainKey);
    const messageKey = new Uint8Array(derived.slice(0, 32));
    this.sendingChainKey = new Uint8Array(derived.slice(32, 64));
    
    const myPubBytes = new Uint8Array(await crypto.subtle.exportKey('raw', this.dhPublicKey || this.dhPrivateKey.publicKey));
    const seq = this.seqSend;
    this.seqSend += 1;
    return { messageKey, myPubBytes, seq, prevChainLen: this.prevChainLength };
  }

  async decrypt(peerDhPubBytes, seq, prevChainLen) {
    const peerB64 = toBase64(peerDhPubBytes);
    const skipKey = `${peerB64}_${seq}`;
    
    if (this.skippedMessageKeys[skipKey]) {
      const keyHex = this.skippedMessageKeys[skipKey];
      delete this.skippedMessageKeys[skipKey];
      return fromHex(keyHex);
    }
    
    const peerDhPub = await crypto.subtle.importKey(
      'raw',
      peerDhPubBytes,
      { name: 'X25519' },
      true,
      []
    );
    
    let dhChanged = false;
    const currentRemoteBytes = this.dhRemotePublicKey ? new Uint8Array(await crypto.subtle.exportKey('raw', this.dhRemotePublicKey)) : null;
    
    if (!currentRemoteBytes || !equals(currentRemoteBytes, peerDhPubBytes)) {
      await this.skipMessages(prevChainLen);
      
      this.dhRemotePublicKey = peerDhPub;
      const dhOut1 = await computeDH(this.dhPrivateKey, this.dhRemotePublicKey);
      const derived1 = await hkdfDerive512(dhOut1, new TextEncoder().encode("AnonyMus-DR-RootRatchet"), this.rootKey);
      this.rootKey = new Uint8Array(derived1.slice(0, 32));
      this.receivingChainKey = new Uint8Array(derived1.slice(32, 64));
      
      const keyPair = await generateKeyPair();
      this.dhPrivateKey = keyPair.privateKey;
      this.dhPublicKey = keyPair.publicKey;
      
      const dhOut2 = await computeDH(this.dhPrivateKey, this.dhRemotePublicKey);
      const derived2 = await hkdfDerive512(dhOut2, new TextEncoder().encode("AnonyMus-DR-RootRatchet"), this.rootKey);
      this.rootKey = new Uint8Array(derived2.slice(0, 32));
      this.sendingChainKey = new Uint8Array(derived2.slice(32, 64));
      
      this.prevChainLength = this.seqSend;
      this.seqSend = 0;
      this.seqRecv = 0;
      dhChanged = true;
    }
    
    await this.skipMessages(seq);
    
    const derived = await hkdfDerive512(new Uint8Array(32), new TextEncoder().encode("AnonyMus-DR-ChainRatchet"), this.receivingChainKey);
    const messageKey = new Uint8Array(derived.slice(0, 32));
    this.receivingChainKey = new Uint8Array(derived.slice(32, 64));
    this.seqRecv += 1;
    
    return messageKey;
  }

  async skipMessages(untilSeq) {
    if (!this.receivingChainKey) return;
    if (this.seqRecv + 100 < untilSeq) {
      throw new Error("Too many skipped messages");
    }
    while (this.seqRecv < untilSeq) {
      const derived = await hkdfDerive512(new Uint8Array(32), new TextEncoder().encode("AnonyMus-DR-ChainRatchet"), this.receivingChainKey);
      const msgKey = new Uint8Array(derived.slice(0, 32));
      this.receivingChainKey = new Uint8Array(derived.slice(32, 64));
      
      const peerPubBytes = new Uint8Array(await crypto.subtle.exportKey('raw', this.dhRemotePublicKey));
      const peerB64 = toBase64(peerPubBytes);
      const skipKey = `${peerB64}_${this.seqRecv}`;
      this.skippedMessageKeys[skipKey] = toHex(msgKey);
      this.seqRecv += 1;
    }
  }
}

async function serializeSession(session) {
  if (!session) return null;
  const privB64 = session.dhPrivateKey ? toBase64(await crypto.subtle.exportKey('pkcs8', session.dhPrivateKey)) : null;
  const pubB64 = session.dhPublicKey ? toBase64(await crypto.subtle.exportKey('raw', session.dhPublicKey)) : null;
  const remB64 = session.dhRemotePublicKey ? toBase64(await crypto.subtle.exportKey('raw', session.dhRemotePublicKey)) : null;
  
  return JSON.stringify({
    dhPrivateKeyPKCS8: privB64,
    dhPublicKeyRaw: pubB64,
    dhRemotePublicKeyRaw: remB64,
    rootKeyHex: session.rootKey ? toHex(session.rootKey) : null,
    sendingChainKeyHex: session.sendingChainKey ? toHex(session.sendingChainKey) : null,
    receivingChainKeyHex: session.receivingChainKey ? toHex(session.receivingChainKey) : null,
    seqSend: session.seqSend,
    seqRecv: session.seqRecv,
    prevChainLength: session.prevChainLength,
    skippedMessageKeys: session.skippedMessageKeys
  });
}

async function deserializeSession(jsonStr) {
  if (!jsonStr) return null;
  const data = JSON.parse(jsonStr);
  const session = new DoubleRatchetSession();
  
  if (data.dhPrivateKeyPKCS8) {
    session.dhPrivateKey = await crypto.subtle.importKey(
      'pkcs8',
      fromBase64(data.dhPrivateKeyPKCS8),
      { name: 'X25519' },
      true,
      ['deriveKey', 'deriveBits']
    );
  }
  if (data.dhPublicKeyRaw) {
    session.dhPublicKey = await crypto.subtle.importKey(
      'raw',
      fromBase64(data.dhPublicKeyRaw),
      { name: 'X25519' },
      true,
      []
    );
  }
  if (data.dhRemotePublicKeyRaw) {
    session.dhRemotePublicKey = await crypto.subtle.importKey(
      'raw',
      fromBase64(data.dhRemotePublicKeyRaw),
      { name: 'X25519' },
      true,
      []
    );
  }
  if (data.rootKeyHex) session.rootKey = fromHex(data.rootKeyHex);
  if (data.sendingChainKeyHex) session.sendingChainKey = fromHex(data.sendingChainKeyHex);
  if (data.receivingChainKeyHex) session.receivingChainKey = fromHex(data.receivingChainKeyHex);
  
  session.seqSend = data.seqSend || 0;
  session.seqRecv = data.seqRecv || 0;
  session.prevChainLength = data.prevChainLength || 0;
  session.skippedMessageKeys = data.skippedMessageKeys || {};
  return session;
}

// ---------------------------------------------------------------------------
// 4. Safety Number Derivation
// ---------------------------------------------------------------------------

async function computeSafetyNumber(myPubKeyB64, theirPubKeyB64) {
  const sorted = [myPubKeyB64, theirPubKeyB64].sort();
  const data = new TextEncoder().encode(sorted[0] + sorted[1]);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashBytes = new Uint8Array(hashBuffer);

  let groups = [];
  for (let i = 0; i < 30; i += 2.5) {
    const byteIdx = Math.floor(i);
    const val = (hashBytes[byteIdx] << 8) | hashBytes[byteIdx + 1];
    groups.push(String(val % 100000).padStart(5, '0'));
    if (groups.length === 12) break;
  }
  return groups.join(' ');
}

// ---------------------------------------------------------------------------
// 5. Encrypt / Decrypt Message (v2 Layered E2E)
// ---------------------------------------------------------------------------

function constructAAD(role, seqNum, sessionId, protocolVersion = 2) {
  if (protocolVersion === 1) {
    const aad = new Uint8Array(5);
    aad[0] = role.charCodeAt(0);
    const view = new DataView(aad.buffer);
    view.setUint32(1, seqNum, false);
    return aad;
  }
  
  const aad = new Uint8Array(1 + 4 + 16 + 1);
  aad[0] = role.charCodeAt(0);
  const view = new DataView(aad.buffer);
  view.setUint32(1, seqNum, false);
  
  const encoder = new TextEncoder();
  const sessionBytes = encoder.encode(sessionId || "");
  const truncatedSession = new Uint8Array(16);
  truncatedSession.set(sessionBytes.slice(0, 16));
  
  aad.set(truncatedSession, 5);
  aad[21] = protocolVersion;
  return aad;
}

async function encryptMessageV2(drSession, plaintext, role, sessionId, myPrivateKeyObj, peerPublicKeyObj) {
  const { messageKey, myPubBytes, seq, prevChainLen } = await drSession.encrypt();
  
  // 1. Inner AES-GCM Encryption
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const textBytes = new TextEncoder().encode(plaintext);
  const textLen = textBytes.length;
  
  const PADDED_SIZE = 16384;
  let paddedLength = PADDED_SIZE;
  if (textLen + 4 > paddedLength) {
    paddedLength = Math.ceil((textLen + 4) / PADDED_SIZE) * PADDED_SIZE;
  }
  const paddedBuffer = new Uint8Array(paddedLength);
  const view = new DataView(paddedBuffer.buffer);
  view.setUint32(0, textLen, false);
  paddedBuffer.set(textBytes, 4);
  
  if (paddedLength > textLen + 4) {
    const paddingBytes = new Uint8Array(paddedLength - textLen - 4);
    crypto.getRandomValues(paddingBytes);
    paddedBuffer.set(paddingBytes, textLen + 4);
  }

  const aad = constructAAD(role, seq, sessionId, 2);
  const keyObj = await crypto.subtle.importKey(
    'raw',
    messageKey,
    { name: 'AES-GCM' },
    false,
    ['encrypt']
  );

  const innerCiphertextBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: aad },
    keyObj,
    paddedBuffer
  );

  // Combine IV + ciphertext
  const innerPayload = new Uint8Array(12 + innerCiphertextBuffer.byteLength);
  innerPayload.set(iv, 0);
  innerPayload.set(new Uint8Array(innerCiphertextBuffer), 12);

  // 2. Outer NaCl Box Encryption
  const pkcs8 = await crypto.subtle.exportKey('pkcs8', myPrivateKeyObj);
  const myRawPriv = getRawPrivateKey(pkcs8);
  const peerRawPub = new Uint8Array(await crypto.subtle.exportKey('raw', peerPublicKeyObj));
  
  const boxNonce = crypto.getRandomValues(new Uint8Array(24));
  const boxCiphertext = nacl.box(innerPayload, boxNonce, peerRawPub, myRawPriv);

  return {
    nacl_nonce: toBase64(boxNonce),
    nacl_ciphertext: toBase64(boxCiphertext),
    dr_dh_public: toBase64(myPubBytes),
    dr_seq: seq,
    dr_pn: prevChainLen
  };
}

async function decryptMessageV2(drSession, payload, role, sessionId, myPrivateKeyObj, peerPublicKeyObj) {
  const boxNonce = fromBase64(payload.nacl_nonce);
  const boxCiphertext = fromBase64(payload.nacl_ciphertext);
  const drPubBytes = fromBase64(payload.dr_dh_public);
  const drSeq = parseInt(payload.dr_seq);
  const drPn = parseInt(payload.dr_pn);

  // 1. Outer NaCl Box Decryption
  const pkcs8 = await crypto.subtle.exportKey('pkcs8', myPrivateKeyObj);
  const myRawPriv = getRawPrivateKey(pkcs8);
  const peerRawPub = new Uint8Array(await crypto.subtle.exportKey('raw', peerPublicKeyObj));

  const innerPayload = nacl.box.open(boxCiphertext, boxNonce, peerRawPub, myRawPriv);
  if (!innerPayload) {
    console.error("NaCl Cryptobox decryption failed");
    return null;
  }

  // 2. Extract Inner IV & Ciphertext
  const iv = innerPayload.slice(0, 12);
  const innerCiphertext = innerPayload.slice(12);

  // 3. Double Ratchet Step
  const messageKey = await drSession.decrypt(drPubBytes, drSeq, drPn);

  // 4. Inner AES-GCM Decryption
  const aad = constructAAD(role, drSeq, sessionId, 2);
  const keyObj = await crypto.subtle.importKey(
    'raw',
    messageKey,
    { name: 'AES-GCM' },
    false,
    ['decrypt']
  );

  const decryptedBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv, additionalData: aad },
    keyObj,
    innerCiphertext
  );

  const view = new DataView(decryptedBuffer);
  const textLen = view.getUint32(0, false);
  
  if (textLen > decryptedBuffer.byteLength - 4) {
    return null;
  }
  
  const textBytes = new Uint8Array(decryptedBuffer, 4, textLen);
  return new TextDecoder().decode(textBytes);
}

// Backward-compatible decrypt wrapper
async function decryptMessage(keyOrSession, ivBase64, ciphertextBase64, role, seqNum, sessionId, myPrivateKeyObj = null, peerPublicKeyObj = null, payload = null) {
  try {
    if (payload && payload.nacl_ciphertext) {
      return await decryptMessageV2(keyOrSession, payload, role, sessionId, myPrivateKeyObj, peerPublicKeyObj);
    } else {
      // V1 Fallback
      const iv = fromBase64(ivBase64);
      const ciphertext = fromBase64(ciphertextBase64);

      let decryptedBuffer = null;
      try {
        const aadV2 = constructAAD(role, seqNum, sessionId, 2);
        decryptedBuffer = await crypto.subtle.decrypt(
          { name: 'AES-GCM', iv, additionalData: aadV2 },
          keyOrSession, // AES-GCM Key object
          ciphertext
        );
      } catch (v2Error) {
        const aadV1 = constructAAD(role, seqNum, sessionId, 1);
        decryptedBuffer = await crypto.subtle.decrypt(
          { name: 'AES-GCM', iv, additionalData: aadV1 },
          keyOrSession,
          ciphertext
        );
      }

      const view = new DataView(decryptedBuffer);
      const textLen = view.getUint32(0, false);
      if (textLen > decryptedBuffer.byteLength - 4) return null;
      
      const textBytes = new Uint8Array(decryptedBuffer, 4, textLen);
      return new TextDecoder().decode(textBytes);
    }
  } catch (err) {
    console.error("Decryption error:", err);
    return null;
  }
}

// ---------------------------------------------------------------------------
// 6. V1 Symmetric Chain Helpers (relay mode & history replay)
// ---------------------------------------------------------------------------

/**
 * Advances a symmetric chain key one step, producing a per-message AES-GCM
 * key and the next chain key (HKDF-SHA256 KDF).
 */
async function deriveChainKeys(chainKey) {
  const hkdfKey = await crypto.subtle.importKey(
    'raw', chainKey, { name: 'HKDF' }, false, ['deriveBits']
  );
  const salt = new Uint8Array(32);
  const msgBits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt, info: new TextEncoder().encode('AnonyMus-MessageKey') },
    hkdfKey, 256
  );
  const nextBits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt, info: new TextEncoder().encode('AnonyMus-ChainKey') },
    hkdfKey, 256
  );
  const messageKey = await crypto.subtle.importKey('raw', msgBits, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
  return { messageKey, nextChainKey: nextBits };
}

/**
 * V1 AES-GCM encrypt (relay mode + v1 P2P fallback).
 * Returns { iv: base64, ciphertext: base64 }.
 */
async function encryptMessage(messageKey, plaintext, role, seqNum, sessionId) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const textBytes = new TextEncoder().encode(plaintext);
  const textLen = textBytes.length;

  const PADDED_SIZE = 16384;
  let paddedLength = PADDED_SIZE;
  if (textLen + 4 > paddedLength) {
    paddedLength = Math.ceil((textLen + 4) / PADDED_SIZE) * PADDED_SIZE;
  }
  const paddedBuffer = new Uint8Array(paddedLength);
  const view = new DataView(paddedBuffer.buffer);
  view.setUint32(0, textLen, false);
  paddedBuffer.set(textBytes, 4);

  const aad = constructAAD(role, seqNum, sessionId, 1);
  const ciphertextBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: aad },
    messageKey,
    paddedBuffer
  );

  return {
    iv: toBase64(iv),
    ciphertext: toBase64(ciphertextBuffer)
  };
}


// ---------------------------------------------------------------------------
// XFTP Chunk Encryption/Decryption Helpers (10.E.1)
// ---------------------------------------------------------------------------

async function hkdfDerive256(ikm, info, salt = new Uint8Array(32)) {
  const hkdfKey = await crypto.subtle.importKey(
    'raw',
    ikm,
    { name: 'HKDF' },
    false,
    ['deriveBits']
  );
  return await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: salt,
      info: info
    },
    hkdfKey,
    256
  );
}

async function encryptChunk(rawBytes, rawKey) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const aesKey = await crypto.subtle.importKey(
    'raw',
    rawKey,
    { name: 'AES-GCM' },
    false,
    ['encrypt']
  );
  const ciphertextBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    aesKey,
    rawBytes
  );
  const encrypted = new Uint8Array(iv.length + ciphertextBuffer.byteLength);
  encrypted.set(iv, 0);
  encrypted.set(new Uint8Array(ciphertextBuffer), iv.length);
  return encrypted;
}

async function decryptChunk(encryptedBytes, rawKey) {
  const iv = encryptedBytes.subarray(0, 12);
  const ciphertext = encryptedBytes.subarray(12);
  const aesKey = await crypto.subtle.importKey(
    'raw',
    rawKey,
    { name: 'AES-GCM' },
    false,
    ['decrypt']
  );
  return await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    aesKey,
    ciphertext
  );
}

