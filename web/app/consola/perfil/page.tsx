"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AppHeader } from "@/components/app-header";
import { CategoryDonut, MonthlyBars } from "@/components/charts";
import { ClientIcon, Logo } from "@/components/logo";
import { DEMO_CLIENT_ID, formatAmount, getProfile, type ClientProfile } from "@/lib/profile";

import "./screen.css";

const UNIT = { fontSize: 15, color: "var(--q-fog)" };

function ProfileScreen() {
  const clientId = useSearchParams().get("cliente") || DEMO_CLIENT_ID;
  const [data, setData] = useState<ClientProfile | null>(null);
  const [action, setAction] = useState<"open" | "applied" | "discarded">("open");

  useEffect(() => {
    getProfile(clientId).then(setData);
  }, [clientId]);

  return (
    <div
      className="s-profile"
      style={{ minHeight: "100vh", display: "flex", flexDirection: "column", fontFamily: "var(--q-font)", color: "var(--q-mist)", background: "var(--q-abyss)" }}
    >
      <AppHeader area="consola" active="/consola/perfil">
        <span className="q-sub">Datos sintéticos de ejemplo</span>
      </AppHeader>

      {data && (
        <main
          style={{
            flex: "1 1 auto", maxWidth: 1360, width: "100%", margin: "0 auto", padding: 24, boxSizing: "border-box",
            display: "flex", flexDirection: "column", gap: 16,
          }}
        >
          <section style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <span
                className="q-st-idle"
                style={{
                  width: 52, height: 52, borderRadius: 16, display: "grid", placeItems: "center",
                  background: "rgba(230,244,241,.06)", boxShadow: "inset 0 0 0 1px rgba(230,244,241,.1)",
                }}
              >
                <ClientIcon size={30} />
              </span>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="q-mono" style={{ fontSize: 20 }}>{data.clientId}</span>
                <span className="q-sub">
                  {data.product} · {data.country} · {data.currency} · últimos {data.windowDays} días
                </span>
              </div>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {data.alerts.length > 0 && (
                <span className="q-chip" style={{ color: "var(--q-amber-soft)", boxShadow: "inset 0 0 0 1px rgba(242,194,122,.4)" }}>
                  {data.alerts.length === 1 ? "1 alerta abierta" : `${data.alerts.length} alertas abiertas`}
                </span>
              )}
              {data.internal.segments.map((s) => (
                <span key={s} className="q-chip">{s}</span>
              ))}
            </div>
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))", gap: 16 }}>
            <div className="q-panel kpi">
              <span className="q-sub">Gasto total · {data.windowDays} días</span>
              <span className="kpi-v">{formatAmount(data.totals.spend)} <span style={UNIT}>{data.currency}</span></span>
              <span className="q-sub">
                {data.totals.prevChangePct === null
                  ? "sin gasto en los días previos"
                  : `${data.totals.prevChangePct > 0 ? "+" : ""}${data.totals.prevChangePct}% vs. ${data.windowDays} días previos`}
              </span>
            </div>
            <div className="q-panel kpi">
              <span className="q-sub">Transacciones</span>
              <span className="kpi-v">{data.totals.transactions}</span>
              <span className="q-sub">~{data.totals.txPerWeek} por semana</span>
            </div>
            <div className="q-panel kpi">
              <span className="q-sub">Ticket promedio</span>
              <span className="kpi-v">{formatAmount(data.totals.avgTicket)} <span style={UNIT}>{data.currency}</span></span>
              <span className="q-sub">máximo: {data.totals.maxTicket.merchant} {formatAmount(data.totals.maxTicket.amount, 2)}</span>
            </div>
            <div className="q-panel kpi">
              <span className="q-sub">Satisfacción (encuestas)</span>
              <span className="kpi-v">{data.internal.csat} <span style={UNIT}>/ 10</span></span>
              <span className="q-sub">última respuesta: {data.internal.csatDate}</span>
            </div>
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(420px, 100%), 1fr))", gap: 16 }}>
            <div className="q-panel">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <span className="h">Gasto por categoría</span>
                <span className="q-sub">{data.windowDays} días</span>
              </div>
              <CategoryDonut
                categories={data.categories}
                total={data.totals.spend}
                ariaLabel="Donut de gasto por categoría"
                unit={`${data.currency} · ${data.windowDays} días`}
                shareOf="gasto"
              />
            </div>

            <div className="q-panel">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <span className="h">Gasto mensual</span>
                <span className="q-sub">{data.currency} · {data.monthly[0][0].slice(0, 4)}</span>
              </div>
              <MonthlyBars monthly={data.monthly} currency={data.currency} height={220} />
              <span className="q-sub">{data.internal.monthlyNote}</span>
            </div>
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(320px, 100%), 1fr))", gap: 16 }}>
            <div className="q-panel">
              <span className="h">Comercios frecuentes</span>
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
                    <span className="q-sub q-mono">{m.count} {data.internal.merchantUnits[m.name] ?? m.unit}</span>
                    <span className="q-mono">{formatAmount(m.amount)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="q-panel">
              <span className="h">Historial con el banco</span>
              <div style={{ display: "flex", flexDirection: "column", gap: 14, fontSize: 14 }}>
                {data.internal.history.map((item) => (
                  <div key={item.title} className="tl">
                    <span style={{ width: 10, height: 10, margin: 5, borderRadius: "50%", background: item.current ? "var(--q-teal)" : "var(--q-fog)" }} />
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span>{item.title}</span>
                      <span className="q-sub">{item.meta}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="q-panel" style={{ boxShadow: "inset 0 0 0 1px rgba(46,196,182,.45)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }} className="h">
                <Logo size={20} />
                Siguiente mejor acción
              </span>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <span style={{ fontSize: 17, fontWeight: 500, letterSpacing: "-0.02em", lineHeight: 1.3 }}>{data.internal.nextBestAction.title}</span>
                <span className="q-sub" style={{ lineHeight: 1.55 }}>{data.internal.nextBestAction.why}</span>
              </div>
              {action === "open" ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  <button type="button" className="q-btn q-btn-primary" onClick={() => setAction("applied")}>Aplicar</button>
                  <button type="button" className="q-btn q-btn-ghost" onClick={() => setAction("discarded")}>Descartar</button>
                </div>
              ) : (
                <span className="q-sub" role="status" style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 40 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: action === "applied" ? "var(--q-teal)" : "var(--q-fog)" }} />
                  {action === "applied" ? "Acción aplicada." : "Acción descartada."}
                </span>
              )}
              <div style={{ height: 1, background: "rgba(230,244,241,.08)" }} />
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 14 }}>{data.internal.secondaryAction.title}</span>
                <span className="q-sub">{data.internal.secondaryAction.why}</span>
              </div>
            </div>
          </section>
        </main>
      )}
    </div>
  );
}

// `useSearchParams` needs a Suspense boundary for the page to be exported as static HTML.
export default function ProfilePage() {
  return (
    <Suspense>
      <ProfileScreen />
    </Suspense>
  );
}
