/**
 * AnonyMus Core WASM loader.
 *
 * Lazily loads the anonymus-core WASM module built from core/rust with:
 *   wasm-pack build core/rust --target web --features wasm --out-dir web/src/pkg
 *
 * Falls back gracefully when the WASM module is not yet built (dev mode
 * without a Rust toolchain) by providing stub implementations so the UI
 * remains functional for layout/UX development.
 */

import { createSignal } from "solid-js";

export interface AnonymusCore {
  generateIdentityKeypair(): { privateKey: Uint8Array; publicKey: Uint8Array };
  x25519Dh(privateKey: Uint8Array, peerPublicKey: Uint8Array): Uint8Array;
  aeadEncrypt(key: Uint8Array, plaintext: Uint8Array): Uint8Array;
  aeadDecrypt(key: Uint8Array, blob: Uint8Array): Uint8Array;
  hkdfDerive(ikm: Uint8Array, info: Uint8Array, outputLen: number, salt?: Uint8Array): Uint8Array;
  ed25519Verify(publicKey: Uint8Array, message: Uint8Array, signature: Uint8Array): void;
  protocolVersion(): number;
}

const [isStub, setIsStub] = createSignal(false);
export { isStub };

let _core: AnonymusCore | null = null;
let _loadPromise: Promise<AnonymusCore> | null = null;

async function loadWasmCore(): Promise<AnonymusCore> {
  try {
    // Dynamic import — only works after wasm-pack build
    const pkg = await import("./pkg/anonymus_core.js");
    await pkg.default(); // initialise the WASM module
    setIsStub(false);
    return pkg as unknown as AnonymusCore;
  } catch (err) {
    if (import.meta.env?.PROD) {
      console.error("[AnonyMus] WASM core could not be loaded in production build!", err);
      throw new Error("WASM core is missing or failed to initialize in production environment.");
    }
    console.warn(
      "[AnonyMus] WASM core not found — using stub. Run `npm run wasm:build` to build it."
    );
    setIsStub(true);
    return getStubCore();
  }
}

/** Get (or initialise) the singleton core instance. */
export async function getCore(): Promise<AnonymusCore> {
  if (_core) return _core;
  if (!_loadPromise) _loadPromise = loadWasmCore();
  _core = await _loadPromise;
  return _core;
}

// ── Stub implementation for development without Rust toolchain ────────────────

function getStubCore(): AnonymusCore {
  const warn = (fn: string) =>
    console.warn(`[AnonyMus stub] ${fn} called — using dummy output`);

  return {
    generateIdentityKeypair() {
      warn("generateIdentityKeypair");
      return { privateKey: new Uint8Array(32), publicKey: new Uint8Array(32) };
    },
    x25519Dh(_privateKey, _peerPublicKey) {
      warn("x25519Dh");
      return new Uint8Array(32);
    },
    aeadEncrypt(_key, plaintext) {
      warn("aeadEncrypt");
      // Return nonce(12) + plaintext for stub passthrough
      const out = new Uint8Array(12 + plaintext.length);
      out.set(plaintext, 12);
      return out;
    },
    aeadDecrypt(_key, blob) {
      warn("aeadDecrypt");
      return blob.slice(12); // strip fake nonce
    },
    hkdfDerive(_ikm, _info, outputLen) {
      warn("hkdfDerive");
      return new Uint8Array(outputLen);
    },
    ed25519Verify(_publicKey, _message, _signature) {
      warn("ed25519Verify");
      // Stub: always passes
    },
    protocolVersion() {
      return 3;
    },
  };
}
