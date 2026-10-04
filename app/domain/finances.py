"""The customer's own finances, shaped for the "Mis finanzas" screen. Pure functions, no I/O.

The figures come from the reviewed spending lookups (`app.domain.spending`), one block per
currency. The screen shows one currency, the one the customer buys in most often; the others are
listed apart, so no money disappears and no two currencies are ever added. The sentences are
templates, not model output: they cannot invent a figure, and they read the same every time.
"""

from typing import Any

CATEGORY_LIMIT = 5  # the screen has five category colours; whatever is left is "Otros"
MERCHANT_LIMIT = 4
ALERT_LIMIT = 5
FREQUENT_AFTER = 3  # purchases at one merchant before the tip talks about how often

OTHER = "Otros"
# The silver layer writes English categories; an older load wrote Spanish ones. A name that is not
# listed is shown as it is.
CATEGORY_NAMES = {
    "food": "Comida",
    "transport": "Transporte",
    "services": "Servicios",
    "entertainment": "Entretenimiento",
    "health": "Salud",
    "other": OTHER,
    "uncategorized": OTHER,
}
PRODUCT_NAMES = {
    "Tarjeta Crédito": "Tarjeta de crédito",
    "Tarjeta Débito": "Tarjeta de débito",
    "Cuenta Corriente": "Cuenta corriente",
    "Cuenta Ahorro": "Cuenta de ahorro",
}
MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
UNKNOWN_MERCHANT = "Comercio sin nombre"


class NoSpending(Exception):
    """The customer made no purchase in the period: there is nothing to show."""


class UnknownCustomer(Exception):
    """No such customer in the warehouse."""


def main_block(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """The currency the customer buys in most often. It counts purchases, not money: amounts of
    different currencies are never compared, so 1,000 USD is not "less" than 5,000 MXN. Ties go to
    the currency that comes first alphabetically, so the choice does not change between calls."""
    if not blocks:
        raise NoSpending
    return min(blocks, key=lambda block: (-block["transactions"], block["currency"]))


def category_name(raw: str) -> str:
    return CATEGORY_NAMES.get(raw.strip().lower(), raw)


def categories(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The biggest `CATEGORY_LIMIT` categories, then "Otros" last: what the donut's colours expect.
    "Other", "Uncategorized" and everything past the limit add up into "Otros"."""
    by_name: dict[str, float] = {}
    for row in rows:
        name = category_name(row["category"])
        by_name[name] = by_name.get(name, 0.0) + row["amount"]
    other = by_name.pop(OTHER, 0.0)
    named = sorted(by_name.items(), key=lambda item: (-item[1], item[0]))
    other += sum(amount for _, amount in named[CATEGORY_LIMIT:])
    shown = [{"name": name, "amount": round(amount, 2)} for name, amount in named[:CATEGORY_LIMIT]]
    return shown + ([{"name": OTHER, "amount": round(other, 2)}] if other > 0 else [])


def top_merchants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": row["merchant_name"],
            "count": row["transactions"],
            "unit": "compra" if row["transactions"] == 1 else "compras",
            "amount": row["amount"],
        }
        for row in rows[:MERCHANT_LIMIT]
    ]


def alerts(rows: list[dict[str, Any]], currency: str) -> list[dict[str, Any]]:
    """Duplicate charges in the screen's currency, newest first."""
    mine = [row for row in rows if row["currency"] == currency]
    mine.sort(key=lambda row: row["at"], reverse=True)
    return [
        {
            "type": "duplicate_charge",
            "merchant": row["merchant_name"],
            "amount": row["amount"],
            "currency": row["currency"],
            "date": row["at"].date().isoformat(),
            "delta_seconds": row["seconds_apart"],
        }
        for row in mine[:ALERT_LIMIT]
    ]


def product_name(product_type: str | None) -> str:
    if not product_type:
        return "Tus productos"
    return PRODUCT_NAMES.get(product_type, product_type)


def _percent(part: float, whole: float) -> int:
    return round(part / whole * 100)


def spending_note(cats: list[dict[str, Any]], spend: float) -> str:
    named = [c for c in cats if c["name"] != OTHER]
    if not named or spend <= 0:
        return ""
    if len(named) >= 2 and named[0]["amount"] + named[1]["amount"] > spend / 2:
        first, second = named[0]["name"].lower(), named[1]["name"].lower()
        return f"Más de la mitad se fue en {first} y {second}."
    top = named[0]
    share = _percent(top["amount"], spend)
    return f"Lo que más pesó fue {top['name'].lower()}, con {share}% del total."


def monthly_note(monthly: list[tuple[str, float]], alert_list: list[dict[str, Any]]) -> str:
    if len(monthly) < 2:
        return ""
    peak = max(monthly, key=lambda item: item[1])[0]
    month_name = MONTHS[int(peak[5:7]) - 1].capitalize()
    note = f"{month_name} fue tu mes más alto."
    if any(alert["date"][:7] == peak for alert in alert_list):
        note += " Incluye el cargo que estamos revisando."
    return note


def tip(alert_list: list[dict[str, Any]], merchants: list[dict[str, Any]], days: int) -> str:
    ask = "¿Te aviso al instante si aparece un cobro repetido?"
    if alert_list:
        merchant = alert_list[0]["merchant"]
        return f"Ya vimos un cobro repetido en {merchant}. ¿Te aviso al instante si vuelve a pasar?"
    frequent = [m for m in merchants if m["count"] >= FREQUENT_AFTER]
    if frequent:
        top = max(frequent, key=lambda m: (m["count"], m["amount"]))
        return (
            f"Compras en {top['name']} cada {round(days / top['count'])} días, más o menos. {ask}"
        )
    return "¿Quieres que te avise al instante si aparece un cobro repetido?"


def own_finances(
    customer_id: str,
    days: int,
    blocks: list[dict[str, Any]],
    facts: dict[str, Any],
    duplicates: list[dict[str, Any]],
    largest: dict[str, Any] | None,
) -> dict[str, Any]:
    """What the customer's own screen shows. Nothing internal to the bank is in here."""
    main = main_block(blocks)
    currency = main["currency"]
    cats = categories(main.get("by_category", []))
    monthly = [(row["month"], row["amount"]) for row in main.get("monthly", [])]
    merchants = top_merchants(main.get("top_merchants", []))
    alert_list = alerts(duplicates, currency)
    biggest = largest or {}
    return {
        "client_id": customer_id,
        "product": product_name(facts.get("product_type")),
        "country": facts["country"],
        "currency": currency,
        "window_days": days,
        "totals": {
            "spend": main["spend"],
            "prev_change_pct": main.get("change_pct"),  # None: there was no spending before
            "transactions": main["transactions"],
            "tx_per_week": main["tx_per_week"],
            "avg_ticket": main["avg_ticket"],
            "max_ticket": {
                "merchant": biggest.get("merchant_name") or UNKNOWN_MERCHANT,
                "amount": biggest.get("amount", main["max_ticket"]),
            },
        },
        "categories": cats,
        "monthly": monthly,
        "top_merchants": merchants,
        "alerts": alert_list,
        "notes": {
            "spending": spending_note(cats, main["spend"]),
            "monthly": monthly_note(monthly, alert_list),
            "tip": tip(alert_list, merchants, days),
        },
        "other_currencies": [
            {"currency": block["currency"], "spend": block["spend"]}
            for block in blocks
            if block is not main
        ],
    }
