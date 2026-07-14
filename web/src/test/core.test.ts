/**
 * Unit tests for the WASM core stub (lib/core.ts).
 *
 * These tests verify that the stub fallback returns correctly shaped output
 * so UI development can proceed without the Rust toolchain.
 */

import { describe, it, expect, vi } from "vitest";

// Mock the WASM pkg so the stub path is taken
vi.mock("../lib/pkg/anonymus_core.js", () => {
  throw new Error("No WASM build");
});

describe("AnonyMus Core loader (stub mode)", () => {
  it("getCore() resolves to an AnonymusCore instance", async () => {
    const { getCore } = await import("../lib/core");
    const core = await getCore();
    expect(core).toBeDefined();
    expect(typeof core.protocolVersion).toBe("function");
  });

  it("protocolVersion returns 3", async () => {
    const { getCore } = await import("../lib/core");
    const core = await getCore();
    expect(core.protocolVersion()).toBe(3);
  });

  it("generateIdentityKeypair returns 32-byte keys", async () => {
    const { getCore } = await import("../lib/core");
    const core = await getCore();
    const { privateKey, publicKey } = core.generateIdentityKeypair();
    expect(privateKey).toBeInstanceOf(Uint8Array);
    expect(publicKey).toBeInstanceOf(Uint8Array);
    expect(privateKey.length).toBe(32);
    expect(publicKey.length).toBe(32);
  });

  it("hkdfDerive returns output of requested length", async () => {
    const { getCore } = await import("../lib/core");
    const core = await getCore();
    const ikm = new Uint8Array(32);
    const info = new TextEncoder().encode("AnonyMus v3");
    const out = core.hkdfDerive(ikm, info, 64);
    expect(out).toBeInstanceOf(Uint8Array);
    expect(out.length).toBe(64);
  });
});
