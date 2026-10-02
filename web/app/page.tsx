"use client";

import { AnimatePresence, motion } from "motion/react";
import { Mic, MicOff, Send, Square, Volume2, VolumeX } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { Button } from "@/components/ui/button";
import { type Speaker, SpeakerIcon, bubbleColor } from "@/components/speaker";
import { Input } from "@/components/ui/input";
import { revealed, visible } from "@/components/spoken";
import { type MicrophoneAccess, useRecorder } from "@/components/use-recorder";

// `operator` is a person of the team answering from the console; `assistant` is the agent.
// `shown`: while the voice reads a reply, how many of its characters the voice has reached; the
// rest is not on screen yet. `reading` tells which reading (see `speaking`) the message belongs to.
type Message = { role: Speaker; text: string; meta?: string; reading?: number; shown?: number };

type ChatResponse = {
  reply: string | null; // null: a person has this chat and answers from the operator console

  thread_id: string;
  customer_id: string | null;
  skill: string | null;
  tools_used: string[];
  handoff: object | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type DemoCustomer = { customer_id: string; first_name: string; country: string; segment: string };

type Session = { customer: string; token: string; expiresAt: number };

const MICROPHONE: Record<MicrophoneAccess, { label: string; look: string }> = {
  "not asked": { label: "Permitir micrófono", look: "" },
  granted: { label: "Micrófono listo", look: "border-emerald-300 text-emerald-700" },
  denied: { label: "Sin acceso al micrófono", look: "border-destructive/40 text-destructive" },
};

// The voice for the reply to a typed message, which Whisper never heard: ã, õ and ç are written
// in Portuguese and not in Spanish.
const PORTUGUESE = /[ãõç]/i;

const LEAD = 0.2; // seconds the text runs ahead of the voice: behind it, it would look broken

function newThread() {
  return crypto.randomUUID();
}

function describe(response: ChatResponse) {
  if (response.handoff) return "→ transferido a una persona";
  if (response.skill) return `skill: ${response.skill} · tools: ${response.tools_used.join(", ") || "—"}`;
  return undefined;
}

export default function Home() {
  const [customerId, setCustomerId] = useState("");
  const [demoCustomers, setDemoCustomers] = useState<DemoCustomer[]>([]);
  const [threadId, setThreadId] = useState(newThread);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [sound, setSound] = useState(false); // the agent's voice: off until the customer turns it on
  const [preparing, setPreparing] = useState(false); // the audio of a reply's first line is on its way
  const { access, allow, recording, start, stop } = useRecorder();

  // Safari only lets a page make sound from a click, so the click that turns the voice on opens
  // this context and every line is played through it.
  const audio = useRef<AudioContext | null>(null);
  const voice = useRef<AudioBufferSourceNode | null>(null); // the line being read aloud
  const speaking = useRef(0); // counts the replies read aloud, and the times one was stopped
  const session = useRef<Session | null>(null);
  const operatorCursor = useRef(0); // how many messages of this thread were already checked
  const list = useRef<HTMLElement>(null);

  // Keep the newest message in view: nobody should have to scroll to notice a reply.
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending, preparing]);

  // The customers offered here are the ones the API lets start a demo session (DEMO_CUSTOMER_IDS).
  useEffect(() => {
    fetch(`${API_URL}/api/demo-customers`)
      .then((response) => (response.ok ? response.json() : []))
      .then((customers: DemoCustomer[]) => {
        setDemoCustomers(customers);
        if (customers.length) setCustomerId(customers[0].customer_id);
      })
      .catch(() => setDemoCustomers([]));
  }, []);

  function changeCustomer(value: string) {
    setCustomerId(value);
    setThreadId(newThread());
    setMessages([]);
    operatorCursor.current = 0;
  }

  // Test identity service: the API signs a short-lived token for the chosen demo customer.
  const authHeader = useCallback(async (customer: string, renew: boolean): Promise<Record<string, string>> => {
    const current = session.current;
    if (!renew && current?.customer === customer && current.expiresAt - Date.now() > 30_000) {
      return { Authorization: `Bearer ${current.token}` };
    }
    const response = await fetch(`${API_URL}/api/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id: customer }),
    });
    if (!response.ok) {
      throw new Error(response.status === 403 ? "Ese cliente no tiene sesión de demostración" : `HTTP ${response.status}`);
    }
    const data: { access_token: string; expires_in: number } = await response.json();
    session.current = { customer, token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 };
    return { Authorization: `Bearer ${data.access_token}` };
  }, []);

  // Once the chat has started, ask every few seconds for what a person of the team wrote in it
  // (they answer from /crm). The agent's own replies arrive with each POST, not here.
  const started = messages.length > 0;
  useEffect(() => {
    if (!started) return;
    let active = true;
    let busy = false;
    const timer = setInterval(async () => {
      if (busy) return;
      busy = true;
      try {
        const customer = customerId.trim();
        const auth = customer ? await authHeader(customer, false) : {};
        const response = await fetch(`${API_URL}/api/chat/${threadId}/operator?after=${operatorCursor.current}`, {
          headers: auth,
        });
        if (!active || !response.ok) return;
        const data: { next: number; messages: { text: string }[] } = await response.json();
        operatorCursor.current = data.next;
        if (data.messages.length) {
          setMessages((prev) => [
            ...prev,
            ...data.messages.map((m) => ({ role: "operator" as const, text: m.text, meta: "Persona del equipo" })),
          ]);
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
  }, [started, threadId, customerId, authHeader]);

  async function post(text: string, renew: boolean) {
    const customer = customerId.trim();
    const auth = customer ? await authHeader(customer, renew) : {};
    return fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ message: text, thread_id: threadId }),
    });
  }

  function fail(error: unknown) {
    setMessages((prev) => [...prev, { role: "assistant", text: `Error: ${(error as Error).message}` }]);
  }

  async function speech(path: "transcribe" | "synthesize", body: BodyInit, headers: Record<string, string> = {}) {
    const customer = customerId.trim();
    const auth = customer ? await authHeader(customer, false) : {};
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
  // sounds: text and voice start together.
  async function speak(reply: string, meta: string | undefined, language: string) {
    const reading = ++speaking.current;
    const context = audio.current!;
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
    setMessages((prev) => [...prev, { role: "assistant", text: reply, meta, reading, shown: 0 }]);
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
          source.connect(context.destination);
          const started = context.currentTime;
          let frame = 0;
          const follow = () => {
            reach(line.index + revealed(line[0], (context.currentTime - started + LEAD) / buffer.duration));
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
      if (reading === speaking.current) setPreparing(false);
      setMessages((prev) => prev.map((m) => (m.reading === reading ? { ...m, shown: undefined } : m)));
    }
  }

  // One customer turn, typed or spoken (`heard`: the language Whisper heard it in). With the voice
  // on the reply is also read aloud, without making the customer wait: they can type or talk
  // while it reads.
  async function submit(text: string, heard?: string) {
    setMessages((prev) => [...prev, { role: "customer", text }]);
    setPending(true);
    try {
      let response = await post(text, false);
      if (response.status === 401 && customerId.trim()) response = await post(text, true); // session expired: sign in again once
      if (response.status === 401) throw new Error("Elige un ID de cliente para iniciar sesión");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data: ChatResponse = await response.json();
      const reply = data.reply;
      if (reply === null) return;
      if (sound) void speak(reply, describe(data), heard ?? (PORTUGUESE.test(text + reply) ? "pt" : "es"));
      else setMessages((prev) => [...prev, { role: "assistant", text: reply, meta: describe(data) }]);
    } catch (error) {
      fail(error);
    } finally {
      setPending(false);
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || pending) return;
    setDraft("");
    hush(); // a new question: stop reading the previous answer
    await submit(text);
  }

  // The mic button: the first click records, the second sends what was said as a normal message.
  async function talk() {
    try {
      if (!recording) {
        hush(); // or the microphone would record the agent
        return await start();
      }
      const recorded = await stop();
      setPending(true);
      const heard: { text: string; language: string } = await (await speech("transcribe", recorded)).json();
      if (heard.text) await submit(heard.text, heard.language); // empty: silence
    } catch (error) {
      fail(error);
    } finally {
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

  return (
    <main className="mx-auto flex h-dvh w-full max-w-2xl flex-col gap-4 p-4">
      <header className="flex flex-col gap-3 pt-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Factored 2026</h1>
            <p className="text-sm text-muted-foreground">Customer-service prototype · synthetic data</p>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={MICROPHONE[access].look}
              onClick={() => allow().catch(fail)}
              aria-label="Allow the microphone"
            >
              {access === "denied" ? <MicOff /> : <Mic />}
              {MICROPHONE[access].label}
            </Button>
            <Button
              type="button"
              variant={sound ? "default" : "outline"}
              size="sm"
              onClick={toggleSound}
              aria-pressed={sound}
              aria-label={sound ? "Turn the agent's voice off" : "Turn the agent's voice on"}
            >
              {sound ? <Volume2 /> : <VolumeX />}
              {sound ? "Voz del agente activada" : "Activar voz del agente"}
            </Button>
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="shrink-0 text-muted-foreground">ID de cliente</span>
          <Input
            value={customerId}
            onChange={(event) => changeCustomer(event.target.value)}
            list="demo-customers"
            placeholder="Tu ID de cliente"
            aria-label="Customer ID"
            className="font-mono"
          />
          <datalist id="demo-customers">
            {demoCustomers.map((c) => (
              <option key={c.customer_id} value={c.customer_id} label={`${c.first_name} · ${c.country} · ${c.segment}`} />
            ))}
          </datalist>
        </label>
      </header>

      <section ref={list} className="flex flex-1 flex-col gap-3 overflow-y-auto">
        <AnimatePresence initial={false}>
          {/* A reply at `shown` 0 is waiting for its voice: it comes on screen when the voice starts. */}
          {messages.filter((message) => message.shown !== 0).map((message, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex max-w-[85%] items-start gap-2 ${message.role === "customer" ? "flex-row-reverse self-end" : "self-start"}`}
            >
              <SpeakerIcon speaker={message.role} />
              <div className="min-w-0">
                {message.role === "customer" ? (
                  <div className={`whitespace-pre-wrap rounded-2xl px-4 py-2 ${bubbleColor(message.role)}`}>
                    {message.text}
                  </div>
                ) : (
                  <div
                    className={`rounded-2xl px-4 py-2 [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5 ${bubbleColor(message.role)}`}
                  >
                    <Markdown>{message.shown === undefined ? message.text : visible(message.text, message.shown)}</Markdown>
                  </div>
                )}
                {message.shown !== undefined && (
                  <button
                    type="button"
                    className="mt-1 px-2 text-xs text-muted-foreground underline"
                    onClick={() => setMessages((prev) => prev.map((m) => (m === message ? { ...m, shown: undefined } : m)))}
                  >
                    Mostrar todo
                  </button>
                )}
                {message.shown === undefined && message.meta && (
                  <p className="mt-1 px-2 text-xs text-muted-foreground">{message.meta}</p>
                )}
              </div>
            </motion.div>
          ))}
          {pending && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="self-start px-2 text-sm text-muted-foreground">
              Escribiendo…
            </motion.div>
          )}
          {preparing && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="self-start px-2 text-sm text-muted-foreground">
              Generando la voz…
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      <form onSubmit={send} className="flex gap-2 pb-4">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Escribe tu consulta… (ej. ¿cuál es mi saldo?)"
          aria-label="Message"
        />
        <Button
          type="button"
          size="icon"
          variant={recording ? "destructive" : "outline"}
          onClick={talk}
          disabled={pending}
          aria-label={recording ? "Stop recording" : "Record a message"}
        >
          {recording ? <Square /> : <Mic />}
        </Button>
        <Button type="submit" size="icon" disabled={pending} aria-label="Send">
          <Send />
        </Button>
      </form>
    </main>
  );
}
