// What the agent proposes and the customer confirms. Every sentence on a card is written by the API,
// in Spanish or Portuguese, from what it stored and verified: this file only carries it. The model
// never sees the confirmation: it is a button on the screen and a route of its own.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export type ActionItem = {
  action_id: string;
  action: string;
  status: string;
  tone: "ok" | "warn" | "error" | "info";
  text: string;
};

export type ActionBatch = {
  batch_id: string | null;
  language: "es" | "pt";
  state: string;
  needs_confirmation: boolean;
  strong: boolean;
  title: string;
  confirm_label: string;
  cancel_label: string;
  strong_note: string | null;
  expires_note: string | null;
  expires_at: string | null;
  inbox_label: string | null; // set when an email is part of it and the demo offers inboxes
  inbox_choices: string[];
  items: ActionItem[];
  escalate: { action: string; reason: string | null }[];
};

export type OutboxMessage = {
  message_id: number;
  channel: string;
  destination: string; // the customer's registered address, masked
  delivered_to: string | null; // the demo inbox it really went to, masked
  subject: string;
  body: string;
  language: string;
  mode: "simulated" | "smtp";
  status: "queued" | "accepted" | "failed";
  created_at: string;
};

export class ActionsError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

const FAILURES: Record<number, string> = {
  401: "Tu sesión terminó. Entra de nuevo.",
  404: "Esa propuesta ya no está disponible.",
};

async function call(path: string, auth: Record<string, string>, body?: object): Promise<Response> {
  const response = await fetch(`${API_URL}${path}`, {
    method: body ? "POST" : "GET",
    headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...auth },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok && response.status !== 404) {
    throw new ActionsError(FAILURES[response.status] ?? "No pude completar esto ahora. Inténtalo de nuevo.", response.status);
  }
  return response;
}

async function decide(path: string, auth: Record<string, string>, body: object): Promise<ActionBatch> {
  const response = await call(path, auth, body);
  if (!response.ok) throw new ActionsError(FAILURES[response.status] ?? FAILURES[404], response.status);
  return response.json();
}

// Runs what the customer confirmed. The API runs it once, however often this is called.
export function confirmActions(
  auth: Record<string, string>,
  batchId: string,
  threadId: string,
  inbox: string | null,
): Promise<ActionBatch> {
  return decide(`/api/actions/${encodeURIComponent(batchId)}/confirm`, auth, {
    thread_id: threadId,
    ...(inbox ? { inbox } : {}),
  });
}

export function cancelActions(auth: Record<string, string>, batchId: string, threadId: string): Promise<ActionBatch> {
  return decide(`/api/actions/${encodeURIComponent(batchId)}/cancel`, auth, { thread_id: threadId });
}

// What the system sent this customer, newest first; `null` while the API has actions off (404).
export async function getOutbox(auth: Record<string, string>): Promise<OutboxMessage[] | null> {
  const response = await call("/api/me/outbox?limit=20", auth);
  return response.status === 404 ? null : response.json();
}
