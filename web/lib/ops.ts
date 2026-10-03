// The figures of the management dashboard (/consola/gerencia).

export type OpsTopic = { name: string; count: number; resolvedPct: number; note: string };

export type OpsHandoff = {
  clientId: string;
  reason: string;
  at: string; // local date and time, "2026-10-03T17:16"
  status: "with_agent" | "resolved";
};

export type OpsSummary = {
  days: number;
  periodStart: string; // "2026-09-20"
  periodEnd: string;
  conversations: number;
  prevChangePct: number; // against the same number of days just before the period
  resolvedByQuipuPct: number;
  resolvedByQuipu: number;
  firstResponseMedianSec: number;
  prevFirstResponseMedianMin: number; // before Quipu, when a person answered first
  csat: number; // out of 5
  surveys: number;
  hoursSaved: number;
  minutesPerConversation: number; // the assumption behind hoursSaved
  daily: number[]; // one count per day, from periodStart to periodEnd
  topics: OpsTopic[];
  recentHandoffs: OpsHandoff[];
};

const PERIOD_END = "2026-10-03";
const MINUTES_PER_CONVERSATION = 6;

// 30 days ending on PERIOD_END. The last 14 are the ones of the design and add up to 2,011.
const DAILY = [
  81, 76, 124, 138, 129, 147, 151, 84, 79, 138, 151, 144, 163, 170, 92, 86,
  142, 156, 131, 168, 174, 95, 88, 151, 163, 170, 182, 190, 104, 97,
];

// For 7 and 14 days this agrees with DAILY; the mock has no data before the 30 days.
const PREV_CHANGE_PCT: Record<number, number> = { 7: 11, 14: 12, 30: 9 };

// The 14-day figures of the design; the other ranges scale them by their share of conversations.
const BASE_CONVERSATIONS = 2011;
const BASE_SURVEYS = 312;
const BASE_TOPICS: OpsTopic[] = [
  { name: "Saldos y movimientos", count: 742, resolvedPct: 96, note: "Casi todo lo resuelve Quipu con una consulta." },
  { name: "Cargos no reconocidos", count: 386, resolvedPct: 61, note: "Los que requieren bloqueo pasan a un agente." },
  { name: "Quejas", count: 371, resolvedPct: 64, note: "Quipu registra la queja y la clasifica." },
  { name: "Encuestas", count: 298, resolvedPct: 98, note: "Quipu responde dudas sobre encuestas anteriores." },
  { name: "Cargos duplicados", count: 214, resolvedPct: 52, note: "Quipu los detecta; el reverso lo aprueba un agente." },
];

const RECENT_HANDOFFS: OpsHandoff[] = [
  { clientId: "DEMO-MX-DUPLICATE", reason: "Cargo duplicado", at: "2026-10-03T17:16", status: "with_agent" },
  { clientId: "DEMO-MX-0421", reason: "Cargo no reconocido", at: "2026-10-03T16:48", status: "resolved" },
  { clientId: "DEMO-MX-0388", reason: "Queja por comisión", at: "2026-10-03T15:02", status: "resolved" },
];

// The backend will serve this at `GET /api/ops/summary?days=<days>`; today it is a mock.
export async function getOpsSummary(days: number): Promise<OpsSummary> {
  const daily = DAILY.slice(-days);
  const conversations = daily.reduce((sum, n) => sum + n, 0);
  const share = conversations / BASE_CONVERSATIONS;

  const topics = BASE_TOPICS.map((t) => ({ ...t, count: Math.round(t.count * share) }));
  // Rounding can leave the topics a few conversations off the total: the largest one absorbs it.
  topics[0].count += conversations - topics.reduce((sum, t) => sum + t.count, 0);

  const start = new Date(`${PERIOD_END}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - (daily.length - 1));

  const resolvedByQuipuPct = 78;
  const resolvedByQuipu = Math.round(conversations * resolvedByQuipuPct / 100);

  return {
    days,
    periodStart: start.toISOString().slice(0, 10),
    periodEnd: PERIOD_END,
    conversations,
    prevChangePct: PREV_CHANGE_PCT[days] ?? 0,
    resolvedByQuipuPct,
    resolvedByQuipu,
    firstResponseMedianSec: 3.8,
    prevFirstResponseMedianMin: 4,
    csat: 4.4,
    surveys: Math.round(BASE_SURVEYS * share),
    hoursSaved: Math.round(resolvedByQuipu * MINUTES_PER_CONVERSATION / 60),
    minutesPerConversation: MINUTES_PER_CONVERSATION,
    daily,
    topics,
    recentHandoffs: RECENT_HANDOFFS,
  };
}
