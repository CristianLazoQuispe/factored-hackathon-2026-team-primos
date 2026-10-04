// The customer's session, shared by the chat and "Mis finanzas": sign in on one and the other is
// signed in too. It lives in the tab's sessionStorage, so it survives moving between screens and
// reloading, and dies with the tab. The password is never kept here.

import { useSyncExternalStore } from "react";

const STORED = "session";

export type Session = { customer: string; email: string; token: string; expiresAt: number };

const listeners = new Set<() => void>();

let current: Session | null | undefined; // undefined: not read from the storage yet

export function readSession(): Session | null {
  if (current === undefined) {
    try {
      const stored = sessionStorage.getItem(STORED);
      current = stored ? (JSON.parse(stored) as Session) : null;
    } catch {
      current = null; // storage can be blocked: the session then lasts only until a reload
    }
  }
  return current;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

// `null` signs out.
export function saveSession(session: Session | null) {
  current = session;
  try {
    if (session) sessionStorage.setItem(STORED, JSON.stringify(session));
    else sessionStorage.removeItem(STORED);
  } catch {
    // see `readSession`
  }
  listeners.forEach((listener) => listener());
}

// The server snapshot is empty, so the static page and the browser agree.
export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, readSession, () => null);
}
