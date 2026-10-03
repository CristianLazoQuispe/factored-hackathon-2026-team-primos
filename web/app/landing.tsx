"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type CSSProperties, type ReactNode, useEffect, useState } from "react";

import { Corona } from "@/components/corona";
import { Logo } from "@/components/logo";

import "./landing.css";

type Mode = "idle" | "speaking";

const MONO = "var(--q-mono)";
const MODES: Mode[] = ["idle", "speaking"];
const LABELS: Record<Mode, string> = { idle: "En espera", speaking: "Respondiendo" };
const TITLES: Record<Mode, string> = { idle: "Quipu está listo", speaking: "Respondiendo en voz alta" };
const CODES: Record<Mode, string> = { idle: "idle", speaking: "tts · streaming" };

const CORD_COLORS = ["#2EC4B6", "#E6F4F1", "#5DA9E9", "#1B998B"];
const EQ = Array.from({ length: 18 }, (_, j) => ({
  col: CORD_COLORS[j % 4],
  top: 14 + ((j * 7) % 5) * 7,
  delay: `${(-(j % 6) * 0.11).toFixed(2)}s`,
}));

// The donut of the "Cliente" card: 90 days of spending by category (sums 13,620 MXN).
const DONUT_COLORS = ["#1FA595", "#BF8218", "#3B82D6", "#CF5E8C", "#8B76DE", "#4F6B6A"];
const DONUT = (() => {
  const values = [4820, 2690, 2140, 1980, 1350, 640], total = 13620;
  const p = (r: number, t: number) => `${(Math.cos(t) * r).toFixed(2)} ${(Math.sin(t) * r).toFixed(2)}`;
  let a = -Math.PI / 2;
  return values.map((v) => {
    const a1 = a + (v / total) * Math.PI * 2, large = a1 - a > Math.PI ? 1 : 0;
    const d = `M${p(94, a)} A94 94 0 ${large} 1 ${p(94, a1)} L${p(60, a1)} A60 60 0 ${large} 0 ${p(60, a)} Z`;
    a = a1;
    return d;
  });
})();

const TRUST = [
  ["Cada respuesta deja traza", "Qué habilidad y qué herramientas usó, visible para el cliente y el equipo."],
  ["El cliente ve sus datos, no las notas del banco", "Segmentos, scores y notas internas solo existen en la consola."],
  ["Una sola identidad", "Quipu responde como asistente del banco, sin revelar el modelo que hay detrás."],
  ["Una persona siempre a un mensaje", "El agente toma el chat cuando quiere y Quipu se detiene."],
];

const sectionHead: CSSProperties = { display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: 24 };
const headText: CSSProperties = { display: "flex", flexDirection: "column", gap: 16 };
const lead: CSSProperties = { margin: 0, color: "#9DB8B5", fontSize: 17, lineHeight: 1.6 };
const cardText: CSSProperties = { margin: 0, color: "#9DB8B5", lineHeight: 1.55 };
const pipeStep: CSSProperties = { flex: "1 1 200px", padding: 20, display: "flex", flexDirection: "column", gap: 10 };
const pipeCaption: CSSProperties = { fontFamily: MONO, fontSize: 12, color: "#5E7F7C" };
const lookCard: CSSProperties = { padding: 26, display: "flex", flexDirection: "column", gap: 18, textDecoration: "none", color: "#E6F4F1" };
const lookTop: CSSProperties = { display: "flex", alignItems: "center", justifyContent: "space-between" };
const lookGo: CSSProperties = { fontSize: 13, color: "#9DB8B5" };
const lookTitle: CSSProperties = { margin: 0, fontSize: 24, fontWeight: 500, letterSpacing: "-0.03em" };
const tick: CSSProperties = { position: "absolute", background: "rgba(230,244,241,.3)" };
const degree: CSSProperties = { position: "absolute", fontFamily: MONO, fontSize: 11, color: "#5E7F7C" };

function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

function Capability({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <div className="panel" style={{ padding: 28, display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: 20, fontWeight: 500, letterSpacing: "-0.02em" }}>{title}</h3>
        <p style={cardText}>{text}</p>
      </div>
      {children}
    </div>
  );
}

function PipeLink() {
  const line: CSSProperties = { flex: 1, height: 2, background: "#2EC4B6" };
  return (
    <div className="pipe-link" style={{ flex: "0 0 48px", alignSelf: "center", display: "flex", alignItems: "center" }}>
      <span style={line} />
      <span style={{ width: 9, height: 9, borderRadius: "50%", background: "#2EC4B6" }} />
      <span style={line} />
    </div>
  );
}

export function Landing() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("idle");
  const [manual, setManual] = useState(false);

  // The hero plays idle <-> speaking on its own until the visitor picks a mode.
  useEffect(() => {
    if (manual) return;
    const timer = setInterval(() => setMode((m) => (m === "idle" ? "speaking" : "idle")), 3600);
    return () => clearInterval(timer);
  }, [manual]);

  // The "Espacio" hint of the main button: the space bar opens the chat, unless it is being
  // used to type or to activate a focused control.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, button, a, [contenteditable]")) return;
      e.preventDefault();
      router.push("/chat");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  return (
    <div className={`s-landing q-st-${mode}`} style={{ fontFamily: "var(--q-font)", color: "#E6F4F1", background: "#04141A", overflow: "hidden" }}>
      <header className="nav" style={{ position: "relative", zIndex: 2, maxWidth: 1200, margin: "0 auto", padding: "20px 32px", display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <a href="#top" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", color: "#E6F4F1" }}>
          <Logo size={30} animated />
          <span style={{ fontWeight: 600, fontSize: 20, letterSpacing: "-0.03em" }}>quipu</span>
        </a>
        <nav style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 28 }}>
          <a className="nl" href="#capacidades">Capacidades</a>
          <a className="nl" href="#miradas">Cliente · Agente · Gerencia</a>
          <a className="nl" href="#agente">Cómo piensa</a>
          <a className="nl" href="#confianza">Confianza</a>
          <Link className="q-btn q-btn-ghost btn-sm" href="/chat">Probar demo</Link>
        </nav>
      </header>

      <section id="top" className="q-grid-bg" style={{ position: "relative", padding: "32px 32px 56px" }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(60% 50% at 72% 48%, rgba(27,153,139,.22), rgba(4,20,26,0) 70%), linear-gradient(180deg, rgba(4,20,26,0) 60%, #04141A 100%)", pointerEvents: "none" }} />
        <div style={{ position: "relative", maxWidth: 1200, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(460px, 100%), 1fr))", gap: "40px 56px", alignItems: "center" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
            <span className="tag" style={{ position: "relative", alignSelf: "flex-start" }}><span className="q-dot" />Agente de voz para banca · Factored 2026</span>
            <h1 className="q-h1" style={{ position: "relative", maxWidth: "10ch" }}>Habla con tu banco.</h1>
            <p style={{ position: "relative", margin: 0, fontSize: 19, lineHeight: 1.55, color: "#9DB8B5", maxWidth: "46ch", textWrap: "pretty" }}>Quipu escucha, busca en tus movimientos y te responde en voz alta. Si algo no cuadra, lo detecta. Si necesitas a una persona, te conecta.</p>
            <div style={{ position: "relative", display: "flex", flexWrap: "wrap", gap: 12 }}>
              <Link className="q-btn q-btn-primary" href="/chat">
                <MicIcon />
                Hablar con Quipu <span className="kbd">Espacio</span>
              </Link>
              <Link className="q-btn q-btn-ghost" href="/consola">Abrir consola del equipo</Link>
            </div>
            <div className="panel" style={{ position: "relative", width: "100%", marginTop: 12, padding: 18, display: "flex", flexDirection: "column", gap: 14, textAlign: "left", backdropFilter: "blur(12px)", boxSizing: "border-box" }}>
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14 }}>
                  <Logo size={22} animated />
                  <span style={{ fontWeight: 500 }}>{TITLES[mode]}</span>
                  <span style={{ color: "#5E7F7C", fontFamily: MONO, fontSize: 12 }}>{CODES[mode]}</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {MODES.map((m) => (
                    <button key={m} type="button" className={m === mode ? "state state-on" : "state"} onClick={() => { setMode(m); setManual(true); }}>{LABELS[m]}</button>
                  ))}
                </div>
              </div>
              <div style={{ height: 1, background: "rgba(230,244,241,.08)" }} />
              <div style={{ display: "grid", gridTemplateColumns: "64px 1fr", gap: "10px 14px", fontSize: 15, lineHeight: 1.5 }}>
                <span style={{ color: "#5E7F7C" }}>Tú</span><span>Veo un movimiento duplicado, ayúdame.</span>
                <span style={{ color: "#2EC4B6" }}>Quipu</span><span>Encontré dos cargos de Uber Trip por 312.40 MXN el 11 de junio, con 4 segundos de diferencia. ¿Te conecto con un agente para revisarlo?</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, paddingLeft: 78 }}><span className="q-chip q-chip-on">data_lookup</span><span className="q-chip">describe_schema</span><span className="q-chip">run_sql</span></div>
            </div>
          </div>
          <div style={{ position: "relative", width: "100%", maxWidth: 520, aspectRatio: "1 / 1", justifySelf: "center" }}>
            <div className="sonar" style={{ inset: 0 }} />
            <div className="sonar" style={{ inset: "12%", borderStyle: "dashed", borderColor: "rgba(230,244,241,.12)" }} />
            <div className="sonar live" style={{ inset: "22%", borderColor: "rgba(46,196,182,.6)" }} />
            <div style={{ ...tick, left: "50%", top: -6, width: 1, height: 14 }} />
            <div style={{ ...tick, left: "50%", bottom: -6, width: 1, height: 14 }} />
            <div style={{ ...tick, top: "50%", left: -6, height: 1, width: 14 }} />
            <div style={{ ...tick, top: "50%", right: -6, height: 1, width: 14 }} />
            <span style={{ ...degree, left: "calc(50% + 10px)", top: 2 }}>000°</span>
            <span style={{ ...degree, right: 12, top: "calc(50% + 6px)" }}>090°</span>
            <div style={{ position: "absolute", inset: 0 }}>
              <Corona mode={mode} />
            </div>
          </div>
        </div>
      </section>

      <section id="capacidades" className="pad" style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 32px", display: "flex", flexDirection: "column", gap: 40 }}>
        <div style={sectionHead}>
          <div style={headText}>
            <span className="label">Capacidades</span>
            <h2 className="q-h2" style={{ maxWidth: "16ch" }}>Lo que antes era una llamada, ahora es una frase.</h2>
          </div>
          <p style={{ ...lead, maxWidth: "36ch" }}>Cuatro cosas que hoy obligan a llamar o esperar, resueltas en una conversación y con traza.</p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(340px, 100%), 1fr))", gap: 16 }}>
          <Capability title="Saldos y movimientos" text="«Dime mis últimos movimientos» y listo.">
            <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", fontSize: 14, borderRadius: 12, overflow: "hidden", boxShadow: "inset 0 0 0 1px rgba(230,244,241,.08)" }}>
              {[["13 jun", "OXXO", "921.67"], ["24 may", "Liverpool", "673.74"], ["23 may", "Pemex", "473.08"]].map(([date, shop, amount], i) => (
                <div key={date} style={{ display: "grid", gridTemplateColumns: "64px 1fr auto", gap: 12, padding: "11px 14px", borderTop: i ? "1px solid rgba(230,244,241,.06)" : undefined }}>
                  <span style={{ color: "#5E7F7C" }}>{date}</span><span>{shop}</span><span style={{ fontFamily: MONO }}>{amount}</span>
                </div>
              ))}
            </div>
          </Capability>

          <Capability title="Cargos duplicados o desconocidos" text="Compara cargos y detecta lo que no cuadra.">
            <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 8, fontSize: 14 }}>
              {["Uber Trip · 11 jun", "Uber Trip · 11 jun · +4 s"].map((charge) => (
                <div key={charge} style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, padding: "12px 14px", borderRadius: 12, background: "rgba(46,196,182,.08)", boxShadow: "inset 0 0 0 1px rgba(46,196,182,.35)" }}>
                  <span>{charge}</span><span style={{ fontFamily: MONO }}>312.40</span>
                </div>
              ))}
              <span style={{ alignSelf: "flex-start" }} className="q-chip q-chip-on">Δ 4 s · posible duplicado</span>
            </div>
          </Capability>

          <Capability title="Voz de ida y vuelta" text="Le hablas, te contesta en voz alta. Todo queda también por escrito.">
            <div style={{ marginTop: "auto", display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 4, padding: 16, borderRadius: 12, boxShadow: "inset 0 0 0 1px rgba(230,244,241,.08)" }}>
              {EQ.map((e, j) => (
                <div key={j} className="eq-c" style={{ color: e.col }}>
                  <div className="cd-l" />
                  <div className="kn" style={{ top: e.top, animationDelay: e.delay }} />
                </div>
              ))}
            </div>
          </Capability>

          <Capability title="Una persona, cuando hace falta" text="Pasa el caso a un agente con todo el contexto. Nadie repite nada.">
            <div style={{ marginTop: "auto", display: "flex", alignItems: "center", gap: 12, padding: 16, borderRadius: 12, boxShadow: "inset 0 0 0 1px rgba(230,244,241,.08)", fontSize: 14 }}>
              <span style={{ width: 36, height: 36, borderRadius: "50%", display: "grid", placeItems: "center", background: "rgba(46,196,182,.14)", boxShadow: "inset 0 0 0 1px rgba(46,196,182,.4)" }}><Logo size={20} /></span>
              <span style={{ flex: "1 1 auto", height: 1, background: "repeating-linear-gradient(90deg, #2EC4B6 0 6px, transparent 6px 12px)" }} />
              <span style={{ padding: "6px 10px", borderRadius: 8, background: "rgba(230,244,241,.06)" }}>Resumen del caso</span>
              <span style={{ flex: "1 1 auto", height: 1, background: "repeating-linear-gradient(90deg, #2EC4B6 0 6px, transparent 6px 12px)" }} />
              <span style={{ width: 36, height: 36, borderRadius: "50%", display: "grid", placeItems: "center", background: "#E6F4F1", color: "#04141A" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" /></svg>
              </span>
            </div>
          </Capability>

          <Capability title="Te avisa antes de que preguntes" text="Si detecta un cobro repetido o raro, Quipu escribe primero.">
            <div style={{ marginTop: "auto", display: "flex", gap: 12, alignItems: "flex-start", padding: 14, borderRadius: 12, background: "rgba(191,130,24,.1)", boxShadow: "inset 0 0 0 1px rgba(242,194,122,.4)", fontSize: 14 }}>
              <Logo size={22} />
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span>Detecté un posible cargo duplicado de Uber Trip. ¿Lo revisamos?</span><span style={{ fontSize: 12, color: "#F2C27A" }}>Alerta · hace un momento</span></div>
            </div>
          </Capability>

          <Capability title="Respuestas con gráficos" text="«¿En qué gasto más?» se responde con un gráfico, no con una lista.">
            <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 8, padding: 16, borderRadius: 12, boxShadow: "inset 0 0 0 1px rgba(230,244,241,.08)", fontSize: 13 }}>
              {[["Súper", "100%", "#1FA595", "35%"], ["Transporte", "56%", "#BF8218", "20%"], ["Combustible", "44%", "#3B82D6", "16%"]].map(([name, width, color, share]) => (
                <div key={name} style={{ display: "grid", gridTemplateColumns: "110px 1fr 44px", gap: 10, alignItems: "center" }}>
                  <span>{name}</span><span style={{ height: 8, width, background: color, borderRadius: "0 4px 4px 0" }} /><span style={{ fontFamily: MONO, textAlign: "right" }}>{share}</span>
                </div>
              ))}
            </div>
          </Capability>
        </div>
      </section>

      <section id="agente" style={{ background: "#071E26", borderTop: "1px solid rgba(230,244,241,.06)", borderBottom: "1px solid rgba(230,244,241,.06)" }}>
        <div className="pad" style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 32px", display: "flex", flexDirection: "column", gap: 48 }}>
          <div style={{ ...headText, maxWidth: 640 }}>
            <span className="label">Cómo piensa</span>
            <h2 className="q-h2">Un agente que muestra su trabajo.</h2>
            <p style={lead}>Cada pregunta pasa por una habilidad y unas herramientas. La traza queda visible debajo de cada respuesta, para el cliente y para el equipo.</p>
          </div>
          <div className="pipe" style={{ display: "flex", flexWrap: "wrap", alignItems: "stretch", gap: 0 }}>
            <div className="panel" style={pipeStep}><span style={pipeCaption}>entrada · voz o texto</span><span style={{ fontSize: 17 }}>«dime mis últimos movimientos»</span></div>
            <PipeLink />
            <div className="panel" style={{ ...pipeStep, boxShadow: "inset 0 0 0 1px rgba(46,196,182,.45)" }}><span style={pipeCaption}>habilidad</span><span style={{ fontFamily: MONO, fontSize: 17, color: "#2EC4B6" }}>data_lookup</span></div>
            <PipeLink />
            <div className="panel" style={pipeStep}><span style={pipeCaption}>herramientas</span><span style={{ fontFamily: MONO, fontSize: 15 }}>describe_schema<br />run_sql</span></div>
            <PipeLink />
            <div className="panel" style={pipeStep}><span style={pipeCaption}>salida · voz y texto</span><span style={{ fontSize: 17 }}>5 movimientos, 1 posible duplicado</span></div>
          </div>
        </div>
      </section>

      <section id="miradas" className="pad" style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 32px", display: "flex", flexDirection: "column", gap: 40 }}>
        <div style={sectionHead}>
          <div style={headText}>
            <span className="label">Un sistema completo</span>
            <h2 className="q-h2" style={{ maxWidth: "18ch" }}>La misma inteligencia, tres miradas.</h2>
          </div>
          <p style={{ ...lead, maxWidth: "38ch" }}>Cada persona ve lo que necesita de los mismos datos, y nada más.</p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(320px, 100%), 1fr))", gap: 16 }}>
          <Link href="/mis-finanzas" className="panel look" style={lookCard}>
            <div style={lookTop}><span className="q-chip q-chip-on">Cliente</span><span style={lookGo}>Mis finanzas →</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}><h3 style={lookTitle}>Entiende en qué se va su dinero</h3><p style={cardText}>Gasto por categoría, mes a mes y alertas que puede resolver con un toque.</p></div>
            <div style={{ marginTop: "auto", display: "flex", alignItems: "center", gap: 18, padding: 16, borderRadius: 14, background: "#04141A" }}>
              <svg width="96" height="96" viewBox="-100 -100 200 200" aria-hidden="true" style={{ flex: "0 0 auto" }}>
                {DONUT.map((d, i) => <path key={i} d={d} fill={DONUT_COLORS[i]} stroke="#04141A" strokeWidth="3" />)}
              </svg>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 12, color: "#9DB8B5" }}>90 días</span><span style={{ fontSize: 22, fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>13,620 <span style={{ fontSize: 13, color: "#9DB8B5" }}>MXN</span></span><span style={{ fontSize: 12, color: "#9DB8B5" }}>35% en súper</span></div>
            </div>
          </Link>
          <Link href="/consola/perfil" className="panel look" style={lookCard}>
            <div style={lookTop}><span className="q-chip" style={{ color: "#5DA9E9", boxShadow: "inset 0 0 0 1px rgba(93,169,233,.5)" }}>Agente</span><span style={lookGo}>Perfil 360 →</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}><h3 style={lookTitle}>Recibe el caso y al cliente completo</h3><p style={cardText}>Conversación, historial, perfil de gasto y la siguiente mejor acción, con su porqué.</p></div>
            <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 10, padding: 16, borderRadius: 14, background: "#04141A", fontSize: 13 }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}><span className="q-chip">Viajero urbano</span><span className="q-chip" style={{ color: "#F2C27A", boxShadow: "inset 0 0 0 1px rgba(242,194,122,.4)" }}>1 alerta</span></div>
              <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}><Logo size={18} /><span>Ofrecer el reverso del cargo duplicado de Uber Trip</span></div>
            </div>
          </Link>
          <Link href="/consola/gerencia" className="panel look" style={lookCard}>
            <div style={lookTop}><span className="q-chip" style={{ color: "#E6F4F1" }}>Gerencia</span><span style={lookGo}>Panel →</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}><h3 style={lookTitle}>Ve el impacto en el centro de atención</h3><p style={cardText}>Cuánto resuelve Quipu solo, qué temas crecen y cuántas horas libera.</p></div>
            <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 10, padding: 16, borderRadius: 14, background: "#04141A" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}><span style={{ fontSize: 30, fontWeight: 500, letterSpacing: "-0.03em" }}>78%</span><span style={{ fontSize: 13, color: "#9DB8B5" }}>resuelto por Quipu</span></div>
              <div style={{ display: "flex", gap: 2, height: 10 }}><span style={{ flex: "78 1 0", background: "#2EC4B6", borderRadius: "4px 0 0 4px" }} /><span style={{ flex: "22 1 0", background: "#3B82D6", borderRadius: "0 4px 4px 0" }} /></div>
              <span style={{ fontSize: 12, color: "#9DB8B5" }}>Datos de ejemplo</span>
            </div>
          </Link>
        </div>
      </section>

      <section id="confianza" style={{ background: "#071E26", borderTop: "1px solid rgba(230,244,241,.06)" }}>
        <div className="pad" style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 32px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(420px, 100%), 1fr))", gap: 48 }}>
          <div style={headText}>
            <span className="label">Confianza</span>
            <h2 className="q-h2" style={{ maxWidth: "18ch" }}>Hecho para un banco, no para una demo.</h2>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            {TRUST.map(([title, text]) => (
              <div key={title} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                <span style={{ flex: "0 0 22px", width: 22, height: 22, borderRadius: 7, display: "grid", placeItems: "center", background: "rgba(46,196,182,.14)", color: "#2EC4B6" }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7" /></svg>
                </span>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 16, fontWeight: 500 }}>{title}</span><span style={{ color: "#9DB8B5", lineHeight: 1.55 }}>{text}</span></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="q-grid-bg" style={{ position: "relative", borderTop: "1px solid rgba(230,244,241,.06)" }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(50% 70% at 50% 100%, rgba(27,153,139,.25), rgba(4,20,26,0) 70%)", pointerEvents: "none" }} />
        <div className="pad" style={{ position: "relative", maxWidth: 1200, margin: "0 auto", padding: "88px 32px", display: "flex", flexDirection: "column", alignItems: "center", gap: 24, textAlign: "center" }}>
          <h2 style={{ margin: 0, fontWeight: 500, fontSize: "clamp(40px, 5.6vw, 76px)", lineHeight: 1, letterSpacing: "-0.05em", maxWidth: "14ch" }}>Pregúntale lo que quieras.</h2>
          <p style={{ margin: 0, color: "#9DB8B5", fontSize: 17 }}>Prototipo con datos sintéticos. Ningún dato real de clientes.</p>
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 12 }}><Link className="q-btn q-btn-primary" href="/chat"><MicIcon />Hablar con Quipu</Link></div>
        </div>
      </section>

      <footer style={{ borderTop: "1px solid rgba(230,244,241,.06)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 32px", display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 16, fontSize: 13, color: "#5E7F7C" }}>
          <span>quipu · Equipo Primos · Factored Hackathon 2026</span>
          <span style={{ fontFamily: MONO }}>datos sintéticos · v0.2</span>
        </div>
      </footer>
    </div>
  );
}
