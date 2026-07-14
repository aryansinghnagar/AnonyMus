/* ChatShell.tsx — Main authenticated layout: sidebar + chat area */

import type { Component } from "solid-js";
import { Show } from "solid-js";
import { activeOnion } from "@stores/contacts";
import { ContactList } from "@components/chat/ContactList";
import { ChatArea } from "@components/chat/ChatArea";
import { TopBar } from "@components/chat/TopBar";
import { CallOverlay } from "@components/chat/CallOverlay";

export const ChatShell: Component = () => {
  return (
    <div class="app-shell">
      <TopBar />
      <CallOverlay />
      <aside class="app-sidebar" aria-label="Contacts">
        <ContactList />
      </aside>
      <main class="app-main" aria-label="Chat area">
        <Show
          when={activeOnion()}
          fallback={<WelcomePane />}
        >
          <ChatArea onion={activeOnion()!} />
        </Show>
      </main>
    </div>
  );
};

const WelcomePane: Component = () => (
  <div
    class="flex flex-col items-center justify-center h-full"
    style="gap:1rem;color:var(--clr-text-3);"
  >
    <div
      class="avatar"
      style="width:72px;height:72px;font-size:2rem;opacity:0.4;"
      aria-hidden="true"
    >
      A
    </div>
    <p class="text-sm" style="text-align:center;max-width:260px;">
      Select a contact to start a secure conversation, or add a new one via the{" "}
      <strong style="color:var(--clr-text-2);">+</strong> button.
    </p>
  </div>
);
