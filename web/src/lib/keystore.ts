/**
 * IndexedDB key store for AnonyMus.
 *
 * Fixes the v1.0 bug where cryptographic keys lived in JavaScript variables
 * and were lost on every page reload. All key material is now stored in
 * IndexedDB, which persists across sessions and page reloads.
 *
 * Schema (DB: "anonymus-keys", version: 1):
 *   - store "identity"    — local identity keypair (privateKey, publicKey)
 *   - store "sessions"    — DR session states, keyed by peer onion address
 *   - store "prekeys"     — signed pre-keys and one-time pre-key pool
 *   - store "contacts"    — contact metadata (onion, nickname, verified)
 */

import { openDB, type DBSchema, type IDBPDatabase } from "idb";

// ── DB Schema ──────────────────────────────────────────────────────────────────

interface AnonymusKeyDB extends DBSchema {
  identity: {
    key: string;
    value: { id: string; privateKey: Uint8Array; publicKey: Uint8Array; createdAt: number };
  };
  sessions: {
    key: string; // peer onion address
    value: { onion: string; state: string; updatedAt: number };
  };
  prekeys: {
    key: string;
    value: {
      id: string;
      type: "signed" | "one-time" | "pq";
      keyBytes: Uint8Array;
      signature?: Uint8Array;
      used: boolean;
      createdAt: number;
    };
    indexes: { "by-type": string };
  };
  contacts: {
    key: string; // onion address
    value: {
      onion: string;
      nickname: string;
      displayName: string;
      verified: boolean;
      lastSeen?: number;
      addedAt: number;
    };
  };
}

// ── DB singleton ───────────────────────────────────────────────────────────────

let _db: IDBPDatabase<AnonymusKeyDB> | null = null;

async function getDB(): Promise<IDBPDatabase<AnonymusKeyDB>> {
  if (_db) return _db;
  _db = await openDB<AnonymusKeyDB>("anonymus-keys", 1, {
    upgrade(db) {
      db.createObjectStore("identity", { keyPath: "id" });
      db.createObjectStore("sessions", { keyPath: "onion" });
      const prekeys = db.createObjectStore("prekeys", { keyPath: "id" });
      prekeys.createIndex("by-type", "type");
      db.createObjectStore("contacts", { keyPath: "onion" });
    },
  });
  return _db;
}

// ── Identity Key ───────────────────────────────────────────────────────────────

export async function storeIdentityKey(
  privateKey: Uint8Array,
  publicKey: Uint8Array
): Promise<void> {
  const db = await getDB();
  await db.put("identity", {
    id: "primary",
    privateKey,
    publicKey,
    createdAt: Date.now(),
  });
}

export async function loadIdentityKey(): Promise<{
  privateKey: Uint8Array;
  publicKey: Uint8Array;
} | null> {
  const db = await getDB();
  const record = await db.get("identity", "primary");
  if (!record) return null;
  return { privateKey: record.privateKey, publicKey: record.publicKey };
}

// ── Double Ratchet Session State ───────────────────────────────────────────────

import { DoubleRatchetSession } from "./crypto";

export async function saveSessionState(onion: string, state: string): Promise<void> {
  const db = await getDB();
  await db.put("sessions", { onion, state, updatedAt: Date.now() });
}

export async function loadSessionState(onion: string): Promise<string | null> {
  const db = await getDB();
  const record = await db.get("sessions", onion);
  return record?.state ?? null;
}

export async function deleteSessionState(onion: string): Promise<void> {
  const db = await getDB();
  await db.delete("sessions", onion);
}

export async function saveSession(onion: string, session: DoubleRatchetSession): Promise<void> {
  await saveSessionState(onion, session.serialize());
}

export async function loadSession(onion: string): Promise<DoubleRatchetSession | null> {
  const stateStr = await loadSessionState(onion);
  if (!stateStr) return null;
  return DoubleRatchetSession.deserialize(stateStr);
}

// ── Pre-keys ───────────────────────────────────────────────────────────────────

export async function storePreKey(
  id: string,
  type: "signed" | "one-time" | "pq",
  keyBytes: Uint8Array,
  signature?: Uint8Array
): Promise<void> {
  const db = await getDB();
  await db.put("prekeys", {
    id,
    type,
    keyBytes,
    signature,
    used: false,
    createdAt: Date.now(),
  });
}

export async function consumeOneTimePreKey(): Promise<
  { id: string; keyBytes: Uint8Array } | null
> {
  const db = await getDB();
  const tx = db.transaction("prekeys", "readwrite");
  const index = tx.store.index("by-type");
  let cursor = await index.openCursor("one-time");
  while (cursor) {
    if (!cursor.value.used) {
      const key = cursor.value;
      await cursor.update({ ...key, used: true });
      await tx.done;
      return { id: key.id, keyBytes: key.keyBytes };
    }
    cursor = await cursor.continue();
  }
  await tx.done;
  return null;
}

// ── Contacts ───────────────────────────────────────────────────────────────────

export async function upsertContact(contact: AnonymusKeyDB["contacts"]["value"]): Promise<void> {
  const db = await getDB();
  await db.put("contacts", contact);
}

export async function loadAllContacts(): Promise<AnonymusKeyDB["contacts"]["value"][]> {
  const db = await getDB();
  return db.getAll("contacts");
}

export async function deleteContact(onion: string): Promise<void> {
  const db = await getDB();
  const tx = db.transaction(["contacts", "sessions"], "readwrite");
  await tx.objectStore("contacts").delete(onion);
  await tx.objectStore("sessions").delete(onion);
  await tx.done;
}
