"""The customer's own finances: the figures behind "Mis finanzas".

Three layers. The pure shaping (what is shown, what is folded, what is left out), the use case
(a failing lookup never becomes a zero) and the route (whose data, which status). The SQL runs
against the demo data and is skipped unless Postgres is up (`make demo-data`).
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound import http
from app.adapters.inbound.auth import issue_token
from app.adapters.inbound.finances_schema import OwnFinances
from app.adapters.outbound import postgres
from app.adapters.outbound.postgres.finances import PostgresFinances
from app.adapters.outbound.postgres.spending import PostgresSpending
from app.application.finances import FinancesUnavailable, own_finances
from app.config import get_settings
from app.domain import finances as domain
from app.domain.evidence import DUPLICATE_WINDOW_SECONDS
from app.domain.finances import NoSpending, UnknownCustomer

DEMO = "DEMO-MX-DUPLICATE"


def block(currency="MXN", **changes):
    base = {
        "currency": currency,
        "spend": 1000.0,
        "previous_spend": 0.0,
        "transactions": 10,
        "avg_ticket": 100.0,
        "max_ticket": 300.0,
        "tx_per_week": 0.8,
        "by_category": [
            {"category": "Transport", "amount": 600.0, "transactions": 5},
            {"category": "Food", "amount": 400.0, "transactions": 5},
        ],
        "top_merchants": [
            {"merchant_name": "Uber Trip", "amount": 600.0, "transactions": 5},
            {"merchant_name": "OXXO", "amount": 400.0, "transactions": 5},
        ],
        "monthly": [
            {"month": "2026-04", "amount": 300.0, "transactions": 3},
            {"month": "2026-05", "amount": 700.0, "transactions": 7},
        ],
    }
    return base | changes


def duplicate(merchant="Uber Trip", currency="MXN", at="2026-05-11T09:00:00", seconds=4):
    return {
        "merchant_name": merchant,
        "amount": 312.4,
        "currency": currency,
        "at": datetime.fromisoformat(at),
        "seconds_apart": seconds,
    }


FACTS = {"country": "México", "product_type": "Tarjeta Crédito"}


def shaped(**changes):
    args = {
        "customer_id": "CLI-A",
        "days": 90,
        "blocks": [block()],
        "facts": FACTS,
        "duplicates": [],
        "largest": {"merchant_name": "Walmart", "amount": 300.0},
    }
    return domain.own_finances(**(args | changes))


# ---- categories: five colours, "Otros" last, nothing lost and nothing added ----


def test_categories_are_named_in_spanish_and_other_ones_add_up_into_otros_at_the_end():
    rows = [
        {"category": "Food", "amount": 100.0},
        {"category": "Other", "amount": 50.0},
        {"category": "Transport", "amount": 300.0},
        {"category": "Uncategorized", "amount": 25.0},
        {"category": "Health", "amount": 10.0},
    ]
    assert domain.categories(rows) == [
        {"name": "Transporte", "amount": 300.0},
        {"name": "Comida", "amount": 100.0},
        {"name": "Salud", "amount": 10.0},
        {"name": "Otros", "amount": 75.0},  # Other + Uncategorized, and last even though bigger
    ]


def test_categories_past_the_fifth_are_folded_into_otros_without_losing_money():
    rows = [
        {"category": f"Cat{i}", "amount": float(a)}
        for i, a in enumerate([70, 60, 50, 40, 30, 20, 10])
    ]
    shown = domain.categories(rows)
    assert [c["name"] for c in shown] == ["Cat0", "Cat1", "Cat2", "Cat3", "Cat4", "Otros"]
    assert shown[-1]["amount"] == 30.0  # 20 + 10
    assert sum(c["amount"] for c in shown) == sum(r["amount"] for r in rows)


def test_otros_is_not_invented_when_there_is_nothing_to_fold():
    shown = domain.categories([{"category": "Food", "amount": 5.0}])
    assert [c["name"] for c in shown] == ["Comida"]
    assert domain.categories([]) == []


def test_a_category_that_is_not_listed_is_shown_as_it_is():
    assert (
        domain.categories([{"category": "Supermercados", "amount": 5.0}])[0]["name"]
        == "Supermercados"
    )


# ---- the currency the screen shows ----


def test_the_main_currency_is_the_one_with_most_purchases_not_the_biggest_number():
    usd, mxn = (
        block("USD", spend=1000.0, transactions=4),
        block("MXN", spend=5000.0, transactions=9),
    )
    assert domain.main_block([usd, mxn])["currency"] == "MXN"
    assert domain.main_block([block("COP"), block("ARS")])["currency"] == "ARS"  # tie: alphabetical


def test_money_in_another_currency_is_listed_apart_and_never_added():
    result = shaped(blocks=[block("MXN", transactions=9), block("USD", spend=77.0, transactions=2)])
    assert result["currency"] == "MXN" and result["totals"]["spend"] == 1000.0
    assert result["other_currencies"] == [{"currency": "USD", "spend": 77.0}]


def test_no_purchases_means_nothing_to_show():
    with pytest.raises(NoSpending):
        domain.main_block([])


# ---- the figures ----


def test_the_change_against_the_period_before_is_unknown_when_there_was_none():
    assert shaped()["totals"]["prev_change_pct"] is None
    assert shaped(blocks=[block(change_pct=8.0)])["totals"]["prev_change_pct"] == 8.0


def test_the_largest_purchase_is_named_even_when_the_bank_did_not_record_the_merchant():
    named = shaped()["totals"]["max_ticket"]
    assert named == {"merchant": "Walmart", "amount": 300.0}
    unnamed = shaped(largest={"merchant_name": None, "amount": 300.0})["totals"]["max_ticket"]
    assert unnamed["merchant"] == domain.UNKNOWN_MERCHANT


def test_only_the_four_biggest_merchants_are_listed_and_one_purchase_is_singular():
    rows = [{"merchant_name": f"M{i}", "amount": 10.0 - i, "transactions": 1 + i} for i in range(6)]
    listed = domain.top_merchants(rows)
    assert [m["name"] for m in listed] == ["M0", "M1", "M2", "M3"]
    assert listed[0]["unit"] == "compra" and listed[1]["unit"] == "compras"


def test_the_product_is_named_for_the_customer():
    assert shaped()["product"] == "Tarjeta de crédito"
    assert domain.product_name("Seguro") == "Seguro"  # not listed: as it is
    assert domain.product_name(None) == "Tus productos"


# ---- duplicate charge alerts ----


def test_alerts_are_only_in_the_screens_currency_newest_first_and_limited():
    rows = [duplicate(at=f"2026-05-{day:02d}T09:00:00") for day in range(1, 9)]
    rows.append(duplicate(merchant="Spotify", currency="USD", at="2026-05-30T09:00:00"))
    listed = domain.alerts(rows, "MXN")
    assert len(listed) == domain.ALERT_LIMIT
    assert [a["date"] for a in listed] == [f"2026-05-{day:02d}" for day in (8, 7, 6, 5, 4)]
    assert {a["currency"] for a in listed} == {"MXN"}


def test_an_alert_carries_what_the_screen_writes():
    (alert,) = shaped(duplicates=[duplicate()])["alerts"]
    assert alert == {
        "type": "duplicate_charge",
        "merchant": "Uber Trip",
        "amount": 312.4,
        "currency": "MXN",
        "date": "2026-05-11",
        "delta_seconds": 4,
    }


# ---- the sentences ----


def test_spending_note_says_where_more_than_half_went_or_the_single_biggest_category():
    over_half = [{"name": "Súper", "amount": 60.0}, {"name": "Transporte", "amount": 20.0}]
    assert domain.spending_note(over_half, 100.0) == "Más de la mitad se fue en súper y transporte."
    spread = [{"name": "Comida", "amount": 30.0}, {"name": "Salud", "amount": 20.0}]
    assert domain.spending_note(spread, 100.0) == "Lo que más pesó fue comida, con 30% del total."
    assert (
        domain.spending_note([{"name": "Otros", "amount": 9.0}], 9.0) == ""
    )  # never names "Otros"


def test_monthly_note_names_the_peak_and_mentions_the_alert_only_when_it_is_in_that_month():
    months = [("2026-04", 300.0), ("2026-05", 700.0)]
    assert domain.monthly_note(months, []) == "Mayo fue tu mes más alto."
    in_may = [{"date": "2026-05-11"}]
    assert domain.monthly_note(months, in_may).endswith("Incluye el cargo que estamos revisando.")
    assert "Incluye" not in domain.monthly_note(months, [{"date": "2026-04-02"}])
    assert domain.monthly_note([("2026-05", 700.0)], []) == ""  # one month has no "highest"


def test_the_tip_leads_with_the_alert_then_with_how_often_they_buy_then_asks_plainly():
    merchants = [
        {"name": "OXXO", "count": 9, "amount": 400.0},
        {"name": "Pemex", "count": 2, "amount": 900.0},
    ]
    assert "cobro repetido en Uber Trip" in domain.tip([{"merchant": "Uber Trip"}], merchants, 90)
    assert domain.tip([], merchants, 90).startswith("Compras en OXXO cada 10 días")
    rare = [{"name": "Pemex", "count": 2, "amount": 900.0}]
    assert (
        domain.tip([], rare, 90)
        == "¿Quieres que te avise al instante si aparece un cobro repetido?"
    )


# ---- the contract with the web ----


def test_the_response_is_camel_case_and_has_nothing_internal():
    result = OwnFinances.model_validate(shaped(duplicates=[duplicate()])).model_dump(by_alias=True)
    assert sorted(result) == sorted(
        [
            "clientId",
            "product",
            "country",
            "currency",
            "windowDays",
            "totals",
            "categories",
            "monthly",
            "topMerchants",
            "alerts",
            "notes",
            "otherCurrencies",
        ]  # fmt: skip
    )
    assert sorted(result["totals"]) == sorted(
        ["spend", "prevChangePct", "transactions", "txPerWeek", "avgTicket", "maxTicket"]
    )
    assert sorted(result["alerts"][0]) == sorted(
        ["type", "merchant", "amount", "currency", "date", "deltaSeconds"]
    )
    assert "internal" not in json.dumps(result)  # the bank's own notes never reach the customer


def test_every_field_the_api_sends_is_declared_in_the_webs_type():
    """A rename on one side breaks the screen silently; this makes it a failing test. Each model
    is looked for in its own TypeScript type, not anywhere in the file."""
    web = (Path(__file__).resolve().parents[1] / "web" / "lib" / "profile.ts").read_text()

    def type_block(name: str) -> str:
        # Over several lines a type ends at a `};` in the first column; a short one is on one line.
        found = re.search(rf"export type {name} = \{{\n(.*?)\n\}};", web, re.DOTALL) or re.search(
            rf"export type {name} = \{{([^\n]*)\}};", web
        )
        assert found, f"web/lib/profile.ts has no `export type {name}`"
        return found.group(1)

    own = {"OwnFinances", "Totals", "MaxTicket", "Notes", "OtherCurrency"}  # all in ClientProfile
    schema = OwnFinances.model_json_schema(by_alias=True)
    models = {"OwnFinances": schema} | schema["$defs"]
    missing = []
    for model, definition in models.items():
        declared = type_block("ClientProfile" if model in own else model)
        missing += [
            f"{model}.{field}"
            for field in definition["properties"]
            if not re.search(rf"\b{field}\??:", declared)
        ]
    assert not missing, f"web/lib/profile.ts does not declare: {missing}"


# ---- the use case: a failing lookup is never a zero ----


class Spending:
    def __init__(self, fail=None):
        self.fail = fail

    async def _rows(self, name, rows):
        if self.fail == name:
            raise RuntimeError(f"{name} is down")
        return rows

    async def totals(self, customer_id, days):
        b = block()
        keys = ("currency", "spend", "previous_spend", "transactions", "avg_ticket", "max_ticket")
        return await self._rows("totals", [{k: b[k] for k in keys}])

    async def by_category(self, customer_id, days):
        return await self._rows(
            "by_category", [{"currency": "MXN"} | r for r in block()["by_category"]]
        )

    async def top_merchants(self, customer_id, days):
        return await self._rows(
            "top_merchants", [{"currency": "MXN"} | r for r in block()["top_merchants"]]
        )

    async def monthly(self, customer_id, days):
        return await self._rows("monthly", [{"currency": "MXN"} | r for r in block()["monthly"]])

    async def foreign(self, customer_id, days):
        return await self._rows("foreign", [])


class Store:
    def __init__(self, fail=None, facts=FACTS, duplicates=None):
        self.fail, self._facts, self._duplicates, self.largest_asked = (
            fail,
            facts,
            duplicates or [],
            [],
        )

    async def facts(self, customer_id):
        if self.fail == "facts":
            raise RuntimeError("down")
        return self._facts

    async def duplicates(self, customer_id, days, window_seconds):
        assert window_seconds == DUPLICATE_WINDOW_SECONDS  # the agent's own definition
        if self.fail == "duplicates":
            raise RuntimeError("down")
        return self._duplicates

    async def largest_purchase(self, customer_id, days, currency):
        self.largest_asked.append(currency)
        if self.fail == "largest":
            raise RuntimeError("down")
        return {"merchant_name": "Walmart", "amount": 300.0}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_the_use_case_puts_the_screen_together_and_asks_for_the_largest_in_its_currency():
    store = Store(duplicates=[duplicate()])
    result = await own_finances(Spending(), store, "CLI-A", 90)
    assert result["totals"]["spend"] == 1000.0 and result["alerts"][0]["merchant"] == "Uber Trip"
    assert store.largest_asked == ["MXN"]


@pytest.mark.anyio
@pytest.mark.parametrize("failing", ["facts", "duplicates", "largest"])
async def test_a_failing_lookup_stops_the_screen_instead_of_reading_as_zero(failing):
    """A missing duplicate check must not read as "no duplicate charges"."""
    with pytest.raises(FinancesUnavailable):
        await own_finances(Spending(), Store(fail=failing), "CLI-A", 90)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failing", ["totals", "by_category", "top_merchants", "monthly", "foreign"]
)
async def test_a_failing_spending_lookup_stops_the_screen_too(failing):
    with pytest.raises(FinancesUnavailable):
        await own_finances(Spending(fail=failing), Store(), "CLI-A", 90)


@pytest.mark.anyio
async def test_an_unknown_customer_and_a_customer_without_purchases_are_told_apart():
    with pytest.raises(UnknownCustomer):
        await own_finances(Spending(), Store(facts=None), "NOBODY", 90)

    class Empty(Spending):
        """No purchases in the period: every lookup filters the same purchases, so all are empty."""

        async def _rows(self, name, rows):
            return []

    with pytest.raises(NoSpending):
        await own_finances(Empty(), Store(), "CLI-A", 90)


# ---- the route ----


SECRET = "s" * 40


@pytest.fixture
def cloud(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "cloud")
    monkeypatch.setattr(settings, "jwt_secret", SECRET)
    return settings


@pytest.fixture
def served(monkeypatch):
    """Replace the use case: records for whom the route asked, and returns a canned screen."""
    calls = []

    async def fake(spending, store, customer_id, days):
        calls.append({"customer": customer_id, "days": days})
        return shaped(customer_id=customer_id, days=days)

    monkeypatch.setattr(http, "own_finances", fake)
    return calls


def bearer(customer_id: str) -> dict:
    token, _ = issue_token(customer_id)
    return {"Authorization": f"Bearer {token}"}


def test_the_route_serves_the_customer_the_token_proves(cloud, served):
    with TestClient(http.app) as client:
        response = client.get("/api/me/finances", headers=bearer("CLI-A"))
    assert response.status_code == 200 and response.json()["clientId"] == "CLI-A"
    assert served == [{"customer": "CLI-A", "days": 90}]
    assert "totals" in response.json() and "internal" not in response.text


def test_the_route_refuses_a_request_without_a_token_in_the_cloud(cloud, served):
    with TestClient(http.app) as client:
        response = client.get("/api/me/finances", params={"customer_id": "CLI-A"})
    assert response.status_code == 401 and served == []


def test_a_customer_cannot_ask_for_somebody_elses_screen(cloud, served):
    with TestClient(http.app) as client:
        response = client.get(
            "/api/me/finances", params={"customer_id": "CLI-B"}, headers=bearer("CLI-A")
        )
    assert response.status_code == 403 and served == []


def test_locally_the_customer_can_be_named_without_a_token_and_must_be_named(monkeypatch, served):
    monkeypatch.setattr(get_settings(), "app_env", "local")
    with TestClient(http.app) as client:
        assert client.get("/api/me/finances", params={"customer_id": "CLI-A"}).status_code == 200
        assert client.get("/api/me/finances").status_code == 400


@pytest.mark.parametrize("days", [0, 6, 366])
def test_the_period_has_limits(cloud, served, days):
    with TestClient(http.app) as client:
        response = client.get("/api/me/finances", params={"days": days}, headers=bearer("CLI-A"))
    assert response.status_code == 422 and served == []


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (UnknownCustomer("x"), 404, "unknown_customer"),
        (NoSpending(), 404, "no_spending_in_period"),
        (FinancesUnavailable("x"), 503, "finances_unavailable"),
    ],
)
def test_each_failure_has_its_own_status(cloud, monkeypatch, error, status, detail):
    async def fail(*args):
        raise error

    monkeypatch.setattr(http, "own_finances", fail)
    with TestClient(http.app) as client:
        response = client.get("/api/me/finances", headers=bearer("CLI-A"))
    assert (response.status_code, response.json()["detail"]) == (status, detail)


# ---- the SQL, against the demo data ----


@pytest.fixture
def demo_data():
    try:
        postgres.ping()
    except Exception:
        pytest.skip("Postgres with the demo data is not running")


@pytest.mark.anyio
async def test_the_duplicate_of_the_demo_customer_is_found_once(demo_data):
    (found,) = await PostgresFinances().duplicates(DEMO, 90, DUPLICATE_WINDOW_SECONDS)
    assert (found["merchant_name"], found["amount"], found["currency"]) == (
        "Uber Trip",
        312.4,
        "MXN",
    )
    assert found["seconds_apart"] == 4 and found["at"].date().isoformat() == "2026-06-11"


@pytest.mark.anyio
async def test_duplicates_belong_to_their_customer_and_respect_the_period(demo_data):
    store = PostgresFinances()
    assert await store.duplicates("DEMO-MX-FX", 90, DUPLICATE_WINDOW_SECONDS) == []
    (portuguese,) = await store.duplicates("DEMO-BR-PORTUGUESE", 90, DUPLICATE_WINDOW_SECONDS)
    assert portuguese["merchant_name"] == "iFood"
    assert (
        await store.duplicates(DEMO, 1, DUPLICATE_WINDOW_SECONDS) == []
    )  # older than the last day
    assert await store.duplicates(DEMO, 90, 2) == []  # 4 seconds apart is not within 2


@pytest.mark.anyio
async def test_facts_and_the_largest_purchase_match_the_data(demo_data):
    store = PostgresFinances()
    facts = await store.facts(DEMO)
    assert facts["country"] == "México" and facts["product_type"] == "Tarjeta Crédito"
    assert await store.facts("NO-SUCH-CUSTOMER") is None
    expected = await postgres.query(
        "SELECT max(amount) AS amount FROM core.transactions WHERE customer_id = %(c)s"
        " AND transaction_type = 'Purchase' AND transaction_status = 'Approved'",
        {"c": DEMO},
    )
    largest = await store.largest_purchase(DEMO, 90, "MXN")
    assert largest["amount"] == expected[0]["amount"]
    assert await store.largest_purchase(DEMO, 90, "USD") is None  # nothing bought in that currency


@pytest.mark.anyio
async def test_the_demo_customers_screen_agrees_with_the_reference_answers(demo_data):
    result = await own_finances(PostgresSpending(), PostgresFinances(), DEMO, 90)
    assert result["currency"] == "MXN" and result["totals"]["spend"] == 20719.1
    assert result["totals"]["transactions"] == 32 and result["totals"]["prev_change_pct"] is None
    assert round(sum(c["amount"] for c in result["categories"]), 2) == 20719.1  # nothing lost
    assert round(sum(amount for _, amount in result["monthly"]), 2) == 20719.1
    assert [m["name"] for m in result["top_merchants"]][:3] == ["Netflix", "OXXO", "Pemex"]
    assert [(a["merchant"], a["amount"], a["delta_seconds"]) for a in result["alerts"]] == [
        ("Uber Trip", 312.4, 4)
    ]
    OwnFinances.model_validate(result)  # and it fits the contract


def test_two_customers_see_only_their_own_screen_through_the_api(demo_data, cloud):
    with TestClient(http.app) as client:
        mine = client.get("/api/me/finances", headers=bearer(DEMO)).json()
        theirs = client.get("/api/me/finances", headers=bearer("DEMO-MX-FX")).json()
        nobody = client.get("/api/me/finances", headers=bearer("NO-SUCH-CUSTOMER"))
    assert mine["clientId"] == DEMO and len(mine["alerts"]) == 1
    assert theirs["clientId"] == "DEMO-MX-FX" and theirs["alerts"] == []
    assert mine["totals"]["spend"] != theirs["totals"]["spend"]
    assert nobody.status_code == 404
