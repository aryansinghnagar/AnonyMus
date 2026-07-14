export default function init(): Promise<void>;
export function generateIdentityKeypair(): { privateKey: Uint8Array; publicKey: Uint8Array };
export function x25519Dh(privateKey: Uint8Array, peerPublicKey: Uint8Array): Uint8Array;
export function aeadEncrypt(key: Uint8Array, plaintext: Uint8Array): Uint8Array;
export function aeadDecrypt(key: Uint8Array, blob: Uint8Array): Uint8Array;
export function hkdfDerive(ikm: Uint8Array, info: Uint8Array, outputLen: number, salt?: Uint8Array): Uint8Array;
export function ed25519Verify(publicKey: Uint8Array, message: Uint8Array, signature: Uint8Array): void;
export function protocolVersion(): number;
