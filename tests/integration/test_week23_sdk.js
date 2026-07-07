// test_week23_sdk.js — Node.js integration sanity check for @anonymus/client SDK

const assert = require('assert');
const {
  generateKeyPair,
  exportPublicKey,
  importPublicKey,
  computeDH,
  DoubleRatchetSession,
  encryptAESGCM,
  decryptAESGCM,
  fromBase64
} = require('../../packages/typescript-sdk/dist/index.js');

async function runTests() {
  console.log("Starting SDK Cryptographic and Double Ratchet test suite...");

  // 1. Key generation and export/import
  console.log("- Testing X25519 Key Generation...");
  const keys = await generateKeyPair();
  assert.ok(keys.publicKey, "Public key should be defined");
  assert.ok(keys.privateKey, "Private key should be defined");

  const exportedPub = await exportPublicKey(keys.publicKey);
  assert.strictEqual(typeof exportedPub, "string", "Exported public key should be base64 string");
  
  const importedPub = await importPublicKey(exportedPub);
  assert.ok(importedPub, "Should successfully import public key");

  // 2. Symmetric AES-GCM encryption/decryption
  console.log("- Testing AES-GCM Encrypt/Decrypt...");
  const secretKey = new Uint8Array(32);
  for (let i = 0; i < 32; i++) secretKey[i] = i;
  
  const plaintext = "Hello secure AnonyMus client!";
  const encrypted = await encryptAESGCM(secretKey, plaintext);
  assert.ok(encrypted.iv, "Should return initialization vector");
  assert.ok(encrypted.ciphertext, "Should return ciphertext payload");

  const decrypted = await decryptAESGCM(secretKey, encrypted.iv, encrypted.ciphertext);
  assert.strictEqual(decrypted, plaintext, "Decrypted message must match original plaintext");

  // 3. Double Ratchet Alice/Bob simulation
  console.log("- Testing Double Ratchet Handshake and E2EE Message exchange...");
  
  // Create Alice and Bob identity keys
  const aliceIdentity = await generateKeyPair();
  const bobIdentity = await generateKeyPair();
  
  const alicePubExport = await exportPublicKey(aliceIdentity.publicKey);
  const bobPubExport = await exportPublicKey(bobIdentity.publicKey);

  // Compute shared secrets via ECDH
  const aliceSharedBuffer = await computeDH(aliceIdentity.privateKey, bobIdentity.publicKey);
  const bobSharedBuffer = await computeDH(bobIdentity.privateKey, aliceIdentity.publicKey);
  
  const aliceShared = new Uint8Array(aliceSharedBuffer);
  const bobShared = new Uint8Array(bobSharedBuffer);
  assert.deepStrictEqual(aliceShared, bobShared, "Shared secrets derived from DH exchange must match");

  // Initialize ratchets
  const alicePubBytes = fromBase64(alicePubExport);
  const bobPubBytes = fromBase64(bobPubExport);
  
  // Alice initializes Alice session with Bob's public key
  const aliceSession = await DoubleRatchetSession.initAlice(aliceShared, bobPubBytes);
  
  // Bob initializes Bob session with Alice's public key
  const bobIdentityPrivRaw = await globalThis.crypto.subtle.exportKey('pkcs8', bobIdentity.privateKey);
  const bobSession = await DoubleRatchetSession.initBob(bobShared, new Uint8Array(bobIdentityPrivRaw));

  // --- Alice sends message 1 to Bob ---
  const encResult1 = await aliceSession.encrypt();
  const msgText1 = "Hey Bob, this is Alice writing via the TypeScript SDK!";
  const cipher1 = await encryptAESGCM(encResult1.messageKey, msgText1);

  // Bob decrypts message 1
  const bobMsgKey1 = await bobSession.decrypt(encResult1.myPubBytes, encResult1.seq, encResult1.prevChainLen);
  const bobDecrypted1 = await decryptAESGCM(bobMsgKey1, cipher1.iv, cipher1.ciphertext);
  assert.strictEqual(bobDecrypted1, msgText1, "Bob failed to decrypt Alice's first message");

  // --- Bob replies with message 2 to Alice ---
  const encResult2 = await bobSession.encrypt();
  const msgText2 = "Hi Alice! The TypeScript SDK double ratchet is fully working!";
  const cipher2 = await encryptAESGCM(encResult2.messageKey, msgText2);

  // Alice decrypts message 2
  const aliceMsgKey2 = await aliceSession.decrypt(encResult2.myPubBytes, encResult2.seq, encResult2.prevChainLen);
  const aliceDecrypted2 = await decryptAESGCM(aliceMsgKey2, cipher2.iv, cipher2.ciphertext);
  assert.strictEqual(aliceDecrypted2, msgText2, "Alice failed to decrypt Bob's reply message");

  console.log("\nALL SDK INTEGRATION SANITY TESTS PASSED SUCCESSFULLY! (OK)");
}

runTests().catch(err => {
  console.error("Test execution failed:", err);
  process.exit(1);
});
