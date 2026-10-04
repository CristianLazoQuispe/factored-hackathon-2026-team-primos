"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppHeader } from "@/components/app-header";
import { CategoryDonut, MonthlyBars } from "@/components/charts";
import { CustomerField } from "@/components/customer-field";
import { Logo } from "@/components/logo";
import { LOOKS_LIKE_CUSTOMER_ID, useCustomerSelection, useDebounced } from "@/lib/customer";
import { formatAmount, getOwnFinances, type OwnFinances } from "@/lib/profile";

import "./screen.css";

const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

const QUESTIONS = [
  "¿En qué gasto más?",
  "¿Cuánto llevo en transporte este mes?",
  "Compárame con el trimestre anterior",
  "¿Tengo algún cargo raro?",
];

export default function FinancePage() {
  const { customerId, demoCustomers, setCustomerId } = useCustomerSelection(); // shared with the chat
  const typed = customerId.trim();
  const wanted = useDebounced(typed, 400); // not every prefix of an ID typed by hand
  const settled = typed === wanted;
  const valid = LOOKS_LIKE_CUSTOMER_ID.test(wanted);
  // What came back, and for whom: one customer's figures are never shown under another's ID.
  const [result, setResult] = useState<{ customer: string; data?: OwnFinances; error?: string } | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [alertsOn, setAlertsOn] = useState(false);

  useEffect(() => {
    if (!valid) return;
    let live = true;
    getOwnFinances(wanted)
      .then((data) => {
        if (!live) return;
        setResult({ customer: wanted, data });
        setDismissed(false);
        setAlertsOn(false);
      })
      .catch((e: unknown) => {
        if (live) setResult({ customer: wanted, error: e instanceof Error ? e.message : "No pudimos cargar tus finanzas." });
      });
    return () => {
      live = false;
    };
  }, [wanted, valid]);

  const current = settled && valid && result?.customer === wanted ? result : null;
  const data = current?.data ?? null;
  const error = current?.error ?? null;
  const status =
    typed === ""
      ? "Elige un cliente o escribe su ID."
      : settled && !valid
        ? "Ese ID no parece de un cliente: empieza con CLI- o DEMO-."
        : error ?? (data ? null : "Cargando…");

  const alert = data?.alerts[0];

  return (
    <div
      className="s-finance"
      style={{ minHeight: "100vh", display: "flex", flexDirection: "column", fontFamily: "var(--q-font)", color: "var(--q-mist)", background: "var(--q-abyss)" }}
    >
      <AppHeader area="cliente" active="/mis-finanzas">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
          <CustomerField value={customerId} onChange={setCustomerId} customers={demoCustomers} />
          {data && <span className="q-sub">{data.product} · datos sintéticos</span>}
        </div>
      </AppHeader>

      {status && (
        <main style={{ flex: "1 1 auto", maxWidth: 1120, width: "100%", margin: "0 auto", padding: "28px 24px", boxSizing: "border-box" }}>
          <p role={error ? "alert" : "status"} style={{ margin: 0, fontSize: 17, color: "var(--q-fog)" }}>{status}</p>
        </main>
      )}

      {data && (
        <main
          style={{
            flex: "1 1 auto", maxWidth: 1120, width: "100%", margin: "0 auto", padding: "28px 24px 40px",
            boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 18,
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <h1 style={{ margin: 0, fontSize: "clamp(30px, 3.6vw, 44px)", fontWeight: 500, letterSpacing: "-0.045em", lineHeight: 1.05 }}>
              Tus últimos {data.windowDays} días
            </h1>
            <p style={{ margin: 0, fontSize: 17, lineHeight: 1.55, color: "var(--q-fog)", maxWidth: "60ch" }}>
              Gastaste <span style={{ color: "var(--q-mist)" }}>{formatAmount(data.totals.spend)} {data.currency}</span>
              {data.totals.prevChangePct !== null && (
                <>
                  , un {Math.abs(data.totals.prevChangePct)}% {data.totals.prevChangePct < 0 ? "menos" : "más"} que en los{" "}
                  {data.windowDays} días anteriores
                </>
              )}
              . {data.notes.spending}
            </p>
            {data.otherCurrencies.length > 0 && (
              <p className="q-sub" style={{ margin: 0, fontSize: 14 }}>
                También gastaste {data.otherCurrencies.map((c) => `${formatAmount(c.spend)} ${c.currency}`).join(" y ")}; no se suma
                a este total porque es otra moneda.
              </p>
            )}
          </div>

          {alert && !dismissed && (
            <section
              className="q-panel"
              style={{
                flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between",
                boxShadow: "inset 0 0 0 1px rgba(242,194,122,.45)", background: "rgba(191,130,24,.08)",
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", gap: 14, flex: "1 1 420px" }}>
                <span
                  style={{
                    flex: "0 0 auto", width: 40, height: 40, borderRadius: 12, display: "grid", placeItems: "center",
                    background: "rgba(242,194,122,.16)", color: "var(--q-amber-soft)",
                  }}
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M12 9v4M12 17h.01" />
                    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
                  </svg>
                </span>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span className="h">Posible cargo duplicado</span>
                  <span className="q-sub" style={{ fontSize: 14, lineHeight: 1.5 }}>
                    Dos cargos de {alert.merchant} por {formatAmount(alert.amount, 2)} {alert.currency} el {Number(alert.date.slice(8))} de{" "}
                    {MONTHS[Number(alert.date.slice(5, 7)) - 1]}, con {alert.deltaSeconds} segundos de diferencia.
                  </span>
                </div>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <Link className="q-btn q-btn-primary q-btn-sm" href="/chat">Revisarlo con Quipu</Link>
                <button type="button" className="q-btn q-btn-ghost q-btn-sm" onClick={() => setDismissed(true)}>No es un error</button>
              </div>
            </section>
          )}
          {alert && dismissed && (
            <section className="q-panel" style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: "14px 20px" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--q-teal)" }} />
              <span className="q-sub" style={{ fontSize: 14 }}>Listo, marcamos los dos cargos de {alert.merchant} como correctos.</span>
            </section>
          )}

          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(420px, 100%), 1fr))", gap: 18 }}>
            <div className="q-panel">
              <span className="h">¿En qué se fue tu dinero?</span>
              <CategoryDonut categories={data.categories} total={data.totals.spend} ariaLabel="Gasto por categoría" unit={data.currency} shareOf="total" />
            </div>

            <div className="q-panel">
              <span className="h">Mes a mes</span>
              <MonthlyBars monthly={data.monthly} currency={data.currency} height={210} />
              <span className="q-sub">{data.notes.monthly}</span>
            </div>
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(320px, 100%), 1fr))", gap: 18 }}>
            <div className="q-panel">
              <span className="h">Donde más compras</span>
              <div style={{ display: "flex", flexDirection: "column", fontSize: 14 }}>
                {data.topMerchants.map((m, i) => (
                  <div
                    key={m.name}
                    style={{
                      display: "grid", gridTemplateColumns: "1fr auto auto", gap: 14, padding: "10px 0",
                      borderBottom: i < data.topMerchants.length - 1 ? "1px solid rgba(230,244,241,.06)" : undefined,
                    }}
                  >
                    <span>{m.name}</span>
                    <span className="q-sub q-mono">{m.count} {m.unit}</span>
                    <span className="q-mono">{formatAmount(m.amount)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="q-panel">
              <span style={{ display: "flex", alignItems: "center", gap: 8 }} className="h">
                <Logo size={20} />
                Un consejo de Quipu
              </span>
              <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6 }}>{data.notes.tip}</p>
              <div
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "12px 14px",
                  borderRadius: 12, boxShadow: "inset 0 0 0 1px rgba(230,244,241,.1)",
                }}
              >
                <span style={{ fontSize: 14 }}>Alertas de cargos duplicados</span>
                <button
                  type="button"
                  className={alertsOn ? "switch switch-on" : "switch switch-off"}
                  onClick={() => setAlertsOn(!alertsOn)}
                  role="switch"
                  aria-checked={alertsOn}
                  aria-label="Alertas de cargos duplicados"
                >
                  <span className="knob" style={{ left: alertsOn ? 25 : 3 }} />
                </button>
              </div>
              <span className="q-sub">{alertsOn ? "Activadas. Te escribiremos por aquí y en el chat." : "Desactivadas."}</span>
            </div>

            <div className="q-panel">
              <span className="h">Pregúntale a Quipu</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {QUESTIONS.map((q) => (
                  <Link key={q} className="sug" href="/chat">{q}</Link>
                ))}
              </div>
              <span className="q-sub" style={{ lineHeight: 1.5 }}>
                Lo que ves aquí sale de tus movimientos. Las notas internas del banco no se muestran.
              </span>
            </div>
          </section>
        </main>
      )}
    </div>
  );
}
