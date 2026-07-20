/* ContactList.tsx — Sidebar contact list with add-contact form */

import type { Contact } from "@lib/api";
import {
  activeOnion,
  addContact,
  contactError,
  contactList,
  setActiveOnion,
} from "@stores/contacts";
import type { Component } from "solid-js";
import { For, Show, createSignal } from "solid-js";

export const ContactList: Component = () => {
  const [showAdd, setShowAdd] = createSignal(false);
  const [newOnion, setNewOnion] = createSignal("");
  const [newNick, setNewNick] = createSignal("");
  const [adding, setAdding] = createSignal(false);

  const handleAdd = async (e: SubmitEvent) => {
    e.preventDefault();
    setAdding(true);
    const ok = await addContact(newOnion().trim(), newNick().trim());
    setAdding(false);
    if (ok) {
      setNewOnion("");
      setNewNick("");
      setShowAdd(false);
    }
  };

  const initials = (c: Contact) => (c.nickname || c.onion_address).slice(0, 2).toUpperCase();

  return (
    <div class="flex-col h-full" style="display:flex;">
      {/* Header */}
      <div
        class="flex items-center justify-between"
        style="padding:1rem;border-bottom:1px solid var(--clr-border);"
      >
        <span class="font-semibold text-sm">Contacts</span>
        <button
          class="btn btn-icon"
          id="contacts-add-btn"
          aria-label="Add contact"
          title="Add contact"
          onClick={() => setShowAdd((v) => !v)}
        >
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
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </div>

      {/* Add contact form */}
      <Show when={showAdd()}>
        <form
          onSubmit={handleAdd}
          style="padding:0.75rem;border-bottom:1px solid var(--clr-border);display:flex;flex-direction:column;gap:0.5rem;"
          aria-label="Add contact form"
        >
          <input
            id="contact-onion-input"
            class="input"
            type="text"
            placeholder="peer.onion address"
            required
            value={newOnion()}
            onInput={(e) => setNewOnion(e.currentTarget.value)}
          />
          <input
            id="contact-nickname-input"
            class="input"
            type="text"
            placeholder="Nickname"
            required
            maxLength={50}
            value={newNick()}
            onInput={(e) => setNewNick(e.currentTarget.value)}
          />
          <Show when={contactError()}>
            <p class="text-error text-xs" role="alert">
              {contactError()}
            </p>
          </Show>
          <button type="submit" id="contact-add-submit" class="btn btn-primary" disabled={adding()}>
            {adding() ? "Adding…" : "Add Contact"}
          </button>
        </form>
      </Show>

      {/* Contact items */}
      <div class="overflow-auto" style="flex:1;padding:0.5rem;">
        <Show
          when={!contactList.loading}
          fallback={
            <div class="flex-col gap-2" style="display:flex;padding:0.5rem;">
              <For each={[1, 2, 3]}>
                {() => <div class="skeleton" style="height:56px;border-radius:var(--radius-md);" />}
              </For>
            </div>
          }
        >
          <Show
            when={(contactList() ?? []).length > 0}
            fallback={
              <p class="text-muted text-sm" style="text-align:center;padding:2rem 1rem;">
                No contacts yet. Press + to add one.
              </p>
            }
          >
            <For each={contactList()}>
              {(contact) => (
                <div
                  class={`contact-item${activeOnion() === contact.onion_address ? " active" : ""}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`Chat with ${contact.nickname}`}
                  onClick={() => setActiveOnion(contact.onion_address)}
                  onKeyDown={(e) => e.key === "Enter" && setActiveOnion(contact.onion_address)}
                >
                  <div class="avatar" aria-hidden="true">
                    {initials(contact)}
                  </div>
                  <div style="flex:1;min-width:0;">
                    <p class="font-medium text-sm truncate">{contact.nickname}</p>
                    <p class="text-xs font-mono truncate" style="color:var(--clr-text-3);">
                      {contact.onion_address.slice(0, 16)}…
                    </p>
                  </div>
                  <Show when={contact.verified}>
                    <span
                      class="badge badge-success"
                      title="Verified"
                      aria-label="Verified contact"
                    >
                      ✓
                    </span>
                  </Show>
                </div>
              )}
            </For>
          </Show>
        </Show>
      </div>
    </div>
  );
};
