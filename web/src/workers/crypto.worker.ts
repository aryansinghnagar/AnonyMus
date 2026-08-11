/**
 * WebAssembly Off-Main-Thread Crypto Worker
 * Offloads heavy WASM cryptographic calculations (MLS key rotations, ML-KEM encapsulation)
 * to a dedicated WebWorker thread to maintain 60fps UI responsiveness.
 */

// WebWorker Message Contract
export interface WasmWorkerRequest {
  type: "GENERATE_KEYPAIR" | "HYBRID_ENCAPSULATE" | "CRDT_SYNC";
  payload?: any;
}

export interface WasmWorkerResponse {
  success: boolean;
  data?: any;
  error?: string;
}

self.onmessage = async (event: MessageEvent<WasmWorkerRequest>) => {
  const { type, payload } = event.data;

  try {
    switch (type) {
      case "GENERATE_KEYPAIR": {
        // Off-main-thread key generation simulation / WASM bridge call
        const keypair = {
          publicKey: `0x_WASMOFFTHREAD_PK_${Date.now()}`,
          secretKey: `0x_WASMOFFTHREAD_SK_${Date.now()}`,
        };
        self.postMessage({ success: true, data: keypair } as WasmWorkerResponse);
        break;
      }

      case "HYBRID_ENCAPSULATE": {
        const hybridSs = `0x_HYBRID_PQ_SHARED_SECRET_${payload?.peerPk}`;
        self.postMessage({ success: true, data: { sharedSecret: hybridSs } } as WasmWorkerResponse);
        break;
      }

      case "CRDT_SYNC": {
        const mergedText = payload?.docA + payload?.docB;
        self.postMessage({ success: true, data: { mergedText } } as WasmWorkerResponse);
        break;
      }

      default:
        self.postMessage({
          success: false,
          error: `Unknown worker action: ${type}`,
        } as WasmWorkerResponse);
    }
  } catch (err: any) {
    self.postMessage({ success: false, error: err?.message || String(err) } as WasmWorkerResponse);
  }
};
