"""Khipear: the rules, the proposal (with its clarifying questions) and the MCP tools, with a fake
ledger."""

from datetime import UTC, datetime

import pytest

from app.adapters.inbound.mcp import transfers as server
from app.application.transfers import execute, propose, transfer_options
from app.domain.transfers import Limits, check, choose, recipient_name, said

pytestmark = pytest.mark.anyio

LIMITS = Limits(per_operation_usd=1000, per_day_usd=3000)


def product(product_id, product_type, last4, balance, currency="MXN", status="Active", owner="C1"):
    return {
        "product_id": product_id,
        "customer_id": owner,
        "product_type": product_type,
        "product_number_last4": last4,
        "currency": currency,
        "current_balance": balance,
        "product_status": status,
    }


SAVINGS = product("P-SAV", "Cuenta Ahorro", "1111", 5000.0)
CHECKING = product("P-CHK", "Cuenta Corriente", "2222", 800.0)
CARD = product("P-CARD", "Tarjeta Crédito", "3333", 1200.0)
LOAN = product("P-LOAN", "Préstamo Personal", "4444", 9000.0)
ANA = product("P-ANA", "Cuenta Ahorro", "9999", 10.0, owner="C2") | {
    "first_name": "Ana",
    "last_name": "Souza Lima",
    "customer_status": "Active",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeLedger:
    def __init__(self, own, others=(), rate=0.05, sent=0.0):
        self.own, self.others, self.rate, self.sent = list(own), list(others), rate, sent
        self.saved = []

    async def products(self, customer_id):
        return self.own

    async def account_by_number(self, account_number):
        return next((a for a in self.others if a.get("account_number") == account_number), None)

    async def accounts_of(self, customer_id):
        return [a for a in self.others if a["customer_id"] == customer_id]

    async def usd_rate(self, currency):
        return self.rate

    async def sent_today_usd(self, customer_id):
        return self.sent

    async def save(self, proposal):
        self.saved.append(proposal)
        return datetime(2026, 10, 5, 12, 5, tzinfo=UTC)


def test_a_lone_candidate_needs_no_question_and_last4_must_match_exactly_one():
    assert choose([SAVINGS], None) is SAVINGS
    assert choose([SAVINGS, CHECKING], None) is None
    assert choose([SAVINGS, CHECKING], "2222") is CHECKING
    assert choose([SAVINGS, CHECKING], "0000") is None
    assert choose([SAVINGS, SAVINGS | {"product_id": "P-2"}], "1111") is None


def test_a_product_counts_as_said_only_when_the_customers_words_name_it():
    assert said("khipea 300 desde la 0022 a mi tarjeta", last4="0022")
    assert not said("khipea 300 a mi tarjeta", last4="0300")  # 300 is the amount
    assert said("paga mi tarjeta", product_type="Tarjeta Crédito")
    assert said("da minha poupança", product_type="Cuenta Ahorro")
    assert not said("khipea 300 a mi tarjeta", product_type="Cuenta Ahorro")
    assert not said("khipea 300", product_type="Seguro")


def test_the_recipient_is_shown_by_first_name_and_last_initial_only():
    assert recipient_name("Ana", "Souza Lima") == "Ana S."
    assert recipient_name("Ana", None) == "Ana"
    assert recipient_name(None, None) == "Cliente"


@pytest.mark.parametrize(
    ("kind", "origin", "destination", "amount", "reason", "code"),
    [
        ("own_accounts", SAVINGS, CHECKING, 0, "invalid_amount", "13"),
        ("own_accounts", SAVINGS, CHECKING, 10.005, "invalid_amount", "13"),
        ("own_accounts", SAVINGS, CHECKING, 5000.01, "insufficient_funds", "51"),
        (
            "own_accounts",
            SAVINGS | {"product_status": "Blocked"},
            CHECKING,
            1,
            "origin_unavailable",
            "57",
        ),
        ("own_accounts", CARD, CHECKING, 1, "origin_unavailable", "57"),
        (
            "own_accounts",
            SAVINGS | {"customer_status": "Suspended"},
            CHECKING,
            1,
            "origin_unavailable",
            "57",
        ),
        ("own_accounts", SAVINGS, SAVINGS, 1, "same_account", "14"),
        ("own_accounts", SAVINGS, CHECKING | {"currency": "USD"}, 1, "currency_mismatch", "57"),
        ("own_accounts", SAVINGS, ANA, 1, "destination_unavailable", "14"),
        ("pay_debt", SAVINGS, CARD, 1200.01, "over_debt", "13"),
        ("pay_debt", SAVINGS, CARD | {"current_balance": 0.0}, 1, "nothing_to_pay", "14"),
        ("third_party", SAVINGS, CHECKING, 1, "own_account", "14"),
        (
            "third_party",
            SAVINGS,
            ANA | {"customer_status": "Closed"},
            1,
            "destination_unavailable",
            "14",
        ),
        (
            "third_party",
            SAVINGS,
            ANA | {"product_status": "Closed"},
            1,
            "destination_unavailable",
            "14",
        ),
    ],
)
def test_what_is_refused_and_with_which_response_code(
    kind, origin, destination, amount, reason, code
):
    block = check(kind, origin, destination, amount, amount * 0.05, 0.0, LIMITS)
    assert (block.reason, block.code) == (reason, code)


def test_limits_apply_to_other_customers_only_and_fail_closed_without_a_rate():
    rich = SAVINGS | {"current_balance": 10_000_000.0}
    assert check("third_party", rich, ANA, 100.0, 1000.0, 0.0, LIMITS) is None
    assert (
        check("third_party", rich, ANA, 100.0, 1000.01, 0.0, LIMITS).reason
        == "over_operation_limit"
    )
    assert (
        check("third_party", rich, ANA, 100.0, 500.0, 2500.01, LIMITS).reason == "over_daily_limit"
    )
    assert check("third_party", rich, ANA, 100.0, None, 0.0, LIMITS).reason == "limit_unknown"
    assert check("own_accounts", rich, CHECKING, 100.0, 999_999.0, 0.0, LIMITS) is None
    assert (
        check("pay_debt", SAVINGS, LOAN | {"product_status": "Suspended"}, 50.0, 2.5, 0, LIMITS)
        is None
    )


async def test_one_account_and_one_debt_are_proposed_without_asking():
    ledger = FakeLedger([SAVINGS, CARD])
    result = await propose(ledger, LIMITS, "C1", "pay_debt", 300)
    assert result["status"] == "proposed"
    assert result["confirmation"] | {"transfer_id": "x"} == {
        "transfer_id": "x",
        "kind": "pay_debt",
        "origin": {"product_type": "Cuenta Ahorro", "last4": "1111"},
        "destination": {"product_type": "Tarjeta Crédito", "last4": "3333"},
        "amount": 300.0,
        "currency": "MXN",
        "expires_at": "2026-10-05T12:05:00+00:00",
    }
    saved = ledger.saved[0]
    assert (saved["customer_id"], saved["origin_product_id"], saved["destination_product_id"]) == (
        "C1",
        "P-SAV",
        "P-CARD",
    )
    assert saved["amount_usd"] == 15.0 and saved["destination_customer_id"] == "C1"


async def test_several_accounts_get_a_question_with_the_options_and_nothing_is_stored():
    ledger = FakeLedger([SAVINGS, CHECKING, CARD, LOAN])
    asked = await propose(ledger, LIMITS, "C1", "pay_debt", 300)
    assert (asked["status"], asked["missing"]) == ("needs_clarification", "origin")
    assert asked["options"] == [
        {"product_type": "Cuenta Ahorro", "last4": "1111", "currency": "MXN", "balance": 5000.0},
        {"product_type": "Cuenta Corriente", "last4": "2222", "currency": "MXN", "balance": 800.0},
    ]
    asked = await propose(ledger, LIMITS, "C1", "pay_debt", 300, from_last4="1111")
    assert asked["missing"] == "destination"
    assert [o["last4"] for o in asked["options"]] == ["3333", "4444"]
    assert asked["options"][0]["debt"] == 1200.0
    assert ledger.saved == []
    named = await propose(
        ledger,
        LIMITS,
        "C1",
        "pay_debt",
        300,
        from_type="Cuenta Corriente",
        to_type="Tarjeta Crédito",
    )  # "paga mi tarjeta desde mi cuenta corriente": one of each, so no question
    assert named["confirmation"]["origin"]["last4"] == "2222"
    assert named["confirmation"]["destination"]["last4"] == "3333"
    done = await propose(ledger, LIMITS, "C1", "pay_debt", 300, from_last4="1111", to_last4="4444")
    assert done["status"] == "proposed" and done["confirmation"]["destination"]["last4"] == "4444"


async def test_the_destination_decides_the_kind_not_the_label_the_model_chose():
    ledger = FakeLedger([SAVINGS, CARD, LOAN], [ANA])
    card = await propose(ledger, LIMITS, "C1", "own_accounts", 300, to_type="Tarjeta Crédito")
    loan = await propose(ledger, LIMITS, "C1", "own_accounts", 300, to_last4="4444")
    other = await propose(ledger, LIMITS, "C1", "pay_debt", 300, to_customer_id="C2")
    assert [r["confirmation"]["kind"] for r in (card, loan, other)] == [
        "pay_debt",
        "pay_debt",
        "third_party",
    ]


async def test_between_two_own_accounts_naming_one_side_settles_the_other():
    ledger = FakeLedger([SAVINGS, CHECKING])
    assert (await propose(ledger, LIMITS, "C1", "own_accounts", 50))["missing"] == "origin"
    to_checking = await propose(ledger, LIMITS, "C1", "own_accounts", 50, to_last4="2222")
    assert to_checking["confirmation"]["origin"]["last4"] == "1111"
    from_checking = await propose(ledger, LIMITS, "C1", "own_accounts", 50, from_last4="2222")
    assert from_checking["confirmation"]["destination"]["last4"] == "1111"
    alone = await propose(FakeLedger([SAVINGS]), LIMITS, "C1", "own_accounts", 50)
    assert (alone["status"], alone["reason"]) == ("blocked", "no_other_account")


async def test_another_customer_by_id_or_by_account_number_never_shows_their_data():
    ana_usd = ANA | {"product_id": "P-ANA-USD", "currency": "USD", "account_number": "7000000002"}
    ledger = FakeLedger([SAVINGS], [ana_usd, ANA | {"account_number": "7000000001"}])
    by_id = await propose(ledger, LIMITS, "C1", "third_party", 200, to_customer_id="c2")
    assert by_id["confirmation"]["destination"] == {"name": "Ana S."}
    assert ledger.saved[0]["destination_product_id"] == "P-ANA"  # the one in the sender's currency
    by_number = await propose(
        ledger, LIMITS, "C1", "third_party", 200, to_account_number="7000000001"
    )
    assert by_number["confirmation"]["destination"] == {"name": "Ana S.", "last4": "9999"}
    assert "balance" not in str(by_id) and "7000000001" not in str(by_number)

    neither = await propose(ledger, LIMITS, "C1", "third_party", 200)
    assert (neither["status"], neither["missing"], neither["options"]) == (
        "needs_clarification",
        "destination",
        [],
    )
    for arguments, reason in [
        ({"to_customer_id": "C9"}, "recipient_not_found"),
        ({"to_account_number": "123"}, "recipient_not_found"),
        ({"to_customer_id": "C1"}, "own_account"),
        ({"to_account_number": "7000000002"}, "currency_mismatch"),
    ]:
        blocked = await propose(ledger, LIMITS, "C1", "third_party", 200, **arguments)
        assert (blocked["status"], blocked["reason"]) == ("blocked", reason), arguments
    only_usd = FakeLedger([SAVINGS], [ana_usd])
    blocked = await propose(only_usd, LIMITS, "C1", "third_party", 200, to_customer_id="C2")
    assert blocked["reason"] == "currency_mismatch"


async def test_a_blocked_proposal_says_why_with_the_response_code_and_stores_nothing():
    ledger = FakeLedger([SAVINGS, CARD])
    blocked = await propose(ledger, LIMITS, "C1", "pay_debt", 6000)
    assert blocked == {
        "status": "blocked",
        "reason": "insufficient_funds",
        "response_code": "51",
        "detail": "The account has 5000.00 MXN.",
    }
    assert ledger.saved == []
    none = await propose(FakeLedger([CARD]), LIMITS, "C1", "pay_debt", 10)
    assert none["reason"] == "no_source_account"


async def test_confirming_checks_the_rules_again_with_what_the_ledger_locked():
    class Ledger(FakeLedger):
        async def execute(self, transfer_id, customer_id, recheck):
            transfer = {"kind": "own_accounts", "amount": 900.0, "amount_usd": 45.0}
            block = recheck(transfer, CHECKING, SAVINGS, 0.0)  # only 800 left since the proposal
            return {"status": "blocked", "block": block}

    result = await execute(Ledger([]), LIMITS, "C1", "T1")
    assert (result["status"], result["reason"], result["response_code"]) == (
        "blocked",
        "insufficient_funds",
        "51",
    )


async def test_options_list_only_what_can_send_and_what_can_be_paid():
    closed = SAVINGS | {"product_id": "P-OLD", "product_status": "Closed"}
    options = await transfer_options(FakeLedger([SAVINGS, closed, CARD, LOAN]), "C1")
    assert [a["last4"] for a in options["accounts"]] == ["1111"]
    assert [d["last4"] for d in options["debts"]] == ["3333", "4444"]


@pytest.fixture
def bank(monkeypatch):
    ledger, audit = FakeLedger([SAVINGS, CHECKING, CARD]), []

    async def record(tool, proposed, decision, reason, executed):
        audit.append((tool, proposed["customer_id"], decision, reason, executed))

    monkeypatch.setattr(server, "ledger", ledger)
    monkeypatch.setattr(server, "record_decision", record)
    return ledger, audit


async def test_tools_take_no_customer_cannot_execute_and_audit_every_outcome(bank):
    from fastmcp import Client

    ledger, audit = bank
    me = {"customer_id": "C1"}
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools} == {"list_transfer_options", "propose_transfer"}
        for tool in tools:
            assert "customer_id" not in tool.input_schema["properties"], tool.name
        pay = {"kind": "pay_debt", "amount": 100}
        assert (await client.call_tool("propose_transfer", pay, raise_on_error=False)).is_error
        asked = await client.call_tool("propose_transfer", pay, meta=me)
        proposed = await client.call_tool("propose_transfer", pay | {"from_last4": "1111"}, meta=me)
        blocked = await client.call_tool(
            "propose_transfer", pay | {"from_last4": "2222", "amount": 900}, meta=me
        )
        await client.call_tool("list_transfer_options", {}, meta=me)
        heard = {"customer_id": "C1", "said": "khipea 100 a mi tarjeta"}
        guess = pay | {"from_last4": "1111", "to_type": "Tarjeta Crédito"}  # 1111 was never said
        guessed = await client.call_tool("propose_transfer", guess, meta=heard)
    assert guessed.structured_content["missing"] == "origin"
    assert asked.structured_content["status"] == "needs_clarification"
    assert proposed.structured_content["confirmation"]["amount"] == 100.0
    assert blocked.structured_content["response_code"] == "51"
    assert len(ledger.saved) == 1
    assert [(tool, decision, executed) for tool, _, decision, _, executed in audit] == [
        ("propose_transfer", "allowed", False),  # a question: nothing was proposed yet
        ("propose_transfer", "needs_confirmation", False),
        ("propose_transfer", "blocked", False),
        ("list_transfer_options", "allowed", True),
        ("propose_transfer", "allowed", False),
    ]
    assert {customer for _, customer, *_ in audit} == {"C1"}
