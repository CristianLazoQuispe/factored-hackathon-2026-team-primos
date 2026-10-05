# ruff: noqa: E501  (SQL statements and fixture rows stay on one line each, so they read as the table they set up)
"""The Postgres side of the actions against a real database. Each test builds its own customer in
`core` and removes it (and everything the actions wrote for it) afterwards, so no demo customer is
touched. Skipped unless Postgres is up with the ops tables (`make demo-data`, or
`psql -f app/adapters/outbound/postgres/migrations/001_actions.sql`)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from app.adapters.outbound import postgres
from app.adapters.outbound.mailer import SimulatedMailer
from app.adapters.outbound.postgres import actions as pg
from app.application.actions import (
    ActionGateway,
    CaseDraft,
    EmailDraft,
    PermanentError,
    TransientError,
)
from app.config import get_settings
from app.domain.actions import AWAITING, CONFIRMED, ActionRecord
from tests.actions_support import MemoryStore

pytestmark = pytest.mark.anyio
ROOT = Path(__file__).resolve().parents[1] / "app/adapters/outbound/postgres"
OPS_TABLES = ("actions", "outbox", "preferences", "card_actions", "handoff_cases", "disputes")


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


class Bank:
    """A customer of its own, with a card for each rule, and a neighbour whose things are off limits."""

    def __init__(self) -> None:
        tag = uuid.uuid4().hex[:8]
        self.id, self.other = f"TEST-ACT-{tag}", f"TEST-OTH-{tag}"
        self.p = {
            k: f"{self.id}-{k}"
            for k in ("credit", "debit", "closed", "suspended", "pastdue", "zero", "savings")
        }
        self.other_card, self.other_tx = f"{self.other}-card", f"{self.other}-tx"
        with psycopg.connect(get_settings().database_url) as conn:
            self.as_of = conn.execute(
                "SELECT max(transaction_date)::date FROM core.transactions"
            ).fetchone()[0]
        self.t = {
            k: f"{self.id}-{k}"
            for k in ("uber1", "uber2", "fraud", "reversed", "declined", "pend_new", "pend_old")
        }

    def create(self) -> None:
        def day(n: int, **kw: int) -> datetime:
            midnight = datetime.combine(self.as_of - timedelta(days=n), datetime.min.time())
            return midnight + timedelta(**kw)

        with psycopg.connect(get_settings().database_url) as conn:
            for cid, mail in ((self.id, "test.actions@demo.bank"), (self.other, "other@demo.bank")):
                conn.execute(
                    "INSERT INTO core.customers (customer_id, country, email, first_name) VALUES (%s,'México',%s,'Prueba')",
                    (cid, mail),
                )
            cards = [
                ("credit", "Tarjeta Crédito", "2951", 8100, "Active", 0), ("debit", "Tarjeta Débito", "0042", 500, "Active", 0),
                ("closed", "Tarjeta Crédito", "0001", 0, "Closed", 0), ("suspended", "Tarjeta Débito", "0002", 0, "Suspended", 0),
                ("pastdue", "Tarjeta Crédito", "0003", 1000, "Active", 12), ("zero", "Tarjeta Crédito", "0004", 0, "Active", 0),
                ("savings", "Cuenta Ahorro", "0005", 900, "Active", 0),
            ]  # fmt: skip
            for key, kind, last4, balance, status, late in cards:
                conn.execute(
                    "INSERT INTO core.products (product_id, customer_id, product_type, product_number_last4, currency, "
                    "current_balance, credit_limit, product_status, days_past_due) VALUES (%s,%s,%s,%s,'MXN',%s,27000,%s,%s)",
                    (self.p[key], self.id, kind, last4, balance, status, late),
                )
            conn.execute(
                "INSERT INTO core.products (product_id, customer_id, product_type, product_number_last4, currency, current_balance, product_status) VALUES (%s,%s,'Tarjeta Crédito','9999','MXN',50,'Active')",
                (self.other_card, self.other),
            )
            conn.execute(
                "INSERT INTO core.billing (product_id, customer_id, as_of, statement_date, due_date, minimum_payment, past_due_amount) "
                "VALUES (%s,%s,%s,%s,%s,450,0)",
                (
                    self.p["credit"],
                    self.id,
                    self.as_of,
                    self.as_of - timedelta(days=26),
                    self.as_of + timedelta(days=4),
                ),
            )
            txs = [
                ("uber1", "Approved", "Uber Trip", 312.40, "México", False, 5, day(7)),
                ("uber2", "Approved", "Uber Trip", 312.40, "México", False, 5, day(7, seconds=4)),
                ("fraud", "Approved", "Tienda X", 999.00, "Rusia", True, 91, day(2)),
                ("reversed", "Reversed", "Cine", 80.00, "México", False, 5, day(9)),
                ("declined", "Declined", "Hotel", 4000.00, "México", False, 5, day(8)),
                ("pend_new", "Pending", "Gasolinera", 600.00, "México", False, 5, day(1)),
                ("pend_old", "Pending", "Gasolinera", 700.00, "México", False, 5, day(6)),
            ]  # fmt: skip
            for key, status, merchant, amount, country, fraud, score, when in txs:
                conn.execute(
                    "INSERT INTO core.transactions (transaction_id, customer_id, product_id, transaction_date, transaction_type, "
                    "amount, currency, merchant_name, transaction_country, transaction_status, is_fraud, fraud_score) "
                    "VALUES (%s,%s,%s,%s,'Purchase',%s,'MXN',%s,%s,%s,%s,%s)",
                    (
                        self.t[key],
                        self.id,
                        self.p["credit"],
                        when,
                        amount,
                        merchant,
                        country,
                        status,
                        fraud,
                        score,
                    ),
                )
            conn.execute(
                "INSERT INTO core.transactions (transaction_id, customer_id, transaction_date, amount, currency, transaction_status) "
                "VALUES (%s,%s,%s,10,'MXN','Approved')", (self.other_tx, self.other, day(3)),
            )  # fmt: skip

    def drop(self) -> None:
        with psycopg.connect(get_settings().database_url) as conn:
            for cid in (self.id, self.other):
                for table in OPS_TABLES:
                    conn.execute(f"DELETE FROM ops.{table} WHERE customer_id = %s", (cid,))
                for table in ("billing", "transactions", "products", "customers"):
                    conn.execute(f"DELETE FROM core.{table} WHERE customer_id = %s", (cid,))


@pytest.fixture
def bank():
    b = Bank()
    b.create()
    try:
        yield b
    finally:
        b.drop()


class CountingMailer(SimulatedMailer):
    def __init__(self) -> None:
        super().__init__(["jccamascah@gmail.com", "otra.persona@gmail.com"])
        self.sent: list[EmailDraft] = []
        self.fail: Exception | None = None

    def send(self, draft: EmailDraft, to: str | None) -> str:
        if self.fail:
            raise self.fail
        self.sent.append(draft)
        return super().send(draft, to)


@pytest.fixture
def mailer() -> CountingMailer:
    return CountingMailer()


@pytest.fixture
def gateway(mailer: CountingMailer) -> ActionGateway:
    return ActionGateway(
        store=pg.PostgresStore(), facts=pg.PostgresFacts(), effects=pg.PostgresEffects(mailer),
        sleep=lambda _: asyncio.sleep(0),
    )  # fmt: skip


def asked(action: str, **params) -> dict:
    return {"action": action, "params": params}


# ---------------------------------------------------------------- facts


async def test_card_facts_come_from_the_bank_and_only_for_its_owner(bank: Bank):
    facts = pg.PostgresFacts()
    card = await facts.card(bank.id, bank.p["credit"])
    assert (card.product_type, card.last4, card.status, card.balance) == (
        "Tarjeta Crédito",
        "2951",
        "Active",
        8100.0,
    )
    assert not card.frozen_by_customer
    assert await facts.card(bank.id, bank.other_card) is None, "a neighbour's card is not found"
    assert await facts.card(bank.other, bank.p["credit"]) is None
    assert await facts.card(bank.id, "no-such-card") is None


async def test_transaction_facts_carry_the_signals(bank: Bank):
    facts = pg.PostgresFacts()
    twin = await facts.transaction(bank.id, bank.t["uber1"])
    assert (
        twin.duplicates == 1 and twin.merchant == "Uber Trip" and twin.customer_country == "México"
    )
    assert twin.as_of == bank.as_of
    fraud = await facts.transaction(bank.id, bank.t["fraud"])
    assert (
        fraud.is_fraud
        and fraud.fraud_score == 91.0
        and fraud.country == "Rusia"
        and fraud.duplicates == 0
    )
    assert (await facts.transaction(bank.id, bank.t["reversed"])).status == "Reversed"
    assert await facts.transaction(bank.id, bank.other_tx) is None, (
        "a neighbour's charge is not found"
    )


async def test_contact_products_and_billing(bank: Bank):
    facts = pg.PostgresFacts()
    assert await facts.email_masked(bank.id) == "t***@demo.bank"
    assert await facts.email_masked("nobody") is None
    kinds = {p["last4"]: p["product_type"] for p in await facts.products(bank.id)}
    assert kinds["2951"] == "Tarjeta Crédito" and "0001" not in kinds, "closed cards are not listed"
    (due,) = await facts.billing(bank.id)
    assert due["last4"] == "2951" and due["minimum_payment"] == 450.0


# ---------------------------------------------------------------- effects


async def test_blocking_and_cancelling_lay_over_the_banks_status(bank: Bank):
    effects, facts = pg.PostgresEffects(SimulatedMailer([])), pg.PostgresFacts()
    freeze = str(uuid.uuid4())
    await effects.card_control(bank.id, bank.p["debit"], "freeze", freeze)
    await effects.card_control(bank.id, bank.p["debit"], "freeze", freeze)  # again: still one row
    card = await facts.card(bank.id, bank.p["debit"])
    assert (card.status, card.frozen_by_customer) == ("Blocked", True)
    assert await effects.card_status(bank.id, bank.p["debit"]) == "Blocked"
    await effects.confirm_card(freeze)
    with psycopg.connect(get_settings().database_url) as conn:
        rows = conn.execute(
            "SELECT verified_at FROM ops.card_actions WHERE product_id = %s", (bank.p["debit"],)
        ).fetchall()
    assert len(rows) == 1 and rows[0][0] is not None
    await effects.card_control(bank.id, bank.p["debit"], "cancel", str(uuid.uuid4()))
    assert (await facts.card(bank.id, bank.p["debit"])).status == "Cancelled"
    assert bank.p["debit"] not in [p.get("product_id") for p in await facts.products(bank.id)]


async def test_a_card_that_is_not_yours_cannot_be_blocked_even_by_mistake(bank: Bank):
    effects = pg.PostgresEffects(SimulatedMailer([]))
    await effects.card_control(bank.id, bank.other_card, "freeze", str(uuid.uuid4()))
    assert (await pg.PostgresFacts().card(bank.other, bank.other_card)).status == "Active"
    with psycopg.connect(get_settings().database_url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM ops.card_actions WHERE product_id = %s", (bank.other_card,)
            ).fetchone()[0]
            == 0
        )


async def test_a_case_is_one_dispute_and_one_handoff_however_often_it_is_opened(bank: Bank):
    effects = pg.PostgresEffects(SimulatedMailer([]))
    draft = CaseDraft(
        str(uuid.uuid4()),
        bank.id,
        "payment_inquiry",
        "Medium",
        ["duplicate_charge"],
        datetime.now(UTC) + timedelta(hours=24),
        {"request": "payment_inquiry"},
        bank.t["uber1"],
    )
    assert await effects.open_case(draft) == await effects.open_case(draft) == draft.case_id
    stored = await effects.read_case(bank.id, draft.case_id)
    assert (stored["status"], stored["priority"], stored["reason_codes"]) == (
        "open",
        "Medium",
        ["duplicate_charge"],
    )
    assert await effects.read_case(bank.other, draft.case_id) is None
    with psycopg.connect(get_settings().database_url) as conn:
        counts = [
            conn.execute(
                f"SELECT count(*) FROM ops.{t} WHERE customer_id = %s", (bank.id,)
            ).fetchone()[0]
            for t in ("disputes", "handoff_cases")
        ]
        ref = conn.execute(
            "SELECT tracking_token FROM ops.disputes WHERE dispute_id = %s", (draft.case_id,)
        ).fetchone()[0]
    assert counts == [1, 1] and ref.startswith("Q-")
    callback = CaseDraft(
        str(uuid.uuid4()),
        bank.id,
        "callback",
        "Low",
        ["callback_requested"],
        datetime.now(UTC),
        {"request": "callback"},
    )
    await effects.open_case(callback)
    with psycopg.connect(get_settings().database_url) as conn:
        assert (
            conn.execute(
                "SELECT dispute_id FROM ops.handoff_cases WHERE case_id = %s", (callback.case_id,)
            ).fetchone()[0]
            is None
        )


async def test_preferences_are_upserted_and_read_back(bank: Bank):
    effects = pg.PostgresEffects(SimulatedMailer([]))
    assert await effects.get_preference(bank.id, "alert.duplicate_charge") is None
    await effects.set_preference(bank.id, "alert.duplicate_charge", True)
    assert await effects.get_preference(bank.id, "alert.duplicate_charge") is True
    await effects.set_preference(bank.id, "alert.duplicate_charge", False)
    assert await effects.get_preference(bank.id, "alert.duplicate_charge") is False
    assert await effects.get_preference(bank.other, "alert.duplicate_charge") is None


def draft(bank: Bank, action_id: str | None = None) -> EmailDraft:
    return EmailDraft(
        bank.id,
        action_id or str(uuid.uuid4()),
        "balances",
        "es",
        "Resumen",
        "Hola,\n\nsaldos",
        "t***@demo.bank",
    )


async def test_a_message_is_stored_masked_and_sent_once_per_action(
    bank: Bank, mailer: CountingMailer
):
    effects, action_id = pg.PostgresEffects(mailer), str(uuid.uuid4())
    first = await effects.send_email(draft(bank, action_id), "o***@gmail.com")
    again = await effects.send_email(draft(bank, action_id), "o***@gmail.com")
    assert first.message_id == again.message_id and len(mailer.sent) == 1
    assert (first.status, first.mode, first.delivered_to) == (
        "accepted",
        "simulated",
        "o***@gmail.com",
    )
    assert await effects.message_status(bank.id, first.message_id) == "accepted"
    assert await effects.message_status(bank.other, first.message_id) is None, (
        "not another customer's message"
    )
    (mine,) = await pg.recent_messages(bank.id)
    assert (
        mine["destination"] == "t***@demo.bank"
        and "otra.persona" not in str(mine)
        and mine["status"] == "accepted"
    )
    assert await pg.recent_messages(bank.other) == []


async def test_failures_are_recorded_honestly(bank: Bank, mailer: CountingMailer):
    effects = pg.PostgresEffects(mailer)
    mailer.fail = TransientError("busy")
    action_id = str(uuid.uuid4())
    for _ in range(2):
        with pytest.raises(TransientError):
            await effects.send_email(draft(bank, action_id), None)
    with psycopg.connect(get_settings().database_url) as conn:
        status, attempts = conn.execute(
            "SELECT status, attempts FROM ops.outbox WHERE action_id = %s", (action_id,)
        ).fetchone()
    assert (status, attempts) == ("queued", 2)
    mailer.fail = PermanentError("send_failed")
    with pytest.raises(PermanentError):
        await effects.send_email(draft(bank, action_id), None)
    mine = await pg.recent_messages(bank.id)
    assert [m["status"] for m in mine] == ["failed"]
    with pytest.raises(PermanentError):
        await effects.send_email(
            draft(bank), "not-in-the-list@evil.test"
        )  # never reaches the mailer
    assert mailer.sent == []


async def test_decisions_are_audited_with_their_verification(bank: Bank):
    tool, conversation = f"test_{uuid.uuid4().hex[:8]}", str(uuid.uuid4())
    await pg.audit_action(
        tool=tool,
        proposed={"k": 1},
        verdict="needs_confirmation",
        reason=None,
        executed=True,
        verified=True,
        conversation_id=conversation,
    )
    await pg.audit_action(
        tool=tool + "x",
        proposed={},
        verdict="blocked",
        reason="not_found",
        executed=False,
        verified=False,
        conversation_id="not-a-uuid",
    )
    with psycopg.connect(get_settings().database_url) as conn:
        rows = conn.execute(
            "SELECT tool, policy_decision, executed, verified, conversation_id::text FROM ops.decision_log WHERE tool IN (%s, %s) ORDER BY tool",
            (tool, tool + "x"),
        ).fetchall()
        conn.execute("DELETE FROM ops.decision_log WHERE tool IN (%s, %s)", (tool, tool + "x"))
    assert rows == [
        (tool, "needs_confirmation", True, True, conversation),
        (tool + "x", "blocked", False, False, None),
    ]


# ---------------------------------------------------------------- the store keeps the same promises as the memory one


def records(
    customer: str, *, n: int = 2, ttl: timedelta = timedelta(minutes=10)
) -> list[ActionRecord]:
    batch, now = str(uuid.uuid4()), datetime.now(UTC)
    return [
        ActionRecord(
            action_id=str(uuid.uuid4()), batch_id=batch, position=i, customer_id=customer, conversation_id=None,
            action="set_alert", params={"kind": "payment_due", "enabled": True}, view={"strong": False},
            decision="needs_confirmation", reason=None, status=AWAITING, language="es",
            idempotency_key=f"{batch}:{i}", created_at=now, expires_at=now + ttl,
        )
        for i in range(n)
    ]  # fmt: skip


@pytest.fixture(params=["memory", "postgres"])
def store(request, bank: Bank):
    return MemoryStore() if request.param == "memory" else pg.PostgresStore()


async def test_store_contract_ownership_order_and_single_claim(store, bank: Bank):
    rows = records(bank.id, n=3)
    await store.insert(rows[::-1])
    mine = await store.batch(rows[0].batch_id, bank.id)
    assert [r.position for r in mine] == [0, 1, 2] and mine[0].params == {
        "kind": "payment_due",
        "enabled": True,
    }
    assert await store.batch(rows[0].batch_id, bank.other) == []
    assert await store.batch("not-a-uuid", bank.id) == []
    now = datetime.now(UTC)
    assert await store.claim(rows[0].batch_id, bank.other, now) == 0, "someone else cannot claim it"
    assert await store.claim(rows[0].batch_id, bank.id, now) == 3
    assert await store.claim(rows[0].batch_id, bank.id, now) == 0, "the second claim wins nothing"
    assert {r.status for r in await store.batch(rows[0].batch_id, bank.id)} == {CONFIRMED}


async def test_store_contract_expiry_cancel_and_marks(store, bank: Bank):
    late = records(bank.id, n=1, ttl=timedelta(minutes=-1))
    await store.insert(late)
    assert await store.claim(late[0].batch_id, bank.id, datetime.now(UTC)) == 0, (
        "an expired batch cannot be claimed"
    )
    assert await store.expire(late[0].batch_id, bank.id, datetime.now(UTC)) == 1
    assert (await store.batch(late[0].batch_id, bank.id))[0].status == "expired"
    live = records(bank.id, n=1)
    await store.insert(live)
    assert await store.cancel(live[0].batch_id, bank.other) == 0
    assert await store.cancel(live[0].batch_id, bank.id) == 1
    assert await store.cancel(live[0].batch_id, bank.id) == 0, (
        "only a waiting batch can be cancelled"
    )
    one = records(bank.id, n=1)
    await store.insert(one)
    action = one[0].action_id
    await store.mark(action, "executing", attempts=1)
    await store.mark(
        action, "failed", reason="temporary_error", attempts=3, finished_at=datetime.now(UTC)
    )
    failed = (await store.batch(one[0].batch_id, bank.id))[0]
    assert (failed.status, failed.reason, failed.attempts) == (
        "failed",
        "temporary_error",
        3,
    ) and failed.finished_at
    await store.mark(action, "verified", result={"ok": True})
    done = (await store.batch(one[0].batch_id, bank.id))[0]
    assert (done.status, done.reason, done.result) == ("verified", None, {"ok": True}), (
        "success clears the reason"
    )


async def test_store_contract_a_newer_proposal_replaces_only_the_ones_waiting_in_its_own_chat(
    store, bank: Bank
):
    chat, other_chat = f"{bank.id}:chat", f"{bank.id}:other"
    old, elsewhere, newest = records(bank.id, n=1), records(bank.id, n=1), records(bank.id, n=1)
    old[0].conversation_id = newest[0].conversation_id = chat
    elsewhere[0].conversation_id = other_chat
    await store.insert(old + elsewhere + newest)
    assert await store.supersede(bank.other, chat, newest[0].batch_id) == 0, "not someone else's"
    assert await store.supersede(bank.id, chat, newest[0].batch_id) == 1
    assert await store.supersede(bank.id, chat, newest[0].batch_id) == 0, "nothing left to replace"
    replaced = (await store.batch(old[0].batch_id, bank.id))[0]
    assert (replaced.status, replaced.reason) == ("cancelled", "superseded")
    for kept in (elsewhere, newest):
        assert (await store.batch(kept[0].batch_id, bank.id))[0].status == AWAITING


# ---------------------------------------------------------------- the whole cycle on real tables


async def test_the_full_cycle_on_real_tables(
    bank: Bank, gateway: ActionGateway, mailer: CountingMailer
):
    asks = [
        asked("open_payment_inquiry", transaction_id=bank.t["uber1"]),
        asked("block_card", product_id=bank.p["credit"]),
        asked("send_summary_email", topic="case_receipt"),
    ]
    view = await gateway.propose(bank.id, asks, language="es")
    assert view["needs_confirmation"] and mailer.sent == []
    done = await gateway.confirm(bank.id, view["batch_id"], inbox="o***@gmail.com")
    assert [i["status"] for i in done["items"]] == ["verified"] * 3
    assert await gateway.confirm(bank.id, view["batch_id"]) == done, (
        "confirming again changes nothing"
    )
    assert (await pg.PostgresFacts().card(bank.id, bank.p["credit"])).status == "Blocked"
    (message,) = await pg.recent_messages(bank.id)
    assert (
        message["subject"].startswith("Recibimos tu consulta Q-") and "Uber Trip" in message["body"]
    )
    assert message["delivered_to"] == "o***@gmail.com" and len(mailer.sent) == 1
    with psycopg.connect(get_settings().database_url) as conn:
        priority, flags = conn.execute(
            "SELECT priority, reason_codes FROM ops.handoff_cases WHERE customer_id = %s",
            (bank.id,),
        ).fetchone()
        verified_at = conn.execute(
            "SELECT verified_at FROM ops.card_actions WHERE product_id = %s", (bank.p["credit"],)
        ).fetchone()[0]
    assert (priority, flags) == ("Medium", ["duplicate_charge"]) and verified_at is not None


@pytest.mark.parametrize(
    ("ask", "status", "why"),
    [
        (("block_card", "closed"), "refused", "card_closed"),
        (("block_card", "suspended"), "escalated", "card_suspended"),
        (("block_card", "savings"), "refused", "not_a_card"),
        (("cancel_card", "credit"), "escalated", "outstanding_balance"),
        (("cancel_card", "pastdue"), "escalated", "past_due"),
        (("cancel_card", "zero"), "awaiting_confirmation", None),
        (("cancel_card", "debit"), "awaiting_confirmation", None),
    ],
)
async def test_card_rules_on_real_data(
    bank: Bank, gateway: ActionGateway, ask: tuple, status: str, why: str | None
):
    action, card = ask
    view = await gateway.propose(bank.id, [asked(action, product_id=bank.p[card])], language="es")
    assert view["items"][0]["status"] == status
    (stored,) = await pg.PostgresStore().batch(view["batch_id"], bank.id)
    assert stored.reason == why


@pytest.mark.parametrize(
    ("tx", "status", "why", "priority"),
    [
        ("uber1", "awaiting_confirmation", None, "Medium"),
        ("fraud", "awaiting_confirmation", None, "High"),
        ("reversed", "refused", "already_reversed", None),
        ("declined", "refused", "was_declined", None),
        ("pend_new", "refused", "still_pending", None),
        ("pend_old", "awaiting_confirmation", None, "Low"),
    ],
)
async def test_inquiry_rules_on_real_data(
    bank: Bank, gateway: ActionGateway, tx: str, status: str, why: str | None, priority: str | None
):
    view = await gateway.propose(
        bank.id, [asked("open_payment_inquiry", transaction_id=bank.t[tx])], language="es"
    )
    assert view["items"][0]["status"] == status
    (stored,) = await pg.PostgresStore().batch(view["batch_id"], bank.id)
    assert stored.reason == why
    if priority:  # a refused inquiry opens no case, so its priority is not part of the promise
        assert stored.view["priority"] == priority


async def test_a_neighbours_charge_and_card_are_not_found(bank: Bank, gateway: ActionGateway):
    asks = [
        asked("open_payment_inquiry", transaction_id=bank.other_tx),
        asked("block_card", product_id=bank.other_card),
    ]
    view = await gateway.propose(bank.id, asks, language="es")
    assert [i["status"] for i in view["items"]] == ["refused", "refused"]
    assert (await pg.PostgresFacts().card(bank.other, bank.other_card)).status == "Active"


async def test_two_confirmations_at_once_run_the_batch_once(bank: Bank, gateway: ActionGateway):
    view = await gateway.propose(
        bank.id, [asked("block_card", product_id=bank.p["debit"])], language="es"
    )
    results = await asyncio.gather(*(gateway.confirm(bank.id, view["batch_id"]) for _ in range(5)))
    assert all(r["items"][0]["status"] in ("verified", "confirmed", "executing") for r in results)
    with psycopg.connect(get_settings().database_url) as conn:
        rows = conn.execute(
            "SELECT count(*) FROM ops.card_actions WHERE product_id = %s", (bank.p["debit"],)
        ).fetchone()[0]
    assert rows == 1, "five requests, one card action"
    final = await gateway.view(bank.id, view["batch_id"])
    assert final["items"][0]["status"] == "verified"


async def test_a_mail_failure_on_real_tables_is_reported_not_hidden(
    bank: Bank, gateway: ActionGateway, mailer: CountingMailer
):
    mailer.fail = PermanentError("send_failed")
    asks = [
        asked("open_payment_inquiry", transaction_id=bank.t["uber1"]),
        asked("send_summary_email", topic="case_receipt"),
    ]
    view = await gateway.propose(bank.id, asks, language="es")
    done = await gateway.confirm(bank.id, view["batch_id"])
    assert [i["status"] for i in done["items"]] == ["verified", "failed"]
    assert "El correo no salió" in done["items"][1]["text"]


# ---------------------------------------------------------------- the migration and the schema agree


def test_the_migration_is_exactly_the_block_in_schema_sql():
    schema = (ROOT / "schema.sql").read_text()
    block = (
        schema.split("-- BEGIN actions migration\n", 1)[1]
        .split("-- END actions migration", 1)[0]
        .strip()
    )
    migration = (ROOT / "migrations/001_actions.sql").read_text()
    assert migration.endswith(block + "\n"), "migrations/001_actions.sql drifted from schema.sql"
