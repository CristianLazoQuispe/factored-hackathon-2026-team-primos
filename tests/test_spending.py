"""Movements, spending, complaints and exchange rate: domain, use case with a fake store, tools."""

from datetime import date, datetime

import pytest

from app.adapters.inbound.mcp import dwh
from app.application.spending import spending_summary
from app.domain.spending import change_pct, complaints_summary, summarize, tx_per_week

pytestmark = pytest.mark.anyio

TOTALS = {
    "currency": "MXN",
    "spend": 1500.0,
    "previous_spend": 1000.0,
    "transactions": 6,
    "avg_ticket": 250.0,
    "max_ticket": 700.0,
}
MOVEMENT = {
    "transaction_date": datetime(2026, 6, 11, 9, 0),
    "amount": 312.4,
    "currency": "MXN",
    "merchant_name": "Uber Trip",
    "transaction_category": None,
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeStore:
    def __init__(self, broken=(), movements=(), complaints=(), rate=None):
        self.broken, self.seen, self.asked = set(broken), [], {}
        self.movement_rows, self.complaint_rows, self.rate = list(movements), complaints, rate

    def _use(self, name: str, customer_id: str) -> None:
        self.seen.append(customer_id)
        if name in self.broken:
            raise RuntimeError(f"{name} is down")

    async def totals(self, customer_id, days):
        self._use("totals", customer_id)
        return [TOTALS, TOTALS | {"currency": "USD", "spend": 20.0, "previous_spend": 0.0}]

    async def by_category(self, customer_id, days):
        self._use("by_category", customer_id)
        return [{"currency": "MXN", "category": "Food", "amount": 900.0, "transactions": 4}]

    async def top_merchants(self, customer_id, days):
        self._use("top_merchants", customer_id)
        return [{"currency": "MXN", "merchant_name": "OXXO", "amount": 900.0, "transactions": 4}]

    async def monthly(self, customer_id, days):
        self._use("monthly", customer_id)
        return [{"currency": "MXN", "month": "2026-06", "amount": 1500.0, "transactions": 6}]

    async def foreign(self, customer_id, days):
        self._use("foreign", customer_id)
        return [{"currency": "MXN", "transactions": 0, "amount": 0.0}]

    async def movements(self, customer_id, limit, **filters):
        self._use("movements", customer_id)
        self.asked = {"limit": limit} | filters
        return self.movement_rows[:limit]

    async def complaints(self, customer_id):
        self._use("complaints", customer_id)
        return list(self.complaint_rows)

    async def exchange_rate(self, source, target, on):
        self.asked = {"source": source, "target": target, "on": on}
        return self.rate


def test_change_is_unknown_without_previous_spending():
    assert change_pct(1500.0, 1000.0) == 50.0
    assert change_pct(500.0, 1000.0) == -50.0
    assert change_pct(1500.0, 0.0) is None and change_pct(None, 1000.0) is None
    assert tx_per_week(6, 30) == 1.4


def test_summary_is_one_block_per_currency_and_leaves_out_what_did_not_run():
    mxn, usd = summarize(30, {"totals": [TOTALS, TOTALS | {"currency": "USD", "spend": 20.0}]})
    assert (mxn["currency"], usd["currency"]) == ("MXN", "USD")
    assert mxn["spend"] == 1500.0 and mxn["change_pct"] == 50.0 and mxn["tx_per_week"] == 1.4
    assert "by_category" not in mxn and "foreign" not in mxn  # those lookups are not in `parts`
    assert summarize(30, {}) == []


def test_complaints_are_counted_by_status_and_open_means_still_being_handled():
    rows = [{"status": s} for s in ("Open", "In Process", "Escalated", "Resolved", "Resolved")]
    summary = complaints_summary(rows + [{"status": "Closed"}] * 10)
    assert summary["count"] == 15 and summary["open"] == 3
    assert {"status": "Resolved", "count": 2} in summary["by_status"]
    assert len(summary["latest"]) == 10
    assert complaints_summary([]) == {"count": 0, "open": 0, "by_status": [], "latest": []}


async def test_summary_runs_every_lookup_as_the_customer_it_was_given():
    store = FakeStore()
    summary = await spending_summary(store, "C1", 30)
    mxn, usd = summary["currencies"]
    assert set(store.seen) == {"C1"} and len(store.seen) == 5
    assert mxn["by_category"] == [{"category": "Food", "amount": 900.0, "transactions": 4}]
    assert mxn["top_merchants"][0]["merchant_name"] == "OXXO"
    assert mxn["foreign"] == {"transactions": 0, "amount": 0.0}  # it ran and found none
    assert "change_pct" not in usd and usd["previous_spend"] == 0.0
    assert summary["unavailable"] == [] and summary["evidence_lookup"] == "get_spending_summary"


async def test_a_failed_lookup_is_unavailable_never_a_zero_and_does_not_sink_the_rest():
    summary = await spending_summary(FakeStore(broken={"foreign", "by_category"}), "C1", 30)
    assert summary["unavailable"] == ["by_category", "foreign"]
    mxn = summary["currencies"][0]
    assert "foreign" not in mxn and "by_category" not in mxn and mxn["spend"] == 1500.0
    no_totals = await spending_summary(FakeStore(broken={"totals"}), "C1", 30)
    assert "spend" not in no_totals["currencies"][0] and no_totals["unavailable"] == ["totals"]


# ---- MCP tools ----


@pytest.fixture
def audit(monkeypatch):
    calls = []

    async def record(tool, proposed, decision, reason, executed):
        calls.append((tool, proposed["customer_id"], decision, executed))

    monkeypatch.setattr(dwh, "record_decision", record)
    return calls


async def test_lookup_tools_run_as_the_session_customer_and_are_audited(monkeypatch, audit):
    from fastmcp import Client

    store = FakeStore(complaints=[{"status": "Open", "creation_date": datetime(2026, 5, 2)}])
    monkeypatch.setattr(dwh, "store", store)
    me = {"customer_id": "C1"}
    async with Client(dwh.mcp) as client:
        summary = await client.call_tool("get_spending_summary", {"days": 90}, meta=me)
        complaints = await client.call_tool("get_complaints", {}, meta=me)
        nobody = await client.call_tool("get_spending_summary", {}, raise_on_error=False)
        too_long = await client.call_tool(
            "get_spending_summary", {"days": 999}, meta=me, raise_on_error=False
        )
    assert summary.structured_content["days"] == 90
    assert complaints.structured_content["open"] == 1
    assert complaints.structured_content["latest"][0]["creation_date"] == "2026-05-02T00:00:00"
    assert nobody.is_error and too_long.is_error
    assert set(store.seen) == {"C1"}
    assert audit == [
        ("get_spending_summary", "C1", "allowed", True),
        ("get_complaints", "C1", "allowed", True),
    ]


async def test_movements_pass_the_filters_and_say_when_there_are_more(monkeypatch, audit):
    from fastmcp import Client

    store = FakeStore(movements=[MOVEMENT] * 5)
    monkeypatch.setattr(dwh, "store", store)
    async with Client(dwh.mcp) as client:
        result = await client.call_tool(
            "get_movements",
            {"merchant": "uber", "order": "largest", "limit": 3, "product_type": "Tarjeta Crédito"},
            meta={"customer_id": "C1"},
        )
        bad = await client.call_tool(
            "get_movements", {"status": "Stolen"}, meta={"customer_id": "C1"}, raise_on_error=False
        )
    content = result.structured_content
    assert content["count"] == 3 and content["truncated"] is True
    assert content["movements"][0] == {
        "transaction_date": "2026-06-11T09:00:00",
        "amount": 312.4,
        "currency": "MXN",
        "merchant_name": "Uber Trip",
    }
    assert store.asked["limit"] == 4 and store.asked["largest"] is True
    assert store.asked["merchant"] == "uber" and store.asked["product_type"] == "Tarjeta Crédito"
    assert store.asked["days"] == 30 and store.asked["status"] is None
    assert bad.is_error  # a status outside the vocabulary never reaches the database
    assert audit == [("get_movements", "C1", "allowed", True)]


async def test_exchange_rate_found_or_not_is_said_plainly(monkeypatch, audit):
    from fastmcp import Client

    rate = {"date": date(2026, 6, 17), "exchange_rate": 17.02, "buy_rate": None}
    monkeypatch.setattr(dwh, "store", FakeStore(rate=rate))
    args = {"source": "USD", "target": "MXN"}
    async with Client(dwh.mcp) as client:
        found = await client.call_tool("get_exchange_rate", args, meta={"customer_id": "C1"})
        monkeypatch.setattr(dwh, "store", FakeStore())
        missing = await client.call_tool(
            "get_exchange_rate", args | {"on": "2020-01-01"}, meta={"customer_id": "C1"}
        )
        nobody = await client.call_tool("get_exchange_rate", args, raise_on_error=False)
    assert found.structured_content == {
        "found": True,
        "date": "2026-06-17",
        "exchange_rate": 17.02,
        "evidence_lookup": "get_exchange_rate",
    }
    assert missing.structured_content == {"found": False, "evidence_lookup": "get_exchange_rate"}
    assert nobody.is_error
