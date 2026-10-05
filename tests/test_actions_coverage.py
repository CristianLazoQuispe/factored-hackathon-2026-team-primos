# ruff: noqa: E501  (the assertions stay on one line each)
"""The coverage tool says what the policy would do for a customer, from their data. Real database, no model."""

import psycopg
import pytest

from app.adapters.outbound import postgres
from app.config import Settings, get_settings
from evals.actions import coverage, world

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def need_database():
    try:
        postgres.ping()
        with psycopg.connect(get_settings().database_url) as conn:
            ready = conn.execute("SELECT to_regclass('ops.actions')").fetchone()[0]
    except Exception:
        pytest.skip("Postgres with the demo data is not running")
    if ready is None:
        pytest.skip("apply app/adapters/outbound/postgres/migrations/001_actions.sql first")


async def cells(fixture: str) -> dict[str, str]:
    customer = world.build(fixture, "Plus", "México", "es")
    try:
        return await coverage.row(customer.id)
    finally:
        world.drop(customer)


async def test_a_credit_card_with_a_balance_can_be_blocked_but_not_cancelled():
    got = await cells("single")
    assert got["cards"] == "1" and got["block_card"] == "confirm"
    assert got["cancel_card"] == "person: outstanding_balance"


async def test_a_debit_card_without_a_balance_can_be_cancelled_with_confirmation():
    got = await cells("cancelable")
    assert got["cancel_card"] == "confirm" and got["block_card"] == "confirm"


async def test_a_card_the_bank_blocked_cannot_be_blocked_again():
    assert (await cells("bank_blocked"))["block_card"] == "refused: already_blocked"


async def test_without_an_email_on_file_the_summary_is_refused_and_the_rest_still_works():
    got = await cells("no_email")
    assert got["email"] == "refused: no_contact_on_file"
    assert (
        got["callback"] == "confirm"
        and got["alert"] == "confirm"
        and got["block_card"] == "confirm"
    )


async def test_a_reversed_and_a_pending_charge_are_the_ones_not_eligible_for_an_inquiry():
    got = await cells("charges")
    assert (
        "already_reversed x1" in got["inquiry_refusals"]
        and "still_pending x1" in got["inquiry_refusals"]
    )
    assert got["inquiry"].startswith("3 of 5")


async def test_a_summary_with_an_email_goes_out_directly_and_a_call_or_alert_asks_first():
    got = await cells("single")
    assert got["email"] == "direct" and got["callback"] == "confirm" and got["alert"] == "confirm"


async def test_a_customer_that_does_not_exist_has_nothing_to_act_on():
    got = await coverage.row("DEMO-NO-SUCH-CUSTOMER")
    assert got["cards"] == "0" and got["block_card"] == "refused: no card"
    assert got["inquiry"] == "0 of 0 charges" and got["email"] == "refused: no_contact_on_file"


async def test_the_default_list_is_the_demo_customers_and_the_offered_ones_without_the_eval_ones(
    monkeypatch,
):
    built = world.build("single", "Plus", "México", "es")
    monkeypatch.setattr(
        coverage,
        "get_settings",
        lambda: Settings(_env_file=None, demo_customer_ids="CLI-AAA, CLI-BBB"),
    )
    try:
        listed = await coverage.customers([])
    finally:
        world.drop(built)
    assert "DEMO-MX-DUPLICATE" in listed and "CLI-AAA" in listed and "CLI-BBB" in listed
    assert built.id not in listed, "the customers the evals build are never offered"
    assert len(listed) == len(set(listed))
    assert await coverage.customers(["CLI-X"]) == ["CLI-X"]


async def test_the_table_has_a_row_per_customer_and_lists_what_cannot_be_asked():
    lines = coverage.table([await cells("charges"), await cells("single")])
    assert (
        lines[0].startswith("| customer | cards |")
        and sum(1 for line in lines if line.startswith("| DEMO-EVL-")) == 2
    )
    assert any("charges not eligible: " in line for line in lines)


async def test_a_closed_card_is_not_something_to_block():
    customer = world.build("single", "Plus", "México", "es")
    try:
        with psycopg.connect(get_settings().database_url) as conn:
            conn.execute(
                "UPDATE core.products SET product_status = 'Closed' WHERE customer_id = %s",
                (customer.id,),
            )
        got = await coverage.row(customer.id)
    finally:
        world.drop(customer)
    assert got["cards"] == "0" and got["block_card"] == "refused: no card"
