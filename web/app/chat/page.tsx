"use client";

import { type ChangeEvent, type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { ActionCard } from "@/components/action-card";
import { AppHeader } from "@/components/app-header";
import { Corona, type CoronaHandle } from "@/components/corona";
import { type Confirmation, KhipuCard } from "@/components/khipu-card";
import { AgentIcon, Logo } from "@/components/logo";
import { OutboxPanel } from "@/components/outbox-panel";
import { revealed, visible } from "@/components/spoken";
import { type MicrophoneAccess, useRecorder } from "@/components/use-recorder";
import { type ActionBatch, type OutboxMessage, cancelActions, confirmActions, getOutbox } from "@/lib/actions";
import { useDemoCustomers } from "@/lib/demo-customers";
import { type Category, formatAmount, getOwnFinances } from "@/lib/profile";
import { readSession, saveSession, useSession } from "@/lib/session";
import type { CoronaMode } from "@/lib/quipu-corona";

import "./screen.css";

// `operator` is a person of the team answering from the console; `assistant` is Quipu.
// `skill` and `tools` are the trace of a reply: what Quipu did to answer.
// `shown`: while the voice reads a reply, how many of its characters the voice has reached; the
// rest is not on screen yet. `reading` tells which reading (see `speaking`) the message belongs to.
type Message = {
  role: "customer" | "assistant" | "operator";
  text: string;
  image?: string; // data URL of a photo the customer attached; it stays on this screen
  skill?: string | null;
  tools?: string[];
  handoff?: boolean;
  confirmation?: Confirmation | null; // a money movement Quipu prepared: the card has the button
  chart?: Category[];
  actions?: ActionBatch; // what the agent proposes: the card the customer confirms
  reading?: number;
  shown?: number;
};

type ChatResponse = {
  reply: string | null; // null: a person has this chat and answers from the operator console

  thread_id: string;
  customer_id: string | null;
  skill: string | null;
  tools_used: string[];
  handoff: object | null;
  actions?: ActionBatch | null; // proposed by the agent; nothing runs until the customer confirms
  confirmation: Confirmation | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_IMAGE_BYTES = 4_000_000;

type Attachment = { mediaType: string; base64: string; preview: string };

function loginFailure(status: number): string {
  if (status === 423) return "Cuenta bloqueada. Espera 15 minutos.";
  if (status === 429) return "Demasiados intentos. Espera un minuto.";
  return "ID o contraseña incorrectos.";
}

const MICROPHONE: Record<MicrophoneAccess, { label: string; color: string }> = {
  "not asked": { label: "Permitir micrófono", color: "var(--q-mist)" },
  granted: { label: "Micrófono listo", color: "var(--q-teal)" },
  denied: { label: "Sin acceso al micrófono", color: "var(--q-amber-soft)" },
};

// What the corona is doing, in words, under it.
const STATUS: Record<CoronaMode, { title: string; code: string }> = {
  idle: { title: "Listo para ayudarte", code: "toca el micrófono o escribe" },
  listening: { title: "Te escucho…", code: "toca de nuevo para enviar" },
  thinking: { title: "Buscando en tus datos…", code: "agente · consultando" },
  speaking: { title: "Respondiendo", code: "quipu · respuesta" },
};

// The agent cannot draw yet (it has no `render_chart` tool), so this one question is answered
// here with the sample profile, to show what a reply with a chart looks like.
const SPENDING = "¿En qué gasto más?";

const SUGGESTIONS = ["¿Cuál es mi saldo?", "Dime mis últimos movimientos", SPENDING];

const CATEGORY_COLORS = ["--q-cat-1", "--q-cat-2", "--q-cat-3", "--q-cat-4", "--q-cat-5", "--q-cat-other"];

const ASK_FOR_A_PERSON = "Quiero hablar con un agente";

// The voice for the reply to a typed message, which Whisper never heard: ã, õ and ç are written
// in Portuguese and not in Spanish.
const PORTUGUESE = /[ãõç]/i;

const LEAD = 0.2; // seconds the text runs ahead of the voice: behind it, it would look broken

const ANSWERING = 2400; // ms the corona "speaks" for a reply that is only written (voice off)

// What Quipu says while it works on a reply. The API answers in one piece and does not tell which
// step it is on, so none of these names one.
const WAITING = ["Pensando", "Atando cabos", "Leyendo los nudos", "Haciendo cuentas", "Revisando con cuidado", "Ya casi"];

const WAITING_TURN = 2500; // ms each of them stays

function Dots() {
  return (
    <span className="dots" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

function Waiting() {
  const [index, setIndex] = useState(() => Math.floor(Math.random() * WAITING.length));
  useEffect(() => {
    // Any of the others, so the line always changes.
    const timer = setInterval(
      () => setIndex((prev) => (prev + 1 + Math.floor(Math.random() * (WAITING.length - 1))) % WAITING.length),
      WAITING_TURN,
    );
    return () => clearInterval(timer);
  }, []);
  return <>{WAITING[index]}</>;
}

function newThread() {
  return crypto.randomUUID();
}

// The token as it is, only if it is still good. For what the customer did not ask for (the message
// tray): unlike `authHeader` it never renews a token and never ends a session.
function currentAuth(): Record<string, string> | null {
  const current = readSession();
  return current && current.expiresAt > Date.now() ? { Authorization: `Bearer ${current.token}` } : null;
}

function trace(response: ChatResponse) {
  return {
    skill: response.skill,
    tools: response.tools_used,
    handoff: response.handoff !== null,
    actions: response.actions ?? undefined,
    confirmation: response.confirmation,
  };
}

function SpendingChart({ categories }: { categories: Category[] }) {
  const [hover, setHover] = useState(-1);
  const top = Math.max(...categories.map((c) => c.amount));
  const total = categories.reduce((sum, c) => sum + c.amount, 0);
  return (
    <div style={{ padding: "18px 20px", borderRadius: 16, background: "var(--q-ocean)", boxShadow: "inset 0 0 0 1px rgba(230,244,241,.09)", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 13 }}>
        <span style={{ fontWeight: 500 }}>Gasto por categoría</span>
        <span style={{ color: "var(--q-fog)" }}>MXN · 90 días</span>
      </div>
      {categories.map((category, index) => (
        <button
          key={category.name}
          type="button"
          className="bar-row"
          onMouseEnter={() => setHover(index)}
          onMouseLeave={() => setHover(-1)}
          onFocus={() => setHover(index)}
          onBlur={() => setHover(-1)}
        >
          <span>{category.name}</span>
          <span className="track">
            <span
              className="fill"
              style={{
                display: "block", width: `${(category.amount / top) * 100}%`,
                background: `var(${CATEGORY_COLORS[Math.min(index, CATEGORY_COLORS.length - 1)]})`,
                opacity: hover === -1 || hover === index ? 1 : 0.4,
              }}
            />
          </span>
          <span style={{ fontFamily: "var(--q-mono)", textAlign: "right" }}>{formatAmount(category.amount)}</span>
        </button>
      ))}
      <span style={{ fontSize: 12, color: "var(--q-fog)", minHeight: 16 }}>
        {hover === -1
          ? "Pasa el cursor por una categoría para ver su peso."
          : `${categories[hover].name}: ${Math.round((categories[hover].amount / total) * 100)}% del total`}
      </span>
    </div>
  );
}

export default function Chat() {
  const session = useSession(); // shared with Mis finanzas
  const customerId = session?.customer ?? "";
  const [user, setUser] = useState("");
  const demoCustomers = useDemoCustomers();
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [threadId, setThreadId] = useState(newThread);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [pending, setPending] = useState(false);
  const [transcribing, setTranscribing] = useState(false); // what was just said is being written down
  const [sound, setSound] = useState(false); // Quipu's voice: off until the customer turns it on
  const [preparing, setPreparing] = useState(false); // the audio of a reply's first line is on its way
  const [answering, setAnswering] = useState(false); // a written reply has just arrived
  const { access, allow, recording, start, stop } = useRecorder();

  // Safari only lets a page make sound from a click, so the click that turns the voice on opens
  // this context and every line is played through it.
  const audio = useRef<AudioContext | null>(null);
  const voice = useRef<AudioBufferSourceNode | null>(null); // the line being read aloud
  const speaking = useRef(0); // counts the replies read aloud, and the times one was stopped
  const secret = useRef(""); // the password, only in memory: after a reload the token cannot be renewed
  const operatorCursor = useRef(0); // how many messages of this thread were already checked
  const fileRef = useRef<HTMLInputElement>(null);
  const corona = useRef<CoronaHandle>(null);
  const answered = useRef<ReturnType<typeof setTimeout>>(undefined);
  const end = useRef<HTMLDivElement>(null);

  // Keep the newest message in view: nobody should have to scroll to notice a reply.
  useEffect(() => {
    if (messages.length) end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending, preparing, transcribing]);

  // The token was issued for this ID and password. Renew it the same way when it is about to expire.
  const authHeader = useCallback(async (renew: boolean): Promise<Record<string, string>> => {
    const current = readSession();
    if (!current) return {};
    if (!renew && current.expiresAt - Date.now() > 30_000) {
      return { Authorization: `Bearer ${current.token}` };
    }
    if (!secret.current) {
      saveSession(null);
      throw new Error("Tu sesión expiró. Vuelve a entrar.");
    }
    const response = await fetch(`${API_URL}/api/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: current.user, password: secret.current }),
    });
    if (!response.ok) {
      throw new Error(loginFailure(response.status));
    }
    const data: { access_token: string; expires_in: number; customer_id: string } = await response.json();
    saveSession({ ...current, customer: data.customer_id, token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 });
    return { Authorization: `Bearer ${data.access_token}` };
  }, []);

  // What the system sent this customer. `null`: this deployment has no actions, so there is no tray.
  const [outbox, setOutbox] = useState<OutboxMessage[] | null>(null);
  const [tray, setTray] = useState(false);
  const refreshOutbox = useCallback(async () => {
    const auth = currentAuth();
    if (!auth) return;
    try {
      setOutbox(await getOutbox(auth));
    } catch {
      // the tray is a convenience: if it cannot be read it stays as it was
    }
  }, []);
  useEffect(() => {
    const auth = customerId ? currentAuth() : null;
    if (!auth) return;
    let live = true;
    getOutbox(auth)
      .then((found) => {
        if (live) setOutbox(found);
      })
      .catch(() => undefined); // the tray is a convenience: if it cannot be read there is none
    return () => {
      live = false;
    };
  }, [customerId]);

  // The customer's answer to a card. The API runs the batch once however often this is called and
  // answers with the card as it stands: done and verified, refused, or waiting for a person.
  async function decide(batchId: string | null, confirm: boolean, inbox: string | null) {
    if (!batchId) return;
    const auth = await authHeader(false);
    const view = confirm ? await confirmActions(auth, batchId, threadId, inbox) : await cancelActions(auth, batchId, threadId);
    setMessages((prev) =>
      prev.map((m) =>
        m.actions?.batch_id === view.batch_id ? { ...m, actions: view, ...(view.escalate.length ? { handoff: true } : {}) } : m,
      ),
    );
    void refreshOutbox();
  }

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setLoginError("");
    const response = await fetch(`${API_URL}/api/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: user.trim(), password }),
    });
    if (!response.ok) {
      setLoginError(loginFailure(response.status));
      return;
    }
    const data: { access_token: string; expires_in: number; customer_id: string } = await response.json();
    secret.current = password;
    saveSession({
      customer: data.customer_id,
      user: user.trim(),
      token: data.access_token,
      expiresAt: Date.now() + data.expires_in * 1000,
    });
    setThreadId(newThread());
    setMessages([]);
    operatorCursor.current = 0;
    setPassword("");
  }

  function signOut() {
    secret.current = "";
    saveSession(null);
    setPassword("");
    setLoginError("");
    setThreadId(newThread());
    setMessages([]);
    setOutbox(null);
    setTray(false);
    operatorCursor.current = 0;
  }

  // Once the chat has started, ask every few seconds for what a person of the team wrote in it
  // (they answer from /consola). Quipu's own replies arrive with each POST, not here.
  const started = messages.length > 0;
  useEffect(() => {
    if (!started) return;
    let active = true;
    let busy = false;
    const timer = setInterval(async () => {
      if (busy) return;
      busy = true;
      try {
        const auth = await authHeader(false);
        const response = await fetch(`${API_URL}/api/chat/${threadId}/operator?after=${operatorCursor.current}`, {
          headers: auth,
        });
        if (!active || !response.ok) return;
        const data: { next: number; messages: { text: string }[] } = await response.json();
        operatorCursor.current = data.next;
        if (data.messages.length) {
          setMessages((prev) => [...prev, ...data.messages.map((m) => ({ role: "operator" as const, text: m.text }))]);
        }
      } catch {
        // The API is unreachable right now: the next tick asks again.
      } finally {
        busy = false;
      }
    }, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [started, threadId, authHeader]);

  async function post(text: string, renew: boolean, image?: Attachment | null) {
    const auth = await authHeader(renew);
    return fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({
        message: text,
        thread_id: threadId,
        ...(image ? { image: image.base64, image_type: image.mediaType } : {}),
      }),
    });
  }

  function fail(error: unknown) {
    setMessages((prev) => [...prev, { role: "assistant", text: `Error: ${(error as Error).message}` }]);
  }

  async function speech(path: "transcribe" | "synthesize", body: BodyInit, headers: Record<string, string> = {}) {
    const auth = await authHeader(false);
    const response = await fetch(`${API_URL}/api/speech/${path}`, { method: "POST", headers: { ...headers, ...auth }, body });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response;
  }

  // Stops the reply being read aloud (`speak` sees that the count moved on and ends) and puts
  // whatever the voice had not reached on screen.
  function hush() {
    speaking.current += 1;
    voice.current?.stop();
    setPreparing(false);
    setMessages((prev) => prev.map((m) => (m.shown === undefined ? m : { ...m, shown: undefined })));
  }

  // Reads a reply aloud line by line and writes it on screen at the pace of the voice. The audio
  // of a whole list of balances takes many seconds to generate, so each line plays as soon as it
  // is ready and the next one is generated meanwhile. Nothing is shown before the first line
  // sounds: text and voice start together. The corona's cords move with the loudness of the voice.
  async function speak(reply: string, traced: ReturnType<typeof trace>, language: string) {
    const reading = ++speaking.current;
    const context = audio.current!;
    const analyser = context.createAnalyser();
    analyser.fftSize = 256;
    analyser.connect(context.destination);
    const samples = new Uint8Array(analyser.frequencyBinCount);
    const loudness = () => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const sample of samples) sum += ((sample - 128) / 128) ** 2;
      return Math.min(1, Math.sqrt(sum / samples.length) * 4);
    };
    const lines = [...reply.matchAll(/[^\n]+/g)].filter((line) => /[\p{L}\p{N}]/u.test(line[0])); // not a `---` rule
    const clip = async (line: string) => {
      const spoken = await speech("synthesize", JSON.stringify({ text: line, language }), {
        "Content-Type": "application/json",
      });
      return context.decodeAudioData(await spoken.arrayBuffer());
    };
    let reached = 0;
    const reach = (shown: number) => {
      if (shown === reached) return;
      reached = shown;
      // A message with `shown` gone was shown whole ("Mostrar todo", `hush`): it stays whole.
      setMessages((prev) => prev.map((m) => (m.reading === reading && m.shown !== undefined ? { ...m, shown } : m)));
    };
    setMessages((prev) => [...prev, { role: "assistant", text: reply, ...traced, reading, shown: 0 }]);
    setPreparing(true);
    try {
      let next = clip(lines[0][0]);
      for (const [index, line] of lines.entries()) {
        const buffer = await next;
        if (reading !== speaking.current) return; // the voice was turned off, or the customer is talking again
        if (lines[index + 1]) next = clip(lines[index + 1][0]);
        setPreparing(false);
        await new Promise<void>((resolve) => {
          const source = context.createBufferSource();
          source.buffer = buffer;
          source.connect(analyser);
          const started = context.currentTime;
          let frame = 0;
          const follow = () => {
            reach(line.index + revealed(line[0], (context.currentTime - started + LEAD) / buffer.duration));
            corona.current?.setLevel(loudness());
            frame = requestAnimationFrame(follow);
          };
          source.onended = () => {
            cancelAnimationFrame(frame); // at the end of the line, or when `hush` stops it
            resolve();
          };
          voice.current = source;
          source.start();
          follow();
        });
        reach(line.index + line[0].length);
      }
    } catch (error) {
      fail(error);
    } finally {
      analyser.disconnect();
      if (reading === speaking.current) {
        setPreparing(false);
        corona.current?.setLevel(null);
      }
      setMessages((prev) => prev.map((m) => (m.reading === reading ? { ...m, shown: undefined } : m)));
    }
  }

  // One customer turn, typed or spoken (`heard`: the language Whisper heard it in). With the voice
  // on the reply is also read aloud, without making the customer wait: they can type or talk
  // while it reads.
  async function submit(text: string, heard?: string, image?: Attachment | null) {
    if (!readSession()) {
      setLoginError("Entra con tu ID y contraseña.");
      return;
    }
    setMessages((prev) => [...prev, { role: "customer", text, image: image?.preview }]);
    setPending(true);
    try {
      let response = await post(text, false, image);
      if (response.status === 401 && readSession()) response = await post(text, true, image); // session expired: sign in again once
      if (response.status === 401) throw new Error("Entra con tu ID y contraseña.");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data: ChatResponse = await response.json();
      const reply = data.reply;
      if (reply === null) return;
      if (sound) void speak(reply, trace(data), heard ?? (PORTUGUESE.test(text + reply) ? "pt" : "es"));
      else {
        setMessages((prev) => [...prev, { role: "assistant", text: reply, ...trace(data) }]);
        setAnswering(true);
        clearTimeout(answered.current);
        answered.current = setTimeout(() => setAnswering(false), ANSWERING);
      }
    } catch (error) {
      fail(error);
    } finally {
      setPending(false);
    }
  }

  async function sampleChart() {
    let finances;
    try {
      finances = await getOwnFinances(await authHeader(false));
    } catch (error) {
      fail(error);
      return;
    }
    const top = finances.categories[0];
    const share = Math.round((top.amount / finances.totals.spend) * 100);
    const text = `En los últimos ${finances.windowDays} días gastaste **${formatAmount(finances.totals.spend)} ${finances.currency}**. Lo que más pesa es **${top.name.toLowerCase()}**: ${share}% del total.`;
    setMessages((prev) => [...prev, { role: "customer", text: SPENDING }, { role: "assistant", text, chart: finances.categories }]);
  }

  function ask(text: string) {
    if (pending || !readSession()) return;
    hush(); // a new question: stop reading the previous answer
    void submit(text);
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!IMAGE_TYPES.includes(file.type) || file.size > MAX_IMAGE_BYTES) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "La imagen tiene que ser jpeg, png o webp, de hasta 4 MB." },
      ]);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const preview = String(reader.result);
      setAttachment({ mediaType: file.type, base64: preview.slice(preview.indexOf(",") + 1), preview });
    };
    reader.readAsDataURL(file);
  }

  function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || pending) return;
    const image = attachment;
    setDraft("");
    setAttachment(null);
    hush();
    void submit(text, undefined, image);
  }

  // The mic button: the first click records, the second sends what was said as a normal message.
  async function talk() {
    try {
      if (!recording) {
        hush(); // or the microphone would record Quipu
        return await start();
      }
      const recorded = await stop();
      setPending(true);
      setTranscribing(true);
      const heard: { text: string; language: string } = await (await speech("transcribe", recorded)).json();
      setTranscribing(false);
      if (heard.text) await submit(heard.text, heard.language); // empty: silence
    } catch (error) {
      fail(error);
    } finally {
      setTranscribing(false);
      setPending(false);
    }
  }

  function toggleSound() {
    if (sound) hush();
    else {
      audio.current ??= new AudioContext();
      void audio.current.resume();
    }
    setSound(!sound);
  }

  // A reply at `shown` 0 is waiting for its voice: it comes on screen when the voice starts.
  const thread = messages.filter((message) => message.shown !== 0);
  const reading = thread.some((message) => message.shown !== undefined);
  const mode: CoronaMode = recording ? "listening" : pending || preparing ? "thinking" : reading || answering ? "speaking" : "idle";
  const last = thread[thread.length - 1];
  const withPerson = messages.some((message) => message.handoff || message.role === "operator");

  return (
    <div className={`s-chat q-st-${mode}`}>
      <AppHeader area="cliente" active="/chat">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
          {customerId ? (
            <>
              <span style={{ fontSize: 13, color: "var(--q-fog)" }}>{session?.user}</span>
              {outbox !== null && (
                <button type="button" className="q-btn q-btn-sm q-btn-ghost" onClick={() => setTray((open) => !open)} aria-expanded={tray}>
                  Mensajes{outbox.length ? ` (${outbox.length})` : ""}
                </button>
              )}
              <button type="button" className="q-btn q-btn-sm q-btn-ghost" onClick={signOut}>
                Salir
              </button>
            </>
          ) : (
            <form onSubmit={signIn} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
              <input
                className="field"
                type="text"
                autoComplete="username"
                list="demo-customers"
                spellCheck={false}
                value={user}
                onChange={(event) => setUser(event.target.value)}
                placeholder="ID de cliente"
                aria-label="ID de cliente"
                required
                style={{ width: 200 }}
              />
              <datalist id="demo-customers">
                {demoCustomers.map((c) => (
                  <option key={c.customer_id} value={c.customer_id} label={`${c.first_name} · ${c.country} · ${c.segment}`} />
                ))}
              </datalist>
              <input
                className="field"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Contraseña"
                title="En la demostración, la contraseña es el mismo ID"
                aria-label="Contraseña"
                required
                style={{ width: 140 }}
              />
              <button type="submit" className="q-btn q-btn-sm q-btn-primary">
                Entrar
              </button>
              {loginError && <span style={{ fontSize: 13, color: "var(--q-amber-soft)" }}>{loginError}</span>}
            </form>
          )}
          <button
            type="button"
            className="q-btn q-btn-sm q-btn-ghost"
            onClick={() => allow().catch(fail)}
            style={{ color: MICROPHONE[access].color }}
          >
            {MICROPHONE[access].label}
          </button>
          <button
            type="button"
            className="q-btn q-btn-sm q-btn-ghost"
            onClick={toggleSound}
            aria-pressed={sound}
            aria-label={sound ? "Silenciar la voz de Quipu" : "Activar la voz de Quipu"}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M11 5 6 9H3v6h3l5 4V5z" />
              {sound ? <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" /> : <path d="m22 9-6 6M16 9l6 6" />}
            </svg>
            <span>{sound ? "Voz" : "Silencio"}</span>
          </button>
        </div>
      </AppHeader>

      {tray && outbox && <OutboxPanel messages={outbox} onClose={() => setTray(false)} />}

      <div className="cols">
        <aside
          className="q-grid-bg side"
          style={{
            position: "relative", flex: "1 1 420px", display: "flex", flexDirection: "column", alignItems: "center",
            justifyContent: "center", gap: 26, padding: "36px 24px", borderRight: "1px solid rgba(230,244,241,.07)", boxSizing: "border-box",
          }}
        >
          <div style={{ position: "absolute", inset: 0, background: "radial-gradient(55% 45% at 50% 42%, rgba(27,153,139,.24), rgba(4,20,26,0) 72%)", pointerEvents: "none" }} />
          <div className="orbbox" style={{ position: "relative", width: 340, maxWidth: "80vw", aspectRatio: "1 / 1" }}>
            <div className="sonar" style={{ inset: 0 }} />
            <div className="sonar" style={{ inset: "12%", borderStyle: "dashed", borderColor: "rgba(230,244,241,.12)" }} />
            <div className="sonar live" style={{ inset: "22%", borderColor: "rgba(46,196,182,.6)" }} />
            <div style={{ position: "absolute", inset: 0 }}>
              <Corona mode={mode} ref={corona} />
            </div>
          </div>
          <div style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center", gap: 6, textAlign: "center" }} aria-live="polite">
            <span style={{ fontSize: 26, fontWeight: 500, letterSpacing: "-0.035em" }}>
              {transcribing ? "Procesando audio…" : STATUS[mode].title}
            </span>
            <span style={{ fontFamily: "var(--q-mono)", fontSize: 12, color: "var(--q-muted)" }}>
              {transcribing ? "voz · transcribiendo" : preparing ? "tts · generando la voz" : STATUS[mode].code}
            </span>
          </div>
          <button
            type="button"
            className={`mic ${recording ? "mic-live" : "mic-idle"}`}
            onClick={talk}
            disabled={pending}
            aria-label={recording ? "Dejar de grabar" : "Hablar con Quipu"}
            style={{ position: "relative" }}
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
          </button>
        </aside>

        <main style={{ flex: "999 1 560px", minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column" }}>
          <div
            className="msgs"
            style={{
              flex: "1 1 auto", overflowY: "auto", padding: 32, display: "flex", flexDirection: "column", gap: 26,
              maxWidth: 780, width: "100%", boxSizing: "border-box", margin: "0 auto",
            }}
          >
            <span style={{ alignSelf: "center", fontFamily: "var(--q-mono)", fontSize: 12, color: "var(--q-muted)" }}>
              {customerId ? "sesión iniciada · datos sintéticos" : "entra con tu ID para empezar · datos sintéticos"}
            </span>

            {!started && customerId && (
              <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 8 }}>
                {SUGGESTIONS.map((text) => (
                  <button key={text} type="button" className="sug" onClick={() => (text === SPENDING ? void sampleChart() : ask(text))}>
                    {text}
                  </button>
                ))}
              </div>
            )}

            {thread.map((message, index) =>
              message.role === "customer" ? (
                <div
                  key={index}
                  style={{
                    alignSelf: "flex-end", maxWidth: "80%", padding: "12px 16px", borderRadius: "16px 16px 4px 16px",
                    background: "var(--q-mist)", color: "var(--q-abyss)", fontSize: 15, whiteSpace: "pre-wrap",
                  }}
                >
                  {message.image && (
                    <img
                      src={message.image}
                      alt=""
                      style={{ display: "block", width: "100%", maxWidth: 240, borderRadius: 8, marginBottom: 8 }}
                    />
                  )}
                  {message.text}
                </div>
              ) : (
                <div key={index} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                  {message.role === "operator" ? <AgentIcon size={28} style={{ flex: "0 0 auto" }} /> : <Logo animated={message === last} />}
                  <div style={{ flex: "1 1 auto", minWidth: 0, display: "flex", flexDirection: "column", gap: 12 }}>
                    {message.role === "operator" && (
                      <span style={{ fontFamily: "var(--q-mono)", fontSize: 12, color: "var(--q-sky)" }}>Agente de soporte</span>
                    )}
                    <div className="reply">
                      <Markdown>{message.shown === undefined ? message.text : visible(message.text, message.shown)}</Markdown>
                    </div>
                    {message.confirmation && <KhipuCard confirmation={message.confirmation} authHeader={authHeader} />}
                    {message.chart && <SpendingChart categories={message.chart} />}
                    {message.actions && (
                      <ActionCard
                        batch={message.actions}
                        onConfirm={(inbox) => decide(message.actions?.batch_id ?? null, true, inbox)}
                        onCancel={() => decide(message.actions?.batch_id ?? null, false, null)}
                      />
                    )}
                    {message.chart && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        <span className="q-chip">render_chart</span>
                        <span className="q-chip" style={{ color: "var(--q-amber-soft)" }}>respuesta de muestra</span>
                      </div>
                    )}
                    {message.shown !== undefined && (
                      <button
                        type="button"
                        className="link"
                        style={{ alignSelf: "flex-start" }}
                        onClick={() => setMessages((prev) => prev.map((m) => (m === message ? { ...m, shown: undefined } : m)))}
                      >
                        Mostrar todo
                      </button>
                    )}
                    {message.shown === undefined && message === last && !withPerson && Boolean(message.tools?.length) && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                        <button type="button" className="q-btn q-btn-sm q-btn-ghost" onClick={() => ask(ASK_FOR_A_PERSON)} disabled={pending}>
                          Conectar con un agente
                        </button>
                      </div>
                    )}
                    {message.shown === undefined && (message.skill || message.handoff) && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {message.skill && <span className="q-chip q-chip-on">{message.skill}</span>}
                        {message.tools?.map((tool) => (
                          <span key={tool} className="q-chip">
                            {tool}
                          </span>
                        ))}
                        {message.handoff && (
                          <span className="q-chip" style={{ color: "var(--q-sky)", boxShadow: "inset 0 0 0 1px rgba(93,169,233,.45)" }}>
                            → agente de soporte
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ),
            )}

            {/* Something is on its way: say so in the thread, where the customer is looking. */}
            {transcribing ? (
              <div
                role="status"
                style={{
                  alignSelf: "flex-end", padding: "12px 16px", borderRadius: "16px 16px 4px 16px",
                  background: "var(--q-mist)", color: "var(--q-abyss)", fontSize: 15, opacity: 0.6,
                }}
              >
                Procesando audio
                <Dots />
              </div>
            ) : (
              (pending || preparing) && (
                <div role="status" style={{ display: "flex", gap: 14, alignItems: "center" }}>
                  <Logo animated />
                  <span style={{ fontSize: 15, color: "var(--q-muted)" }}>
                    {pending ? <Waiting /> : "Preparando la voz"}
                    <Dots />
                  </span>
                </div>
              )
            )}
            <div ref={end} />
          </div>

          <form className="composer" onSubmit={send} style={{ padding: "16px 32px 24px", maxWidth: 780, width: "100%", boxSizing: "border-box", margin: "0 auto" }}>
            {attachment && (
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <img src={attachment.preview} alt="" style={{ height: 56, width: 56, objectFit: "cover", borderRadius: 8 }} />
                <button type="button" className="link" onClick={() => setAttachment(null)}>
                  Quitar
                </button>
              </div>
            )}
            <div
              style={{
                display: "flex", alignItems: "center", gap: 8, padding: "6px 6px 6px 8px", borderRadius: 16,
                background: "rgba(11,42,51,.6)", boxShadow: "inset 0 0 0 1px rgba(230,244,241,.12)",
              }}
            >
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={onFile} />
              <button
                type="button"
                aria-label="Adjuntar imagen"
                disabled={!customerId || pending}
                onClick={() => fileRef.current?.click()}
                style={{
                  flex: "0 0 auto", width: 44, height: 44, border: "none", borderRadius: 12, cursor: "pointer",
                  background: "transparent", color: "var(--q-mist)",
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                </svg>
              </button>
              <label htmlFor="q-input" className="q-sr-only">
                Escribe tu consulta
              </label>
              <input
                id="q-input"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={customerId ? "Pregunta por tu saldo, un cargo o una queja…" : "Entra con tu ID para preguntar"}
                disabled={!customerId}
                autoComplete="off"
                style={{ flex: "1 1 auto", minWidth: 0, minHeight: 44, border: "none", background: "transparent", font: "inherit", fontSize: 15, color: "var(--q-mist)", outline: "none" }}
              />
              <button type="submit" className="q-btn q-btn-sm q-btn-primary" disabled={pending || !customerId} aria-label="Enviar" style={{ width: 44, padding: 0 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 19V5M6 11l6-6 6 6" />
                </svg>
              </button>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}
