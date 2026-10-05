"""Khipear against the real demo data: the proposal, the confirmation and what they write.
Skipped unless Postgres is up (`make demo-data`). Each test starts from the fixtures' balances
(the demo may have moved them) and leaves the balances as it found them."""

import psycopg
import pytest

from app.adapters.outbound import postgres
from app.adapters.outbound.postgres.transfers import PostgresLedger
from app.application.transfers import (
    cancel,
    execute,
    propose,
    propose_service_payment,
    service_bills,
)
from app.config import get_settings
from app.domain.transfers import Limits
from data_pipeline.fixtures import KHIPU_PRODUCTS

pytestmark = pytest.mark.anyio
ME, OTHER = "DEMO-MX-KHIPU", "DEMO-MX-RECIBE"
SAVINGS, CHECKING, CARD, LOAN = (f"{ME}-{s}" for s in ("AHORRO", "CORRIENTE", "CARD", "LOAN"))
LIMITS = Limits(per_operation_usd=1000, per_day_usd=3000)
ledger = PostgresLedger()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def db():
    try:
        postgres.ping()
    except Exception:
        pytest.skip("Postgres with the demo data is not running")
    with psycopg.connect(get_settings().database_url, autocommit=True) as pg:
        if not pg.execute("SELECT to_regclass('ops.transfers')").fetchone()[0]:
            pytest.skip("ops.transfers is missing: run `make db-load`")
        mine = "customer_id IN (%s, %s)"
        before = pg.execute(
            f"SELECT product_id, current_balance FROM core.products WHERE {mine}", (ME, OTHER)
        ).fetchall()
        started = pg.execute("SELECT now()").fetchone()[0]
        set_balance = "UPDATE core.products SET current_balance = %s WHERE product_id = %s"
        for customer, suffix, *_, initial, _limit, _rate in KHIPU_PRODUCTS:
            pg.execute(set_balance, (initial, f"{customer}-{suffix}"))
        bills = "UPDATE core.service_bills SET status = %s, paid_at = %s WHERE bill_id = %s"
        paid = pg.execute(
            f"SELECT status, paid_at, bill_id FROM core.service_bills WHERE {mine}", (ME, OTHER)
        ).fetchall()
        for _status, _paid_at, bill_id in paid:
            pg.execute(bills, ("pending", None, bill_id))
        yield pg
        for product_id, balance in before:
            pg.execute(set_balance, (balance, product_id))
        for row in paid:
            pg.execute(bills, row)
        made = f"FROM ops.transfers WHERE created_at >= %s AND {mine}"
        pg.execute(
            "DELETE FROM core.transactions WHERE left(transaction_id, 20) IN (SELECT 'KHP-' ||"
            f" upper(left(replace(transfer_id::text, '-', ''), 16)) {made})",
            (started, ME, OTHER),
        )
        pg.execute(f"DELETE {made}", (started, ME, OTHER))


def balance(pg, product_id: str) -> float:
    return float(
        pg.execute(
            "SELECT current_balance FROM core.products WHERE product_id = %s", (product_id,)
        ).fetchone()[0]
    )


async def proposed(kind: str, amount: float, limits: Limits = LIMITS, **arguments) -> str:
    result = await propose(ledger, limits, ME, kind, amount, **arguments)
    assert result["status"] == "proposed", result
    return result["confirmation"]["transfer_id"]


async def test_between_own_accounts_moves_once_even_when_confirmed_twice(db):
    anchor = db.execute("SELECT max(transaction_date) FROM core.transactions").fetchone()[0]
    asked = await propose(ledger, LIMITS, ME, "own_accounts", 100)
    assert asked["missing"] == "origin" and [o["last4"] for o in asked["options"]] == [
        "0011",
        "0022",
    ]
    transfer_id = await proposed("own_accounts", 100, from_last4="0011")
    assert balance(db, SAVINGS) == 25_000  # a proposal moves nothing

    first = await execute(ledger, LIMITS, ME, transfer_id)
    again = await execute(ledger, LIMITS, ME, transfer_id)
    assert first == again and first["status"] == "executed"
    assert first["receipt"]["origin"] == {
        "product_type": "Cuenta Ahorro",
        "last4": "0011",
        "new_balance": 24_900.0,
    }
    assert (balance(db, SAVINGS), balance(db, CHECKING)) == (24_900, 8_100)
    movements = db.execute(
        "SELECT product_id, transaction_type, amount, transaction_date, transaction_status,"
        " response_code, channel FROM core.transactions WHERE transaction_id LIKE %s"
        " ORDER BY transaction_id",
        (f"KHP-{transfer_id.replace('-', '')[:16].upper()}-%",),
    ).fetchall()
    assert [(m[0], m[1], float(m[2])) for m in movements] == [
        (CHECKING, "Deposit", 100.0),
        (SAVINGS, "Transfer", 100.0),
    ]
    # Dated at the dataset's last moment: the agent's "last 30 days" windows do not move.
    assert {m[3:] for m in movements} == {(anchor, "Approved", "00", "App")}


async def test_paying_a_card_or_a_loan_lowers_the_debt(db):
    card = await proposed("pay_debt", 300, from_last4="0022", to_last4="5454")
    loan = await proposed("pay_debt", 1000, from_last4="0022", to_last4="6767")
    assert (await execute(ledger, LIMITS, ME, card))["status"] == "executed"
    receipt = (await execute(ledger, LIMITS, ME, loan))["receipt"]
    assert receipt["origin"]["new_balance"] == 6_700.0
    assert (balance(db, CARD), balance(db, LOAN)) == (4_000, 41_000)
    card_from_savings = {"from_last4": "0011", "to_last4": "5454"}
    too_much = await propose(ledger, LIMITS, ME, "pay_debt", 4_500, **card_from_savings)
    assert (too_much["reason"], too_much["response_code"]) == ("over_debt", "13")


async def test_another_customer_by_account_number_or_by_id(db):
    by_number = await propose(
        ledger, LIMITS, ME, "third_party", 200, from_last4="0011", to_account_number="4000000033"
    )
    assert by_number["confirmation"]["destination"] == {"name": "Renata V.", "last4": "0033"}
    by_id = await propose(
        ledger, LIMITS, ME, "third_party", 50, from_last4="0011", to_customer_id=OTHER.lower()
    )
    assert by_id["confirmation"]["destination"] == {"name": "Renata V."}  # the MXN one, by code
    for result in (by_number, by_id):
        done = await execute(ledger, LIMITS, ME, result["confirmation"]["transfer_id"])
        assert done["status"] == "executed"
    assert (balance(db, SAVINGS), balance(db, f"{OTHER}-AHORRO")) == (24_750, 1_250)
    assert balance(db, f"{OTHER}-USD") == 150

    usd = await propose(
        ledger, LIMITS, ME, "third_party", 10, from_last4="0011", to_account_number="4000000044"
    )
    card_number = await propose(
        ledger, LIMITS, ME, "third_party", 10, from_last4="0011", to_account_number="5454"
    )
    assert (usd["reason"], card_number["reason"]) == ("currency_mismatch", "recipient_not_found")


async def test_limits_to_other_customers_per_operation_and_per_day(db):
    already = await ledger.sent_today_usd(ME)  # what the demo sent today counts too
    tight = Limits(per_operation_usd=60, per_day_usd=already + 100)  # 1,000 MXN is about USD 55
    send = {"from_last4": "0011", "to_customer_id": OTHER}
    over = await propose(ledger, tight, ME, "third_party", 2_000, **send)
    assert (over["reason"], over["response_code"]) == ("over_operation_limit", "61")
    first = await proposed("third_party", 1_000, tight, **send)
    second = await proposed("third_party", 1_000, tight, **send)  # proposed before the first ran
    assert (await execute(ledger, tight, ME, first))["status"] == "executed"
    assert (await propose(ledger, tight, ME, "third_party", 1_000, **send))["reason"] == (
        "over_daily_limit"
    )
    late = await execute(ledger, tight, ME, second)  # the limit is checked again on confirming
    assert (late["status"], late["reason"]) == ("blocked", "over_daily_limit")
    assert balance(db, SAVINGS) == 24_000


async def test_a_balance_that_changed_since_the_proposal_blocks_the_confirmation(db):
    everything = await proposed("own_accounts", 8_000, from_last4="0022")
    some = await proposed("own_accounts", 500, from_last4="0022")
    assert (await execute(ledger, LIMITS, ME, some))["status"] == "executed"
    late = await execute(ledger, LIMITS, ME, everything)
    assert (late["status"], late["reason"], late["response_code"]) == (
        "blocked",
        "insufficient_funds",
        "51",
    )
    assert (await execute(ledger, LIMITS, ME, everything))["status"] == "blocked"  # for good
    assert (balance(db, CHECKING), balance(db, SAVINGS)) == (7_500, 25_500)


async def test_expired_cancelled_and_someone_elses_proposals_never_execute(db):
    expired = await proposed("own_accounts", 10, from_last4="0011")
    db.execute(
        "UPDATE ops.transfers SET expires_at = now() - interval '1 second' WHERE transfer_id = %s",
        (expired,),
    )
    assert await execute(ledger, LIMITS, ME, expired) == {"status": "expired"}

    cancelled = await proposed("own_accounts", 10, from_last4="0011")
    assert await cancel(ledger, OTHER, cancelled) == {"status": "not_found"}
    assert await cancel(ledger, ME, cancelled) == {"status": "cancelled"}
    assert await execute(ledger, LIMITS, ME, cancelled) == {"status": "cancelled"}

    mine = await proposed("own_accounts", 10, from_last4="0011")
    assert await execute(ledger, LIMITS, OTHER, mine) == {"status": "not_found"}
    assert balance(db, SAVINGS) == 25_000


async def test_a_dispute_scenario_customer_can_pay_their_card_without_being_asked_which(db):
    scenario = "DEMO-MX-DUPLICATE"  # one savings account and one card: nothing to ask
    result = await propose(ledger, LIMITS, scenario, "pay_debt", 100)
    try:
        assert result["status"] == "proposed", result
        assert result["confirmation"]["origin"] == {
            "product_type": "Cuenta Ahorro",
            "last4": "0001",
        }
        assert result["confirmation"]["currency"] == "MXN"
    finally:
        db.execute("DELETE FROM ops.transfers WHERE customer_id = %s", (scenario,))


async def test_paying_a_service_bill_once_lowers_the_balance_and_marks_it_paid(db):
    listed = (await service_bills(ledger, ME))["bills"]
    assert [b["service"] for b in listed] == ["internet", "cable", "luz"]  # the one due first
    asked = await propose_service_payment(ledger, ME, "luz")
    assert asked["missing"] == "origin"
    ready = await propose_service_payment(ledger, ME, "luz", from_last4="0022")
    confirmation = ready["confirmation"]
    assert (confirmation["amount"], confirmation["destination"]["name"]) == (
        630.0,
        "Servicios Públicos Luz",
    )
    transfer_id = confirmation["transfer_id"]
    assert balance(db, CHECKING) == 8_000  # a proposal pays nothing

    first = await execute(ledger, LIMITS, ME, transfer_id)
    again = await execute(ledger, LIMITS, ME, transfer_id)
    assert first == again and first["receipt"]["origin"]["new_balance"] == 7_370.0
    assert balance(db, CHECKING) == 7_370
    assert [b["service"] for b in (await service_bills(ledger, ME))["bills"]] == [
        "internet",
        "cable",
    ]
    movements = db.execute(
        "SELECT product_id, transaction_type, transaction_category, merchant_name, amount"
        " FROM core.transactions WHERE transaction_id LIKE %s",
        (f"KHP-{transfer_id.replace('-', '')[:16].upper()}-%",),
    ).fetchall()
    assert [(*m[:4], float(m[4])) for m in movements] == [
        (CHECKING, "Payment", "Services", "Servicios Públicos Luz", 630.0)
    ]
    assert (await propose_service_payment(ledger, ME, "luz"))["reason"] == "nothing_to_pay"


async def test_a_bill_paid_since_the_proposal_blocks_the_second_confirmation(db):
    pay = {"service": "cable", "from_last4": "0011"}
    one = (await propose_service_payment(ledger, ME, **pay))["confirmation"]["transfer_id"]
    two = (await propose_service_payment(ledger, ME, **pay))["confirmation"]["transfer_id"]
    assert (await execute(ledger, LIMITS, ME, one))["status"] == "executed"
    late = await execute(ledger, LIMITS, ME, two)
    assert (late["status"], late["reason"]) == ("blocked", "already_paid")
    assert balance(db, SAVINGS) == 25_000 - 387
    assert (await execute(ledger, LIMITS, OTHER, one))["status"] == "not_found"
