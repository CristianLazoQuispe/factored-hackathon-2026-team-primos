// The customer's earlier conversations. The API keeps them per customer and only ever shows the
// ones the token proves; this file only carries them. A card number typed in the chat is already
// stored by its last four digits. `null` means this deployment keeps no history (the API answers
// 404), so there is nothing to show.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export type Outcome = "answered" | "proposed" | "done" | "refused" | "cancelled" | "handed_off";

export type PastConversation = {
  conversation_id: string;
  title: string | null; // the first thing the customer asked
  skill: string | null;
  outcome: Outcome | null;
  language: string | null;
  last_message_at: string | null;
  messages: number;
};

// `operator` is a person of the team who answered from the console; `assistant` is Quipu.
export type PastMessage = {
  role: "customer" | "assistant" | "operator";
  content: string;
  skill: string | null;
  created_at: string | null;
};

export type OpenedConversation = Omit<PastConversation, "messages"> & { messages: PastMessage[] };

export class MemoryError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

const FAILURES: Record<number, string> = {
  401: "Tu sesión terminó. Entra de nuevo.",
};

async function call(path: string, auth: Record<string, string>, method: "GET" | "DELETE" = "GET"): Promise<Response> {
  const response = await fetch(`${API_URL}${path}`, { method, headers: auth });
  if (!response.ok && response.status !== 404) {
    throw new MemoryError(FAILURES[response.status] ?? "No pude leer tu historial ahora. Inténtalo de nuevo.", response.status);
  }
  return response;
}

// The most recent first; `null` while the API has the memory off (404).
export async function getConversations(auth: Record<string, string>): Promise<PastConversation[] | null> {
  const response = await call("/api/me/conversations", auth);
  return response.status === 404 ? null : response.json();
}

// `null`: not found, or not the customer's. The API answers the same for both.
export async function getConversation(auth: Record<string, string>, id: string): Promise<OpenedConversation | null> {
  const response = await call(`/api/me/conversations/${encodeURIComponent(id)}`, auth);
  return response.status === 404 ? null : response.json();
}

// Forgets everything kept of this customer's conversations. Returns how many went.
export async function forgetConversations(auth: Record<string, string>): Promise<number> {
  const response = await call("/api/me/conversations", auth, "DELETE");
  if (response.status === 404) return 0;
  const done: { deleted: number } = await response.json();
  return done.deleted;
}
