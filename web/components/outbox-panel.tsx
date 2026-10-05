"use client";

import type { OutboxMessage } from "@/lib/actions";

// What the system sent this customer: the phone of the demo. It says what is true about each
// message: a simulated one was kept here and went nowhere; one sent through a real server was
// accepted by it. "Delivered" is never said, because nothing here can verify it.

const STATUS: Record<OutboxMessage["status"], string> = {
  accepted: "aceptado por el servidor",
  queued: "en cola",
  failed: "falló",
};

function how(message: OutboxMessage): { label: string; color: string } {
  if (message.mode === "simulated") return { label: "simulado · no se envió", color: "var(--q-amber-soft)" };
  return { label: STATUS[message.status], color: message.status === "failed" ? "#F28B82" : "var(--q-teal)" };
}

type Props = { messages: OutboxMessage[]; onClose: () => void };

export function OutboxPanel({ messages, onClose }: Props) {
  return (
    <section
      role="dialog"
      aria-label="Mensajes enviados"
      style={{
        position: "fixed", top: 72, right: 16, zIndex: 30, width: "min(440px, 92vw)", maxHeight: "70vh", overflow: "auto",
        padding: "16px 18px", borderRadius: 16, background: "var(--q-ocean)", display: "flex", flexDirection: "column", gap: 12,
        boxShadow: "inset 0 0 0 1px rgba(230,244,241,.12), 0 18px 50px -12px rgba(0,0,0,.65)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 14, fontWeight: 500 }}>Mensajes enviados al cliente</span>
        <button type="button" className="q-btn q-btn-sm q-btn-ghost" onClick={onClose} aria-label="Cerrar los mensajes">
          Cerrar
        </button>
      </div>

      {messages.length === 0 && <span style={{ fontSize: 13, color: "var(--q-fog)" }}>Todavía no se ha enviado ningún mensaje.</span>}

      {messages.map((message) => {
        const sent = how(message);
        return (
          <details key={message.message_id} style={{ fontSize: 13 }}>
            <summary style={{ cursor: "pointer", display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <span style={{ fontWeight: 500 }}>{message.subject}</span>
              <span className="q-chip" style={{ color: sent.color }}>
                {sent.label}
              </span>
            </summary>
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6, color: "var(--q-fog)" }}>
              <span>Para: {message.destination}</span>
              {message.delivered_to && <span>Buzón de demostración: {message.delivered_to}</span>}
              <span>{new Date(message.created_at).toLocaleString("es")}</span>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "inherit", color: "var(--q-mist)" }}>{message.body}</pre>
            </div>
          </details>
        );
      })}
    </section>
  );
}
