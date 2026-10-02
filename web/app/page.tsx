"use client";

import { AnimatePresence, motion } from "motion/react";
import { Send } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Message = { role: "user" | "assistant"; text: string; meta?: string };

type ChatResponse = {
  reply: string;
  thread_id: string;
  customer_id: string | null;
  skill: string | null;
  tools_used: string[];
  handoff: object | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type DemoCustomer = { customer_id: string; first_name: string; country: string; segment: string };

type Session = { customer: string; token: string; expiresAt: number };

function newThread() {
  return crypto.randomUUID();
}

function describe(response: ChatResponse) {
  if (response.handoff) return "→ transferido a una persona";
  if (response.skill) return `skill: ${response.skill} · tools: ${response.tools_used.join(", ") || "—"}`;
  return undefined;
}

export default function Home() {
  const [customerId, setCustomerId] = useState("");
  const [demoCustomers, setDemoCustomers] = useState<DemoCustomer[]>([]);
  const [threadId, setThreadId] = useState(newThread);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);

  const session = useRef<Session | null>(null);

  // The customers offered here are the ones the API lets start a demo session (DEMO_CUSTOMER_IDS).
  useEffect(() => {
    fetch(`${API_URL}/api/demo-customers`)
      .then((response) => (response.ok ? response.json() : []))
      .then((customers: DemoCustomer[]) => {
        setDemoCustomers(customers);
        if (customers.length) setCustomerId(customers[0].customer_id);
      })
      .catch(() => setDemoCustomers([]));
  }, []);

  function changeCustomer(value: string) {
    setCustomerId(value);
    setThreadId(newThread());
    setMessages([]);
  }

  // Test identity service: the API signs a short-lived token for the chosen demo customer.
  async function authHeader(customer: string, renew: boolean): Promise<Record<string, string>> {
    const current = session.current;
    if (!renew && current?.customer === customer && current.expiresAt - Date.now() > 30_000) {
      return { Authorization: `Bearer ${current.token}` };
    }
    const response = await fetch(`${API_URL}/api/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id: customer }),
    });
    if (!response.ok) {
      throw new Error(response.status === 403 ? "Ese cliente no tiene sesión de demostración" : `HTTP ${response.status}`);
    }
    const data: { access_token: string; expires_in: number } = await response.json();
    session.current = { customer, token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 };
    return { Authorization: `Bearer ${data.access_token}` };
  }

  async function post(text: string, renew: boolean) {
    const customer = customerId.trim();
    const auth = customer ? await authHeader(customer, renew) : {};
    return fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ message: text, thread_id: threadId }),
    });
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || pending) return;
    setDraft("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setPending(true);
    try {
      let response = await post(text, false);
      if (response.status === 401 && customerId.trim()) response = await post(text, true); // session expired: sign in again once
      if (response.status === 401) throw new Error("Elige un ID de cliente para iniciar sesión");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data: ChatResponse = await response.json();
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply, meta: describe(data) }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: "assistant", text: `Error: ${(error as Error).message}` }]);
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex h-dvh w-full max-w-2xl flex-col gap-4 p-4">
      <header className="flex flex-col gap-3 pt-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Factored 2026</h1>
          <p className="text-sm text-muted-foreground">Customer-service prototype · synthetic data</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="shrink-0 text-muted-foreground">ID de cliente</span>
          <Input
            value={customerId}
            onChange={(event) => changeCustomer(event.target.value)}
            list="demo-customers"
            placeholder="Tu ID de cliente"
            aria-label="Customer ID"
            className="font-mono"
          />
          <datalist id="demo-customers">
            {demoCustomers.map((c) => (
              <option key={c.customer_id} value={c.customer_id} label={`${c.first_name} · ${c.country} · ${c.segment}`} />
            ))}
          </datalist>
        </label>
      </header>

      <section className="flex flex-1 flex-col gap-3 overflow-y-auto">
        <AnimatePresence initial={false}>
          {messages.map((message, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={message.role === "user" ? "self-end max-w-[85%]" : "self-start max-w-[85%]"}
            >
              {message.role === "user" ? (
                <div className="whitespace-pre-wrap rounded-2xl bg-primary px-4 py-2 text-primary-foreground">
                  {message.text}
                </div>
              ) : (
                <div className="rounded-2xl bg-muted px-4 py-2 [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5">
                  <Markdown>{message.text}</Markdown>
                </div>
              )}
              {message.meta && <p className="mt-1 px-2 text-xs text-muted-foreground">{message.meta}</p>}
            </motion.div>
          ))}
          {pending && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="self-start px-2 text-sm text-muted-foreground">
              Escribiendo…
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      <form onSubmit={send} className="flex gap-2 pb-4">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Escribe tu consulta… (ej. ¿cuál es mi saldo?)"
          aria-label="Message"
        />
        <Button type="submit" size="icon" disabled={pending} aria-label="Send">
          <Send />
        </Button>
      </form>
    </main>
  );
}
