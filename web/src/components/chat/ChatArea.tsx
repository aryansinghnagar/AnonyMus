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
            {contact()?.nickname ?? props.onion.slice(0, 16) + "…"}
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
                      {/* In Phase 5 this decrypts via WASM DR session */}
                      {atob(msg.ciphertext_b64)}
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
            e.currentTarget.style.height = e.currentTarget.scrollHeight + "px";
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
