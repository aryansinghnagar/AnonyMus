// Placeholder for anonymus-core WASM build.
// This file satisfies Vite/TypeScript compile-time import analysis when the WASM is not yet built.
// When compiled via wasm-pack, this file is overwritten with the actual generated JS wrapper.

export default async function init() {
  throw new Error("WASM not initialized");
}

export function generateIdentityKeypair() {
  throw new Error("WASM not initialized");
}

export function x25519Dh() {
  throw new Error("WASM not initialized");
}

export function aeadEncrypt() {
  throw new Error("WASM not initialized");
}

export function aeadDecrypt() {
  throw new Error("WASM not initialized");
}

export function hkdfDerive() {
  throw new Error("WASM not initialized");
}

export function ed25519Verify() {
  throw new Error("WASM not initialized");
}

export function protocolVersion() {
  return 3;
}
