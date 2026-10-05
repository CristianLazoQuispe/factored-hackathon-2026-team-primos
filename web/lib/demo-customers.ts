// The customers the API offers (DEMO_CUSTOMER_IDS): the IDs that can sign in, shown as suggestions in
// the sign-in form. Fetched once; a failed fetch is not remembered.

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export type DemoCustomer = { customer_id: string; first_name: string; country: string; segment: string };

let offered: Promise<DemoCustomer[]> | undefined;

function load(): Promise<DemoCustomer[]> {
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

export function useDemoCustomers(): DemoCustomer[] {
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  useEffect(() => {
    let live = true;
    load().then((found) => {
      if (live) setCustomers(found);
    });
    return () => {
      live = false;
    };
  }, []);
  return customers;
}
