"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppHeader } from "@/components/app-header";
import { getOpsSummary, type OpsSummary } from "@/lib/ops";

import "./screen.css";

const RANGES = [7, 14, 30];
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const AXIS_MAX = 200; // top of the chart's scale, which is also the height of its viewBox
const STATUS = {
  with_agent: { label: "Con agente", color: "#5DA9E9" },
  resolved: { label: "Resuelto", color: "#9DB8B5" },
};

const num = (n: number) => n.toLocaleString("en-US");

// "20 sep" for the day `offset` days after an ISO date.
function dayLabel(iso: string, offset: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + offset);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

export default function OpsPage() {
  const [days, setDays] = useState(14);
  const [summary, setSummary] = useState<OpsSummary | null>(null);
  const [hoverDay, setHoverDay] = useState(-1);
  const [hoverTopic, setHoverTopic] = useState(-1);

  useEffect(() => {
    let current = true;
    getOpsSummary(days).then((s) => {
      if (current) setSummary(s);
    });
    return () => {
      current = false;
    };
  }, [days]);

  return (
    <div className="s-ops" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", fontFamily: "var(--q-font)", color: "#E6F4F1", background: "#04141A" }}>
      <AppHeader area="consola" active="/consola/gerencia">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
          <div style={{ display: "flex", gap: 4, padding: 4, borderRadius: 12, boxShadow: "inset 0 0 0 1px rgba(230,244,241,.08)" }}>
            {RANGES.map((r) => (
              <button
                key={r}
                type="button"
                className={r === days ? "seg seg-on" : "seg"}
                aria-pressed={r === days}
                onClick={() => {
                  setDays(r);
                  setHoverDay(-1);
                }}
              >
                {r} días
              </button>
            ))}
          </div>
          <span className="q-sub">Datos sintéticos de ejemplo</span>
        </div>
      </AppHeader>

      {summary && <Dashboard s={summary} hoverDay={hoverDay} setHoverDay={setHoverDay} hoverTopic={hoverTopic} setHoverTopic={setHoverTopic} />}
    </div>
  );
}

function Dashboard({ s, hoverDay, setHoverDay, hoverTopic, setHoverTopic }: {
  s: OpsSummary;
  hoverDay: number;
  setHoverDay: (i: number) => void;
  hoverTopic: number;
  setHoverTopic: (i: number) => void;
}) {
  const n = s.daily.length;
  const labels = s.daily.map((_, i) => dayLabel(s.periodStart, i));
  const pts = s.daily.map((v, i) => [((i + 0.5) / n) * 1000, AXIS_MAX - v]);
  const line = "M" + pts.map((p) => `${p[0].toFixed(1)} ${p[1]}`).join(" L");
  const area = `${line} L${pts[n - 1][0].toFixed(1)} ${AXIS_MAX} L${pts[0][0].toFixed(1)} ${AXIS_MAX} Z`;
  // The range can change while a day is hovered, so the index is checked against this series.
  const tip = hoverDay >= 0 && hoverDay < n ? hoverDay : -1;
  const tipX = `${(((tip + 0.5) / n) * 100).toFixed(2)}%`;
  const maxTopic = Math.max(...s.topics.map((t) => t.count));
  const humanPct = 100 - s.resolvedByQuipuPct;

  const gridLine = (label: number, strong = false) => (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span className="q-mono q-sub" style={{ width: 32, textAlign: "right", fontSize: 11 }}>{label}</span>
      <span style={{ flex: 1, height: 1, background: strong ? "rgba(230,244,241,.18)" : "rgba(230,244,241,.07)" }} />
    </div>
  );

  return (
    <main style={{ flex: "1 1 auto", maxWidth: 1360, width: "100%", margin: "0 auto", padding: 24, boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 16 }}>
      <h1 style={{ margin: 0, fontSize: 28, fontWeight: 500, letterSpacing: "-0.04em" }}>
        Impacto de Quipu · {labels[0]} – {labels[n - 1]} {s.periodEnd.slice(0, 4)}
      </h1>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(210px, 100%), 1fr))", gap: 16 }}>
        <div className="q-panel panel" style={{ gap: 6 }}>
          <span className="q-sub">Conversaciones</span>
          <span className="kpi-v">{num(s.conversations)}</span>
          <span className="q-sub">{s.prevChangePct >= 0 ? "+" : ""}{s.prevChangePct}% vs. {s.days} días previos</span>
        </div>
        <div className="q-panel panel" style={{ gap: 6, boxShadow: "inset 0 0 0 1px rgba(46,196,182,.45)" }}>
          <span className="q-sub">Resueltas por Quipu</span>
          <span className="kpi-v">{s.resolvedByQuipuPct}%</span>
          <span className="q-sub">{num(s.resolvedByQuipu)} sin intervención humana</span>
        </div>
        <div className="q-panel panel" style={{ gap: 6 }}>
          <span className="q-sub">Primera respuesta</span>
          <span className="kpi-v">{s.firstResponseMedianSec.toFixed(1)} s</span>
          <span className="q-sub">mediana · antes: {s.prevFirstResponseMedianMin} min</span>
        </div>
        <div className="q-panel panel" style={{ gap: 6 }}>
          <span className="q-sub">Satisfacción</span>
          <span className="kpi-v">{s.csat.toFixed(1)} <span style={{ fontSize: 15, color: "#9DB8B5" }}>/ 5</span></span>
          <span className="q-sub">{num(s.surveys)} encuestas respondidas</span>
        </div>
        <div className="q-panel panel" style={{ gap: 6 }}>
          <span className="q-sub">Horas de agente liberadas</span>
          <span className="kpi-v">{num(s.hoursSaved)} h</span>
          <span className="q-sub">supuesto: {s.minutesPerConversation} min por consulta</span>
        </div>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(520px, 100%), 1fr))", gap: 16 }}>
        <div className="q-panel panel">
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <span className="h">Conversaciones por día</span>
            <span className="q-sub">{tip >= 0 ? `${labels[tip]} · ${s.daily[tip]} conversaciones` : "Pasa el cursor por la línea"}</span>
          </div>
          <div style={{ position: "relative", height: 220, paddingLeft: 40 }}>
            <div style={{ position: "absolute", left: 0, right: 0, top: 0, bottom: 22, display: "flex", flexDirection: "column", justifyContent: "space-between", pointerEvents: "none" }}>
              {gridLine(AXIS_MAX)}
              {gridLine(AXIS_MAX / 2)}
              {gridLine(0, true)}
            </div>
            <div style={{ position: "absolute", left: 40, right: 0, top: 0, bottom: 22 }}>
              <svg width="100%" height="100%" viewBox={`0 0 1000 ${AXIS_MAX}`} preserveAspectRatio="none" style={{ position: "absolute", inset: 0, overflow: "visible" }} aria-hidden="true">
                <path d={area} fill="rgba(31,165,149,.14)" />
                <path d={line} stroke="#2EC4B6" strokeWidth="2" fill="none" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
              </svg>
              {tip >= 0 && (
                <>
                  <div style={{ position: "absolute", top: 0, bottom: 0, left: tipX, width: 1, background: "rgba(230,244,241,.35)", pointerEvents: "none" }} />
                  <div style={{ position: "absolute", left: tipX, top: `${(100 - (s.daily[tip] / AXIS_MAX) * 100).toFixed(1)}%`, width: 10, height: 10, margin: "-5px 0 0 -5px", borderRadius: "50%", background: "#2EC4B6", boxShadow: "0 0 0 2px #071E26", pointerEvents: "none" }} />
                </>
              )}
              <div style={{ position: "absolute", inset: 0, display: "flex" }}>
                {s.daily.map((v, i) => (
                  <button
                    key={i}
                    type="button"
                    className="col"
                    onMouseEnter={() => setHoverDay(i)}
                    onFocus={() => setHoverDay(i)}
                    onMouseLeave={() => setHoverDay(-1)}
                    onBlur={() => setHoverDay(-1)}
                    aria-label={`${labels[i]}: ${v} conversaciones`}
                  />
                ))}
              </div>
            </div>
            <div style={{ position: "absolute", left: 40, right: 0, bottom: 0, display: "flex", justifyContent: "space-between" }}>
              {[0, Math.floor(n / 2), n - 1].map((i) => (
                <span key={i} className="q-sub q-mono" style={{ fontSize: 11 }}>{labels[i]}</span>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span>Quién resolvió</span>
              <span className="q-sub">{num(s.conversations)} conversaciones</span>
            </div>
            <div style={{ display: "flex", gap: 2, height: 12 }}>
              <span style={{ flex: `${s.resolvedByQuipuPct} 1 0`, background: "#2EC4B6", borderRadius: "4px 0 0 4px" }} />
              <span style={{ flex: `${humanPct} 1 0`, background: "#3B82D6", borderRadius: "0 4px 4px 0" }} />
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 18, fontSize: 13 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: "#2EC4B6" }} />Quipu · {s.resolvedByQuipuPct}%
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: "#3B82D6" }} />Agente de soporte · {humanPct}%
              </span>
            </div>
          </div>
        </div>

        <div className="q-panel panel">
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <span className="h">Temas más consultados</span>
            <span className="q-sub">volumen · % que resolvió Quipu</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {s.topics.map((t, i) => (
              <button
                key={t.name}
                type="button"
                className="trow"
                onMouseEnter={() => setHoverTopic(i)}
                onFocus={() => setHoverTopic(i)}
                onMouseLeave={() => setHoverTopic(-1)}
                onBlur={() => setHoverTopic(-1)}
              >
                <span>{t.name}</span>
                <span style={{ height: 10 }}>
                  <span style={{ display: "block", height: "100%", width: `${((t.count / maxTopic) * 100).toFixed(1)}%`, background: "#1FA595", borderRadius: "0 4px 4px 0", opacity: hoverTopic === -1 || hoverTopic === i ? 1 : 0.4 }} />
                </span>
                <span className="q-mono" style={{ textAlign: "right" }}>{num(t.count)}</span>
                <span className="q-mono" style={{ textAlign: "right", color: "#9DB8B5" }}>{t.resolvedPct}%</span>
              </button>
            ))}
          </div>
          <span className="q-sub" style={{ minHeight: 18 }}>{hoverTopic >= 0 ? s.topics[hoverTopic].note : ""}</span>
          <div style={{ height: 1, background: "rgba(230,244,241,.08)" }} />
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, paddingBottom: 6 }}>
              <span className="h">Derivaciones recientes</span>
              <Link href="/consola" style={{ fontSize: 13 }}>Ver en la consola</Link>
            </div>
            <div className="tbl q-sub" style={{ fontSize: 12 }}><span>Cliente</span><span>Motivo</span><span>Hora</span><span>Estado</span></div>
            {s.recentHandoffs.map((h, i) => (
              <Link
                key={h.clientId}
                href={`/consola/perfil?cliente=${h.clientId}`}
                className="tbl"
                style={i === s.recentHandoffs.length - 1 ? { borderBottom: "none" } : undefined}
              >
                <span className="q-mono">{h.clientId}</span>
                <span>{h.reason}</span>
                <span className="q-mono">{h.at.slice(11, 16)}</span>
                <span style={{ color: STATUS[h.status].color }}>{STATUS[h.status].label}</span>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
