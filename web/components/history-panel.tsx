"use client";

import { PastConversations, PastTranscript } from "@/components/history";
import type { OpenedConversation, PastConversation } from "@/lib/memory";

// The earlier conversations, one button away at any moment, also in the middle of a chat. It looks like
// the tray of messages: the same place, the same way to close it.

type Props = {
  items: PastConversation[];
  opened: OpenedConversation | null;
  note: string;
  busy: boolean;
  onOpen: (id: string) => void;
  onBack: () => void;
  onHide: () => void;
  onClose: () => void;
};

export function HistoryPanel({ items, opened, note, busy, onOpen, onBack, onHide, onClose }: Props) {
  return (
    <section
      role="dialog"
      aria-label="Conversaciones anteriores"
      style={{
        position: "fixed", top: 72, right: 16, zIndex: 30, width: "min(480px, 92vw)", maxHeight: "75vh", overflow: "auto",
        padding: "16px 18px", borderRadius: 16, background: "var(--q-ocean)", display: "flex", flexDirection: "column", gap: 12,
        boxShadow: "inset 0 0 0 1px rgba(230,244,241,.12), 0 18px 50px -12px rgba(0,0,0,.65)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 14, fontWeight: 500 }}>Tus conversaciones</span>
        <button type="button" className="q-btn q-btn-sm q-btn-ghost" onClick={onClose} aria-label="Cerrar el historial">
          Cerrar
        </button>
      </div>

      {opened ? (
        <PastTranscript conversation={opened} onBack={onBack} />
      ) : items.length === 0 ? (
        <span style={{ fontSize: 13, color: "var(--q-fog)" }}>
          Todavía no tienes conversaciones anteriores. Aparecerán aquí cuando empieces una nueva.
        </span>
      ) : (
        <PastConversations items={items} onOpen={onOpen} onHide={onHide} busy={busy} />
      )}

      {note && <span style={{ fontSize: 13, color: "var(--q-amber-soft)" }}>{note}</span>}
    </section>
  );
}
