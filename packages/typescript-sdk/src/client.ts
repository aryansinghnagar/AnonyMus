// client.ts — Socket.IO protocol adapter and queue client wrapper for AnonyMus TS SDK

import { io, Socket } from 'socket.io-client';
import {
  generateKeyPair,
  exportPublicKey,
  importPublicKey,
  computeDH,
  DoubleRatchetSession,
  encryptAESGCM,
  decryptAESGCM,
  toBase64,
  fromBase64
} from './crypto';

export class AnonyMusClient {
  private socket: Socket | null = null;
  private serverUrl: string;
  private myKeys: { publicKey: CryptoKey; privateKey: CryptoKey } | null = null;
  private myPublicKeyExported: string | null = null;
  private myQueueId: string | null = null;
  private theirQueueId: string | null = null;
  private theirPublicKeyExported: string | null = null;
  private ratchet: DoubleRatchetSession | null = null;
  private messageListeners: ((msg: any) => void)[] = [];

  constructor(serverUrl: string) {
    this.serverUrl = serverUrl;
  }

  public async connect(): Promise<void> {
    this.socket = io(this.serverUrl, {
      transports: ['websocket'],
      autoConnect: true
    });
    
    this.myKeys = await generateKeyPair();
    this.myPublicKeyExported = await exportPublicKey(this.myKeys.publicKey);

    return new Promise((resolve) => {
      this.socket!.on('connect', () => {
        resolve();
      });

      this.socket!.on('queue_payload', async (data: { queue_id: string; payload: string }) => {
        await this.handleQueuePayload(data.payload);
      });
    });
  }

  public async createQueue(): Promise<string> {
    if (!this.socket) throw new Error("Client not connected");
    return new Promise((resolve) => {
      this.socket!.emit('create_queue');
      this.socket!.once('queue_created', (data: { queue_id: string }) => {
        this.myQueueId = data.queue_id;
        resolve(data.queue_id);
      });
    });
  }

  public getInviteLink(): string {
    if (!this.myQueueId || !this.myPublicKeyExported) {
      throw new Error("Queue not created yet");
    }
    const hashObj = { q: this.myQueueId, k: this.myPublicKeyExported };
    return `${this.serverUrl}/#${encodeURIComponent(JSON.stringify(hashObj))}`;
  }

  public async acceptInvite(inviteUrl: string): Promise<void> {
    if (!this.socket) throw new Error("Client not connected");
    if (!this.myKeys) throw new Error("Client keys not generated");
    
    const hashIdx = inviteUrl.indexOf('#');
    if (hashIdx === -1) throw new Error("Invalid invite URL");
    const hashStr = decodeURIComponent(inviteUrl.substring(hashIdx + 1));
    const inviteData = JSON.parse(hashStr);
    
    this.theirQueueId = inviteData.q;
    this.theirPublicKeyExported = inviteData.k;
    
    // Derive pairwise keys
    const theirKey = await importPublicKey(this.theirPublicKeyExported!);
    const sharedSecretBuffer = await computeDH(this.myKeys.privateKey, theirKey);
    const sharedSecret = new Uint8Array(sharedSecretBuffer);
    
    const isAlice = this.myPublicKeyExported! < this.theirPublicKeyExported!;
    if (isAlice) {
      // Alice initiates the Double Ratchet
      const peerDhPubBytes = fromBase64(this.theirPublicKeyExported!);
      this.ratchet = await DoubleRatchetSession.initAlice(sharedSecret, peerDhPubBytes);
    } else {
      // Bob prepares Bob session
      const getCrypto = (): Crypto => {
        if (typeof window !== 'undefined' && window.crypto) return window.crypto;
        if (typeof globalThis !== 'undefined' && (globalThis as any).crypto) return (globalThis as any).crypto;
        throw new Error("Web Cryptography API not found");
      };
      const myDhPrivRaw = await getCrypto().subtle.exportKey('pkcs8', this.myKeys.privateKey);
      this.ratchet = await DoubleRatchetSession.initBob(sharedSecret, new Uint8Array(myDhPrivRaw as any));
    }

    // Register peer connection on backend
    this.socket.emit('register_peer', {
      my_queue: this.myQueueId,
      peer_queue: this.theirQueueId
    });

    // Send handshake
    const handshakePayload = JSON.stringify({
      type: 'handshake',
      reply_queue: this.myQueueId,
      public_key: this.myPublicKeyExported
    });

    this.socket.emit('push_queue', {
      queue_id: this.theirQueueId,
      payload: handshakePayload
    });
  }

  public async sendMessage(text: string): Promise<void> {
    if (!this.socket || !this.theirQueueId || !this.ratchet) {
      throw new Error("Session not established. Complete handshake first.");
    }

    const { messageKey, myPubBytes, seq, prevChainLen } = await this.ratchet.encrypt();
    const messagePayload = JSON.stringify({
      type: 'text',
      content: text,
      timestamp: Date.now()
    });

    const encrypted = await encryptAESGCM(messageKey, messagePayload);
    
    const outerPayload = JSON.stringify({
      type: 'message',
      iv: encrypted.iv,
      ciphertext: encrypted.ciphertext,
      dh_pub: toBase64(myPubBytes.buffer as any),
      seq: seq,
      prev_chain_len: prevChainLen
    });

    this.socket.emit('push_queue', {
      queue_id: this.theirQueueId,
      payload: outerPayload
    });
  }

  public onMessage(listener: (msg: any) => void): void {
    this.messageListeners.push(listener);
  }

  private async handleQueuePayload(payloadStr: string): Promise<void> {
    try {
      const payload = JSON.parse(payloadStr);
      const type = payload.type;

      if (type === 'handshake') {
        this.theirQueueId = payload.reply_queue;
        this.theirPublicKeyExported = payload.public_key;
        if (!this.myKeys) return;

        const theirKey = await importPublicKey(this.theirPublicKeyExported!);
        const sharedSecretBuffer = await computeDH(this.myKeys.privateKey, theirKey);
        const sharedSecret = new Uint8Array(sharedSecretBuffer);

        const isAlice = this.myPublicKeyExported! < this.theirPublicKeyExported!;
        if (isAlice) {
          const peerDhPubBytes = fromBase64(this.theirPublicKeyExported!);
          this.ratchet = await DoubleRatchetSession.initAlice(sharedSecret, peerDhPubBytes);
        } else {
          const getCrypto = (): Crypto => {
            if (typeof window !== 'undefined' && window.crypto) return window.crypto;
            if (typeof globalThis !== 'undefined' && (globalThis as any).crypto) return (globalThis as any).crypto;
            throw new Error("Web Cryptography API not found");
          };
          const myDhPrivRaw = await getCrypto().subtle.exportKey('pkcs8', this.myKeys.privateKey);
          this.ratchet = await DoubleRatchetSession.initBob(sharedSecret, new Uint8Array(myDhPrivRaw as any));
        }

        // Register peer connection on backend
        this.socket!.emit('register_peer', {
          my_queue: this.myQueueId,
          peer_queue: this.theirQueueId
        });
      } else if (type === 'message') {
        if (!this.ratchet) return;
        
        const peerDhPubBytes = fromBase64(payload.dh_pub);
        const messageKey = await this.ratchet.decrypt(peerDhPubBytes, payload.seq, payload.prev_chain_len);
        
        const decryptedText = await decryptAESGCM(messageKey, payload.iv, payload.ciphertext);
        const msgObj = JSON.parse(decryptedText);

        for (const listener of this.messageListeners) {
          listener(msgObj);
        }
      }
    } catch (err) {
      console.error("Failed to process queue payload:", err);
    }
  }

  public disconnect(): void {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }
}
