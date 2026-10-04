// A client's finances, as shown in "Mis finanzas" (customer) and in "Perfil 360" (staff console).

export type Category = { name: string; amount: number };

export type Merchant = {
  name: string;
  count: number;
  // What `count` counts, in the customer's words: "veces", "viajes", "cargas", "compras".
  unit: string;
  amount: number;
};

export type Alert = {
  type: "duplicate_charge";
  merchant: string;
  amount: number;
  currency: string;
  date: string; // YYYY-MM-DD, the day of the first of the two charges
  deltaSeconds: number;
};

export type Suggestion = { title: string; why: string };

export type HistoryItem = {
  title: string;
  meta: string;
  // The interaction that is still open: it gets the teal dot.
  current?: boolean;
};

export type ClientProfile = {
  clientId: string;
  product: string;
  country: string;
  currency: string;
  windowDays: number;
  totals: {
    spend: number;
    prevChangePct: number | null; // null: there was no spending in the period before
    transactions: number;
    txPerWeek: number;
    avgTicket: number;
    maxTicket: { merchant: string; amount: number };
  };
  // In the fixed order of the category colours (--q-cat-1..5, then --q-cat-other).
  categories: Category[];
  monthly: [month: string, amount: number][]; // month is YYYY-MM
  topMerchants: Merchant[];
  alerts: Alert[];
  // Spending in currencies the screen does not show; they are never added to the total.
  otherCurrencies: { currency: string; spend: number }[];
  // Sentences written for the customer.
  notes: { spending: string; monthly: string; tip: string };
  // Console only: it never reaches the customer.
  internal: {
    segments: string[];
    csat: number;
    csatDate: string;
    nextBestAction: Suggestion;
    secondaryAction: Suggestion;
    history: HistoryItem[];
    monthlyNote: string;
    // The staff's word for a merchant's count, where it differs from the customer's.
    merchantUnits: Record<string, string>;
  };
};

// What the customer's own screen gets: the type has no `internal`, so that screen cannot read it.
export type OwnFinances = Omit<ClientProfile, "internal">;

export const DEMO_CLIENT_ID = "DEMO-MX-DUPLICATE";

// Sample figures: `getProfile` (the staff console) still uses them until its endpoint exists.
const OWN: OwnFinances = {
  clientId: DEMO_CLIENT_ID,
  product: "Tarjeta de crédito",
  country: "México",
  currency: "MXN",
  windowDays: 90,
  totals: {
    spend: 13620,
    prevChangePct: 8,
    transactions: 33,
    txPerWeek: 2.6,
    avgTicket: 412,
    maxTicket: { merchant: "OXXO", amount: 921.67 },
  },
  categories: [
    { name: "Súper y conveniencia", amount: 4820 },
    { name: "Transporte", amount: 2690 },
    { name: "Combustible", amount: 2140 },
    { name: "Tiendas departamentales", amount: 1980 },
    { name: "Restaurantes", amount: 1350 },
    { name: "Otros", amount: 640 },
  ],
  monthly: [["2026-01", 3980], ["2026-02", 4210], ["2026-03", 4560], ["2026-04", 4120], ["2026-05", 4460], ["2026-06", 5040]],
  topMerchants: [
    { name: "OXXO", count: 9, unit: "veces", amount: 2980 },
    { name: "Uber Trip", count: 8, unit: "viajes", amount: 2410 },
    { name: "Pemex", count: 5, unit: "cargas", amount: 2140 },
    { name: "Liverpool", count: 3, unit: "compras", amount: 1620 },
  ],
  alerts: [{ type: "duplicate_charge", merchant: "Uber Trip", amount: 312.4, currency: "MXN", date: "2026-06-11", deltaSeconds: 4 }],
  otherCurrencies: [],
  notes: {
    spending: "Más de la mitad se fue en súper y transporte.",
    monthly: "Junio fue tu mes más alto. Incluye el cargo que estamos revisando.",
    tip: "Viajas en Uber casi cada semana. ¿Te aviso al instante si aparece un cobro repetido?",
  },
};

const INTERNAL: ClientProfile["internal"] = {
  segments: ["Viajero urbano", "Compras pequeñas y frecuentes"],
  csat: 8,
  csatDate: "may 2026",
  nextBestAction: {
    title: "Ofrecer el reverso del cargo duplicado de Uber Trip (312.40 MXN)",
    why: "Dos cargos idénticos con 4 s de diferencia. El cliente ya pidió ayuda y su satisfacción es buena: resolverlo rápido la protege.",
  },
  secondaryAction: {
    title: "Sugerir alertas de cargos duplicados",
    why: "Usa transporte por app casi cada semana.",
  },
  history: [
    { title: "Chat con Quipu · cargo duplicado", meta: "hoy · derivado a agente", current: true },
    { title: "Encuesta de satisfacción · 8/10", meta: "may 2026" },
    { title: "Queja · demora en reposición de tarjeta", meta: "mar 2026 · resuelta" },
  ],
  monthlyNote: "Junio incluye el cargo duplicado de Uber Trip (312.40 MXN).",
  merchantUnits: { OXXO: "visitas" },
};

// The backend will serve this at `GET /api/clients/:id/profile`. Today every ID gets the same mock.
export async function getProfile(clientId: string): Promise<ClientProfile> {
  return { ...OWN, clientId, internal: INTERNAL };
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export class FinancesError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Test identity service: the API signs a short-lived token for a demo customer.
export async function demoAuth(clientId: string): Promise<Record<string, string>> {
  const response = await fetch(`${API_URL}/api/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_id: clientId }),
  });
  if (!response.ok) throw new FinancesError(response.status, "No pudimos iniciar la sesión de demostración.");
  const data: { access_token: string } = await response.json();
  return { Authorization: `Bearer ${data.access_token}` };
}

// What the API says when it cannot serve the screen, in the customer's words.
const FINANCES_ERRORS: Record<number, string> = {
  401: "Tu sesión expiró. Vuelve a entrar.",
  404: "Todavía no hay movimientos en este periodo.",
  503: "No pudimos cargar tus finanzas ahora. Inténtalo de nuevo en un momento.",
};

// `GET /api/me/finances`: the customer's own screen, without the `internal` block. Who the customer
// is comes from the token, never from the URL. Without `auth` it signs in as `clientId` (demo).
export async function getOwnFinances(clientId: string, auth?: Record<string, string>): Promise<OwnFinances> {
  const headers = auth ?? (await demoAuth(clientId));
  const response = await fetch(`${API_URL}/api/me/finances`, { headers });
  if (!response.ok) {
    throw new FinancesError(response.status, FINANCES_ERRORS[response.status] ?? `Error ${response.status}`);
  }
  return response.json();
}

// Amounts are written the same way on every screen: 13,620 and 312.40.
export function formatAmount(amount: number, decimals = 0): string {
  return amount.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
