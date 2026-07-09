// crypto.ts — End-to-end encryption for AnonyMus TypeScript SDK

const getCrypto = (): Crypto => {
  if (typeof window !== 'undefined' && window.crypto) {
    return window.crypto;
  }
  if (typeof globalThis !== 'undefined' && (globalThis as any).crypto) {
    return (globalThis as any).crypto;
  }
  throw new Error("Secure Web Cryptography API not found in this environment.");
};

export function toBase64(arrayBuffer: ArrayBuffer): string {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = '';
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export function fromBase64(base64String: string): Uint8Array {
  const binary = atob(base64String);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function toHex(arrayBuffer: ArrayBuffer): string {
  return Array.prototype.map.call(new Uint8Array(arrayBuffer), x => ('00' + x.toString(16)).slice(-2)).join('');
}

export function fromHex(hexString: string): Uint8Array {
  const bytes = new Uint8Array(hexString.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hexString.substring(i * 2, i * 2 + 2), 16);
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

export async function generateKeyPair(): Promise<{ publicKey: CryptoKey; privateKey: CryptoKey }> {
  const cryptoInstance = getCrypto();
  const keyPair = (await cryptoInstance.subtle.generateKey(
    { name: 'X25519' },
    true,
    ['deriveKey', 'deriveBits']
  )) as any;
  return { publicKey: keyPair.publicKey, privateKey: keyPair.privateKey };
}

export async function exportPublicKey(publicKey: CryptoKey): Promise<string> {
  const cryptoInstance = getCrypto();
  const rawKey = await cryptoInstance.subtle.exportKey('raw', publicKey);
  return toBase64(rawKey);
}

export async function importPublicKey(base64String: string): Promise<CryptoKey> {
  const cryptoInstance = getCrypto();
  const rawKey = fromBase64(base64String);
  return await cryptoInstance.subtle.importKey(
    'raw',
    rawKey as any,
    { name: 'X25519' },
    true,
    []
  );
}

export async function computeDH(privateKey: CryptoKey, publicKey: CryptoKey): Promise<ArrayBuffer> {
  const cryptoInstance = getCrypto();
  return await cryptoInstance.subtle.deriveBits(
    { name: 'X25519', public: publicKey },
    privateKey,
    256
  );
}

export async function hkdfDerive512(ikm: Uint8Array, info: Uint8Array, salt: Uint8Array = new Uint8Array(32)): Promise<ArrayBuffer> {
  const cryptoInstance = getCrypto();
  const hkdfKey = await cryptoInstance.subtle.importKey(
    'raw',
    ikm as any,
    { name: 'HKDF' },
    false,
    ['deriveKey', 'deriveBits']
  );
  return await cryptoInstance.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: salt as any,
      info: info as any
    },
    hkdfKey,
    512
  );
}

export async function encryptAESGCM(key: Uint8Array, plaintext: string): Promise<{ iv: string; ciphertext: string }> {
  const cryptoInstance = getCrypto();
  const aesKey = await cryptoInstance.subtle.importKey(
    'raw',
    key as any,
    { name: 'AES-GCM' },
    false,
    ['encrypt']
  );
  const iv = cryptoInstance.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(plaintext);
  const ciphertext = await cryptoInstance.subtle.encrypt(
    { name: 'AES-GCM', iv: iv },
    aesKey,
    encoded
  );
  return {
    iv: toBase64(iv.buffer as any),
    ciphertext: toBase64(ciphertext as any)
  };
}

export async function decryptAESGCM(key: Uint8Array, ivB64: string, ciphertextB64: string): Promise<string> {
  const cryptoInstance = getCrypto();
  const aesKey = await cryptoInstance.subtle.importKey(
    'raw',
    key as any,
    { name: 'AES-GCM' },
    false,
    ['decrypt']
  );
  const iv = fromBase64(ivB64);
  const ciphertext = fromBase64(ciphertextB64);
  const decrypted = await cryptoInstance.subtle.decrypt(
    { name: 'AES-GCM', iv: iv as any },
    aesKey,
    ciphertext as any
  );
  return new TextDecoder().decode(decrypted);
}

export class DoubleRatchetSession {
  public dhPrivateKey: CryptoKey | null = null;
  public dhPublicKey: CryptoKey | null = null;
  public dhRemotePublicKey: CryptoKey | null = null;
  public rootKey: Uint8Array | null = null;
  public sendingChainKey: Uint8Array | null = null;
  public receivingChainKey: Uint8Array | null = null;
  public seqSend = 0;
  public seqRecv = 0;
  public prevChainLength = 0;
  public skippedMessageKeys: Record<string, string> = {}; // { "peer_dh_b64_seq": "key_hex" }

  public static async initAlice(sharedSecret: Uint8Array, peerDhPubBytes: Uint8Array): Promise<DoubleRatchetSession> {
    const cryptoInstance = getCrypto();
    const session = new DoubleRatchetSession();
    const keyPair = await generateKeyPair();
    session.dhPrivateKey = keyPair.privateKey;
    session.dhPublicKey = keyPair.publicKey;
    session.dhRemotePublicKey = await cryptoInstance.subtle.importKey(
      'raw',
      peerDhPubBytes as any,
      { name: 'X25519' },
      true,
      []
    );

    const dhOut = await computeDH(session.dhPrivateKey, session.dhRemotePublicKey);
    const derived = await hkdfDerive512(new Uint8Array(dhOut), new TextEncoder().encode("AnonyMus-DR-RootRatchet"), sharedSecret);

    session.rootKey = new Uint8Array(derived.slice(0, 32));
    session.sendingChainKey = new Uint8Array(derived.slice(32, 64));
    session.receivingChainKey = null;
    return session;
  }

  public static async initBob(sharedSecret: Uint8Array, myDhPrivBytes: Uint8Array): Promise<DoubleRatchetSession> {
    const cryptoInstance = getCrypto();
    const session = new DoubleRatchetSession();
    session.dhPrivateKey = await cryptoInstance.subtle.importKey(
      'pkcs8',
      myDhPrivBytes as any,
      { name: 'X25519' },
      true,
      ['deriveKey', 'deriveBits']
    );
    session.dhRemotePublicKey = null;
    session.rootKey = sharedSecret;
    session.sendingChainKey = null;
    session.receivingChainKey = null;
    return session;
  }

  public async encrypt(): Promise<{ messageKey: Uint8Array; myPubBytes: Uint8Array; seq: number; prevChainLen: number }> {
    const cryptoInstance = getCrypto();
    if (!this.sendingChainKey) {
      throw new Error("Sending chain key not initialized");
    }
    const derived = await hkdfDerive512(new Uint8Array(32), new TextEncoder().encode("AnonyMus-DR-ChainRatchet"), this.sendingChainKey);
    const messageKey = new Uint8Array(derived.slice(0, 32));
    this.sendingChainKey = new Uint8Array(derived.slice(32, 64));

    const dhKeyToExport = this.dhPublicKey || (this.dhPrivateKey as any).publicKey;
    const myPubBytes = new Uint8Array(await cryptoInstance.subtle.exportKey('raw', dhKeyToExport));
    const seq = this.seqSend;
    this.seqSend += 1;
    return { messageKey, myPubBytes, seq, prevChainLen: this.prevChainLength };
  }

  public async decrypt(peerDhPubBytes: Uint8Array, seq: number, prevChainLen: number): Promise<Uint8Array> {
    const cryptoInstance = getCrypto();
    const peerB64 = toBase64(peerDhPubBytes.buffer as any);
    const skipKey = `${peerB64}_${seq}`;

    if (this.skippedMessageKeys[skipKey]) {
      const keyHex = this.skippedMessageKeys[skipKey];
      delete this.skippedMessageKeys[skipKey];
      return fromHex(keyHex);
    }

    const peerDhPub = await cryptoInstance.subtle.importKey(
      'raw',
      peerDhPubBytes as any,
      { name: 'X25519' },
      true,
      []
    );

    let currentRemoteBytes: Uint8Array | null = null;
    if (this.dhRemotePublicKey) {
      currentRemoteBytes = new Uint8Array(await cryptoInstance.subtle.exportKey('raw', this.dhRemotePublicKey));
    }

    if (!currentRemoteBytes || !equals(currentRemoteBytes, peerDhPubBytes)) {
      await this.skipMessages(prevChainLen);

      this.dhRemotePublicKey = peerDhPub;
      if (!this.dhPrivateKey || !this.rootKey) {
        throw new Error("Decryption keys not fully initialized");
      }
      const dhOut1 = await computeDH(this.dhPrivateKey, this.dhRemotePublicKey);
      const derived1 = await hkdfDerive512(new Uint8Array(dhOut1), new TextEncoder().encode("AnonyMus-DR-RootRatchet"), this.rootKey);
      this.rootKey = new Uint8Array(derived1.slice(0, 32));
      this.receivingChainKey = new Uint8Array(derived1.slice(32, 64));

      const keyPair = await generateKeyPair();
      this.dhPrivateKey = keyPair.privateKey;
      this.dhPublicKey = keyPair.publicKey;

      const dhOut2 = await computeDH(this.dhPrivateKey, this.dhRemotePublicKey);
      const derived2 = await hkdfDerive512(new Uint8Array(dhOut2), new TextEncoder().encode("AnonyMus-DR-RootRatchet"), this.rootKey);
      this.rootKey = new Uint8Array(derived2.slice(0, 32));
      this.sendingChainKey = new Uint8Array(derived2.slice(32, 64));

      this.prevChainLength = this.seqSend;
      this.seqSend = 0;
      this.seqRecv = 0;
    }

    await this.skipMessages(seq);

    if (!this.receivingChainKey) {
      throw new Error("Receiving chain key not initialized");
    }
    const derived = await hkdfDerive512(new Uint8Array(32), new TextEncoder().encode("AnonyMus-DR-ChainRatchet"), this.receivingChainKey);
    const messageKey = new Uint8Array(derived.slice(0, 32));
    this.receivingChainKey = new Uint8Array(derived.slice(32, 64));
    this.seqRecv += 1;

    return messageKey;
  }

  private async skipMessages(untilSeq: number): Promise<void> {
    const cryptoInstance = getCrypto();
    if (!this.receivingChainKey) return;
    if (this.seqRecv + 100 < untilSeq) {
      throw new Error("Too many skipped messages");
    }
    while (this.seqRecv < untilSeq) {
      const derived = await hkdfDerive512(new Uint8Array(32), new TextEncoder().encode("AnonyMus-DR-ChainRatchet"), this.receivingChainKey);
      const msgKey = new Uint8Array(derived.slice(0, 32));
      this.receivingChainKey = new Uint8Array(derived.slice(32, 64));

      if (!this.dhRemotePublicKey) {
        throw new Error("Remote DH public key not set for skipped messages");
      }
      const peerPubBytes = new Uint8Array(await cryptoInstance.subtle.exportKey('raw', this.dhRemotePublicKey));
      const peerB64 = toBase64(peerPubBytes.buffer as any);
      const skipKey = `${peerB64}_${this.seqRecv}`;
      this.skippedMessageKeys[skipKey] = toHex(msgKey.buffer as any);
      this.seqRecv += 1;
    }
  }
}
