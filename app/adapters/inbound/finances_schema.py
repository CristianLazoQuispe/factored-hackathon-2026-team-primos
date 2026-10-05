"""The shape of `GET /api/me/finances`: what the "Mis finanzas" screen reads.

The JSON is camelCase because the web is TypeScript; the Python side stays snake_case. This is the
contract: `web/lib/profile.ts` has the same shape (`OwnFinances`), and a test pins the field names.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MaxTicket(Camel):
    merchant: str
    amount: float


class Totals(Camel):
    spend: float
    prev_change_pct: float | None  # None: there was no spending in the period before
    transactions: int
    tx_per_week: float
    avg_ticket: float
    max_ticket: MaxTicket


class Category(Camel):
    name: str
    amount: float


class Merchant(Camel):
    name: str
    count: int
    unit: str
    amount: float


class Alert(Camel):
    type: Literal["duplicate_charge"]
    merchant: str
    amount: float
    currency: str
    date: str  # YYYY-MM-DD, the day of the first of the two charges
    delta_seconds: int


class Notes(Camel):
    spending: str
    monthly: str
    tip: str


class OtherCurrency(Camel):
    currency: str
    spend: float


class OwnFinances(Camel):
    client_id: str
    product: str
    country: str
    currency: str
    window_days: int
    totals: Totals
    categories: list[Category]  # the biggest five, then "Otros" last
    monthly: list[tuple[str, float]]  # [YYYY-MM, amount]
    top_merchants: list[Merchant]
    alerts: list[Alert]
    notes: Notes
    other_currencies: list[OtherCurrency]  # spending in currencies the screen does not show
