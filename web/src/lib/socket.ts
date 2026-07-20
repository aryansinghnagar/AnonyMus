/**
 * Socket.IO client connection manager for AnonyMus.
 *
 * Configures connection options to fallback to WebSockets/WebTransport,
 * integrates with Solid.js reactive stores to receive real-time messages,
 * and maintains connection status indicators.
 */

import { refetchContacts } from "@stores/contacts";
import { receiveMessage } from "@stores/messages";
import { type Socket, io } from "socket.io-client";

let socket: Socket | null = null;

export function getSocket(): Socket {
  if (socket) return socket;

  // Build connection URL based on current host (with proxy handling /v3 vs root)
  const socketUrl = window.location.origin;

  socket = io(socketUrl, {
    autoConnect: false,
    transports: ["websocket", "webtransport", "polling"], // WebTransport fallback
    reconnectionAttempts: 10,
    reconnectionDelay: 1000,
    withCredentials: true,
  });

  // ── Event Handlers ─────────────────────────────────────────────────────────

  socket.on("connect", () => {
    console.log("[Socket] Connected successfully");
  });

  socket.on("disconnect", (reason) => {
    console.warn("[Socket] Disconnected:", reason);
  });

  socket.on("connect_error", (error) => {
    console.error("[Socket] Connection error:", error);
  });

  // Handle incoming message (P2P message received from node/relay)
  socket.on("message_received", (data: any) => {
    console.log("[Socket] New message received via Socket.IO:", data);
    if (data.sender_onion && data.message) {
      receiveMessage(data.sender_onion, data.message);
    }
  });

  // Handle contact request / handshake status change
  socket.on("contact_status_change", (data: any) => {
    console.log("[Socket] Contact status changed:", data);
    void refetchContacts();
  });

  // Handle new contact handshake invite
  socket.on("handshake_received", (data: any) => {
    console.log("[Socket] New handshake request received:", data);
    void refetchContacts();
  });

  return socket;
}

export function connectSocket(): void {
  const s = getSocket();
  if (!s.connected) {
    s.connect();
  }
}

export function disconnectSocket(): void {
  if (socket?.connected) {
    socket.disconnect();
  }
}
