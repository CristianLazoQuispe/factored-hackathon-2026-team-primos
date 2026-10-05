// Behaviour tests of the history components and of the client of the API. The web has no test
// framework, so: esbuild bundles this file, jsdom plays the browser, and `fetch` is a fake.
// Run them with `bash tests/run.sh` (it installs nothing in the project).
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body><div id=root></div></body></html>", { url: "http://localhost/" });
globalThis.window = dom.window; globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
for (const k of ["HTMLElement", "Node", "Event", "MouseEvent", "SVGElement"]) globalThis[k] = dom.window[k];

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = React;
const { PastConversations, PastTranscript } = await import("@/components/history");
const { HistoryPanel } = await import("@/components/history-panel");
const { useHistory } = await import("@/lib/use-history");
const { saveSession } = await import("@/lib/session");
const memory = await import("@/lib/memory");
globalThis.sessionStorage = dom.window.sessionStorage;

let failures = 0, total = 0;
function check(name, ok, detail = "") { total++; if (!ok) { failures++; console.log("  ✗", name, detail); } else console.log("  ✓", name); }

async function mount(element) {
  const host = dom.window.document.createElement("div"); dom.window.document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(element); });
  return { host, unmount: () => act(async () => root.unmount()) };
}
const click = (el) => act(async () => { el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
const buttons = (host, text) => [...host.querySelectorAll("button")].filter((b) => b.textContent.includes(text));

const items = [
  { conversation_id: "a", title: "bloquea mi tarjeta", skill: "account_actions", outcome: "done", language: "es", last_message_at: "2026-10-04T10:00:00Z", messages: 4 },
  { conversation_id: "b", title: "<img src=x onerror=alert(1)>", skill: null, outcome: "handed_off", language: "es", last_message_at: "2026-10-03T09:00:00Z", messages: 1 },
  { conversation_id: "c", title: null, skill: null, outcome: "hacked", language: null, last_message_at: null, messages: 2 },
];

console.log("PastConversations");
{
  const calls = { open: [], hide: 0 };
  const m = await mount(React.createElement(PastConversations, { items, onOpen: (id) => calls.open.push(id), onHide: () => calls.hide++, busy: false }));
  const html = m.host.innerHTML;
  check("lists every conversation", m.host.querySelectorAll("li").length === 3);
  check("a long list scrolls instead of pushing the page down", m.host.querySelector("ul").style.overflowY === "auto" && m.host.querySelector("ul").style.maxHeight !== "");
  check("shows the title, the count and singular/plural", html.includes("bloquea mi tarjeta") && html.includes("4 mensajes") && html.includes("1 mensaje<") );
  check("a missing title says so", html.includes("Sin título"));
  check("shows the result in words", html.includes("hecha") && html.includes("con una persona"));
  check("an unknown result shows no chip", !html.includes("hacked"));
  check("a title with HTML is text, never markup", !m.host.querySelector("img") && html.includes("&lt;img src=x"));
  await click(buttons(m.host, "bloquea mi tarjeta")[0]);
  check("opening a conversation passes its id", calls.open.join() === "a");
  check("nothing is hidden by opening", calls.hide === 0);
  await m.unmount();
}
{
  const m = await mount(React.createElement(PastConversations, { items: [], onOpen() {}, onHide() {}, busy: false }));
  check("with nothing to show it renders nothing at all", m.host.innerHTML === "");
  await m.unmount();
}
console.log("Hiding (nothing is deleted)");
{
  const calls = { hide: 0 };
  const m = await mount(React.createElement(PastConversations, { items, onOpen() {}, onHide: () => calls.hide++, busy: false }));
  check("the button is offered, the question is not yet", buttons(m.host, "Ocultar mi historial").length === 1 && !m.host.textContent.includes("conserva el registro"));
  await click(buttons(m.host, "Ocultar mi historial")[0]);
  check("it asks first and says the bank keeps the record", m.host.textContent.includes("El banco conserva el registro") && calls.hide === 0);
  check("the alert is announced", m.host.querySelector("[role=alert]") !== null);
  await click(buttons(m.host, "No")[0]);
  check("'No' goes back and hides nothing", calls.hide === 0 && buttons(m.host, "Ocultar mi historial").length === 1);
  await click(buttons(m.host, "Ocultar mi historial")[0]);
  await click(buttons(m.host, "Sí, ocultar")[0]);
  check("'Sí, ocultar' hides once and closes the question", calls.hide === 1 && !m.host.textContent.includes("conserva el registro"));
  await m.unmount();
}
{
  const m = await mount(React.createElement(PastConversations, { items, onOpen() {}, onHide() {}, busy: true }));
  check("while hiding, the button cannot be pressed again", buttons(m.host, "Ocultar mi historial")[0].disabled === true);
  await click(buttons(m.host, "Ocultar mi historial")[0]);
  await m.unmount();
}

console.log("PastTranscript");
{
  let back = 0;
  const conversation = { conversation_id: "a", title: "x", skill: null, outcome: "handed_off", language: "es", last_message_at: "2026-10-04T10:00:00Z", messages: [
    { role: "customer", content: "<script>alert(1)</script> hola\nsegunda línea", skill: null, created_at: null },
    { role: "assistant", content: "Tu saldo es **100 USD**. <b>no</b>", skill: "balance_inquiry", created_at: null },
    { role: "operator", content: "Hola, soy Marta.", skill: null, created_at: null },
  ] };
  const m = await mount(React.createElement(PastTranscript, { conversation, onBack: () => back++ }));
  const html = m.host.innerHTML;
  check("shows all three messages in order", html.indexOf("hola") < html.indexOf("Tu saldo") && html.indexOf("Tu saldo") < html.indexOf("soy Marta"));
  check("the customer's text is text, not markup", !m.host.querySelector("script") && html.includes("&lt;script&gt;"));
  check("the assistant's Markdown is rendered", m.host.querySelector("strong")?.textContent === "100 USD");
  check("raw HTML in a reply is not rendered", !m.host.querySelector("b") && html.includes("&lt;b&gt;no"));
  check("a person of the team is labelled", html.includes("Agente de soporte"));
  check("the result is shown", html.includes("con una persona"));
  check("it says the conversation is over", m.host.textContent.includes("ya terminó"));
  await click(buttons(m.host, "Tus conversaciones")[0]);
  check("'back' is called once", back === 1);
  await m.unmount();
}

console.log("lib/memory (a fake fetch)");
{
  const seen = [];
  const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
  const run = (response) => { globalThis.fetch = async (url, init) => { seen.push({ url, method: init.method, headers: init.headers }); return response; }; };
  const auth = { Authorization: "Bearer t" };
  run(reply(200, [{ conversation_id: "a" }]));
  check("the list is read with the token", (await memory.getConversations(auth))[0].conversation_id === "a" && seen.at(-1).url.endsWith("/api/me/conversations") && seen.at(-1).headers.Authorization === "Bearer t" && seen.at(-1).method === "GET");
  run(reply(404, { detail: "chat_memory_disabled" }));
  check("404 on the list means the memory is off: null", (await memory.getConversations(auth)) === null);
  run(reply(404, { detail: "unknown_conversation" }));
  check("404 on one conversation: null", (await memory.getConversation(auth, "zz")) === null);
  run(reply(200, { conversation_id: "a", messages: [] }));
  await memory.getConversation(auth, "a/../b?x=1");
  check("an id is encoded into the path", seen.at(-1).url.endsWith("/api/me/conversations/a%2F..%2Fb%3Fx%3D1"));
  run(reply(200, { hidden: 3 }));
  check("hiding uses DELETE and returns the count", (await memory.hideConversations(auth)) === 3 && seen.at(-1).method === "DELETE" && seen.at(-1).url.endsWith("/api/me/conversations"));
  run(reply(200, { hidden: 1 }));
  await memory.hideConversations(auth, "hilo/1 abierto");
  check("the chat that is open is named and encoded", seen.at(-1).url.endsWith("/api/me/conversations?thread_id=hilo%2F1%20abierto"));
  run(reply(404, {}));
  check("hiding with the memory off is 0, not an error", (await memory.hideConversations(auth)) === 0);
  for (const [status, text] of [[401, "sesión terminó"], [500, "No pude leer"], [403, "No pude leer"]]) {
    run(reply(status, {}));
    let error; try { await memory.getConversations(auth); } catch (e) { error = e; }
    check(`HTTP ${status} is an error the customer can read`, error instanceof memory.MemoryError && error.message.includes(text) && error.status === status);
  }
}

console.log("HistoryPanel");
{
  const log = { close: 0, back: 0, open: [], hide: 0 };
  const props = (extra) => ({ items, opened: null, note: "", busy: false, onOpen: (id) => log.open.push(id), onBack: () => log.back++, onHide: () => log.hide++, onClose: () => log.close++, ...extra });
  let m = await mount(React.createElement(HistoryPanel, props({ items: [] })));
  check("with none yet it says so, and the panel is still there", m.host.textContent.includes("Todavía no tienes conversaciones anteriores") && m.host.querySelector("[role=dialog]") !== null);
  check("with none there is nothing to hide", buttons(m.host, "Ocultar mi historial").length === 0);
  await click(buttons(m.host, "Cerrar")[0]);
  check("it can be closed", log.close === 1);
  await m.unmount();
  m = await mount(React.createElement(HistoryPanel, props({})));
  check("it lists them all", m.host.querySelectorAll("li").length === 3);
  await click(buttons(m.host, "bloquea mi tarjeta")[0]);
  check("it opens one", log.open.join() === "a");
  await m.unmount();
  const opened = { conversation_id: "a", title: "x", skill: null, outcome: "done", language: "es", last_message_at: "2026-10-04T10:00:00Z", messages: [{ role: "customer", content: "hola", skill: null, created_at: null }] };
  m = await mount(React.createElement(HistoryPanel, props({ opened })));
  check("an open conversation replaces the list", m.host.querySelectorAll("li").length === 0 && m.host.textContent.includes("hola"));
  await click(buttons(m.host, "Tus conversaciones")[0]);
  check("it goes back to the list", log.back === 1);
  await m.unmount();
  m = await mount(React.createElement(HistoryPanel, props({ note: "No pude leer tu historial ahora." })));
  check("a problem is told", m.host.textContent.includes("No pude leer tu historial ahora."));
  await m.unmount();
}

console.log("useHistory (the wiring of the screen)");
{
  const calls = [];
  let handler = () => ({ ok: true, status: 200, json: async () => [] });
  globalThis.fetch = async (url, init) => { calls.push({ url, method: init.method, auth: init.headers?.Authorization }); return handler(url, init, calls.length); };
  const json = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
  const signIn = (customer, token = `token-${customer}`, minutes = 30) => saveSession({ customer, user: customer, token, expiresAt: Date.now() + minutes * 60_000 });
  const sees = (customer, title) => [{ conversation_id: `${customer}-1`, title, skill: null, outcome: "answered", language: "es", last_message_at: "2026-10-04T10:00:00Z", messages: 2 }];
  let api;
  function Probe({ customer, thread }) { api = useHistory(customer, thread); return null; }
  const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  const mountProbe = async (customer, thread = "t-actual") => {
    const host = dom.window.document.createElement("div"); dom.window.document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => root.render(React.createElement(Probe, { customer, thread })));
    await settle();
    return { root, rerender: (c, t = thread) => act(async () => root.render(React.createElement(Probe, { customer: c, thread: t }))), unmount: () => act(async () => root.unmount()) };
  };

  // signed in: it loads, once, with the customer's token
  signIn("C1"); handler = () => json(200, sees("C1", "lo de C1"));
  let probe = await mountProbe("C1");
  check("it loads the list when the customer is signed in, once", calls.length === 1 && calls[0].url.endsWith("/api/me/conversations") && calls[0].method === "GET");
  check("with the customer's own token", calls[0].auth === "Bearer token-C1");
  check("and shows it", api.history?.[0].title === "lo de C1" && api.opened === null && api.note === "");
  await probe.unmount();

  // nobody signed in
  calls.length = 0; probe = await mountProbe("");
  check("with nobody signed in it asks for nothing and shows nothing", calls.length === 0 && api.history === null);
  await probe.unmount();

  // an expired token
  calls.length = 0; signIn("C1", "viejo", -5); probe = await mountProbe("C1");
  check("an expired token is not used: no request", calls.length === 0 && api.history === null);
  await probe.unmount();

  // the memory is off
  calls.length = 0; signIn("C1"); handler = () => json(404, { detail: "chat_memory_disabled" });
  probe = await mountProbe("C1");
  check("with the memory off there is no history to show", calls.length === 1 && api.history === null);
  await probe.unmount();

  // another customer signs in on the same screen
  calls.length = 0; signIn("C1"); handler = () => json(200, sees("C1", "PRIVADO DE C1"));
  probe = await mountProbe("C1");
  check("first customer sees their own", api.history?.[0].title === "PRIVADO DE C1");
  let release; const late = new Promise((r) => (release = r));
  signIn("C2"); handler = () => late.then(() => json(200, sees("C2", "lo de C2")));
  await probe.rerender("C2");
  check("the next customer is not shown the previous one's list, not even for an instant", api.history === null);
  check("and asks with their own token", calls.at(-1).auth === "Bearer token-C2");
  await act(async () => { release(); await new Promise((r) => setTimeout(r, 0)); });
  check("they see their own when it arrives", api.history?.[0].title === "lo de C2" && !JSON.stringify(api).includes("PRIVADO"));
  check("and if the screen is for the first one while the session is still the second's, nothing is asked or shown", (await probe.rerender("C1"), api.history === null));
  const asked = calls.length;
  await act(async () => { await api.refresh(); await api.open("C2-1"); await api.hide(); });
  check("no action reaches the server with somebody else's token", calls.length === asked);
  await probe.unmount();

  // a late answer for a customer who already left is ignored
  calls.length = 0; signIn("C1"); let lateC1; handler = () => new Promise((r) => (lateC1 = () => r(json(200, sees("C1", "TARDÍO DE C1")))));
  probe = await mountProbe("C1");
  signIn("C2"); handler = () => json(200, sees("C2", "de C2"));
  await probe.rerender("C2"); await settle();
  await act(async () => { lateC1(); await new Promise((r) => setTimeout(r, 0)); });
  check("an old customer's late answer never reaches the next one", api.history?.[0].title === "de C2" && !JSON.stringify(api.history).includes("TARDÍO"));
  await probe.unmount();

  // opening one
  calls.length = 0; signIn("C1");
  const full = { conversation_id: "C1-1", title: "x", skill: null, outcome: "done", language: "es", last_message_at: null, messages: [{ role: "customer", content: "hola", skill: null, created_at: null }] };
  handler = (url) => (url.includes("C1-1") ? json(200, full) : json(200, sees("C1", "x")));
  probe = await mountProbe("C1");
  await act(async () => { await api.open("C1-1"); });
  check("opening one reads it with the token", calls.at(-1).url.endsWith("/api/me/conversations/C1-1") && api.opened?.messages[0].content === "hola");
  await act(async () => api.back());
  check("going back closes it", api.opened === null);
  handler = () => json(404, { detail: "unknown_conversation" });
  await act(async () => { await api.open("zz"); });
  check("one that is not there says so and opens nothing", api.opened === null && api.note.includes("ya no está disponible"));
  handler = () => json(500, {});
  await act(async () => { await api.open("zz"); });
  check("a server problem is told in words", api.opened === null && api.note.includes("No pude leer"));
  await probe.unmount();

  // what is open, or said, does not pass to the next customer
  calls.length = 0; signIn("C1");
  handler = (url) => (url.includes("C1-1") ? json(200, full) : json(200, sees("C1", "x")));
  probe = await mountProbe("C1");
  await act(async () => { await api.open("C1-1"); });
  const readingC1 = api.opened?.messages[0].content === "hola";
  handler = () => json(500, {});
  await act(async () => { await api.open("zz"); });
  check("(setup) the first customer is reading a conversation and has a message", readingC1 && api.note.includes("No pude leer"));
  signIn("C2"); handler = () => json(200, sees("C2", "de C2"));
  await probe.rerender("C2"); await settle();
  check("the next customer is not shown the previous one's open conversation", api.opened === null);
  check("nor the previous one's message", api.note === "");
  await probe.unmount();

  // hiding closes what was being read
  calls.length = 0; signIn("C1");
  handler = (url, init) => (init.method === "DELETE" ? json(200, { hidden: 1 }) : url.includes("C1-1") ? json(200, full) : json(200, sees("C1", "x")));
  probe = await mountProbe("C1");
  await act(async () => { await api.open("C1-1"); });
  await act(async () => { await api.hide(); });
  check("hiding closes the conversation that was being read", api.opened === null);
  await probe.unmount();

  // hiding
  calls.length = 0; signIn("C1");
  let hidden = false;
  handler = (url, init) => (init.method === "DELETE" ? ((hidden = true), json(200, { hidden: 1 })) : json(200, hidden ? sees("C1", "la abierta") : [...sees("C1", "vieja"), ...sees("C1b", "la abierta")]));
  probe = await mountProbe("C1", "hilo-abierto");
  await act(async () => { await api.hide(); });
  const del = calls.find((c) => c.method === "DELETE");
  check("hiding names the chat that is open, so it stays", del.url.endsWith("/api/me/conversations?thread_id=hilo-abierto") && del.auth === "Bearer token-C1");
  check("and reloads the list afterwards", calls.at(-1).method === "GET" && api.history.length === 1 && api.history[0].title === "la abierta");
  check("hiding is not busy once it is done", api.hiding === false);
  handler = () => json(500, {});
  await act(async () => { await api.hide(); });
  check("if hiding fails it says so and the list stays", api.note.includes("No pude") && api.history.length === 1 && api.hiding === false);
  await probe.unmount();

  // refresh
  calls.length = 0; signIn("C1"); handler = () => json(200, sees("C1", "uno"));
  probe = await mountProbe("C1");
  handler = () => json(200, [...sees("C1", "uno"), ...sees("C1b", "dos")]);
  await act(async () => { await api.refresh(); });
  check("refresh reads it again", api.history.length === 2);
  await probe.unmount();
}

console.log(`\n${total - failures}/${total} passed`);
process.exit(failures ? 1 : 0);
