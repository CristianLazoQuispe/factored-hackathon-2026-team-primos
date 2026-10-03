"""Balances, debts and profile: domain facts and the MCP tools with a fake database."""

from datetime import date

import pytest

from app.adapters.inbound.mcp import accounts
from app.domain.accounts import balance_totals, credit_available, present, tenure_years

pytestmark = pytest.mark.anyio

CARD = {
    "product_type": "Tarjeta Crédito",
    "product_number_last4": "1234",
    "currency": "MXN",
    "current_balance": 8100.0,
    "credit_limit": 27000.0,
    "product_status": "Active",
}
SAVINGS = CARD | {"product_type": "Cuenta Ahorro", "current_balance": 500.0, "credit_limit": None}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_credit_available_is_only_known_for_a_card_with_limit_and_balance():
    assert credit_available(CARD) == 18900.0
    assert credit_available(CARD | {"current_balance": 30000.0}) == 0  # over the limit
    assert credit_available(CARD | {"credit_limit": None}) is None
    assert credit_available(SAVINGS | {"credit_limit": 1000.0}) is None


def test_totals_never_mix_currencies_groups_or_inactive_products():
    totals = balance_totals(
        [
            SAVINGS,
            SAVINGS | {"product_type": "Cuenta Corriente", "current_balance": 250.5},
            SAVINGS | {"currency": "USD", "current_balance": 40.0},
            SAVINGS | {"product_status": "Closed", "current_balance": 9999.0},
            SAVINGS | {"product_type": "Tarjeta Débito", "current_balance": 77.0},
            SAVINGS | {"current_balance": None},
            CARD,
        ]
    )
    assert totals == [
        {"group": "debt", "currency": "MXN", "total": 8100.0, "products": 1},
        {"group": "deposits", "currency": "MXN", "total": 750.5, "products": 2},
        {"group": "deposits", "currency": "USD", "total": 40.0, "products": 1},
    ]


def test_unknowns_stay_absent_and_tenure_needs_dates_that_make_sense():
    assert present({"a": None, "b": 0, "c": date(2026, 6, 18)}) == {"b": 0, "c": "2026-06-18"}
    assert tenure_years(date(2021, 3, 15), date(2026, 6, 17)) == 5
    assert tenure_years(date(2021, 6, 18), date(2026, 6, 17)) == 4
    assert tenure_years(None, date(2026, 6, 17)) is None
    assert tenure_years(date(2027, 1, 1), date(2026, 6, 17)) is None


@pytest.fixture
def bank(monkeypatch):
    seen, audit = [], []

    async def fetch_balances(customer_id, product_type=None):
        seen.append(customer_id)
        return [CARD, SAVINGS]

    async def fetch_debts(customer_id, product_types):
        seen.append(customer_id)
        debt = {k: CARD[k] for k in ("product_type", "product_number_last4", "currency")}
        billed = {"debt": 8100.0, "due_date": date(2026, 7, 4), "minimum_payment": 500.0}
        return [
            debt | billed | {"as_of": date(2026, 6, 18), "remaining_installments": None},
            debt | {"debt": 10.0, "as_of": None, "due_date": None},  # no schedule on record
        ][: len(product_types)]

    async def fetch_profile(customer_id):
        seen.append(customer_id)
        return {
            "first_name": "Lucía",
            "segment": None,
            "customer_since": date(2021, 3, 15),
            "as_of": date(2026, 6, 17),
        }

    async def fetch_products_held(customer_id):
        return [{"product_type": "Tarjeta Crédito", "products": 1, "active": 1}]

    async def record(tool, proposed, decision, reason, executed):
        audit.append((tool, proposed["customer_id"], decision, executed))

    monkeypatch.setattr(accounts, "fetch_balances", fetch_balances)
    monkeypatch.setattr(accounts, "fetch_debts", fetch_debts)
    monkeypatch.setattr(accounts, "fetch_profile", fetch_profile)
    monkeypatch.setattr(accounts, "fetch_products_held", fetch_products_held)
    monkeypatch.setattr(accounts, "record_decision", record)
    return seen, audit


async def test_tools_take_no_customer_run_as_the_session_customer_and_are_audited(bank):
    from fastmcp import Client

    seen, audit = bank
    async with Client(accounts.mcp) as client:
        tools = await client.list_tools()
        for tool in tools:
            assert "customer_id" not in tool.input_schema["properties"], tool.name
        for tool in tools:
            await client.call_tool(tool.name, {}, meta={"customer_id": "C1"})
            assert (await client.call_tool(tool.name, {}, raise_on_error=False)).is_error
    assert {t.name for t in tools} == {"get_balances", "get_debts", "get_profile"}
    assert set(seen) == {"C1"}
    assert sorted(audit) == [
        ("get_balances", "C1", "allowed", True),
        ("get_debts", "C1", "allowed", True),
        ("get_profile", "C1", "allowed", True),
    ]


async def test_balances_come_with_credit_available_and_totals(bank):
    from fastmcp import Client

    async with Client(accounts.mcp) as client:
        result = await client.call_tool("get_balances", {}, meta={"customer_id": "C1"})
    card, savings = result.structured_content["products"]
    assert card["credit_available"] == 18900.0
    assert "credit_available" not in savings and "credit_limit" not in savings
    assert {t["group"] for t in result.structured_content["totals"]} == {"debt", "deposits"}


async def test_debts_say_they_are_team_generated_and_leave_unknowns_out(bank):
    from fastmcp import Client

    async with Client(accounts.mcp) as client:
        result = await client.call_tool("get_debts", {}, meta={"customer_id": "C1"})
        one = await client.call_tool(
            "get_debts", {"product_type": "Tarjeta Crédito"}, meta={"customer_id": "C1"}
        )
        bad = await client.call_tool(
            "get_debts",
            {"product_type": "Cuenta Ahorro"},
            meta={"customer_id": "C1"},
            raise_on_error=False,
        )
    content = result.structured_content
    assert content["as_of"] == "2026-06-18" and content["billing_provenance"] == "team_generated"
    billed, unbilled = content["debts"]
    assert billed["due_date"] == "2026-07-04" and billed["minimum_payment"] == 500.0
    assert "remaining_installments" not in billed and "as_of" not in billed
    assert unbilled == {
        "product_type": "Tarjeta Crédito",
        "product_number_last4": "1234",
        "currency": "MXN",
        "debt": 10.0,
    }
    assert len(one.structured_content["debts"]) == 1
    assert bad.is_error  # a savings account is not a debt


async def test_profile_gives_tenure_and_only_what_is_on_record(bank):
    from fastmcp import Client

    async with Client(accounts.mcp) as client:
        result = await client.call_tool("get_profile", {}, meta={"customer_id": "C1"})
    profile = result.structured_content
    assert profile["customer_since"] == "2021-03-15" and profile["tenure_years"] == 5
    assert "segment" not in profile and "as_of" not in profile
    assert profile["products"] == [{"product_type": "Tarjeta Crédito", "products": 1, "active": 1}]
