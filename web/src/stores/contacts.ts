/**
 * Contacts store — reactive contact list and active-contact selection.
 */

import { createSignal, createResource } from "solid-js";
import { contacts as api, type Contact } from "@lib/api";

// ── State ────────────────────────────────────────────────────────────────────

const [activeOnion, setActiveOnion] = createSignal<string | null>(null);
const [contactError, setContactError] = createSignal<string | null>(null);

// Resource — auto-fetches and tracks loading/error states
const [contactList, { refetch: refetchContacts }] = createResource<Contact[]>(
  async () => {
    try {
      return await api.list();
    } catch {
      return [];
    }
  }
);

export { activeOnion, setActiveOnion, contactList, refetchContacts, contactError };

export function activeContact(): Contact | undefined {
  return contactList()?.find((c) => c.onion_address === activeOnion());
}

export async function addContact(onion: string, nickname: string): Promise<boolean> {
  setContactError(null);
  try {
    await api.create(onion, nickname);
    await refetchContacts();
    return true;
  } catch (e: any) {
    setContactError(e.detail ?? "Failed to add contact");
    return false;
  }
}

export async function removeContact(id: number): Promise<void> {
  await api.delete(id).catch(() => {});
  await refetchContacts();
  if (contactList()?.find((c) => c.id === id) == null) {
    setActiveOnion(null);
  }
}
