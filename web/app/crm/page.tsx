"use client";

import { Send } from "lucide-react";
import { type FormEvent, useEffect, useState, useSyncExternalStore } from "react";
import Markdown from "react-markdown";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type Message = { role: "customer" | "assistant" | "operator"; text: string; at: string };

type Conversation = {
  thread_key: string;
  customer_id: string | null;
  status: "bot" | "waiting" | "human";
  case_file: Record<string, unknown> | null;
  messages: Message[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const STORED_KEY = "operator-key";

const STATUS = {
  waiting: { label: "Espera a una persona", style: "bg-destructive/10 text-destructive" },
  human: { label: "Lo atiende una persona", style: "bg-primary text-primary-foreground" },
  bot: { label: "Con el asistente", style: "bg-muted text-muted-foreground" },
};

const SENDER = { customer: "Cliente", assistant: "Asistente", operator: "Tú" };

// The console's API (app/adapters/inbound/http.py): a GET without `body`, a POST with it.
function crm(path: string, key: string, body?: object) {
  return fetch(`${API_URL}/api/crm/${path}`, {
    method: body ? "POST" : "GET",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
  });
}

// The operator key lives in sessionStorage, so a reload keeps the operator signed in for the life
// of the tab. `saveKey("")` signs out.
const keyListeners = new Set<() => void>();

function subscribeToKey(listener: () => void) {
  keyListeners.add(listener);
  return () => void keyListeners.delete(listener);
}

function saveKey(value: string) {
  if (value) sessionStorage.setItem(STORED_KEY, value);
  else sessionStorage.removeItem(STORED_KEY);
  keyListeners.forEach((listener) => listener());
}

function time(at: string) {
  return new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function Crm() {
  const key = useSyncExternalStore(
    subscribeToKey,
    () => sessionStorage.getItem(STORED_KEY) ?? "",
    () => "", // the static export is built without a browser: signed out
  );
  const [keyDraft, setKeyDraft] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState("");

  // The console mirrors the API's memory: ask for every chat again every few seconds.
  useEffect(() => {
    if (!key) return;
    let active = true;
    async function refresh() {
      try {
        const response = await crm("conversations", key);
        if (!active) return;
        if (response.status === 401) {
          saveKey("");
          setNotice("Clave de operador incorrecta.");
        } else if (response.ok) {
          const data: Conversation[] = await response.json();
          if (active) setConversations(data);
        }
      } catch {
        // The API is unreachable right now: the next tick asks again.
      }
    }
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [key]);

  function signIn(event: FormEvent) {
    event.preventDefault();
    const value = keyDraft.trim();
    if (!value) return;
    setNotice("");
    setKeyDraft("");
    saveKey(value);
  }

  // Replying takes the chat from the assistant; releasing gives it back.
  async function act(path: "reply" | "release", body: { thread_key: string; text?: string }) {
    const response = await crm(path, key, body);
    if (response.status === 404) return setNotice("Ese chat ya no está en memoria: el servicio se reinició.");
    if (!response.ok) return setNotice(`No se pudo completar la acción (HTTP ${response.status}).`);
    const updated: Conversation = await response.json();
    setNotice("");
    setConversations((prev) => prev.map((c) => (c.thread_key === updated.thread_key ? updated : c)));
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || !selected) return;
    setDraft("");
    await act("reply", { thread_key: selected, text });
  }

  if (!key) {
    return (
      <main className="mx-auto flex h-dvh w-full max-w-sm flex-col justify-center gap-4 p-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Consola de atención</h1>
          <p className="text-sm text-muted-foreground">Ingresa la clave de operador para ver los chats.</p>
        </div>
        <form onSubmit={signIn} className="flex gap-2">
          <Input
            type="password"
            value={keyDraft}
            onChange={(event) => setKeyDraft(event.target.value)}
            placeholder="Clave de operador"
            aria-label="Operator key"
          />
          <Button type="submit">Entrar</Button>
        </form>
        {notice && <p className="text-sm text-destructive">{notice}</p>}
      </main>
    );
  }

  const open = conversations.find((c) => c.thread_key === selected);

  return (
    <main className="mx-auto flex h-dvh w-full max-w-6xl flex-col gap-4 p-4 md:flex-row">
      <aside className="flex shrink-0 flex-col gap-2 overflow-y-auto md:w-80">
        <header className="pt-2">
          <h1 className="text-2xl font-semibold tracking-tight">Consola de atención</h1>
          <p className="text-sm text-muted-foreground">
            {conversations.length
              ? "Chats de esta sesión del servicio. Se pierden cuando el servicio se apaga."
              : "Aún no hay chats. Aparecen aquí cuando un cliente escribe."}
          </p>
        </header>
        {conversations.map((c) => (
          <button
            key={c.thread_key}
            onClick={() => setSelected(c.thread_key)}
            aria-current={c.thread_key === selected}
            className="flex flex-col gap-1 rounded-xl border p-3 text-left hover:bg-muted aria-[current=true]:border-primary aria-[current=true]:bg-muted"
          >
            <span className="flex items-center justify-between gap-2">
              <span className="truncate font-mono text-sm">{c.customer_id ?? "Sin identificar"}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{time(c.messages[c.messages.length - 1].at)}</span>
            </span>
            <span className={`self-start rounded-full px-2 py-0.5 text-xs ${STATUS[c.status].style}`}>
              {STATUS[c.status].label}
            </span>
            <span className="truncate text-sm text-muted-foreground">{c.messages[c.messages.length - 1].text}</span>
          </button>
        ))}
      </aside>

      {open ? (
        <section className="flex min-h-0 flex-1 flex-col gap-3">
          <header className="flex items-center justify-between gap-2 pt-2">
            <div>
              <h2 className="font-mono text-lg">{open.customer_id ?? "Sin identificar"}</h2>
              <p className="text-sm text-muted-foreground">{STATUS[open.status].label}</p>
            </div>
            {open.status !== "bot" && (
              <Button variant="outline" onClick={() => act("release", { thread_key: open.thread_key })}>
                Devolver al asistente
              </Button>
            )}
          </header>

          {open.case_file && (
            <Card>
              <CardHeader>
                <CardTitle>Caso derivado por el asistente</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                  {Object.entries(open.case_file).map(([field, value]) => (
                    <div key={field} className="contents">
                      <dt className="text-muted-foreground">{field}</dt>
                      <dd className="break-words">{typeof value === "string" ? value : JSON.stringify(value)}</dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
          )}

          <div className="flex flex-1 flex-col gap-3 overflow-y-auto">
            {open.messages.map((message, index) => (
              <div key={index} className={message.role === "customer" ? "self-start max-w-[85%]" : "self-end max-w-[85%]"}>
                <div
                  className={
                    message.role === "operator"
                      ? "whitespace-pre-wrap rounded-2xl bg-primary px-4 py-2 text-primary-foreground"
                      : message.role === "customer"
                        ? "whitespace-pre-wrap rounded-2xl bg-muted px-4 py-2"
                        : "rounded-2xl border px-4 py-2 [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5"
                  }
                >
                  {message.role === "assistant" ? <Markdown>{message.text}</Markdown> : message.text}
                </div>
                <p className="mt-1 px-2 text-xs text-muted-foreground">
                  {SENDER[message.role]} · {time(message.at)}
                </p>
              </div>
            ))}
          </div>

          {notice && <p className="text-sm text-destructive">{notice}</p>}
          <form onSubmit={send} className="flex gap-2 pb-4">
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={
                open.status === "human" ? "Escribe tu respuesta…" : "Responde para tomar el chat: el asistente dejará de contestar"
              }
              aria-label="Reply"
            />
            <Button type="submit" size="icon" aria-label="Send">
              <Send />
            </Button>
          </form>
        </section>
      ) : (
        <section className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
          Elige un chat para ver la conversación completa.
        </section>
      )}
    </main>
  );
}
