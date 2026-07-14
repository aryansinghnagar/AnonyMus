/* TopBar.tsx — Application top bar with logo, node status, and settings */

import type { Component } from "solid-js";
import { user, logout, triggerPanicWipe } from "@stores/session";
import { isStub } from "@lib/core";

export const TopBar: Component = () => {
  return (
    <header class="app-topbar" role="banner">
      {/* Brand */}
      <div class="flex items-center gap-2" style="flex:1;">
        <div
          class="avatar"
          style="width:32px;height:32px;font-size:1rem;font-weight:700;"
          aria-hidden="true"
        >
          A
        </div>
        <span style="font-weight:700;font-size:var(--font-size-md);letter-spacing:-0.3px;">
          AnonyMus
        </span>
        <span
          class="badge badge-accent"
          style="font-size:10px;"
          title="Protocol version 3"
        >
          v3
        </span>
        {isStub() && (
          <span
            class="badge badge-danger animate-pulse"
            style="font-size:10px; background-color: var(--clr-error); color: var(--clr-bg); font-weight: bold; padding: 0.125rem 0.375rem; border-radius: var(--radius-sm);"
            title="WASM crypto core is missing — running insecure stub implementation!"
          >
            Insecure (Stub Crypto)
          </span>
        )}
      </div>

      {/* Node status indicator */}
      <div class="flex items-center gap-2" aria-label="Node status">
        <span class="status-dot online" title="Node online" />
        <span class="text-xs text-muted font-mono">
          {user()?.onion_address
            ? user()!.onion_address!.slice(0, 8) + "…"
            : "no onion"}
        </span>
      </div>

      {/* User menu */}
      <div class="flex items-center gap-1" style="margin-left:1rem;">
        <span class="text-sm text-muted">{user()?.username}</span>
        <button
          class="btn btn-ghost"
          id="topbar-logout"
          style="padding:0.375rem 0.75rem;font-size:var(--font-size-xs);"
          onClick={logout}
          title="Sign out"
          aria-label="Sign out"
        >
          Sign out
        </button>
        <button
          class="btn btn-danger"
          id="topbar-panic"
          style="padding:0.375rem 0.75rem;font-size:var(--font-size-xs);background-color:var(--clr-error);color:white;font-weight:bold;margin-left:0.5rem;border:none;border-radius:var(--radius-sm);cursor:pointer;"
          onClick={triggerPanicWipe}
          title="Secure Obliviate Panic Wipe"
          aria-label="Secure Obliviate Panic Wipe"
        >
          Panic
        </button>
      </div>
    </header>
  );
};
