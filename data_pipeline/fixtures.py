"""Generate the team-made dispute demo scenarios into `data/sample/fixtures/`.

The organizer data has no near-duplicate charges and ~3 transactions per customer per quarter,
so the scenarios the agent must demonstrate are seeded here. Every row is synthetic, team-generated,
and flagged `is_synthetic_fixture = true` when loaded. Deterministic (fixed seed).

Scenarios (one demo customer each, with a dense 90-day history so localization is non-trivial):
    DEMO-MX-DUPLICATE     same Uber charge posted twice, 4 seconds apart -> bank error
    DEMO-CO-PENDING       online purchase still Pending -> likely to release on its own
    DEMO-MX-FX            USD purchase, amount differs from the price seen in MXN -> FX
    DEMO-AR-FRAUD         3 high-amount purchases in another city, flagged as fraud -> human
    DEMO-CO-AMBIGUOUS     4 charges on the same day -> clarifying question
    DEMO-MX-OWN-PURCHASE  charge made from the customer's own app session -> evidence conflict
    DEMO-AR-REVERSED      charge already reversed -> explain, nothing to dispute
    DEMO-BR-PORTUGUESE    Portuguese-speaking customer with a duplicate charge -> PT flow

    python -m data_pipeline.fixtures
"""

import random
from datetime import date, datetime, timedelta

import polars as pl

from app.config import get_settings

NOW = datetime(2026, 6, 18, 12, 0, 0)
SEED = 2026
MERCHANTS = {  # category: the organizer's taxonomy (transactions.transaction_category)
    "México": [
        ("OXXO", "Other"),
        ("Walmart", "Food"),
        ("Uber Trip", "Transport"),
        ("Netflix", "Entertainment"),
        ("Liverpool", "Other"),
        ("Pemex", "Transport"),
    ],
    "Colombia": [
        ("Éxito", "Food"),
        ("Rappi", "Food"),
        ("Uber Trip", "Transport"),
        ("Falabella", "Other"),
        ("Spotify", "Entertainment"),
        ("Terpel", "Transport"),
    ],
    "Argentina": [
        ("Carrefour", "Food"),
        ("Mercado Libre", "Other"),
        ("Cabify", "Transport"),
        ("YPF", "Transport"),
        ("PedidosYa", "Food"),
        ("Netflix", "Entertainment"),
    ],
    "Brazil": [
        ("Pão de Açúcar", "Food"),
        ("iFood", "Food"),
        ("99 Táxi", "Transport"),
        ("Americanas", "Other"),
        ("Spotify", "Entertainment"),
        ("Shell", "Transport"),
    ],
}
PROFILES = [  # id, first, last, city, country, accent, language, currency
    (
        "DEMO-MX-DUPLICATE",
        "Lucía",
        "Hernández Soto",
        "Ciudad de México",
        "México",
        "mexican",
        "es",
        "MXN",
    ),
    ("DEMO-CO-PENDING", "Andrés", "Gómez Rincón", "Bogotá", "Colombia", "colombian", "es", "COP"),
    ("DEMO-MX-FX", "Mariana", "López Ruiz", "Monterrey", "México", "mexican", "es", "MXN"),
    (
        "DEMO-AR-FRAUD",
        "Martina",
        "Fernández",
        "Buenos Aires",
        "Argentina",
        "argentine",
        "es",
        "ARS",
    ),
    (
        "DEMO-CO-AMBIGUOUS",
        "Camilo",
        "Restrepo Díaz",
        "Medellín",
        "Colombia",
        "colombian",
        "es",
        "COP",
    ),
    (
        "DEMO-MX-OWN-PURCHASE",
        "Diego",
        "Ramírez Cruz",
        "Guadalajara",
        "México",
        "mexican",
        "es",
        "MXN",
    ),
    ("DEMO-AR-REVERSED", "Sofía", "Gutiérrez", "Rosario", "Argentina", "argentine", "es", "ARS"),
    ("DEMO-BR-PORTUGUESE", "Ana", "Souza Lima", "São Paulo", "Brazil", "brazilian", "pt", "USD"),
]
TYPICAL_AMOUNT = {"MXN": 450, "COP": 95_000, "ARS": 28_000, "USD": 35}
OPENED = date(2021, 3, 15)  # every demo customer registered and opened the card that day


def tx(
    tx_id,
    customer,
    product,
    when,
    amount,
    currency,
    merchant,
    category,
    city,
    country,
    status="Approved",
    is_fraud=False,
    channel="POS",
    fraud_score=5.0,
):
    return {
        "transaction_id": tx_id,
        "customer_id": customer,
        "product_id": product,
        "transaction_date": when,
        "transaction_type": "Purchase",
        "transaction_category": category,
        "amount": round(amount, 2),
        "currency": currency,
        "amount_usd": None,
        "channel": channel,
        "merchant_name": merchant,
        "transaction_country": country,
        "transaction_city": city,
        "transaction_status": status,
        "response_code": "00",
        "is_fraud": is_fraud,
        "fraud_score": fraud_score,
    }


def build() -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    customers, products, transactions, sessions = [], [], [], []
    for cid, first, last, city, country, accent, lang, ccy in PROFILES:
        card = f"{cid}-CARD"
        customers.append(
            {
                "customer_id": cid,
                "document_type": "DEMO",
                "document_number": f"DOC-{cid}",
                "first_name": first,
                "last_name": last,
                "date_of_birth": datetime(1988, 5, 12).date(),
                "email": f"{cid.lower()}@demo.bank",
                "mobile_phone": None,
                "city": city,
                "country": country,
                "detected_accent": accent,
                "preferred_language": lang,
                "segment": "Plus",
                "customer_status": "Active",
                "registration_date": OPENED,
            }
        )
        products.append(
            {
                "product_id": card,
                "customer_id": cid,
                "product_type": "Tarjeta Crédito",
                "product_number_last4": f"{rng.randint(1000, 9999)}",
                "currency": ccy,
                "current_balance": TYPICAL_AMOUNT[ccy] * 18.0,
                "credit_limit": TYPICAL_AMOUNT[ccy] * 60,
                "product_status": "Active",
                "interest_rate": 36.0,
                "opening_date": OPENED,
                "expiration_date": date(2029, 3, 31),
                "days_past_due": 0,
            }
        )
        # Dense background history: ~30 approved purchases over the last 90 days.
        for i in range(30):
            merchant, category = rng.choice(MERCHANTS[country])
            when = NOW - timedelta(days=rng.uniform(2, 90), minutes=rng.randint(0, 600))
            amount = TYPICAL_AMOUNT[ccy] * rng.uniform(0.2, 2.5)
            transactions.append(
                tx(
                    f"{cid}-TX{i:03d}",
                    cid,
                    card,
                    when,
                    amount,
                    ccy,
                    merchant,
                    category,
                    city,
                    country,
                )
            )
        sessions.append(
            {
                "session_id": f"{cid}-SES-BASE",
                "customer_id": cid,
                "started_at": NOW - timedelta(days=10),
                "ended_at": NOW - timedelta(days=10, minutes=-6),
                "channel": "Android App",
                "platform": "Android",
                "ip_country": country,
                "ip_city": city,
                "had_login": True,
                "events": 12,
            }
        )

    def add(customer, suffix, when, amount, merchant, category, **kw):
        profile = next(p for p in PROFILES if p[0] == customer)
        city, country, ccy = (
            kw.pop("city", profile[3]),
            kw.pop("country", profile[4]),
            kw.pop("currency", profile[7]),
        )
        transactions.append(
            tx(
                f"{customer}-{suffix}",
                customer,
                f"{customer}-CARD",
                when,
                amount,
                ccy,
                merchant,
                category,
                city,
                country,
                **kw,
            )
        )

    t = NOW - timedelta(days=7, hours=3)
    add("DEMO-MX-DUPLICATE", "DUP-A", t, 312.40, "Uber Trip", "Transport")
    add("DEMO-MX-DUPLICATE", "DUP-B", t + timedelta(seconds=4), 312.40, "Uber Trip", "Transport")
    add(
        "DEMO-CO-PENDING",
        "PENDING",
        NOW - timedelta(days=1),
        148_900,
        "Amazon Mktp",
        "Other",
        status="Pending",
        channel="Web",
        city="Seattle",
        country="USA",
    )
    add(
        "DEMO-MX-FX",
        "FX",
        NOW - timedelta(days=4),
        1_043.00,
        "Best Buy US",
        "Other",
        channel="Web",
        city="Austin",
        country="USA",
    )
    for k, hours in enumerate((1, 1.5, 2)):
        add(
            "DEMO-AR-FRAUD",
            f"FRAUD-{k}",
            NOW - timedelta(hours=hours),
            161_700,
            "ElectroMax Córdoba",
            "Other",
            city="Córdoba",
            is_fraud=True,
            fraud_score=91.0,
        )
    day = (NOW - timedelta(days=1)).replace(hour=9)
    for k, (merchant, amount) in enumerate(
        [("Rappi", 42_000), ("Éxito", 131_500), ("Uber Trip", 18_300), ("Amazon Mktp", 149_900)]
    ):
        add(
            "DEMO-CO-AMBIGUOUS",
            f"SAMEDAY-{k}",
            day + timedelta(hours=3 * k),
            amount,
            merchant,
            "Other",
            channel="Web" if merchant == "Amazon Mktp" else "POS",
        )
    own = NOW - timedelta(days=2, hours=5)
    add("DEMO-MX-OWN-PURCHASE", "OWN", own, 2_899.00, "Liverpool", "Other", channel="App")
    sessions.append(
        {
            "session_id": "DEMO-MX-OWN-PURCHASE-SES-BUY",
            "customer_id": "DEMO-MX-OWN-PURCHASE",
            "started_at": own - timedelta(minutes=3),
            "ended_at": own + timedelta(minutes=2),
            "channel": "iOS App",
            "platform": "iOS",
            "ip_country": "México",
            "ip_city": "Guadalajara",
            "had_login": True,
            "events": 9,
        }
    )
    add(
        "DEMO-AR-REVERSED",
        "REVERSED",
        NOW - timedelta(days=5),
        54_000,
        "Mercado Libre",
        "Other",
        status="Reversed",
        channel="Web",
    )
    t = NOW - timedelta(days=3, hours=2)
    add("DEMO-BR-PORTUGUESE", "DUP-A", t, 27.90, "iFood", "Food", channel="App")
    add(
        "DEMO-BR-PORTUGUESE",
        "DUP-B",
        t + timedelta(seconds=6),
        27.90,
        "iFood",
        "Food",
        channel="App",
    )
    return {
        "customers": customers,
        "products": products,
        "transactions": transactions,
        "app_sessions": sessions,
    }


def main() -> None:
    out = get_settings().data_dir / "sample" / "fixtures"
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in build().items():
        pl.DataFrame(rows, infer_schema_length=None).write_parquet(out / f"{name}.parquet")
        print(f"{name:14s} {len(rows):4d} rows -> {out / name}.parquet")


if __name__ == "__main__":
    main()
