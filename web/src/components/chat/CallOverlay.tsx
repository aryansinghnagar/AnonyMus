import type { Component } from "solid-js";
import { createEffect, createSignal, onCleanup, Show } from "solid-js";
import { callState, activePeerOnion, remoteStream, answerCall, hangupCall } from "@stores/calls";
import { user } from "@stores/session";

export const CallOverlay: Component = () => {
  let audioEl: HTMLAudioElement | undefined;
  const [duration, setDuration] = createSignal(0);
  let timerId: any;

  createEffect(() => {
    if (callState() === "connected") {
      setDuration(0);
      timerId = setInterval(() => {
        setDuration(d => d + 1);
      }, 1000);
    } else {
      clearInterval(timerId);
      setDuration(0);
    }
  });

  onCleanup(() => {
    clearInterval(timerId);
  });

  // Bind remote stream to hidden audio playback element
  createEffect(() => {
    const stream = remoteStream();
    if (stream && audioEl) {
      audioEl.srcObject = stream;
      audioEl.play().catch(e => console.warn("[Call] Failed to autoplay remote audio stream:", e));
    }
  });

  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60).toString().padStart(2, "0");
    const s = (sec % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const myOnion = () => user()?.onion_address || "";

  return (
    <Show when={callState() !== "idle"}>
      <div
        class="flex flex-col items-center justify-center"
        style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(18, 18, 23, 0.96);backdrop-filter:blur(10px);z-index:9999;color:white;padding:2rem;"
      >
        <audio ref={audioEl} autoplay style="display:none;" />

        <div
          class="flex flex-col items-center gap-6"
          style="max-width:400px;text-align:center;background:var(--clr-bg-2);border:1px solid var(--clr-border-2);padding:3rem;border-radius:var(--radius-lg);box-shadow:var(--shadow-lg);"
        >
          <div
            class="avatar animate-pulse"
            style="width:80px;height:80px;font-size:2.5rem;background:var(--clr-accent);color:var(--clr-bg);display:flex;align-items:center;justify-content:center;border-radius:50%;font-weight:bold;"
          >
            C
          </div>

          <div>
            <h2 style="font-size:var(--font-size-lg);font-weight:700;margin-bottom:0.5rem;letter-spacing:-0.3px;">
              <Show when={callState() === "calling"}>Calling Contact</Show>
              <Show when={callState() === "incoming"}>Incoming Voice Call</Show>
              <Show when={callState() === "connected"}>Call in Progress</Show>
            </h2>
            <p class="text-sm font-mono text-muted" style="word-break:break-all;">
              {activePeerOnion()?.slice(0, 16)}...
            </p>
          </div>

          <Show when={callState() === "connected"}>
            <div style="font-size:2.25rem;font-weight:700;font-family:monospace;color:var(--clr-accent);">
              {formatDuration(duration())}
            </div>
            <div class="text-xs text-accent animate-pulse" style="letter-spacing:1.5px;text-transform:uppercase;">
              Secured Peer-to-Peer Loop
            </div>
          </Show>

          <div class="flex items-center gap-4" style="margin-top:1rem;width:100%;justify-content:center;">
            <Show when={callState() === "incoming"}>
              <button
                class="btn btn-accent"
                style="background-color:var(--clr-accent);color:var(--clr-bg);font-weight:bold;padding:0.75rem 1.5rem;border:none;border-radius:var(--radius-sm);cursor:pointer;"
                onClick={() => answerCall(myOnion())}
              >
                Answer
              </button>
            </Show>

            <button
              class="btn btn-danger"
              style="background-color:var(--clr-error);color:white;font-weight:bold;padding:0.75rem 1.5rem;border:none;border-radius:var(--radius-sm);cursor:pointer;"
              onClick={() => hangupCall(myOnion())}
            >
              <Show when={callState() === "incoming"}>Decline</Show>
              <Show when={callState() !== "incoming"}>Hang Up</Show>
            </button>
          </div>
        </div>
      </div>
    </Show>
  );
};
