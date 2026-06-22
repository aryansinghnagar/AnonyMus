# AnonyMus Master Debug Plan & Roast

Look, I'm going to be straight with you. You asked me to tear this project apart, and my god, did you leave me a feast. You've built a "Zero-Knowledge Chat App" that somehow manages to have zero knowledge of how cross-platform cryptography or basic scalable architecture actually works. 

This codebase is a ticking time bomb of mismatched encryption, memory leaks, and amateur hour security flaws. But hey, you asked for it. Put your big boy pants on, because we're going to fix this absolute dumpster fire. 

Below is the master task list. Feed this to an AI, or fix it yourself if you hate your free time.

## 🚨 CRITICAL PRIORITY: Cross-Platform Cryptographic Failures

Your Web client and Android client are literally speaking two different languages while pretending to use the same encryption. If a Web user talks to an Android user, every single message will fail to decrypt. It's a spectacular failure of protocol design.

- [ ] **TASK 1: Unify the AES-GCM Padding Scheme**
  - **The Flaw:** In `crypto.js`, you implemented a 4-byte big-endian length prefix followed by random padding bytes. In Android's `crypto_utils.kt`, you just pad the string with spaces (`' '`) to a multiple of 512! If Android sends a message to Web, Web reads the first 4 bytes of text ("Hell") as a 32-bit integer length (1.2 GB) and crashes/fails. If Web sends to Android, Android decodes unprintable length bytes and random padding as text.
  - **The Fix:** Pick ONE standard padding scheme. The Length-Prefixed Binary + Random Padding scheme in JS is superior. Implement the exact same `ByteBuffer` parsing in Kotlin: write 4-bytes length, write text, fill the rest with `SecureRandom` bytes.

- [ ] **TASK 2: Fix the Safety Number Calculation**
  - **The Flaw:** The whole point of a Safety Number is that both users compare it to prevent Man-in-the-Middle attacks. In `chat.js`, you convert the SHA-256 hash to a **Hex string** and group by 8 characters. In Android, you convert the hash to a **Decimal string** (`toString(10)`) and group by 4 characters. They will NEVER match.
  - **The Fix:** Standardize on the Web implementation. In Kotlin, map the SHA-256 byte array to a hex string (`%02x`), split it into 8-character chunks, and join with hyphens.

- [ ] **TASK 3: Implement HKDF for the Shared Secret**
  - **The Flaw:** You take the raw ECDH output and use it *directly* as an AES-256 key. This is a massive cryptographic sin. ECDH outputs are not uniformly distributed. 
  - **The Fix:** Pass the ECDH shared secret through HKDF (HMAC-based Extract-and-Expand Key Derivation Function) to derive the actual AES-256 key. Do this in both WebCrypto (`deriveBits` -> `HKDF`) and Android (`javax.crypto.Mac` or a library like BouncyCastle).

- [ ] **TASK 4: Separate Send/Receive Keys & Prevent Replay Attacks**
  - **The Flaw:** Both users use the exact same key for sending and receiving. If an attacker intercepts an encrypted payload, they can just replay it back into the queue. The receiver will happily decrypt it because AES-GCM only authenticates the ciphertext.
  - **The Fix:** Sort the public keys to determine who is "Alice" and "Bob". Use HKDF to derive TWO separate keys: `client_write_key` and `server_write_key`. Also, embed a sequence number or timestamp in the AES-GCM AAD (Additional Authenticated Data) to reject replay attacks.

## 🏗️ HIGH PRIORITY: Architectural & Backend Flaws

Your backend is currently held together by duct tape and prayers. 

- [ ] **TASK 5: Rip Out In-Memory Queues**
  - **The Flaw:** In `server.py`, `queues` and `sid_to_queues` are global memory dictionaries. The moment you deploy this to production using Gunicorn/uWSGI with multiple workers, requests will hit different workers. Peer A on Worker 1 will never be able to connect to Peer B on Worker 2. Your Zero-Knowledge chat is currently Zero-Scaling.
  - **The Fix:** Use a message broker like Redis. Flask-SocketIO natively supports Redis as a message queue. Move your `queues` tracking into Redis so any worker can route a message to any client.

- [ ] **TASK 6: Stop Sending Magic Strings as Plaintext**
  - **The Flaw:** `__PSYCHOHISTORICAL_STATIC__` and `__OBLIVIATE__` are sent as standard text messages. If a user maliciously (or accidentally) types `__OBLIVIATE__` in the chat, it will remotely wipe the peer's chat and trigger an Infinity Snap.
  - **The Fix:** Move control signals OUT of the plaintext. Use a structured JSON payload *inside* the encryption envelope. e.g., `{"type": "control", "action": "obliviate"}` vs `{"type": "text", "content": "Hello"}`.

- [ ] **TASK 7: Fix Flask Secret Key Management**
  - **The Flaw:** `app.secret_key = os.environ.get('FLASK_SECRET_KEY')`. If this is weak or accidentally committed in an `.env` file, your entire session management is compromised.
  - **The Fix:** Add a fallback mechanism that generates a cryptographically secure random key on startup (`os.urandom(32)`) if the environment variable isn't set (though this invalidates sessions on restart, it's better than crashing or using a default). Ensure the key is properly rotated.

- [ ] **TASK 8: Session Fixation Mitigation is Weak**
  - **The Flaw:** `session.clear()` followed by `session['username'] = username` is an okay start, but it relies on Flask's default client-side session cookie generation. 
  - **The Fix:** Explicitly rotate the session identifier on login. Even better, stop using cookie-based sessions for a zero-knowledge app. Issue short-lived JWTs or rely entirely on the secure WebSocket channel.

## 📱 MEDIUM PRIORITY: Android App Specific Issues

Your Android app is trying to be secure, but it's shooting itself in the foot.

- [ ] **TASK 9: Infinity Snap Fails to Wipe State**
  - **The Flaw:** `infinitySnap()` in `chat_manager.kt` brutally kills the process (`android.os.Process.killProcess`), which is already bad practice. Worse, it NEVER clears `prefs.sessionCookie`! When the user restarts the app, it happily auto-logs them back in.
  - **The Fix:** Properly clear all SharedPreferences, nullify all memory state, and use standard Intent routing to kick the user back to the AuthScreen instead of murdering the PID.

- [ ] **TASK 10: Unsafe SSL TrustManager is Too Broad**
  - **The Flaw:** When `trustSelfSigned` is true, you blindly accept ALL certificates. This opens the app to complete MITM attacks on the transport layer, effectively relying *only* on the end-to-end encryption.
  - **The Fix:** Implement Trust-On-First-Use (TOFU) or pin the specific self-signed certificate hash, rather than a blanket "trust everything" policy.

## 🌐 MEDIUM PRIORITY: Web App Specific Issues

- [ ] **TASK 11: Stop Spamming Clipboard Permissions**
  - **The Flaw:** `navigator.clipboard.readText()` runs in the background to auto-clear the clipboard. Browsers despise this and will block it or constantly spam the user with permission prompts.
  - **The Fix:** Only clear the clipboard if you wrote to it in the first place, or use a simpler timeout-based `writeText('')` without trying to read it first.

- [ ] **TASK 12: Incomplete CSP (Content Security Policy)**
  - **The Flaw:** You restrict `script-src` to `'self'` and `cdn.socket.io`, but you need to ensure `unsafe-eval` is explicitly blocked. 
  - **The Fix:** Ensure the CSP header strictly prevents any XSS vectors. Add stricter `frame-ancestors` and `form-action` directives.

## Final Thoughts
This project has an awesome concept—a zero-knowledge, disappearing chat protocol with panic buttons. But the execution is currently a mess of incompatible cryptography and state-management disasters. Stop building features, start fixing the foundation. Work through this list one by one. I'm watching you.
