"use client";

import Link from "next/link";
import { type FormEvent, type ReactNode, useEffect, useRef, useState, useSyncExternalStore } from "react";
import Markdown from "react-markdown";

import { AppHeader } from "@/components/app-header";
import { AgentIcon, ClientIcon, Logo } from "@/components/logo";

import "./screen.css";

type Role = "customer" | "assistant" | "operator";

type Message = { role: Role; text: string; at: string };

type Status = "bot" | "waiting" | "human";

type Conversation = {
  thread_key: string;
  customer_id: string | null;
  status: Status;
  case_file: Record<string, unknown> | null;
  messages: Message[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const STORED_KEY = "operator-key";

const STATUS: Record<Status, { label: string; detail: string; color: string }> = {
  waiting: { label: "Necesita un agente", detail: "Espera a un agente de soporte · Quipu en pausa", color: "var(--q-amber-soft)" },
  human: { label: "Atendido por agente", detail: "Atendido por agente de soporte · Quipu en pausa", color: "var(--q-sky)" },
  bot: { label: "Con Quipu", detail: "Lo atiende Quipu", color: "var(--q-teal)" },
};

// Who wrote a message: name, colour and the tile behind the icon.
const AUTHOR: Record<Role, { name: string; color: string; tile: string }> = {
  assistant: { name: "Quipu", color: "var(--q-teal)", tile: "rgba(46,196,182,.08)" },
  customer: { name: "Cliente", color: "var(--q-mist)", tile: "rgba(230,244,241,.06)" },
  operator: { name: "Agente de soporte", color: "var(--q-sky)", tile: "rgba(93,169,233,.12)" },
};

const FILTERS: { label: string; shows: (status: Status) => boolean }[] = [
  { label: "Todas", shows: () => true },
  { label: "Con agente", shows: (status) => status !== "bot" },
  { label: "Con Quipu", shows: (status) => status === "bot" },
];

function AuthorIcon({ role, size }: { role: Role; size: number }) {
  if (role === "assistant") return <Logo animated size={size} />;
  return role === "customer" ? <ClientIcon size={size} /> : <AgentIcon size={size} />;
}

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

function count(messages: Message[], role: Role) {
  const total = messages.filter((message) => message.role === role).length;
  return `${total} ${total === 1 ? "mensaje" : "mensajes"}`;
}

function Screen({ children }: { children: ReactNode }) {
  return (
    <div className="s-console">
      <AppHeader area="consola" active="/consola">
        <div className="legend" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 18, fontSize: 13, color: "var(--q-fog)" }}>
          {(["assistant", "customer", "operator"] as const).map((role) => (
            <span key={role} className="q-st-idle" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <AuthorIcon role={role} size={20} />
              {AUTHOR[role].name}
            </span>
          ))}
        </div>
      </AppHeader>
      {children}
    </div>
  );
}

export default function Console() {
  const key = useSyncExternalStore(
    subscribeToKey,
    () => sessionStorage.getItem(STORED_KEY) ?? "",
    () => "", // the static export is built without a browser: signed out
  );
  const [keyDraft, setKeyDraft] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState(0);
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState("");
  const list = useRef<HTMLDivElement>(null);
  const open = conversations.find((c) => c.thread_key === selected);
  const shown = open?.messages.length;

  // Keep the newest message of the open chat in view, when the chat is opened and as it grows.
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [selected, shown]);

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

  // Replying takes the chat from Quipu; releasing gives it back.
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
      <Screen>
        <main style={{ flex: "1 1 auto", display: "grid", placeItems: "center", padding: 24 }}>
          <div style={{ width: "100%", maxWidth: 380, display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <h1 style={{ margin: 0, fontSize: 28, fontWeight: 500, letterSpacing: "-0.035em" }}>Consola del equipo</h1>
              <p className="q-sub" style={{ margin: 0, fontSize: 14 }}>
                Ingresa la clave de operador para ver las conversaciones.
              </p>
            </div>
            <form onSubmit={signIn} style={{ display: "flex", gap: 8 }}>
              <label htmlFor="operator-key" className="q-sr-only">
                Clave de operador
              </label>
              <input
                id="operator-key"
                className="field"
                type="password"
                value={keyDraft}
                onChange={(event) => setKeyDraft(event.target.value)}
                placeholder="Clave de operador"
                style={{ flex: "1 1 auto", minWidth: 0 }}
              />
              <button type="submit" className="q-btn q-btn-sm q-btn-primary">
                Entrar
              </button>
            </form>
            {notice && <p style={{ margin: 0, fontSize: 13, color: "var(--q-amber-soft)" }}>{notice}</p>}
          </div>
        </main>
      </Screen>
    );
  }

  // The first message a person of the team wrote is where they took the chat from Quipu.
  const takenAt = open?.messages.findIndex((message) => message.role === "operator") ?? -1;

  return (
    <Screen>
      <div className="cols">
        <nav
          aria-label="Conversaciones"
          style={{
            flex: "1 1 280px", padding: 18, display: "flex", flexDirection: "column", gap: 12, overflowY: "auto",
            borderRight: "1px solid rgba(230,244,241,.07)", boxSizing: "border-box",
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, padding: 4, borderRadius: 12, boxShadow: "inset 0 0 0 1px rgba(230,244,241,.08)" }}>
            {FILTERS.map((option, index) => (
              <button key={option.label} type="button" className={index === filter ? "seg seg-on" : "seg"} onClick={() => setFilter(index)}>
                {option.label} · {conversations.filter((c) => option.shows(c.status)).length}
              </button>
            ))}
          </div>
          {!conversations.length && (
            <p className="q-sub" style={{ margin: 0, lineHeight: 1.5 }}>
              Aún no hay conversaciones. Aparecen aquí cuando un cliente escribe, y se pierden cuando el servicio se apaga.
            </p>
          )}
          {conversations
            .filter((c) => FILTERS[filter].shows(c.status))
            .map((c) => (
              <button
                key={c.thread_key}
                type="button"
                className={c.thread_key === selected ? "conv conv-on" : "conv"}
                onClick={() => setSelected(c.thread_key)}
                aria-current={c.thread_key === selected}
              >
                <span style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ fontFamily: "var(--q-mono)", fontSize: 13 }}>{c.customer_id ?? "Sin identificar"}</span>
                  <span style={{ fontSize: 12, color: "var(--q-muted)" }}>{time(c.messages[c.messages.length - 1].at)}</span>
                </span>
                <span className="q-st-speaking" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: STATUS[c.status].color }}>
                  {c.status === "bot" ? <Logo animated bold size={16} /> : <AgentIcon size={16} />}
                  {STATUS[c.status].label}
                </span>
                <span style={{ fontSize: 13, color: "var(--q-fog)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {c.messages[c.messages.length - 1].text}
                </span>
              </button>
            ))}
        </nav>

        {open ? (
          <>
            <section className="thread" style={{ flex: "999 1 520px", minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column" }}>
              <div
                style={{
                  display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12,
                  padding: "16px 28px", borderBottom: "1px solid rgba(230,244,241,.07)",
                }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  <span style={{ fontFamily: "var(--q-mono)", fontSize: 15 }}>{open.customer_id ?? "Sin identificar"}</span>
                  <span style={{ fontSize: 13, color: "var(--q-fog)" }}>{STATUS[open.status].detail}</span>
                </div>
                {open.status !== "bot" && (
                  <button type="button" className="q-btn q-btn-sm q-btn-primary" onClick={() => act("release", { thread_key: open.thread_key })}>
                    Devolver a Quipu
                  </button>
                )}
              </div>

              <div ref={list} style={{ flex: "1 1 auto", overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 20 }}>
                {open.messages.map((message, index) => (
                  <div key={index} style={{ display: "contents" }}>
                    {index === takenAt && (
                      <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: "var(--q-mono)", fontSize: 12, color: "var(--q-sky)" }}>
                        <span style={{ flex: 1, height: 1, background: "rgba(93,169,233,.3)" }} />
                        Agente de soporte tomó la conversación · {time(message.at)}
                        <span style={{ flex: 1, height: 1, background: "rgba(93,169,233,.3)" }} />
                      </div>
                    )}
                    <div className="msg">
                      <span className="q-ico q-st-idle" style={{ width: 32, height: 32, background: AUTHOR[message.role].tile }}>
                        <AuthorIcon role={message.role} size={24} />
                      </span>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
                        <span className="who" style={{ color: AUTHOR[message.role].color }}>
                          {AUTHOR[message.role].name} · {time(message.at)}
                        </span>
                        <div className="body" style={message.role === "assistant" ? undefined : { whiteSpace: "pre-wrap" }}>
                          {message.role === "assistant" ? <Markdown>{message.text}</Markdown> : message.text}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {notice && <p style={{ margin: 0, padding: "0 28px", fontSize: 13, color: "var(--q-amber-soft)" }}>{notice}</p>}
              <form onSubmit={send} style={{ padding: "14px 28px 22px" }}>
                <div
                  style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "6px 6px 6px 14px", borderRadius: 16,
                    background: "rgba(11,42,51,.6)", boxShadow: "inset 0 0 0 1px rgba(93,169,233,.35)",
                  }}
                >
                  <span className="q-ico q-st-idle">
                    <AgentIcon size={22} />
                  </span>
                  <label htmlFor="agent-input" className="q-sr-only">
                    Responder al cliente
                  </label>
                  <input
                    id="agent-input"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder={open.status === "human" ? "Responde como agente de soporte…" : "Responde para tomar la conversación: Quipu dejará de contestar"}
                    autoComplete="off"
                    style={{ flex: "1 1 auto", minWidth: 0, minHeight: 44, border: "none", background: "transparent", font: "inherit", fontSize: 14, color: "var(--q-mist)", outline: "none" }}
                  />
                  <button type="submit" className="q-btn q-btn-sm q-btn-primary" aria-label="Enviar" style={{ width: 44, padding: 0 }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M12 19V5M6 11l6-6 6 6" />
                    </svg>
                  </button>
                </div>
              </form>
            </section>

            <aside
              style={{
                flex: "1 1 300px", padding: 22, display: "flex", flexDirection: "column", gap: 20, overflowY: "auto",
                borderLeft: "1px solid rgba(230,244,241,.07)", background: "var(--q-ocean)", boxSizing: "border-box",
              }}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <span className="q-st-thinking" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--q-teal)" }}>
                  <Logo animated bold size={18} />
                  Resumen de Quipu
                </span>
                <span style={{ fontSize: 20, fontWeight: 500, letterSpacing: "-0.03em", lineHeight: 1.25 }}>
                  {open.case_file ? "Caso derivado a soporte" : "Sin derivación"}
                </span>
                {!open.case_file && (
                  <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: "var(--q-fog)" }}>
                    Quipu atiende esta conversación. Si el cliente pide una persona, el resumen del caso aparece aquí.
                  </p>
                )}
              </div>
              {open.case_file && (
                <div style={{ display: "flex", flexDirection: "column", borderRadius: 14, overflow: "hidden", boxShadow: "inset 0 0 0 1px rgba(230,244,241,.09)" }}>
                  {Object.entries(open.case_file)
                    .filter(([, value]) => value !== null && !(Array.isArray(value) && !value.length))
                    .map(([field, value]) => (
                    <div key={field} className="kv">
                      <span style={{ color: "var(--q-fog)" }}>{field}</span>
                      <span>{typeof value === "string" ? value : JSON.stringify(value)}</span>
                    </div>
                    ))}
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <span style={{ fontSize: 13, color: "var(--q-fog)" }}>Quién intervino</span>
                <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13 }}>
                  {(["assistant", "customer", "operator"] as const).map((role) => (
                    <span key={role} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span style={{ color: AUTHOR[role].color }}>{AUTHOR[role].name}</span>
                      <span style={{ fontFamily: "var(--q-mono)", color: "var(--q-fog)" }}>{count(open.messages, role)}</span>
                    </span>
                  ))}
                </div>
              </div>
              {open.customer_id && (
                <Link href={`/consola/perfil?cliente=${encodeURIComponent(open.customer_id)}`} style={{ fontSize: 14 }}>
                  Ver perfil 360 del cliente →
                </Link>
              )}
            </aside>
          </>
        ) : (
          <section className="thread" style={{ flex: "999 1 520px", display: "grid", placeItems: "center", padding: 24, fontSize: 14, color: "var(--q-fog)" }}>
            Elige una conversación para verla completa.
          </section>
        )}
      </div>
    </Screen>
  );
}
