"""The action gateway end to end, with in-memory ports: what runs, what is refused, what fails."""

import pytest

from app.application.actions import NotFound
from tests.actions_support import World, card, tx

pytestmark = pytest.mark.anyio

BLOCK = {"action": "block_card", "params": {"product_id": "CARD-1"}}
INQUIRY = {"action": "open_payment_inquiry", "params": {"transaction_id": "T1"}}
RECEIPT = {"action": "send_summary_email", "params": {"topic": "case_receipt"}}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def w() -> World:
    return World()


def statuses(view: dict) -> list[str]:
    return [item["status"] for item in view["items"]]


def reasons(w: World, view: dict) -> list[str | None]:
    return [r.reason for r in w.store.rows.values() if r.batch_id == view["batch_id"]]


# ---------------------------------------------------------------- the normal path


async def test_blocking_a_card_waits_for_the_customer_and_runs_once_confirmed(w: World):
    view = await w.gateway.propose("C1", [BLOCK], language="es")
    assert view["needs_confirmation"] and statuses(view) == ["awaiting_confirmation"]
    assert (
        "Bloquear temporalmente tu tarjeta de crédito terminada en 2951" in view["items"][0]["text"]
    )
    assert w.effects.calls == [], "nothing may run before the customer confirms"

    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["verified"] and not done["needs_confirmation"]
    assert w.effects.calls[0] == ("card_control", "C1", "CARD-1", "freeze")
    assert [c[0] for c in w.effects.calls] == ["card_control", "confirm_card"], (
        "verified, then noted"
    )
    assert "quedó bloqueada" in done["items"][0]["text"]
    assert w.facts.cards[("C1", "CARD-1")].status == "Blocked"


async def test_confirming_twice_runs_the_batch_once(w: World):
    view = await w.gateway.propose("C1", [BLOCK], language="es")
    first = await w.gateway.confirm("C1", view["batch_id"])
    second = await w.gateway.confirm("C1", view["batch_id"])
    assert first == second
    assert [c[0] for c in w.effects.calls] == ["card_control", "confirm_card"]


async def test_a_batch_runs_in_order_and_the_receipt_describes_the_case(w: World):
    view = await w.gateway.propose("C1", [INQUIRY, BLOCK, RECEIPT], language="es")
    assert statuses(view) == ["awaiting_confirmation"] * 3, "an allowed item rides with the batch"
    done = await w.gateway.confirm("C1", view["batch_id"], inbox="a@demo.test")
    assert statuses(done) == ["verified"] * 3
    ran = [c[0] for c in w.effects.calls if c[0] != "confirm_card"]
    assert ran == ["open_case", "card_control", "send_email"]
    mail = w.effects.sent[0]
    assert "Q-" in mail.subject and "Uber Trip" in mail.body and "312.40" in mail.body
    assert w.effects.inboxes_used == ["a@demo.test"]


async def test_an_email_that_needs_no_confirmation_runs_at_once(w: World):
    w.facts.product_rows["C1"] = [
        {
            "product_type": "Cuenta Ahorro",
            "last4": "1111",
            "balance": 500.0,
            "currency": "MXN",
            "limit": None,
        }
    ]
    view = await w.gateway.propose(
        "C1", [{"action": "send_summary_email", "params": {"topic": "balances"}}], language="es"
    )
    assert statuses(view) == ["verified"] and not view["needs_confirmation"]
    assert "aceptó tu mensaje para c***@demo.bank" in view["items"][0]["text"]


async def test_portuguese_gets_portuguese_text(w: World):
    view = await w.gateway.propose("C1", [BLOCK], language="pt")
    assert (
        "Bloquear temporariamente o seu cartão de crédito com final 2951"
        in view["items"][0]["text"]
    )
    assert view["confirm_label"] == "Confirmar" and "expira" in view["expires_note"]


async def test_alerts_and_callbacks_are_stored_and_read_back(w: World):
    asks = [
        {"action": "set_alert", "params": {"kind": "duplicate_charge"}},
        {"action": "request_callback", "params": {"window": "morning"}},
    ]
    view = await w.gateway.propose("C1", asks, language="es")
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["verified", "verified"]
    assert w.effects.prefs[("C1", "alert.duplicate_charge")] is True
    assert "Referencia Q-" in done["items"][1]["text"]


# ---------------------------------------------------------------- when it must not act


async def test_another_customers_card_looks_like_a_card_that_does_not_exist(w: World):
    w.facts.cards[("C2", "CARD-2")] = card("CARD-2")
    view = await w.gateway.propose(
        "C1", [{"action": "block_card", "params": {"product_id": "CARD-2"}}], language="es"
    )
    assert statuses(view) == ["refused"] and reasons(w, view) == ["not_found"]
    assert w.effects.calls == []


async def test_someone_elses_batch_cannot_be_confirmed_or_seen(w: World):
    view = await w.gateway.propose("C1", [BLOCK], language="es")
    for call in (w.gateway.confirm, w.gateway.cancel, w.gateway.view):
        with pytest.raises(NotFound):
            await call("C2", view["batch_id"])
    assert w.effects.calls == []


@pytest.mark.parametrize(
    ("setup", "status", "why"),
    [
        (dict(status="Blocked"), "refused", "already_blocked"),
        (dict(status="Closed"), "refused", "card_closed"),
        (dict(status="Suspended"), "escalated", "card_suspended"),
        (dict(product_type="Cuenta Ahorro"), "refused", "not_a_card"),
    ],
)
async def test_block_card_refusals(w: World, setup: dict, status: str, why: str):
    w.facts.cards[("C1", "CARD-1")] = card(**setup)
    view = await w.gateway.propose("C1", [BLOCK], language="es")
    assert statuses(view) == [status] and reasons(w, view) == [why]
    assert w.effects.calls == []


@pytest.mark.parametrize(
    ("setup", "status", "why"),
    [
        (dict(balance=8100.0), "escalated", "outstanding_balance"),
        (dict(days_past_due=12), "escalated", "past_due"),
        (dict(status="Blocked"), "escalated", "blocked_by_bank"),
        (dict(status="Closed"), "refused", "card_closed"),
        (dict(), "awaiting_confirmation", None),
        (dict(product_type="Tarjeta Débito", balance=999.0), "awaiting_confirmation", None),
        (dict(status="Blocked", frozen_by_customer=True), "awaiting_confirmation", None),
    ],
)
async def test_cancel_card_rules_come_from_the_data(
    w: World, setup: dict, status: str, why: str | None
):
    w.facts.cards[("C1", "CARD-1")] = card(**setup)
    ask = {"action": "cancel_card", "params": {"product_id": "CARD-1"}}
    view = await w.gateway.propose("C1", [ask], language="es")
    assert statuses(view) == [status] and reasons(w, view) == [why]
    assert view["strong"] is (status == "awaiting_confirmation")


async def test_a_cancellation_spells_out_that_it_cannot_be_undone(w: World):
    ask = {"action": "cancel_card", "params": {"product_id": "CARD-1"}}
    view = await w.gateway.propose("C1", [ask], language="es")
    assert view["strong_note"] == "Esta acción no se puede deshacer."
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert w.facts.cards[("C1", "CARD-1")].status == "Cancelled" and statuses(done) == ["verified"]


@pytest.mark.parametrize(
    ("action", "status", "why"),
    [
        ("transfer_money", "refused", "money_movement_not_authorized"),
        ("make_payment", "refused", "money_movement_not_authorized"),
        ("refund", "escalated", "needs_human_approval"),
        ("change_phone", "escalated", "identity_change"),
        ("raise_limit", "escalated", "credit_policy"),
        ("reissue_card", "escalated", "physical_card"),
        ("unblock_card", "escalated", "unfreeze_needs_review"),
        ("delete_everything", "escalated", "unknown_action"),
        ("", "escalated", "unknown_action"),
    ],
)
async def test_what_is_never_automated_is_refused_or_goes_to_a_person(
    w: World, action: str, status: str, why: str
):
    view = await w.gateway.propose(
        "C1", [{"action": action, "params": {"product_id": "CARD-1"}}], language="es"
    )
    assert statuses(view) == [status] and reasons(w, view) == [why]
    assert w.effects.calls == []
    assert bool(view["escalate"]) is (status == "escalated")


@pytest.mark.parametrize(
    "bad",
    [
        {"action": "block_card", "params": {}},
        {"action": "block_card", "params": {"product_id": "CARD-1", "also": "everything"}},
        {"action": "block_card", "params": {"product_id": ""}},
        {"action": "set_alert", "params": {"kind": "something_else"}},
        {"action": "request_callback", "params": {"window": "midnight"}},
        {"action": "block_card", "params": "CARD-1"},
    ],
)
async def test_invalid_parameters_are_refused_not_guessed(w: World, bad: dict):
    view = await w.gateway.propose("C1", [bad], language="es")
    assert statuses(view) == ["refused"] and reasons(w, view) == ["invalid_params"]
    assert w.effects.calls == []


async def test_only_three_actions_per_batch(w: World):
    asks = [{"action": "set_alert", "params": {"kind": "payment_due"}}] * 4
    view = await w.gateway.propose("C1", asks, language="es")
    assert statuses(view) == ["awaiting_confirmation"] * 3 + ["refused"]
    assert reasons(w, view)[3] == "too_many_actions"


@pytest.mark.parametrize(
    ("setup", "why"),
    [
        (dict(status="Reversed"), "already_reversed"),
        (dict(status="Declined"), "was_declined"),
        (dict(status="Pending", age_days=1), "still_pending"),
    ],
)
async def test_a_charge_that_needs_no_case_gets_none(w: World, setup: dict, why: str):
    w.facts.txs[("C1", "T1")] = tx(**setup)
    view = await w.gateway.propose("C1", [INQUIRY], language="es")
    assert statuses(view) == ["refused"] and reasons(w, view) == [why]


async def test_a_charge_pending_for_days_is_worth_a_case(w: World):
    w.facts.txs[("C1", "T1")] = tx(status="Pending", age_days=6)
    view = await w.gateway.propose("C1", [INQUIRY], language="es")
    assert statuses(view) == ["awaiting_confirmation"]


async def test_a_receipt_needs_a_case_in_the_same_batch(w: World):
    view = await w.gateway.propose("C1", [RECEIPT], language="es")
    assert statuses(view) == ["refused"] and reasons(w, view) == ["no_case_to_confirm"]


async def test_no_email_on_file_means_no_email(w: World):
    w.facts.emails["C1"] = None
    view = await w.gateway.propose(
        "C1", [{"action": "send_summary_email", "params": {"topic": "balances"}}], language="es"
    )
    assert statuses(view) == ["refused"] and reasons(w, view) == ["no_contact_on_file"]


async def test_fraud_signals_raise_the_priority_and_the_sla(w: World):
    w.facts.txs[("C1", "T1")] = tx(is_fraud=True, fraud_score=91.0, country="Rusia", duplicates=0)
    view = await w.gateway.propose("C1", [INQUIRY], language="es")
    assert "Prioridad High" in view["items"][0]["text"] and "4 h" in view["items"][0]["text"]
    done = await w.gateway.confirm("C1", view["batch_id"])
    draft = next(iter(w.effects.cases.values()))["draft"]
    assert draft.priority == "High" and "possible_fraud" in draft.reason_codes
    assert any("posible fraude" in q for q in draft.case_file["unresolved"])
    assert statuses(done) == ["verified"]


# ---------------------------------------------------------------- confirmation, expiry, cancel


async def test_an_expired_confirmation_does_nothing(w: World):
    view = await w.gateway.propose("C1", [BLOCK], language="es")
    w.clock.advance(minutes=11)
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["expired"] and "caducó" in done["items"][0]["text"]
    assert w.effects.calls == []


async def test_a_cancelled_batch_cannot_be_confirmed_later(w: World):
    view = await w.gateway.propose("C1", [BLOCK], language="es")
    cancelled = await w.gateway.cancel("C1", view["batch_id"])
    assert statuses(cancelled) == ["cancelled"]
    again = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(again) == ["cancelled"] and w.effects.calls == []


async def test_what_changed_between_proposal_and_confirmation_is_checked_again(w: World):
    view = await w.gateway.propose("C1", [BLOCK], language="es")
    w.facts.cards[("C1", "CARD-1")] = card(status="Blocked")  # the bank blocked it meanwhile
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["refused"] and w.effects.calls == []
    assert "ya está bloqueada" in done["items"][0]["text"]


# ---------------------------------------------------------------- failures, retries, verification


async def test_a_transient_failure_is_retried_a_bounded_number_of_times(w: World):
    w.effects.send_transient_failures = 2
    asks = [INQUIRY, RECEIPT]
    view = await w.gateway.propose("C1", asks, language="es")
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["verified", "verified"]
    assert (
        w.store.rows[
            next(r.action_id for r in w.store.rows.values() if r.action == "send_summary_email")
        ].attempts
        == 3
    )
    assert w.sleeps == [0.2, 0.4]


async def test_when_retries_run_out_it_says_so_and_never_claims_it_sent(w: World):
    w.effects.send_transient_failures = 99
    view = await w.gateway.propose("C1", [INQUIRY, RECEIPT], language="es")
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["verified", "failed"]
    text = done["items"][1]["text"]
    assert "No pude completarlo" in text and "aceptó" not in text
    assert sum(1 for c in w.effects.calls if c[0] == "send_email") == 3


async def test_a_permanent_failure_is_not_retried(w: World):
    w.effects.send_permanent_failure = True
    view = await w.gateway.propose("C1", [INQUIRY, RECEIPT], language="es")
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["verified", "failed"]
    assert sum(1 for c in w.effects.calls if c[0] == "send_email") == 1 and w.sleeps == []
    assert "El correo no salió" in done["items"][1]["text"]


async def test_an_effect_that_cannot_be_read_back_is_not_reported_as_done(w: World):
    w.effects.silent_card = True
    view = await w.gateway.propose("C1", [BLOCK], language="es")
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["failed"] and "bloqueada" not in done["items"][0]["text"]
    assert done["escalate"] == [{"action": "block_card", "reason": "verification_failed"}]


async def test_when_the_case_cannot_be_verified_the_receipt_is_skipped(w: World):
    w.effects.silent_case = True
    view = await w.gateway.propose("C1", [INQUIRY, RECEIPT], language="es")
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["failed", "skipped"] and w.effects.sent == []


async def test_an_email_the_server_took_but_that_cannot_be_found_is_not_reported_as_sent(w: World):
    w.effects.forget_messages = True
    view = await w.gateway.propose("C1", [INQUIRY, RECEIPT], language="es")
    done = await w.gateway.confirm("C1", view["batch_id"])
    assert statuses(done) == ["verified", "failed"]
    assert "aceptó" not in done["items"][1]["text"]
    assert done["escalate"] == [{"action": "send_summary_email", "reason": "verification_failed"}]


async def test_a_database_failure_while_proposing_goes_to_a_person(w: World):
    w.facts.broken = True
    view = await w.gateway.propose("C1", [BLOCK], language="es")
    assert statuses(view) == ["escalated"] and reasons(w, view) == ["temporary_error"]
    assert view["escalate"] and w.effects.calls == []


# ---------------------------------------------------------------- audit


async def test_every_decision_and_outcome_is_audited(w: World):
    view = await w.gateway.propose("C1", [BLOCK, {"action": "refund", "params": {}}], language="es")
    await w.gateway.confirm("C1", view["batch_id"])
    seen = [(r["tool"], r["verdict"], r["executed"], r["verified"]) for r in w.audit.rows]
    assert ("block_card", "needs_confirmation", False, False) in seen
    assert ("refund", "escalated", False, False) in seen
    assert ("block_card", "needs_confirmation", True, True) in seen
