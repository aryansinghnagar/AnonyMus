import { createSignal } from "solid-js";
import { sendMessage } from "./messages";

export type CallState = "idle" | "calling" | "incoming" | "connected";

const [callState, setCallState] = createSignal<CallState>("idle");
const [activePeerOnion, setActivePeerOnion] = createSignal<string | null>(null);
const [localStream, setLocalStream] = createSignal<MediaStream | null>(null);
const [remoteStream, setRemoteStream] = createSignal<MediaStream | null>(null);

let peerConnection: RTCPeerConnection | null = null;
let pendingOfferSdp: string | null = null;

// Default STUN server list for NAT traversal
const ICE_SERVERS = [{ urls: "stun:stun.l.google.com:19302" }];

export { callState, activePeerOnion, localStream, remoteStream };

export async function startCall(peerOnion: string, myOnion: string): Promise<void> {
  if (callState() !== "idle") return;
  setCallState("calling");
  setActivePeerOnion(peerOnion);

  try {
    const stream = await navigator.mediaDevices
      .getUserMedia({ audio: true, video: false })
      .catch(() => {
        console.warn(
          "[Call] No microphone found or permission denied. Falling back to silent capture.",
        );
        return new MediaStream();
      });
    setLocalStream(stream);

    peerConnection = new RTCPeerConnection({ iceServers: ICE_SERVERS });

    stream.getTracks().forEach((track) => {
      peerConnection?.addTrack(track, stream);
    });

    peerConnection.ontrack = (event) => {
      if (event.streams && event.streams[0]) {
        setRemoteStream(event.streams[0]);
      }
    };

    peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        sendSignal(peerOnion, myOnion, { type: "ice", candidate: event.candidate });
      }
    };

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);

    await sendSignal(peerOnion, myOnion, { type: "offer", sdp: offer.sdp });
  } catch (err) {
    console.error("[Call] Failed to start call:", err);
    cleanupCall();
  }
}

export async function answerCall(myOnion: string): Promise<void> {
  const peerOnion = activePeerOnion();
  if (callState() !== "incoming" || !peerOnion) return;

  try {
    const stream = await navigator.mediaDevices
      .getUserMedia({ audio: true, video: false })
      .catch(() => {
        console.warn(
          "[Call] No microphone found or permission denied. Falling back to silent capture.",
        );
        return new MediaStream();
      });
    setLocalStream(stream);

    peerConnection = new RTCPeerConnection({ iceServers: ICE_SERVERS });

    stream.getTracks().forEach((track) => {
      peerConnection?.addTrack(track, stream);
    });

    peerConnection.ontrack = (event) => {
      if (event.streams && event.streams[0]) {
        setRemoteStream(event.streams[0]);
      }
    };

    peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        sendSignal(peerOnion, myOnion, { type: "ice", candidate: event.candidate });
      }
    };

    if (pendingOfferSdp) {
      await peerConnection.setRemoteDescription(
        new RTCSessionDescription({ type: "offer", sdp: pendingOfferSdp }),
      );
      const answer = await peerConnection.createAnswer();
      await peerConnection.setLocalDescription(answer);
      await sendSignal(peerOnion, myOnion, { type: "answer", sdp: answer.sdp });
      setCallState("connected");
    }
  } catch (err) {
    console.error("[Call] Failed to answer call:", err);
    cleanupCall();
  }
}

export async function handleIncomingSignal(
  peerOnion: string,
  myOnion: string,
  signal: any,
): Promise<void> {
  console.log("[Call] Received signaling message:", signal);

  if (signal.type === "offer") {
    if (callState() !== "idle") {
      // Busy: auto-reject call
      await sendSignal(peerOnion, myOnion, { type: "hangup" });
      return;
    }
    setCallState("incoming");
    setActivePeerOnion(peerOnion);
    pendingOfferSdp = signal.sdp;
  } else if (signal.type === "answer") {
    if (callState() === "calling" && peerConnection) {
      await peerConnection.setRemoteDescription(
        new RTCSessionDescription({ type: "answer", sdp: signal.sdp }),
      );
      setCallState("connected");
    }
  } else if (signal.type === "ice") {
    if (peerConnection && signal.candidate) {
      await peerConnection.addIceCandidate(new RTCIceCandidate(signal.candidate)).catch(() => {});
    }
  } else if (signal.type === "hangup") {
    cleanupCall();
  }
}

export function hangupCall(myOnion?: string): void {
  const peerOnion = activePeerOnion();
  if (peerOnion && myOnion) {
    void sendSignal(peerOnion, myOnion, { type: "hangup" });
  }
  cleanupCall();
}

function cleanupCall() {
  if (localStream()) {
    localStream()
      ?.getTracks()
      .forEach((track) => track.stop());
  }
  setLocalStream(null);
  setRemoteStream(null);
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }
  setCallState("idle");
  setActivePeerOnion(null);
  pendingOfferSdp = null;
}

async function sendSignal(peerOnion: string, myOnion: string, signal: any) {
  const signalMsg = `__CALL_SIGNAL__:${JSON.stringify(signal)}`;
  await sendMessage(peerOnion, signalMsg, myOnion);
}
