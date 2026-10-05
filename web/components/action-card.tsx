"use client";

import { useState } from "react";

import type { ActionBatch, ActionItem } from "@/lib/actions";

// What the agent proposes, as the API wrote it: exactly what will be done, built from the stored
// action and never from the model's prose. The buttons are the confirmation. Once the API has run
// it (or refused it) the same card shows what was verified.

const TONES: Record<ActionItem["tone"], { mark: string; color: string; label: string }> = {
  ok: { mark: "✓", color: "var(--q-teal)", label: "Hecho y verificado" },
  warn: { mark: "!", color: "var(--q-amber-soft)", label: "No se hizo" },
  error: { mark: "✕", color: "#F28B82", label: "No se pudo" },
  info: { mark: "•", color: "var(--q-sky)", label: "Pendiente de tu confirmación" },
};

type Props = {
  batch: ActionBatch;
  onConfirm: (inbox: string | null) => Promise<void>;
  onCancel: () => Promise<void>;
};

export function ActionCard({ batch, onConfirm, onCancel }: Props) {
  const [busy, setBusy] = useState<"confirm" | "cancel" | null>(null);
  const [failure, setFailure] = useState("");
  const [inbox, setInbox] = useState(batch.inbox_choices[0] ?? "");

  async function run(kind: "confirm" | "cancel", action: () => Promise<void>) {
    if (busy) return; // a second click while the first is on its way would ask the API twice
    setBusy(kind);
    setFailure("");
    try {
      await action();
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "No pude completar esto ahora.");
    } finally {
      setBusy(null);
    }
  }

  const waiting = batch.needs_confirmation;
  return (
    <div
      role="group"
      aria-label={batch.title}
      style={{
        padding: "18px 20px", borderRadius: 16, background: "var(--q-ocean)", display: "flex", flexDirection: "column", gap: 12,
        boxShadow: waiting ? "inset 0 0 0 1px rgba(46,196,182,.5)" : "inset 0 0 0 1px rgba(230,244,241,.09)",
      }}
    >
      <span style={{ fontSize: 13, fontWeight: 500, color: waiting ? "var(--q-teal)" : "var(--q-fog)" }}>{batch.title}</span>

      <ul aria-live="polite" style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        {batch.items.map((item) => {
          const tone = TONES[item.tone];
          return (
            <li key={item.action_id} style={{ display: "flex", gap: 10, alignItems: "flex-start", fontSize: 14 }}>
              <span
                role="img"
                aria-label={tone.label}
                style={{
                  flex: "0 0 auto", width: 20, height: 20, borderRadius: 10, display: "grid", placeItems: "center",
                  fontSize: 12, color: "var(--q-abyss)", background: tone.color,
                }}
              >
                {tone.mark}
              </span>
              <span style={{ minWidth: 0 }}>{item.text}</span>
            </li>
          );
        })}
      </ul>

      {waiting && batch.strong_note && (
        <span style={{ fontSize: 13, color: "var(--q-amber-soft)" }}>⚠ {batch.strong_note}</span>
      )}

      {waiting && batch.inbox_label && batch.inbox_choices.length > 0 && (
        <label style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, fontSize: 13, color: "var(--q-fog)" }}>
          {batch.inbox_label}
          <select className="field" value={inbox} onChange={(event) => setInbox(event.target.value)} disabled={busy !== null}>
            {batch.inbox_choices.map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </select>
        </label>
      )}

      {waiting && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          <button
            type="button"
            className="q-btn q-btn-sm q-btn-primary"
            disabled={busy !== null}
            onClick={() => run("confirm", () => onConfirm(inbox || null))}
          >
            {busy === "confirm" ? "…" : batch.confirm_label}
          </button>
          <button type="button" className="q-btn q-btn-sm q-btn-ghost" disabled={busy !== null} onClick={() => run("cancel", onCancel)}>
            {busy === "cancel" ? "…" : batch.cancel_label}
          </button>
        </div>
      )}

      {waiting && batch.expires_note && <span style={{ fontSize: 12, color: "var(--q-muted)" }}>{batch.expires_note}</span>}

      {failure && (
        <span role="alert" style={{ fontSize: 13, color: "var(--q-amber-soft)" }}>
          {failure}
        </span>
      )}
    </div>
  );
}
