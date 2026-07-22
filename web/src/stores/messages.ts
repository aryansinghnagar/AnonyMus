/**
 * Messages store — per-conversation message list with E2EE.
 *
 * Messages are stored in memory keyed by peer onion address.
 * The DR session state is persisted to IndexedDB via keystore.ts.
 */

import { type Message, messages as api } from "@lib/api";
import { getCore } from "@lib/core";
import {
  DoubleRatchetSession,
  decryptSealedSender,
  encryptSealedSender,
  fromBase64,
  toBase64,
} from "@lib/crypto";
import { loadIdentityKey, loadSession, saveSession } from "@lib/keystore";
import { createSignal } from "solid-js";
import { handleIncomingSignal } from "./calls";
import { contactList } from "./contacts";
import { user } from "./session";

// ── State ────────────────────────────────────────────────────────────────────

// messages per conversation: onion → Message[]
const [messageMap, setMessageMap] = createSignal<Record<string, Message[]>>({});
const [sending, setSending] = createSignal(false);
const [messageError, setMessageError] = createSignal<string | null>(null);

export { messageMap, sending, messageError };

// ── Helpers ───────────────────────────────────────────────────────────────────

export function getMessages(onion: string): Message[] {
  return messageMap()[onion] ?? [];
}

function setMessages(onion: string, msgs: Message[]) {
  setMessageMap((prev) => ({ ...prev, [onion]: msgs }));
}

/** Helper to derive our own local symmetric key for encrypt-to-self */
async function getLocalEncryptionKey(): Promise<Uint8Array> {
  const identity = await loadIdentityKey();
  if (!identity) {
    throw new Error("Identity key not initialized");
  }
  const core = await getCore();
  return core.hkdfDerive(identity.privateKey, new TextEncoder().encode("AnonyMus-Local-Key"), 32);
}

/**
 * Decrypt a single message envelope.
 */
export async function decryptMessage(onion: string, msg: Message): Promise<string> {
  try {
    // Decode the envelope
    const envelopeRaw = atob(msg.ciphertext_b64);
    const envelope = JSON.parse(envelopeRaw);

    const identity = await loadIdentityKey();
    if (!identity) {
      throw new Error("Identity key not found");
    }

    let resolvedOnion = onion;
    if (msg.sender_onion === "sealed" && (msg as any).sealed_sender) {
      try {
        const decryptedSender = await decryptSealedSender(
          (msg as any).sealed_sender,
          identity.privateKey,
        );
        await api.resolveSender(msg.message_id, decryptedSender);
        msg.sender_onion = decryptedSender;
        resolvedOnion = decryptedSender;
      } catch (e) {
        console.error("[SealedSender] Fail to decrypt sealed sender in history:", e);
      }
    }

    const ourPubB64 = toBase64(identity.publicKey);

    // Check who sent the message
    if (msg.sender_onion !== resolvedOnion) {
      // Sent by us — decrypt self_ciphertext
      if (!envelope.self_ciphertext) {
        throw new Error("Self ciphertext missing from envelope");
      }
      const localKey = await getLocalEncryptionKey();
      const selfBlob = fromBase64(envelope.self_ciphertext);
      const core = await getCore();
      const decryptedBytes = core.aeadDecrypt(localKey, selfBlob);
      return new TextDecoder().decode(decryptedBytes);
    } else {
      // Sent by peer — decrypt Bob's ciphertext using Double Ratchet
      let sessionObj = await loadSession(onion);
      if (!sessionObj) {
        const contact = contactList()?.find((c) => c.onion_address === onion);
        if (!contact || !contact.shared_secret_b64 || !contact.public_key_b64) {
          throw new Error("Double Ratchet session not established with peer");
        }
        const sharedSecret = fromBase64(contact.shared_secret_b64);
        const peerPub = fromBase64(contact.public_key_b64);

        const isAlice = ourPubB64 < contact.public_key_b64;
        if (isAlice) {
          sessionObj = await DoubleRatchetSession.initAlice(sharedSecret, peerPub);
        } else {
          sessionObj = await DoubleRatchetSession.initBob(sharedSecret, identity.privateKey);
        }
      }

      const peerDhPub = fromBase64(envelope.dh_pub);
      const iv = fromBase64(msg.iv_b64);
      const ciphertext = fromBase64(envelope.ciphertext);

      const plaintext = await sessionObj.decrypt(
        peerDhPub,
        iv,
        ciphertext,
        envelope.seq,
        envelope.prev_chain_len,
      );

      // Save updated ratchet state
      await saveSession(onion, sessionObj);
      return plaintext;
    }
  } catch (err: any) {
    console.error("[Decrypt] Failed to decrypt message:", err);
    throw err;
  }
}

// ── Actions ───────────────────────────────────────────────────────────────────

export async function loadMessages(onion: string, limit = 50): Promise<void> {
  try {
    const msgs = await api.history(onion, limit);

    // Decrypt all messages
    const decryptedMsgs: Message[] = [];
    for (const msg of msgs) {
      try {
        const plaintext = await decryptMessage(onion, msg);
        if (plaintext.startsWith("__CALL_SIGNAL__:")) {
          continue;
        }
        decryptedMsgs.push({
          ...msg,
          ciphertext_b64: btoa(plaintext), // Store plaintext temporarily in store for UI
        });
      } catch (err) {
        // Fallback: show encrypted
        decryptedMsgs.push(msg);
      }
    }

    setMessages(onion, decryptedMsgs.reverse()); // oldest first
  } catch {
    setMessages(onion, []);
  }
}

/**
 * Send an encrypted message to a peer.
 */
export async function sendMessage(
  onion: string,
  plaintext: string,
  _myOnion: string,
): Promise<boolean> {
  setSending(true);
  setMessageError(null);
  try {
    const existing = getMessages(onion);
    const seqNum = existing.length;

    // Load identity
    const identity = await loadIdentityKey();
    if (!identity) {
      throw new Error("Identity key not initialized");
    }

    const ourPubB64 = toBase64(identity.publicKey);

    const contact = contactList()?.find((c) => c.onion_address === onion);

    // Load or initialize Double Ratchet session
    let sessionObj = await loadSession(onion);
    if (!sessionObj) {
      if (!contact || !contact.shared_secret_b64 || !contact.public_key_b64) {
        throw new Error("E2EE pairing session not negotiated with this contact.");
      }
      const sharedSecret = fromBase64(contact.shared_secret_b64);
      const peerPub = fromBase64(contact.public_key_b64);

      const isAlice = ourPubB64 < contact.public_key_b64;
      if (isAlice) {
        sessionObj = await DoubleRatchetSession.initAlice(sharedSecret, peerPub);
      } else {
        sessionObj = await DoubleRatchetSession.initBob(sharedSecret, identity.privateKey);
      }
      await saveSession(onion, sessionObj);
    }

    // Encrypt message for Bob using Double Ratchet
    const enc = await sessionObj.encrypt(plaintext);
    await saveSession(onion, sessionObj);

    // Encrypt message for ourselves (local backup storage)
    const localKey = await getLocalEncryptionKey();
    const core = await getCore();
    const selfEncBytes = core.aeadEncrypt(localKey, new TextEncoder().encode(plaintext));
    const selfCiphertextB64 = toBase64(selfEncBytes);

    // Build the E2EE envelope
    const envelope = {
      ciphertext: enc.ciphertextB64,
      self_ciphertext: selfCiphertextB64,
      dh_pub: enc.dhPubB64,
      seq: enc.seq,
      prev_chain_len: enc.prevChainLen,
    };
    const envelopeB64 = btoa(JSON.stringify(envelope));

    let sealedSender = undefined;
    if (contact && contact.public_key_b64) {
      try {
        sealedSender = await encryptSealedSender(_myOnion, contact.public_key_b64);
      } catch (err) {
        console.error("[SealedSender] Error generating sealed sender:", err);
      }
    }

    const msg = await api.send(onion, envelopeB64, enc.ivB64, seqNum, undefined, sealedSender);

    // Append the plaintext message locally in UI store
    const uiMsg = {
      ...msg,
      ciphertext_b64: btoa(plaintext),
    };
    setMessages(onion, [...existing, uiMsg]);
    return true;
  } catch (e: any) {
    setMessageError(e.detail ?? e.message ?? "Failed to send message");
    return false;
  } finally {
    setSending(false);
  }
}

export async function softDeleteMessage(onion: string, messageId: string): Promise<void> {
  await api.softDelete(messageId).catch(() => {});
  setMessages(
    onion,
    getMessages(onion).map((m) => (m.message_id === messageId ? { ...m, is_deleted: true } : m)),
  );
}

/** Called when an incoming message arrives via Socket.IO. */
export async function receiveMessage(onion: string, msg: Message): Promise<void> {
  try {
    let targetOnion = onion;
    if (onion === "sealed" && (msg as any).sealed_sender) {
      const identity = await loadIdentityKey();
      if (!identity) throw new Error("No identity key found");
      targetOnion = await decryptSealedSender((msg as any).sealed_sender, identity.privateKey);
      await api.resolveSender(msg.message_id, targetOnion);
      msg.sender_onion = targetOnion;
    }

    const plaintext = await decryptMessage(targetOnion, msg);
    if (plaintext.startsWith("__CALL_SIGNAL__:")) {
      const signalJson = plaintext.slice("__CALL_SIGNAL__:".length);
      try {
        const signalObj = JSON.parse(signalJson);
        const myOnion = user()?.onion_address || "";
        await handleIncomingSignal(targetOnion, myOnion, signalObj);
      } catch (err) {
        console.error("[Call] Failed to parse call signal:", err);
      }
      return;
    }

    const decryptedMsg = { ...msg, ciphertext_b64: btoa(plaintext) };
    setMessages(targetOnion, [...getMessages(targetOnion), decryptedMsg]);
  } catch (err) {
    console.error("Failed to decrypt real-time incoming message:", err);
    setMessages(onion, [...getMessages(onion), msg]);
  }
}
