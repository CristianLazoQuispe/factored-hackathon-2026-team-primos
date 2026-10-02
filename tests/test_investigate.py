"""Charge investigation: domain facts, the use case with a fake warehouse, and the MCP tools."""

from datetime import date, datetime

import pytest

from app.adapters.inbound.mcp import investigation
from app.application.investigate import investigate_charge, investigate_matching
from app.domain.evidence import duplicate_facts, fx_facts, pending_facts

pytestmark = pytest.mark.anyio

TX = {
    "transaction_id": "T1",
    "transaction_date": datetime(2026, 6, 10, 12, 0),
    "amount": 312.4,
    "currency": "MXN",
    "merchant_name": "Uber Trip",
    "channel": "POS",
    "transaction_status": "Approved",
    "transaction_country": "México",
}
RATE = {"date": date(2026, 6, 9), "exchange_rate": 0.06}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeWarehouse:
    def __init__(
        self, transaction=TX, twin=None, home="Mexico", rate=RATE, broken=(), matches=(), twins=None
    ):
        self.transaction_row, self.twin, self.home, self.rate = transaction, twin, home, rate
        self.matches, self.twins = list(matches), twins or {}
        self.broken = set(broken)
        self.seen: list[str] = []

    def _use(self, name: str, customer_id: str | None = None) -> None:
        if customer_id:
            self.seen.append(customer_id)
        if name in self.broken:
            raise RuntimeError(f"{name} is down")

    async def transaction(self, customer_id, transaction_id):
        self._use("transaction", customer_id)
        return self.transaction_row

    async def duplicate_of(self, customer_id, transaction_id, window_seconds):
        self._use("duplicate", customer_id)
        return self.twins.get(transaction_id, self.twin)

    async def search(self, customer_id, days, merchant, min_amount, max_amount):
        self._use("search", customer_id)
        return self.matches

    async def home_country(self, customer_id):
        self._use("home", customer_id)
        return self.home

    async def fx_rate_to_usd(self, currency, on):
        self._use("rate")
        return self.rate


# ---- domain ----


def test_duplicate_none_is_a_real_no_and_a_row_is_a_finding():
    assert duplicate_facts(None) == {"found": False}
    twin = {"transaction_id": "T0", "seconds_apart": 4, "merchant_name": "Uber", "amount": 1.0}
    assert duplicate_facts(twin | {"currency": "MXN"})["duplicate_of"] == "T0"


def test_pending_and_reversed_come_from_the_status():
    assert pending_facts(TX | {"transaction_status": "Pending"})["is_pending"] is True
    assert pending_facts(TX | {"transaction_status": "Reversed"})["is_reversed"] is True
    assert pending_facts(TX)["is_pending"] is False


def test_fx_folds_accents_and_only_prices_foreign_purchases():
    home = fx_facts(TX, "Mexico", RATE)  # "México" vs "Mexico" is the same country
    assert home["is_foreign"] is False and "reference_rate_to_usd" not in home
    abroad = fx_facts(TX | {"transaction_country": "USA"}, "Mexico", RATE)
    assert abroad["is_foreign"] is True
    assert abroad["amount_usd_at_reference_rate"] == 18.74


def test_fx_leaves_unknowns_absent_instead_of_guessing():
    assert fx_facts(TX | {"transaction_country": None}, "Mexico", RATE) == {}
    no_rate = fx_facts(TX | {"transaction_country": "USA"}, "Mexico", None)
    assert no_rate["is_foreign"] is True and "reference_rate_to_usd" not in no_rate


# ---- use case ----


async def test_unknown_or_foreign_transaction_id_gets_one_neutral_error():
    report = await investigate_charge(FakeWarehouse(transaction=None), "C1", "T-OTHER")
    assert report == {"error": "No such charge in this customer's account."}


async def test_report_carries_all_facts_and_only_the_session_customer():
    twin = {"transaction_id": "T0", "seconds_apart": 4, "merchant_name": "Uber Trip"}
    warehouse = FakeWarehouse(twin=twin | {"amount": 312.4, "currency": "MXN"})
    report = await investigate_charge(warehouse, "C1", "T1")
    assert report["duplicate"]["found"] is True
    assert report["pending"]["status"] == "Approved"
    assert report["unavailable"] == [] and report["evidence_lookup"] == "investigate_charge"
    assert set(warehouse.seen) == {"C1"}


async def test_a_failing_lookup_is_unavailable_never_a_no_and_the_rest_survive():
    report = await investigate_charge(FakeWarehouse(broken={"duplicate"}), "C1", "T1")
    assert report["unavailable"] == ["duplicate"]
    assert "duplicate" not in report  # absent, so it cannot be read as "found: False"
    assert report["pending"]["is_pending"] is False and "fx" in report


async def test_fx_fails_as_a_whole_when_either_of_its_lookups_fails():
    report = await investigate_charge(FakeWarehouse(broken={"rate"}), "C1", "T1")
    assert report["unavailable"] == ["fx"] and "duplicate" in report


# ---- MCP tools ----


async def test_tools_never_take_a_customer_id():
    from fastmcp import Client

    async with Client(investigation.mcp) as client:
        for tool in await client.list_tools():
            assert "customer_id" not in tool.input_schema["properties"], tool.name


async def test_tool_runs_as_the_session_customer_and_audits_the_decision(monkeypatch):
    from fastmcp import Client

    warehouse, audit = FakeWarehouse(), []

    async def record(tool, proposed, decision, reason, executed):
        audit.append((tool, proposed, decision, executed))

    monkeypatch.setattr(investigation, "warehouse", warehouse)
    monkeypatch.setattr(investigation, "record_decision", record)
    async with Client(investigation.mcp) as client:
        result = await client.call_tool(
            "investigate_charge", {"transaction_id": "T1"}, meta={"customer_id": "C1"}
        )
        assert result.structured_content["pending"]["status"] == "Approved"
        missing = await client.call_tool(
            "investigate_charge", {"transaction_id": "T1"}, raise_on_error=False
        )
    assert set(warehouse.seen) == {"C1"}
    assert missing.is_error  # no session customer, no data
    assert audit == [
        ("investigate_charge", {"customer_id": "C1", "transaction_id": "T1"}, "allowed", True)
    ]


# ---- investigate every matching charge in one call ----


def twin_of(other: str) -> dict:
    return {
        "transaction_id": other,
        "seconds_apart": 4,
        "merchant_name": "Uber Trip",
        "amount": 312.4,
        "currency": "MXN",
    }


async def test_matching_charges_are_named_by_position_and_twins_point_at_each_other():
    warehouse = FakeWarehouse(
        matches=[{"transaction_id": "B"}, {"transaction_id": "A"}, {"transaction_id": "C"}],
        twins={"B": twin_of("A"), "A": twin_of("B")},
    )
    report = await investigate_matching(warehouse, "C1", 30, "uber", None, None)
    assert report["count"] == 3 and report["not_checked"] == 0
    assert report["evidence_lookup"] == "investigate_charges"
    first, second, third = report["charges"]
    assert first["duplicate"]["duplicate_of"] == "#2"
    assert second["duplicate"]["duplicate_of"] == "#1"
    assert third["duplicate"] == {"found": False}
    assert "transaction_id" not in first["transaction"] and first["transaction"]["ref"] == "#1"


async def test_a_twin_outside_the_list_is_not_named_by_its_internal_id():
    warehouse = FakeWarehouse(
        matches=[{"transaction_id": "B"}], twins={"B": twin_of("SECRET-ID-9")}
    )
    report = await investigate_matching(warehouse, "C1", 30, None, None, None)
    assert "SECRET-ID-9" not in str(report)


async def test_no_matches_is_zero_charges_and_a_broken_search_is_not_a_no():
    empty = await investigate_matching(FakeWarehouse(), "C1", 30, "uber", None, None)
    assert empty["count"] == 0 and empty["charges"] == []
    with pytest.raises(RuntimeError):  # the search itself failing must not read as "no charges"
        await investigate_matching(FakeWarehouse(broken={"search"}), "C1", 30, None, None, None)


async def test_the_combined_tool_runs_as_the_session_customer_and_audits(monkeypatch):
    from fastmcp import Client

    warehouse = FakeWarehouse(matches=[{"transaction_id": "T1"}])
    audit = []

    async def record(tool, proposed, decision, reason, executed):
        audit.append((tool, proposed["customer_id"], decision))

    monkeypatch.setattr(investigation, "warehouse", warehouse)
    monkeypatch.setattr(investigation, "record_decision", record)
    async with Client(investigation.mcp) as client:
        result = await client.call_tool(
            "investigate_charges", {"merchant": "uber"}, meta={"customer_id": "C1"}
        )
    assert result.structured_content["count"] == 1
    assert set(warehouse.seen) == {"C1"}
    assert audit == [("investigate_charges", "C1", "allowed")]


async def test_findings_list_each_verified_fact_once_with_the_pair_counted_a_single_time():
    warehouse = FakeWarehouse(
        matches=[{"transaction_id": "B"}, {"transaction_id": "A"}],
        twins={"B": twin_of("A"), "A": twin_of("B")},
    )
    report = await investigate_matching(warehouse, "C1", 30, "uber", None, None)
    (finding,) = report["findings"]  # two charges flag each other: still ONE finding
    assert finding["kind"] == "duplicate" and finding["charges"] == ["#1", "#2"]
    assert finding["seconds_apart"] == 4 and len(finding["at"]) == 2


async def test_findings_cover_pending_reversed_and_foreign_and_are_empty_when_nothing_is_wrong():
    pending = FakeWarehouse(
        transaction=TX | {"transaction_status": "Pending", "transaction_country": "USA"},
        matches=[{"transaction_id": "T1"}],
    )
    kinds = [
        f["kind"]
        for f in (await investigate_matching(pending, "C1", 30, None, None, None))["findings"]
    ]
    assert kinds == ["pending", "foreign_purchase"]
    clean = await investigate_matching(
        FakeWarehouse(matches=[{"transaction_id": "T1"}]), "C1", 30, None, None, None
    )
    assert clean["findings"] == [] and clean["count"] == 1
