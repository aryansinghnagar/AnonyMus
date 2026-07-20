// crypto.ts — End-to-end encryption and Double Ratchet implementation for SolidJS client

import { getCore } from "./core";

export function toHex(arr: Uint8Array): string {
  return Array.prototype.map.call(arr, (x: number) => ("00" + x.toString(16)).slice(-2)).join("");
}

export function fromHex(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = Number.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

export function toBase64(arr: Uint8Array): string {
  let binary = "";
  const len = arr.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(arr[i]);
  }
  return btoa(binary);
}

export function fromBase64(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function equals(a: Uint8Array, b: Uint8Array): boolean {
  if (a.byteLength !== b.byteLength) return false;
  for (let i = 0; i < a.byteLength; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

export class DoubleRatchetSession {
  public dhPrivateKey: Uint8Array | null = null;
  public dhPublicKey: Uint8Array | null = null;
  public dhRemotePublicKey: Uint8Array | null = null;
  public rootKey: Uint8Array | null = null;
  public sendingChainKey: Uint8Array | null = null;
  public receivingChainKey: Uint8Array | null = null;
  public seqSend = 0;
  public seqRecv = 0;
  public prevChainLength = 0;
  public skippedMessageKeys: Record<string, string> = {}; // { "peer_dh_b64_seq": "key_hex" }

  public static async initAlice(
    sharedSecret: Uint8Array,
    peerDhPub: Uint8Array,
  ): Promise<DoubleRatchetSession> {
    const core = await getCore();
    const session = new DoubleRatchetSession();
    const keyPair = core.generateIdentityKeypair();
    session.dhPrivateKey = keyPair.privateKey;
    session.dhPublicKey = keyPair.publicKey;
    session.dhRemotePublicKey = peerDhPub;

    const dhOut = core.x25519Dh(session.dhPrivateKey, session.dhRemotePublicKey);
    const derived = core.hkdfDerive(
      dhOut,
      new TextEncoder().encode("AnonyMus-DR-RootRatchet"),
      64,
      sharedSecret,
    );

    session.rootKey = derived.slice(0, 32);
    session.sendingChainKey = derived.slice(32, 64);
    session.receivingChainKey = null;
    return session;
  }

  public static async initBob(
    sharedSecret: Uint8Array,
    myDhPriv: Uint8Array,
  ): Promise<DoubleRatchetSession> {
    const session = new DoubleRatchetSession();
    session.dhPrivateKey = myDhPriv;
    session.dhRemotePublicKey = null;
    session.rootKey = sharedSecret;
    session.sendingChainKey = null;
    session.receivingChainKey = null;
    return session;
  }

  public async encrypt(
    plaintext: string,
  ): Promise<{
    ciphertextB64: string;
    ivB64: string;
    dhPubB64: string;
    seq: number;
    prevChainLen: number;
  }> {
    const core = await getCore();
    if (!this.sendingChainKey) {
      throw new Error("Sending chain key not initialized");
    }
    const derived = core.hkdfDerive(
      new Uint8Array(32),
      new TextEncoder().encode("AnonyMus-DR-ChainRatchet"),
      64,
      this.sendingChainKey,
    );
    const messageKey = derived.slice(0, 32);
    this.sendingChainKey = derived.slice(32, 64);

    const textBytes = new TextEncoder().encode(plaintext);
    const len = textBytes.length;
    let blockSize = 2048;
    while (len + 4 > blockSize) {
      blockSize += 2048;
    }
    const padded = new Uint8Array(blockSize);
    const view = new DataView(padded.buffer);
    view.setUint32(0, len, false);
    padded.set(textBytes, 4);
    if (len + 4 < blockSize) {
      const randBytes = new Uint8Array(blockSize - 4 - len);
      crypto.getRandomValues(randBytes);
      padded.set(randBytes, 4 + len);
    }

    const encryptedBytes = core.aeadEncrypt(messageKey, padded);

    // aeadEncrypt returns `nonce || ciphertext || tag`
    // Split into 12-byte nonce (IV) and the rest
    const iv = encryptedBytes.slice(0, 12);
    const ciphertext = encryptedBytes.slice(12);

    const seq = this.seqSend;
    this.seqSend += 1;

    return {
      ciphertextB64: toBase64(ciphertext),
      ivB64: toBase64(iv),
      dhPubB64: toBase64(this.dhPublicKey!),
      seq,
      prevChainLen: this.prevChainLength,
    };
  }

  public async decrypt(
    peerDhPub: Uint8Array,
    iv: Uint8Array,
    ciphertext: Uint8Array,
    seq: number,
    prevChainLen: number,
  ): Promise<string> {
    const core = await getCore();
    const peerB64 = toBase64(peerDhPub);
    const skipKey = `${peerB64}_${seq}`;

    let messageKey: Uint8Array;

    if (this.skippedMessageKeys[skipKey]) {
      messageKey = fromHex(this.skippedMessageKeys[skipKey]);
      delete this.skippedMessageKeys[skipKey];
    } else {
      if (!this.dhRemotePublicKey || !equals(this.dhRemotePublicKey, peerDhPub)) {
        await this.skipMessages(prevChainLen);

        this.dhRemotePublicKey = peerDhPub;
        if (!this.dhPrivateKey || !this.rootKey) {
          throw new Error("Decryption keys not fully initialized");
        }
        const dhOut1 = core.x25519Dh(this.dhPrivateKey, this.dhRemotePublicKey);
        const derived1 = core.hkdfDerive(
          dhOut1,
          new TextEncoder().encode("AnonyMus-DR-RootRatchet"),
          64,
          this.rootKey,
        );
        this.rootKey = derived1.slice(0, 32);
        this.receivingChainKey = derived1.slice(32, 64);

        const keyPair = core.generateIdentityKeypair();
        this.dhPrivateKey = keyPair.privateKey;
        this.dhPublicKey = keyPair.publicKey;

        const dhOut2 = core.x25519Dh(this.dhPrivateKey, this.dhRemotePublicKey);
        const derived2 = core.hkdfDerive(
          dhOut2,
          new TextEncoder().encode("AnonyMus-DR-RootRatchet"),
          64,
          this.rootKey,
        );
        this.rootKey = derived2.slice(0, 32);
        this.sendingChainKey = derived2.slice(32, 64);

        this.prevChainLength = this.seqSend;
        this.seqSend = 0;
        this.seqRecv = 0;
      }

      await this.skipMessages(seq);

      if (!this.receivingChainKey) {
        throw new Error("Receiving chain key not initialized");
      }
      const derived = core.hkdfDerive(
        new Uint8Array(32),
        new TextEncoder().encode("AnonyMus-DR-ChainRatchet"),
        64,
        this.receivingChainKey,
      );
      messageKey = derived.slice(0, 32);
      this.receivingChainKey = derived.slice(32, 64);
      this.seqRecv += 1;
    }

    // Reconstruct the blob expected by core.aeadDecrypt: `nonce || ciphertext || tag`
    const blob = new Uint8Array(iv.length + ciphertext.length);
    blob.set(iv, 0);
    blob.set(ciphertext, iv.length);

    const decryptedBytes = core.aeadDecrypt(messageKey, blob);
    const view = new DataView(
      decryptedBytes.buffer,
      decryptedBytes.byteOffset,
      decryptedBytes.byteLength,
    );
    const len = view.getUint32(0, false);
    if (len > decryptedBytes.length - 4) {
      throw new Error("Decrypted length header exceeds message buffer bounds.");
    }
    const textBytes = decryptedBytes.subarray(4, 4 + len);
    return new TextDecoder().decode(textBytes);
  }

  private async skipMessages(untilSeq: number): Promise<void> {
    const core = await getCore();
    if (!this.receivingChainKey) return;
    if (this.seqRecv + 100 < untilSeq) {
      throw new Error("Too many skipped messages");
    }
    while (this.seqRecv < untilSeq) {
      const derived = core.hkdfDerive(
        new Uint8Array(32),
        new TextEncoder().encode("AnonyMus-DR-ChainRatchet"),
        64,
        this.receivingChainKey,
      );
      const msgKey = derived.slice(0, 32);
      this.receivingChainKey = derived.slice(32, 64);

      if (!this.dhRemotePublicKey) {
        throw new Error("Remote DH public key not set for skipped messages");
      }
      const peerB64 = toBase64(this.dhRemotePublicKey);
      const skipKey = `${peerB64}_${this.seqRecv}`;
      this.skippedMessageKeys[skipKey] = toHex(msgKey);
      this.seqRecv += 1;
    }
  }

  public serialize(): string {
    const obj = {
      dhPrivateKey: this.dhPrivateKey ? toHex(this.dhPrivateKey) : null,
      dhPublicKey: this.dhPublicKey ? toHex(this.dhPublicKey) : null,
      dhRemotePublicKey: this.dhRemotePublicKey ? toHex(this.dhRemotePublicKey) : null,
      rootKey: this.rootKey ? toHex(this.rootKey) : null,
      sendingChainKey: this.sendingChainKey ? toHex(this.sendingChainKey) : null,
      receivingChainKey: this.receivingChainKey ? toHex(this.receivingChainKey) : null,
      seqSend: this.seqSend,
      seqRecv: this.seqRecv,
      prevChainLength: this.prevChainLength,
      skippedMessageKeys: this.skippedMessageKeys,
    };
    return JSON.stringify(obj);
  }

  public static deserialize(str: string): DoubleRatchetSession {
    const obj = JSON.parse(str);
    const session = new DoubleRatchetSession();
    session.dhPrivateKey = obj.dhPrivateKey ? fromHex(obj.dhPrivateKey) : null;
    session.dhPublicKey = obj.dhPublicKey ? fromHex(obj.dhPublicKey) : null;
    session.dhRemotePublicKey = obj.dhRemotePublicKey ? fromHex(obj.dhRemotePublicKey) : null;
    session.rootKey = obj.rootKey ? fromHex(obj.rootKey) : null;
    session.sendingChainKey = obj.sendingChainKey ? fromHex(obj.sendingChainKey) : null;
    session.receivingChainKey = obj.receivingChainKey ? fromHex(obj.receivingChainKey) : null;
    session.seqSend = obj.seqSend;
    session.seqRecv = obj.seqRecv;
    session.prevChainLength = obj.prevChainLength;
    session.skippedMessageKeys = obj.skippedMessageKeys || {};
    return session;
  }
}

export interface SealedSenderBlock {
  ephemeral_pub: string;
  ciphertext: string;
  iv: string;
}

export async function encryptSealedSender(
  senderOnion: string,
  recipientPubKeyB64: string,
): Promise<SealedSenderBlock> {
  const core = await getCore();
  const recipientPubKey = fromBase64(recipientPubKeyB64);
  const ephemKp = core.generateIdentityKeypair();
  const dh = core.x25519Dh(ephemKp.privateKey, recipientPubKey);
  const info = new TextEncoder().encode("AnonyMus-SealedSender-Key");
  const derived = core.hkdfDerive(dh, info, 32);
  const plaintextBytes = new TextEncoder().encode(senderOnion);
  const encryptedBytes = core.aeadEncrypt(derived, plaintextBytes);
  const iv = encryptedBytes.slice(0, 12);
  const ciphertext = encryptedBytes.slice(12);

  return {
    ephemeral_pub: toBase64(ephemKp.publicKey),
    ciphertext: toBase64(ciphertext),
    iv: toBase64(iv),
  };
}

export async function decryptSealedSender(
  sealedBlock: SealedSenderBlock,
  myPrivateKey: Uint8Array,
): Promise<string> {
  const core = await getCore();
  const ephemeralPub = fromBase64(sealedBlock.ephemeral_pub);
  const ciphertext = fromBase64(sealedBlock.ciphertext);
  const iv = fromBase64(sealedBlock.iv);
  const dh = core.x25519Dh(myPrivateKey, ephemeralPub);
  const info = new TextEncoder().encode("AnonyMus-SealedSender-Key");
  const derived = core.hkdfDerive(dh, info, 32);
  const blob = new Uint8Array(iv.length + ciphertext.length);
  blob.set(iv, 0);
  blob.set(ciphertext, iv.length);
  const decryptedBytes = core.aeadDecrypt(derived, blob);
  return new TextDecoder().decode(decryptedBytes);
}
