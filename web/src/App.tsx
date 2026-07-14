/* App.tsx — Root application component with auth routing */

import type { Component } from "solid-js";
import { createEffect, Show } from "solid-js";
import { initSession, loading, user } from "@stores/session";
import { AuthPage } from "@components/auth/AuthPage";
import { ChatShell } from "@components/chat/ChatShell";

export const App: Component = () => {
  // Initialise session from cookie on mount
  createEffect(() => {
    initSession();
  });

  // Manage socket connection based on user authentication state
  createEffect(() => {
    const currentUser = user();
    if (currentUser) {
      import("@lib/socket").then(({ connectSocket }) => connectSocket());
    } else {
      import("@lib/socket").then(({ disconnectSocket }) => disconnectSocket());
    }
  });

  return (
    <Show
      when={!loading()}
      fallback={
        <div class="auth-page" aria-label="Loading AnonyMus">
          <div class="flex flex-col items-center gap-4">
            <div class="avatar" style="width:64px;height:64px;font-size:2rem;">A</div>
            <div class="skeleton" style="width:120px;height:16px;" />
          </div>
        </div>
      }
    >
      <Show when={user()} fallback={<AuthPage />}>
        <ChatShell />
      </Show>
    </Show>
  );
};
