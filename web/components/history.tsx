"use client";

import { useState } from "react";
import Markdown from "react-markdown";

import type { OpenedConversation, Outcome, PastConversation } from "@/lib/memory";

// What Quipu remembers of this customer, as the customer sees it: their earlier conversations, and
// one of them opened. It only says what the API stored. Nothing here is sent to the agent: the
// agent is told a short summary by the server, never the messages.

const OUTCOME: Record<Outcome, { label: string; color: string }> = {
  answered: { label: "respondida", color: "var(--q-fog)" },
  proposed: { label: "con una propuesta", color: "var(--q-amber-soft)" },
  done: { label: "hecha", color: "var(--q-teal)" },
  refused: { label: "rechazada", color: "var(--q-amber-soft)" },
  cancelled: { label: "cancelada", color: "var(--q-fog)" },
  handed_off: { label: "con una persona", color: "var(--q-sky)" },
};

function when(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function Result({ outcome }: { outcome: Outcome | null }) {
  if (!outcome || !(outcome in OUTCOME)) return null;
  return (
    <span className="q-chip" style={{ color: OUTCOME[outcome].color }}>
      {OUTCOME[outcome].label}
    </span>
  );
}

type ListProps = {
  items: PastConversation[];
  onOpen: (id: string) => void;
  onForget: () => void;
  busy: boolean; // the history is being deleted
};

// The list shown when the customer comes in, beside the suggestions.
export function PastConversations({ items, onOpen, onForget, busy }: ListProps) {
  const [asking, setAsking] = useState(false); // "are you sure?" before deleting
  if (items.length === 0) return null;
  return (
    <section aria-label="Conversaciones anteriores" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <span style={{ fontFamily: "var(--q-mono)", fontSize: 12, color: "var(--q-muted)" }}>tus conversaciones anteriores</span>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
        {items.map((item) => (
          <li key={item.conversation_id}>
            <button
              type="button"
              className="q-btn q-btn-ghost"
              onClick={() => onOpen(item.conversation_id)}
              style={{ width: "100%", justifyContent: "space-between", textAlign: "left", gap: 12, padding: "10px 16px", height: "auto" }}
            >
              <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                <span style={{ fontSize: 15, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.title || "Sin título"}</span>
                <span style={{ fontSize: 12, color: "var(--q-muted)" }}>
                  {when(item.last_message_at)} · {item.messages} {item.messages === 1 ? "mensaje" : "mensajes"}
                </span>
              </span>
              <Result outcome={item.outcome} />
            </button>
          </li>
        ))}
      </ul>

      {asking ? (
        <div role="alert" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, fontSize: 13, color: "var(--q-fog)" }}>
          <span>Se borrará todo tu historial de conversaciones. No se puede deshacer.</span>
          <button
            type="button"
            className="q-btn q-btn-sm q-btn-ghost"
            disabled={busy}
            onClick={() => {
              setAsking(false);
              onForget();
            }}
          >
            Sí, borrar
          </button>
          <button type="button" className="q-btn q-btn-sm q-btn-ghost" onClick={() => setAsking(false)}>
            No
          </button>
        </div>
      ) : (
        <button type="button" className="link" style={{ alignSelf: "flex-start" }} onClick={() => setAsking(true)} disabled={busy}>
          Borrar mi historial
        </button>
      )}
    </section>
  );
}

type TranscriptProps = { conversation: OpenedConversation; onBack: () => void };

// One earlier conversation, to read. It is over: what the customer writes next starts a new one.
export function PastTranscript({ conversation, onBack }: TranscriptProps) {
  return (
    <section aria-label="Conversación anterior" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
        <button type="button" className="q-btn q-btn-sm q-btn-ghost" onClick={onBack}>
          ← Tus conversaciones
        </button>
        <span style={{ fontSize: 13, color: "var(--q-muted)" }}>{when(conversation.last_message_at)}</span>
        <Result outcome={conversation.outcome} />
      </div>

      {conversation.messages.map((message, index) =>
        message.role === "customer" ? (
          <div
            key={index}
            style={{
              alignSelf: "flex-end", maxWidth: "80%", padding: "12px 16px", borderRadius: "16px 16px 4px 16px",
              background: "var(--q-mist)", color: "var(--q-abyss)", fontSize: 15, whiteSpace: "pre-wrap",
            }}
          >
            {message.content}
          </div>
        ) : (
          <div key={index} style={{ display: "flex", flexDirection: "column", gap: 6, maxWidth: "88%" }}>
            {message.role === "operator" && <span style={{ fontFamily: "var(--q-mono)", fontSize: 12, color: "var(--q-sky)" }}>Agente de soporte</span>}
            <div className="reply">
              <Markdown>{message.content}</Markdown>
            </div>
          </div>
        ),
      )}

      <span style={{ fontSize: 12, color: "var(--q-muted)" }}>Esta conversación ya terminó. Lo que escribas ahora empieza una nueva.</span>
    </section>
  );
}
