const fs = require('fs');
const path = require('path');
const vm = require('vm');

// Simple polyfill for atob/btoa if needed in older node
if (typeof btoa === 'undefined') {
  global.btoa = function (str) {
    return Buffer.from(str, 'binary').toString('base64');
  };
}
if (typeof atob === 'undefined') {
  global.atob = function (b64Encoded) {
    return Buffer.from(b64Encoded, 'base64').toString('binary');
  };
}

// Ensure crypto is available
if (typeof crypto === 'undefined' || !crypto.subtle) {
  try {
    global.crypto = require('crypto').webcrypto;
  } catch (err) {
    console.error("Web Crypto API not available. Node >= 15 is required.");
    process.exit(1);
  }
}

const cryptoJsPath = path.join(__dirname, '..', '..', '..', 'web', 'static', 'crypto.js');
const cryptoCode = fs.readFileSync(cryptoJsPath, 'utf8');

// Load crypto.js into the global context
vm.runInThisContext(cryptoCode);

async function runTests() {
  let passed = 0;
  let failed = 0;

  function assertEqual(actual, expected, msg) {
    if (actual === expected) {
      console.log(`[PASS] ${msg}`);
      passed++;
    } else {
      console.error(`[FAIL] ${msg}: Expected '${expected}', got '${actual}'`);
      failed++;
    }
  }

  try {
    console.log("Generating keys...");
    const keysA = await generateKeyPair();
    const pubA = await exportPublicKey(keysA.publicKey);
    
    const keysB = await generateKeyPair();
    const pubB = await exportPublicKey(keysB.publicKey);

    // 1. Safety Number Verification
    const sn1 = await computeSafetyNumber(pubA, pubB);
    const sn2 = await computeSafetyNumber(pubB, pubA);
    assertEqual(sn1, sn2, "Safety numbers match for both parties");
    assertEqual(sn1.length, 71, "Safety number has correct length (64 hex + 7 dashes)");
    
    // Test 256-bit utilization
    if (sn1.split('-').length === 8) {
      console.log(`[PASS] Safety number utilizes all 256 bits (8 chunks of 8 hex chars)`);
      passed++;
    } else {
      console.error(`[FAIL] Safety number does not utilize all 256 bits: ${sn1}`);
      failed++;
    }

    // 2. Encryption/Decryption Round Trip
    const importedPubB = await importPublicKey(pubB);
    const sessionKeysA = await deriveSessionKeys(keysA.privateKey, importedPubB, pubA, pubB);

    const importedPubA = await importPublicKey(pubA);
    const sessionKeysB = await deriveSessionKeys(keysB.privateKey, importedPubA, pubB, pubA);

    const isAlice = pubA < pubB;
    const roleA = isAlice ? 'A' : 'B';
    const roleB = isAlice ? 'B' : 'A';

    const sessionId = await computeSafetyNumber(pubA, pubB);

    // Derive message keys from the chain keys
    let chainA_send = sessionKeysA.sendChainKey;
    let chainB_recv = sessionKeysB.recvChainKey;

    const { messageKey: msgKeyA_send, nextChainKey: nextChainA_send } = await deriveChainKeys(chainA_send);
    chainA_send = nextChainA_send;

    const { messageKey: msgKeyB_recv, nextChainKey: nextChainB_recv } = await deriveChainKeys(chainB_recv);
    chainB_recv = nextChainB_recv;

    // Normal message
    const msg1 = "Hello World!";
    const enc1 = await encryptMessage(msgKeyA_send, msg1, roleA, 0, sessionId);
    const dec1 = await decryptMessage(msgKeyB_recv, enc1.iv, enc1.ciphertext, roleA, 0, sessionId);
    assertEqual(dec1, msg1, "Standard message round-trips perfectly");

    // Message with trailing spaces (the bug fix)
    let chainB_send = sessionKeysB.sendChainKey;
    let chainA_recv = sessionKeysA.recvChainKey;

    const { messageKey: msgKeyB_send, nextChainKey: nextChainB_send } = await deriveChainKeys(chainB_send);
    chainB_send = nextChainB_send;

    const { messageKey: msgKeyA_recv, nextChainKey: nextChainA_recv } = await deriveChainKeys(chainA_recv);
    chainA_recv = nextChainA_recv;

    const msg2 = "Hello trailing spaces    ";
    const enc2 = await encryptMessage(msgKeyB_send, msg2, roleB, 0, sessionId);
    const dec2 = await decryptMessage(msgKeyA_recv, enc2.iv, enc2.ciphertext, roleB, 0, sessionId);
    assertEqual(dec2, msg2, "Message with trailing spaces round-trips perfectly");

    // Test sequence number mismatch (should fail to decrypt)
    const { messageKey: msgKeyA_send2, nextChainKey: nextChainA_send2 } = await deriveChainKeys(chainA_send);
    chainA_send = nextChainA_send2;

    const { messageKey: msgKeyB_recv2, nextChainKey: nextChainB_recv2 } = await deriveChainKeys(chainB_recv);
    chainB_recv = nextChainB_recv2;

    const enc3 = await encryptMessage(msgKeyA_send2, "Replay test", roleA, 1, sessionId);
    const dec3 = await decryptMessage(msgKeyB_recv2, enc3.iv, enc3.ciphertext, roleA, 2, sessionId);
    assertEqual(dec3, null, "Decryption fails when sequence numbers mismatch");

  } catch (err) {
    console.error("Test execution failed:", err);
    failed++;
  }

  console.log(`\nTests finished. Passed: ${passed}, Failed: ${failed}`);
  if (failed > 0) process.exit(1);
}

runTests();
