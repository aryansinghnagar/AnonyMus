/* ChatArea.tsx — Message thread + composer for a single conversation */

import { activeContact } from "@stores/contacts";
import { getMessages, loadMessages, messageError, sendMessage, sending } from "@stores/messages";
import { user } from "@stores/session";
import type { Component } from "solid-js";
import { For, Show, createEffect, createSignal } from "solid-js";

import { startCall } from "@stores/calls";

interface Props {
  onion: string;
}

// Audit fix ANO-UX-001: helper to safely render a message body.
// - If the message was successfully decrypted (the store rewrote
//   ``ciphertext_b64`` to ``btoa(plaintext)``), decode the base64 back
//   to the plaintext string and display it.
// - If decryption failed (the store left the original ciphertext), display
//   a placeholder so the user is not shown raw binary mojibake.
function renderMessageBody(msg: { ciphertext_b64: string; is_decrypted?: boolean }): string {
  // Heuristic: the store sets ``ciphertext_b64 = btoa(plaintext)`` on
  // successful decryption. If the value decodes cleanly to valid UTF-8, we
  // treat it as decrypted plaintext. If it decodes to bytes outside the
  // printable range, we treat the message as still-encrypted and show a
  // placeholder instead.
  try {
    const decoded = atob(msg.ciphertext_b64);
    // Check that the decoded string is plausible UTF-8 text (every char
    // code is in the printable range or a common whitespace char).
    let printable = true;
    for (let i = 0; i < decoded.length; i++) {
      const c = decoded.charCodeAt(i);
      // Allow printable ASCII (32-126), tab (9), newline (10), carriage
      // return (13), and any non-ASCII (>= 160, which covers Latin-1 +
      // UTF-8 continuation bytes when interpreted as Latin-1).
      if (c < 9 || (c > 13 && c < 32) || (c > 126 && c < 160)) {
        printable = false;
        break;
      }
    }
    if (printable) {
      return decoded;
    }
    // Not printable — treat as still-encrypted ciphertext.
    return "🔒 Encrypted message — decryption pending";
  } catch {
    // ``atob`` failed entirely — not valid base64. Show a placeholder.
    return "🔒 Encrypted message — decryption pending";
  }
}

export const ChatArea: Component<Props> = (props) => {
  let bottomRef: HTMLDivElement | undefined;
  const [text, setText] = createSignal("");

  // Load messages when the active conversation changes
  createEffect(() => {
    void loadMessages(props.onion);
  });

  // Auto-scroll to bottom when messages change
  createEffect(() => {
    getMessages(props.onion); // track reactivity
    queueMicrotask(() => bottomRef?.scrollIntoView({ behavior: "smooth" }));
  });

  const contact = () => activeContact();
  const msgs = () => getMessages(props.onion);
  const myOnion = () => user()?.onion_address ?? "";

  const handleSend = async (e: SubmitEvent | KeyboardEvent) => {
    e.preventDefault();
    const t = text().trim();
    if (!t || sending()) return;
    setText("");
    await sendMessage(props.onion, t, myOnion());
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend(e);
    }
  };

  const formatTime = (iso: string) =>
    new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <div class="flex-col h-full" style="display:flex;">
      {/* Chat header */}
      <div
        class="flex items-center gap-3"
        style="padding:0.875rem 1.25rem;border-bottom:1px solid var(--clr-border);background:var(--clr-bg-1);"
      >
        <div class="avatar" style="width:36px;height:36px;font-size:0.875rem;" aria-hidden="true">
          {(contact()?.nickname ?? props.onion).slice(0, 2).toUpperCase()}
        </div>
        <div>
          <p class="font-semibold text-sm">
            {contact()?.nickname ?? `${props.onion.slice(0, 16)}…`}
          </p>
          <p class="text-xs font-mono" style="color:var(--clr-text-3);">
            {props.onion.slice(0, 20)}…
          </p>
        </div>
        <div style="margin-left:auto;" class="flex items-center gap-2">
          <button
            class="btn btn-ghost"
            style="padding:0.375rem 0.75rem;font-size:var(--font-size-xs);margin-right:0.5rem;border-radius:var(--radius-sm);border:1px solid var(--clr-border-2);cursor:pointer;"
            onClick={() => startCall(props.onion, myOnion())}
            title="Voice Call"
            aria-label="Voice Call"
          >
            Call
          </button>
          <span class="status-dot online" />
          <span class="text-xs text-muted">E2E encrypted</span>
        </div>
      </div>

      {/* Message thread */}
      <div
        class="overflow-auto"
        style="flex:1;padding:1.25rem;display:flex;flex-direction:column;gap:0.5rem;"
        role="log"
        aria-label="Message thread"
        aria-live="polite"
      >
        <Show
          when={msgs().length > 0}
          fallback={
            <div
              class="flex flex-col items-center justify-center h-full"
              style="gap:0.5rem;opacity:0.5;"
            >
              <p class="text-sm text-muted">No messages yet</p>
              <p class="text-xs text-muted">Send a message to start the conversation</p>
            </div>
          }
        >
          <For each={msgs()}>
            {(msg) => {
              const sent = msg.sender_onion === myOnion();
              return (
                <Show
                  when={!msg.is_deleted}
                  fallback={
                    <div
                      class={`msg-bubble ${sent ? "sent" : "recv"}`}
                      style="opacity:0.4;font-style:italic;"
                    >
                      Message deleted
                    </div>
                  }
                >
                  <div
                    style={`display:flex;flex-direction:column;align-items:${sent ? "flex-end" : "flex-start"};`}
                  >
                    <div
                      class={`msg-bubble ${sent ? "sent" : "recv"}`}
                      role="article"
                      aria-label={`${sent ? "Sent" : "Received"} message`}
                    >
                      {/* Audit fix ANO-UX-001: render decrypted plaintext via
                          the renderMessageBody helper. Previously this called
                          ``atob(msg.ciphertext_b64)`` directly, which rendered
                          raw AES-GCM ciphertext bytes as Latin-1 mojibake
                          (the comment "In Phase 5 this decrypts via WASM DR
                          session" indicated the decryption pipeline was not
                          wired up, but the store in messages.ts had already
                          wired it up — the UI just wasn't using the result). */}
                      {renderMessageBody(msg)}
                    </div>
                    <p class="msg-time">{formatTime(msg.sent_at)}</p>
                  </div>
                </Show>
              );
            }}
          </For>
        </Show>
        {/* Scroll anchor */}
        <div ref={bottomRef} aria-hidden="true" />
      </div>

      {/* Error banner */}
      <Show when={messageError()}>
        <div style="padding:0.5rem 1.25rem;background:rgba(248,113,113,0.1);" role="alert">
          <p class="text-error text-xs">{messageError()}</p>
        </div>
      </Show>

      {/* Composer */}
      <form
        onSubmit={handleSend}
        style="padding:1rem 1.25rem;border-top:1px solid var(--clr-border);background:var(--clr-bg-1);display:flex;gap:0.75rem;align-items:flex-end;"
        aria-label="Message composer"
      >
        <textarea
          id="chat-input"
          class="input"
          style="resize:none;min-height:44px;max-height:160px;line-height:1.5;"
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          rows={1}
          value={text()}
          onInput={(e) => {
            setText(e.currentTarget.value);
            // Auto-resize
            e.currentTarget.style.height = "auto";
            e.currentTarget.style.height = `${e.currentTarget.scrollHeight}px`;
          }}
          onKeyDown={handleKeyDown}
          disabled={sending()}
          aria-label="Message text"
        />
        <button
          type="submit"
          id="chat-send-btn"
          class="btn btn-primary"
          style="height:44px;padding:0 1.25rem;flex-shrink:0;"
          disabled={sending() || !text().trim()}
          aria-label="Send message"
        >
          <Show when={!sending()} fallback={<span>…</span>}>
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </Show>
        </button>
      </form>
    </div>
  );
};
