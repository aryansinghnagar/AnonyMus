/* AuthPage.tsx — Login and registration page */

import { authError, login, register } from "@stores/session";
import type { Component } from "solid-js";
import { Show, createSignal } from "solid-js";

type Mode = "login" | "register";

export const AuthPage: Component = () => {
  const [mode, setMode] = createSignal<Mode>("login");
  const [username, setUsername] = createSignal("");
  const [password, setPassword] = createSignal("");
  const [busy, setBusy] = createSignal(false);

  const handleSubmit = async (e: SubmitEvent) => {
    e.preventDefault();
    setBusy(true);
    if (mode() === "login") {
      await login(username(), password());
    } else {
      await register(username(), password());
    }
    setBusy(false);
  };

  return (
    <div class="auth-page">
      <div class="glass auth-card">
        {/* Logo / Brand */}
        <div class="flex flex-col items-center gap-3" style="margin-bottom:2rem;">
          <div
            class="avatar"
            style="width:56px;height:56px;font-size:1.75rem;box-shadow:var(--shadow-glow);"
            aria-hidden="true"
          >
            A
          </div>
          <h1 style="font-size:var(--font-size-xl);font-weight:700;letter-spacing:-0.5px;">
            AnonyMus
          </h1>
          <p class="text-muted text-sm" style="text-align:center;">
            Privacy-first encrypted messaging over Tor
          </p>
        </div>

        {/* Tab switcher */}
        <div
          class="flex"
          style="background:var(--clr-surface);border-radius:var(--radius-md);padding:4px;margin-bottom:1.5rem;"
          role="tablist"
        >
          <button
            role="tab"
            aria-selected={mode() === "login"}
            class="btn w-full"
            style={
              mode() === "login"
                ? "background:var(--clr-accent);color:#fff;"
                : "color:var(--clr-text-2);"
            }
            onClick={() => setMode("login")}
            id="tab-login"
          >
            Sign In
          </button>
          <button
            role="tab"
            aria-selected={mode() === "register"}
            class="btn w-full"
            style={
              mode() === "register"
                ? "background:var(--clr-accent);color:#fff;"
                : "color:var(--clr-text-2);"
            }
            onClick={() => setMode("register")}
            id="tab-register"
          >
            Create Account
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} aria-labelledby={`tab-${mode()}`}>
          <div class="flex-col gap-3" style="display:flex;">
            <div>
              <label
                for="auth-username"
                class="text-sm font-medium"
                style="display:block;margin-bottom:6px;"
              >
                Username
              </label>
              <input
                id="auth-username"
                type="text"
                class="input"
                placeholder="e.g. satoshi"
                autocomplete="username"
                required
                minLength={1}
                maxLength={64}
                value={username()}
                onInput={(e) => setUsername(e.currentTarget.value)}
                disabled={busy()}
              />
            </div>

            <div>
              <label
                for="auth-password"
                class="text-sm font-medium"
                style="display:block;margin-bottom:6px;"
              >
                Password
              </label>
              <input
                id="auth-password"
                type="password"
                class="input"
                placeholder="••••••••"
                autocomplete={mode() === "login" ? "current-password" : "new-password"}
                required
                minLength={8}
                value={password()}
                onInput={(e) => setPassword(e.currentTarget.value)}
                disabled={busy()}
              />
            </div>

            <Show when={authError()}>
              <p class="text-error text-sm" role="alert">
                {authError()}
              </p>
            </Show>

            <button
              type="submit"
              id="auth-submit"
              class="btn btn-primary w-full"
              style="margin-top:0.5rem;padding:0.75rem;"
              disabled={busy()}
            >
              {busy() ? "Please wait…" : mode() === "login" ? "Sign In" : "Create Account"}
            </button>
          </div>
        </form>

        <p class="text-muted text-xs" style="text-align:center;margin-top:1.5rem;">
          All messages are end-to-end encrypted using the Signal Protocol + ML-KEM-768 post-quantum
          ratchet.
        </p>
      </div>
    </div>
  );
};
