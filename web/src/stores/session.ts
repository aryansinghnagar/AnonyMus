/**
 * Session store — authentication state and current user.
 *
 * Uses Solid.js reactive primitives for fine-grained reactivity.
 */

import { createSignal } from "solid-js";
import { auth, node, type User } from "@lib/api";
import { loadIdentityKey, storeIdentityKey } from "@lib/keystore";
import { getCore } from "@lib/core";

const [user, setUser] = createSignal<User | null>(null);
const [loading, setLoading] = createSignal(true);
const [authError, setAuthError] = createSignal<string | null>(null);

export { user, loading, authError };

async function ensureIdentityKeyInitialized(): Promise<void> {
  const identity = await loadIdentityKey();
  if (!identity) {
    const core = await getCore();
    const kp = core.generateIdentityKeypair();
    await storeIdentityKey(kp.privateKey, kp.publicKey);
    console.log("[Identity] New identity keypair initialized in IndexedDB");
  }
}

/** Load the current user from the session cookie on page load. */
export async function initSession(): Promise<void> {
  try {
    const me = await auth.me();
    setUser(me);
    await ensureIdentityKeyInitialized();
  } catch {
    setUser(null);
  } finally {
    setLoading(false);
  }
}

export async function login(username: string, password: string): Promise<boolean> {
  setAuthError(null);
  try {
    const res = await auth.login(username, password);
    setUser(res);
    await ensureIdentityKeyInitialized();
    return true;
  } catch (e: any) {
    setAuthError(e.detail ?? "Login failed");
    return false;
  }
}

export async function register(username: string, password: string): Promise<boolean> {
  setAuthError(null);
  try {
    await auth.register(username, password);
    // Auto-login after registration
    return login(username, password);
  } catch (e: any) {
    setAuthError(e.detail ?? "Registration failed");
    return false;
  }
}

export async function logout(): Promise<void> {
  await auth.logout().catch(() => {});
  setUser(null);
}

export async function triggerPanicWipe(): Promise<void> {
  const confirmWipe = confirm(
    "WARNING: You are about to initiate the Panic Wipe. This will securely erase all local chats, cryptographic identity keys, and configurations immediately. This action CANNOT BE UNDONE. Proceed?"
  );
  if (!confirmWipe) return;

  try {
    const DB_NAME = "anonymus-keys";
    const req = indexedDB.deleteDatabase(DB_NAME);
    req.onsuccess = () => console.log("[Panic] IndexedDB deleted successfully.");
    req.onerror = () => console.error("[Panic] Failed to delete IndexedDB.");

    localStorage.clear();
    sessionStorage.clear();

    await node.obliviate().catch(() => {});
  } catch (err) {
    console.error("[Panic] Secure wipe failed:", err);
  } finally {
    window.location.href = "/";
  }
}
