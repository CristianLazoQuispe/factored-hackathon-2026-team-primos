"use client";

import { useState } from "react";

import { formatAmount } from "@/lib/profile";

// What the agent proposed (`confirmation` of a chat reply). Quipu prepares it; only the Confirmar
// button here moves money, through /api/khipu/confirm, where no model runs.
type Side = { product_type?: string; last4?: string; name?: string };

export type Confirmation = {
  transfer_id: string;
  kind: "own_accounts" | "pay_debt" | "third_party";
  origin: Side;
  destination: Side;
  amount: number;
  currency: string;
  expires_at: string;
};

type Outcome = {
  status: "executed" | "blocked" | "expired" | "cancelled";
  reason?: string;
  receipt?: { origin: Side & { new_balance: number } };
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

const TITLE: Record<Confirmation["kind"], string> = {
  own_accounts: "Entre mis cuentas",
  pay_debt: "Pago de deuda",
  third_party: "Khipu a otro cliente",
};

const BLOCKED: Record<string, string> = {
  insufficient_funds: "No hay fondos suficientes en la cuenta de origen.",
  over_debt: "El monto es mayor que la deuda.",
  over_operation_limit: "Supera el límite por operación.",
  over_daily_limit: "Supera el límite diario para otros clientes.",
};

function side(value: Side): string {
  const number = value.last4 ? ` •${value.last4}` : "";
  return `${value.name ?? value.product_type ?? ""}${number}`;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 16, fontSize: 14 }}>
      <span style={{ color: "var(--q-fog)" }}>{label}</span>
      <span style={{ textAlign: "right" }}>{children}</span>
    </div>
  );
}

export function KhipuCard({
  confirmation,
  authHeader,
}: {
  confirmation: Confirmation;
  authHeader: (renew: boolean) => Promise<Record<string, string>>;
}) {
  const [sending, setSending] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [error, setError] = useState("");

  async function send(action: "confirm" | "cancel") {
    setSending(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/khipu/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(await authHeader(false)) },
        body: JSON.stringify({ transfer_id: confirmation.transfer_id }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setOutcome(await response.json());
    } catch (failure) {
      setError(`No se pudo enviar (${(failure as Error).message}). Nada se movió: intenta de nuevo.`);
    } finally {
      setSending(false);
    }
  }

  const amount = `${formatAmount(confirmation.amount, 2)} ${confirmation.currency}`;
  const until = new Date(confirmation.expires_at).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
  return (
    <div
      data-testid="khipu-card"
      style={{
        display: "flex", flexDirection: "column", gap: 10, maxWidth: 380, padding: 16, borderRadius: 14,
        background: "rgba(230,244,241,.03)", boxShadow: "inset 0 0 0 1px rgba(46,196,182,.35)",
      }}
    >
      <span style={{ fontFamily: "var(--q-mono)", fontSize: 12, color: "var(--q-teal)" }}>{TITLE[confirmation.kind]}</span>
      <Row label="Desde">{side(confirmation.origin)}</Row>
      <Row label="Para">{side(confirmation.destination)}</Row>
      <Row label="Monto">
        <strong>{amount}</strong>
      </Row>
      {outcome === null && (
        <>
          <span style={{ fontSize: 12, color: "var(--q-muted)" }}>Nada se mueve hasta que confirmes. Válido hasta las {until}.</span>
          <div style={{ display: "flex", gap: 10 }}>
            <button type="button" className="q-btn q-btn-sm q-btn-primary" onClick={() => void send("confirm")} disabled={sending}>
              Confirmar
            </button>
            <button type="button" className="q-btn q-btn-sm q-btn-ghost" onClick={() => void send("cancel")} disabled={sending}>
              Cancelar
            </button>
          </div>
        </>
      )}
      {outcome?.status === "executed" && (
        <span role="status" style={{ fontSize: 14, color: "var(--q-teal)" }}>
          Hecho. Nuevo saldo de {side(outcome.receipt!.origin)}: {formatAmount(outcome.receipt!.origin.new_balance, 2)}{" "}
          {confirmation.currency}
        </span>
      )}
      {outcome?.status === "cancelled" && (
        <span role="status" style={{ fontSize: 14, color: "var(--q-fog)" }}>
          Cancelado. No se movió nada.
        </span>
      )}
      {outcome?.status === "expired" && (
        <span role="status" style={{ fontSize: 14, color: "var(--q-amber-soft)" }}>
          La propuesta venció y no se movió nada. Pídela otra vez.
        </span>
      )}
      {outcome?.status === "blocked" && (
        <span role="status" style={{ fontSize: 14, color: "var(--q-amber-soft)" }}>
          No se movió nada. {BLOCKED[outcome.reason ?? ""] ?? "La operación ya no cumple las reglas del banco."}
        </span>
      )}
      {error && (
        <span role="alert" style={{ fontSize: 13, color: "var(--q-amber-soft)" }}>
          {error}
        </span>
      )}
    </div>
  );
}
