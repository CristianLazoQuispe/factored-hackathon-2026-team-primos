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
const memory = await import("@/lib/memory");

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
  const calls = { open: [], forget: 0 };
  const m = await mount(React.createElement(PastConversations, { items, onOpen: (id) => calls.open.push(id), onForget: () => calls.forget++, busy: false }));
  const html = m.host.innerHTML;
  check("lists every conversation", m.host.querySelectorAll("li").length === 3);
  check("shows the title, the count and singular/plural", html.includes("bloquea mi tarjeta") && html.includes("4 mensajes") && html.includes("1 mensaje<") );
  check("a missing title says so", html.includes("Sin título"));
  check("shows the result in words", html.includes("hecha") && html.includes("con una persona"));
  check("an unknown result shows no chip", !html.includes("hacked"));
  check("a title with HTML is text, never markup", !m.host.querySelector("img") && html.includes("&lt;img src=x"));
  await click(buttons(m.host, "bloquea mi tarjeta")[0]);
  check("opening a conversation passes its id", calls.open.join() === "a");
  check("nothing is deleted by opening", calls.forget === 0);
  await m.unmount();
}
{
  const m = await mount(React.createElement(PastConversations, { items: [], onOpen() {}, onForget() {}, busy: false }));
  check("with nothing to show it renders nothing at all", m.host.innerHTML === "");
  await m.unmount();
}
console.log("Forgetting");
{
  const calls = { forget: 0 };
  const m = await mount(React.createElement(PastConversations, { items, onOpen() {}, onForget: () => calls.forget++, busy: false }));
  check("the button is offered, the question is not yet", buttons(m.host, "Borrar mi historial").length === 1 && !m.host.textContent.includes("No se puede deshacer"));
  await click(buttons(m.host, "Borrar mi historial")[0]);
  check("it asks first and says it cannot be undone", m.host.textContent.includes("No se puede deshacer") && calls.forget === 0);
  check("the alert is announced", m.host.querySelector("[role=alert]") !== null);
  await click(buttons(m.host, "No")[0]);
  check("'No' goes back and deletes nothing", calls.forget === 0 && buttons(m.host, "Borrar mi historial").length === 1);
  await click(buttons(m.host, "Borrar mi historial")[0]);
  await click(buttons(m.host, "Sí, borrar")[0]);
  check("'Sí, borrar' deletes once and closes the question", calls.forget === 1 && !m.host.textContent.includes("No se puede deshacer"));
  await m.unmount();
}
{
  const m = await mount(React.createElement(PastConversations, { items, onOpen() {}, onForget() {}, busy: true }));
  check("while deleting, the button cannot be pressed again", buttons(m.host, "Borrar mi historial")[0].disabled === true);
  await click(buttons(m.host, "Borrar mi historial")[0]);
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
  run(reply(200, { deleted: 3 }));
  check("forgetting uses DELETE and returns the count", (await memory.forgetConversations(auth)) === 3 && seen.at(-1).method === "DELETE");
  run(reply(404, {}));
  check("forgetting with the memory off is 0, not an error", (await memory.forgetConversations(auth)) === 0);
  for (const [status, text] of [[401, "sesión terminó"], [500, "No pude leer"], [403, "No pude leer"]]) {
    run(reply(status, {}));
    let error; try { await memory.getConversations(auth); } catch (e) { error = e; }
    check(`HTTP ${status} is an error the customer can read`, error instanceof memory.MemoryError && error.message.includes(text) && error.status === status);
  }
}

console.log(`\n${total - failures}/${total} passed`);
process.exit(failures ? 1 : 0);
