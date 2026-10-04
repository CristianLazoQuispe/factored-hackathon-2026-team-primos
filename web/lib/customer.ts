// The customer chosen in the "Cliente" field, shared by the chat and "Mis finanzas": change it in one
// and the other follows. It lives in the tab's sessionStorage, so it survives moving between screens
// and reloading, and dies with the tab.

import { useEffect, useState, useSyncExternalStore } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const STORED = "customer-id";

// What a customer ID looks like: the prefix and at least six more characters. This only avoids asking
// the API about half-typed IDs; the API decides whether the customer exists and may start a session.
export const LOOKS_LIKE_CUSTOMER_ID = /^(?:CLI|DEMO)-[A-Z0-9-]{6,}$/i;

export type DemoCustomer = { customer_id: string; first_name: string; country: string; segment: string };

const listeners = new Set<() => void>();

function read(): string {
  try {
    return sessionStorage.getItem(STORED) ?? "";
  } catch {
    return ""; // storage can be blocked: the choice then lasts only until the page is left
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

export function selectCustomer(value: string) {
  try {
    if (value) sessionStorage.setItem(STORED, value);
    else sessionStorage.removeItem(STORED);
  } catch {
    // see `read`
  }
  listeners.forEach((listener) => listener());
}

// The customers the API offers (DEMO_CUSTOMER_IDS), fetched once. A failed fetch is not remembered.
let offered: Promise<DemoCustomer[]> | undefined;

function loadDemoCustomers(): Promise<DemoCustomer[]> {
  if (!offered) {
    offered = fetch(`${API_URL}/api/demo-customers`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<DemoCustomer[]>;
      })
      .catch(() => {
        offered = undefined;
        return [];
      });
  }
  return offered;
}

// The chosen customer and the ones offered as suggestions. With nobody chosen yet, the first one
// offered is chosen. The server snapshot is empty, so the static page and the browser agree.
export function useCustomerSelection() {
  const customerId = useSyncExternalStore(subscribe, read, () => "");
  const [demoCustomers, setDemoCustomers] = useState<DemoCustomer[]>([]);

  useEffect(() => {
    let live = true;
    loadDemoCustomers().then((customers) => {
      if (!live) return;
      setDemoCustomers(customers);
      if (customers.length && !read()) selectCustomer(customers[0].customer_id);
    });
    return () => {
      live = false;
    };
  }, []);

  return { customerId, demoCustomers, setCustomerId: selectCustomer };
}

// `value`, but only after it has stopped changing for `ms`: typing an ID must not ask the API about
// every prefix of it.
export function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}
