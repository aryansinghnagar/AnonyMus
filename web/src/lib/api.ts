/**
 * AnonyMus v3 API client — typed wrappers around the FastAPI v3 REST endpoints.
 *
 * All requests use the browser's built-in fetch with credentials: "include"
 * so the session cookie is sent automatically.
 */

const BASE = "/v3";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface User {
  id: number;
  username: string;
  onion_address: string | null;
  created_at: string;
}

export interface Contact {
  id: number;
  owner_onion: string;
  onion_address: string;
  nickname: string;
  verified: boolean;
  added_at: string;
  public_key_b64?: string;
  shared_secret_b64?: string;
  status: string;
}

export interface Message {
  message_id: string;
  sender_onion: string;
  recipient_onion: string;
  ciphertext_b64: string;
  iv_b64: string;
  sequence_number: number;
  sent_at: string;
  delivered: boolean;
  is_deleted: boolean;
  disappears_at: string | null;
}

export interface NodeInfo {
  onion_address: string | null;
  username: string;
}

export interface PreKeyBundle {
  onion_address: string;
  identity_key: string;
  signed_prekey: string;
  signed_prekey_sig: string;
  pq_prekey: string;
  pq_prekey_sig: string;
  one_time_prekey: string | null;
  one_time_pq_prekey: string | null;
  published_at: string;
  opk_pool_size: number;
}

// ── Internal fetch helper ─────────────────────────────────────────────────────

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export const auth = {
  register: (username: string, password: string) =>
    apiFetch<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  login: (username: string, password: string) =>
    apiFetch<User>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  logout: () => apiFetch<void>("/auth/logout", { method: "POST" }),

  me: () => apiFetch<User>("/auth/me"),
};

// ── Contacts ──────────────────────────────────────────────────────────────────

export const contacts = {
  list: () => apiFetch<Contact[]>("/contacts/"),

  create: (onion_address: string, nickname: string) =>
    apiFetch<Contact>("/contacts/", {
      method: "POST",
      body: JSON.stringify({ onion_address, nickname }),
    }),

  delete: (id: number) => apiFetch<void>(`/contacts/${id}`, { method: "DELETE" }),
};

// ── Messages ──────────────────────────────────────────────────────────────────

export interface SealedSenderBlock {
  ephemeral_pub: string;
  ciphertext: string;
  iv: string;
}

export const messages = {
  history: (onion: string, limit = 50, before?: string) =>
    apiFetch<Message[]>(`/messages/${onion}?limit=${limit}${before ? `&before=${before}` : ""}`),

  send: (
    recipient_onion: string,
    ciphertext_b64: string,
    iv_b64: string,
    sequence_number: number,
    disappears_at?: string,
    sealed_sender?: SealedSenderBlock | null,
  ) =>
    apiFetch<Message>("/messages/", {
      method: "POST",
      body: JSON.stringify({
        recipient_onion,
        ciphertext_b64,
        iv_b64,
        sequence_number,
        disappears_at,
        sealed_sender,
      }),
    }),

  resolveSender: (message_id: string, sender_onion: string) =>
    apiFetch<{ success: boolean }>(`/messages/${message_id}/resolve_sender`, {
      method: "POST",
      body: JSON.stringify({ sender_onion }),
    }),

  softDelete: (message_id: string) =>
    apiFetch<void>(`/messages/${message_id}`, { method: "DELETE" }),
};

// ── Node ──────────────────────────────────────────────────────────────────────

export const node = {
  info: () => apiFetch<NodeInfo>("/node/info"),

  generateInvite: () =>
    apiFetch<{ invite_onion: string; service_name: string; token: string }>("/node/invite", {
      method: "POST",
    }),

  getRelay: () => apiFetch<{ preferred_file_relay: string }>("/node/settings/relay"),

  setRelay: (preferred_file_relay: string) =>
    apiFetch<{ preferred_file_relay: string }>("/node/settings/relay", {
      method: "POST",
      body: JSON.stringify({ preferred_file_relay }),
    }),

  obliviate: () => apiFetch<{ success: boolean }>("/node/obliviate", { method: "POST" }),
};

// ── Keys ─────────────────────────────────────────────────────────────────────

export const keys = {
  publish: (bundle: {
    onion_address: string;
    identity_key: string;
    signed_prekey: string;
    signed_prekey_sig: string;
    pq_prekey: string;
    pq_prekey_sig: string;
    one_time_prekeys: string[];
    one_time_pq_prekeys: string[];
  }) =>
    apiFetch<{ success: boolean; opk_count: number }>("/keys/publish", {
      method: "POST",
      body: JSON.stringify(bundle),
    }),

  fetch: (onion: string) => apiFetch<PreKeyBundle>(`/keys/${onion}`),

  rotate: (body: {
    onion_address: string;
    signed_prekey: string;
    signed_prekey_sig: string;
    pq_prekey: string;
    pq_prekey_sig: string;
  }) =>
    apiFetch<{ success: boolean }>("/keys/rotate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ── Notifications ─────────────────────────────────────────────────────────────

export const notifications = {
  register: (onion_address: string) =>
    apiFetch<{ token: string }>("/notifications/register", {
      method: "POST",
      body: JSON.stringify({ onion_address }),
    }),

  poll: (tokens: string[]) =>
    apiFetch<{ has_new: Record<string, boolean> }>(
      `/notifications/poll?tokens=${tokens.join(",")}`,
    ),

  clear: (tokens: string[]) =>
    apiFetch<{ success: boolean }>("/notifications/clear", {
      method: "POST",
      body: JSON.stringify({ tokens }),
    }),
};

export { ApiError };
