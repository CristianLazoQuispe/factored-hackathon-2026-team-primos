"""Reviewed SQL of the accounts and lookup tools against the real demo data. The pinned answers
are the same ones `tests/dwh_questions.py` expects from the SQL path. Skipped unless Postgres is
up (`make demo-data`)."""

from datetime import date

import pytest

from app.adapters.outbound import postgres
from app.adapters.outbound.postgres.accounts import fetch_debts, fetch_profile
from app.adapters.outbound.postgres.spending import PostgresSpending
from app.application.spending import spending_summary
from app.domain.accounts import DEBT_TYPES
from app.domain.spending import complaints_summary

pytestmark = pytest.mark.anyio
ALL_TIME = 365
NO_FILTER = dict.fromkeys(
    (
        "product_type",
        "last4",
        "transaction_type",
        "status",
        "merchant",
        "category",
        "min_amount",
        "max_amount",
    )
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def need_demo_data():
    try:
        postgres.ping()
    except Exception:
        pytest.skip("Postgres with the demo data is not running")


async def movements(customer_id: str, limit: int, largest: bool = False, **filters) -> list[dict]:
    asked = NO_FILTER | {"days": ALL_TIME, "largest": largest} | filters
    return await PostgresSpending().movements(customer_id, limit, **asked)


async def test_spending_summary_matches_the_reference_answers():
    summary = await spending_summary(PostgresSpending(), "DEMO-MX-DUPLICATE", ALL_TIME)
    (mxn,) = summary["currencies"]
    assert summary["unavailable"] == [] and mxn["currency"] == "MXN"
    assert mxn["spend"] == 20719.1 and mxn["previous_spend"] == 0
    top = [(m["merchant_name"], m["amount"]) for m in mxn["top_merchants"][:3]]
    assert top == [("Netflix", 5273.69), ("OXXO", 3468.64), ("Pemex", 3427.04)]
    by_category = sum(c["amount"] for c in mxn["by_category"])
    assert by_category == pytest.approx(mxn["spend"]) == sum(m["amount"] for m in mxn["monthly"])
    assert {c["category"] for c in mxn["by_category"]} <= {
        "Food",
        "Transport",
        "Services",
        "Entertainment",
        "Health",
        "Other",
    }
    assert mxn["foreign"] == {"transactions": 0, "amount": 0.0}


async def test_the_previous_period_is_the_same_number_of_days_before():
    (mxn,) = (await spending_summary(PostgresSpending(), "DEMO-MX-DUPLICATE", 30))["currencies"]
    whole = (await spending_summary(PostgresSpending(), "DEMO-MX-DUPLICATE", 60))["currencies"][0]
    assert mxn["spend"] + mxn["previous_spend"] == pytest.approx(whole["spend"])
    assert "change_pct" in mxn


async def test_foreign_spending_is_what_was_bought_outside_the_customers_country():
    summary = await spending_summary(PostgresSpending(), "DEMO-MX-FX", ALL_TIME)
    assert summary["currencies"][0]["foreign"] == {"transactions": 1, "amount": 1043.0}


async def test_movements_filter_sort_and_only_show_the_customers_own():
    uber = await movements("DEMO-MX-DUPLICATE", 5, merchant="uber")
    assert len(uber) >= 2 and uber[0]["amount"] == 312.4 and uber[0]["currency"] == "MXN"
    assert uber[0]["product_type"] == "Tarjeta Crédito" and "transaction_id" not in uber[0]
    biggest = await movements("DEMO-BR-PORTUGUESE", 3, largest=True, status="Approved")
    assert [(m["merchant_name"], m["amount"]) for m in biggest] == [
        ("99 Táxi", 85.97),
        ("Pão de Açúcar", 84.75),
        ("iFood", 82.94),
    ]
    assert await movements("DEMO-MX-FX", 5, merchant="uber", last4="0000") == []
    assert await movements("NOBODY", 5) == []


async def test_complaints_and_exchange_rate_match_the_reference_answers():
    summary = complaints_summary(await PostgresSpending().complaints("CLI-J0N40EZVP1P6"))
    assert summary["count"] == 2 and summary["open"] == 1
    assert summary["by_status"] == [
        {"status": "Open", "count": 1},
        {"status": "Resolved", "count": 1},
    ]
    store = PostgresSpending()
    latest = await store.exchange_rate("USD", "MXN", None)
    assert latest["exchange_rate"] == 17.021219
    earlier = await store.exchange_rate("USD", "MXN", date(2026, 5, 1))
    assert earlier["date"] == date(2026, 5, 1)
    assert await store.exchange_rate("USD", "MXN", date(2020, 1, 1)) is None


async def test_every_credit_card_and_loan_has_a_billing_row_that_agrees_with_its_days_past_due():
    rows = await postgres.query(
        """SELECT count(*) AS debts, count(b.product_id) AS billed,
                  count(*) FILTER (WHERE p.days_past_due > 0
                                   AND b.as_of - b.due_date <> p.days_past_due) AS disagree,
                  count(*) FILTER (WHERE b.minimum_payment > p.current_balance + 0.01) AS over
           FROM core.products p LEFT JOIN core.billing b USING (product_id)
           WHERE p.product_type = ANY(%(types)s)""",
        {"types": list(DEBT_TYPES)},
    )
    assert rows[0]["debts"] == rows[0]["billed"] > 0
    assert rows[0]["disagree"] == 0 and rows[0]["over"] == 0


async def test_debts_and_profile_of_the_demo_customer():
    (card,) = await fetch_debts("DEMO-MX-DUPLICATE", list(DEBT_TYPES))
    assert card["debt"] == 8100.0 and card["due_date"] == date(2026, 7, 4)
    assert card["minimum_payment"] == 500.0 and card["days_past_due"] == 0
    assert await fetch_debts("DEMO-MX-DUPLICATE", ["Préstamo Personal"]) == []
    profile = await fetch_profile("DEMO-MX-DUPLICATE")
    assert profile["customer_since"] == date(2021, 3, 15) and profile["as_of"] == date(2026, 6, 17)
    assert await fetch_profile("NOBODY") is None
