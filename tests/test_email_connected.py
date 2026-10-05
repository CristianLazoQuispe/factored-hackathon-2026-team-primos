# ruff: noqa: E501, F811  (the sentences stay on one line; pytest fixtures are imported by name)
"""The template connected: the balances summary and the receipt of a transfer, from the content to the
button that confirms the money.

No mail server and no model. What the messages say, that the HTML and the text carry the same figures,
that a hostile name cannot become markup, that the mailer builds what Gmail needs, that a transfer is
never touched by its receipt, and that every receipt goes out once."""

import html as html_lib
import logging
import re
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound import confirmation_mail, http
from app.adapters.outbound.email_template import compose
from app.adapters.outbound.mailer import SmtpMailer
from app.adapters.outbound.postgres.transfers import _receipt
from app.application.actions import EmailDraft
from app.application.transfers import propose, propose_service_payment
from app.config import Settings, get_settings
from app.domain import email_content as ec
from tests.actions_support import World
from tests.test_khipu_flow import ME, bank  # noqa: F401  (the fixture)
from tests.test_transfers import ANA, CARD, CHECKING, LIGHT, LIMITS, SAVINGS, FakeLedger

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


ACCOUNT = {
    "product_type": "Cuenta Corriente",
    "last4": "1650",
    "balance": 2693.23,
    "currency": "USD",
    "limit": None,
}
SAVING = {
    "product_type": "Cuenta Ahorro",
    "last4": "7788",
    "balance": 100.0,
    "currency": "USD",
    "limit": None,
}
CREDIT = {
    "product_type": "Tarjeta Crédito",
    "last4": "2813",
    "balance": 1976.52,
    "currency": "USD",
    "limit": 35160.64,
}
DEBIT = {
    "product_type": "Tarjeta Débito",
    "last4": "5537",
    "balance": 81.45,
    "currency": "USD",
    "limit": None,
}
LOAN = {
    "product_type": "Préstamo Personal",
    "last4": "9090",
    "balance": 9000.0,
    "currency": "USD",
    "limit": 12000.0,
}


def visible_text(page: str) -> str:
    """What a person reads of an HTML page: tags gone, entities decoded, blanks collapsed."""
    without_style = re.sub(r"<(style|script)\b.*?</\1>", " ", page, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", without_style)))


def rows_of(content: ec.EmailContent) -> list[ec.Row]:
    return [row for section in content.sections for row in section.rows]


# ------------------------------------------------------------------ the content of the balances summary


def test_the_balances_are_grouped_and_every_product_is_in_its_group():
    content = ec.balances_content("es", [CREDIT, ACCOUNT, DEBIT, LOAN, SAVING])
    assert [s.title for s in content.sections] == ["Cuentas", "Tarjetas", "Otros productos"]
    accounts, cards, others = content.sections
    assert [r.label for r in accounts.rows] == ["Cuenta Corriente ·· 1650", "Cuenta Ahorro ·· 7788"]
    assert [r.label for r in cards.rows] == ["Tarjeta Crédito ·· 2813", "Tarjeta Débito ·· 5537"]
    assert [r.label for r in others.rows] == ["Préstamo Personal ·· 9090"]
    assert content.subject == "Tu resumen de saldos · quipu" and content.kind == "balances"


def test_the_limit_is_a_detail_under_the_product_that_has_one_and_only_there():
    content = ec.balances_content("es", [ACCOUNT, CREDIT, DEBIT])
    by_label = {r.label: r for r in rows_of(content)}
    assert by_label["Tarjeta Crédito ·· 2813"].detail == "Límite 35,160.64 USD"
    assert by_label["Tarjeta Crédito ·· 2813"].value == "1,976.52 USD"
    assert (
        by_label["Tarjeta Débito ·· 5537"].detail == ""
        and by_label["Cuenta Corriente ·· 1650"].detail == ""
    )


def test_the_big_figure_is_the_money_in_the_accounts_when_they_share_a_currency():
    content = ec.balances_content("es", [ACCOUNT, SAVING, CREDIT])
    assert (content.highlight_label, content.highlight_value) == (
        "Disponible en tus cuentas",
        "2,793.23 USD",
    )
    assert "2,793.23 USD" in content.preheader


def test_accounts_in_two_currencies_are_never_added_together():
    pesos = ACCOUNT | {"currency": "MXN", "balance": 1000.0}
    content = ec.balances_content("es", [ACCOUNT, pesos])
    assert content.highlight_value == "" and content.highlight_label == ""
    assert {r.value for r in rows_of(content)} == {"2,693.23 USD", "1,000.00 MXN"}, (
        "each one in its own currency"
    )


def test_without_accounts_there_is_no_big_figure_and_without_products_the_message_says_so():
    assert ec.balances_content("es", [CREDIT]).highlight_value == ""
    empty = ec.balances_content("es", [])
    assert empty.sections == () and "No encontramos productos" in empty.intro
    assert ec.content_text(empty).endswith("Mensaje de demostración con datos sintéticos.")


def test_a_missing_last4_or_balance_is_shown_as_unknown_not_as_a_crash():
    odd = {
        "product_type": "Cuenta Corriente",
        "last4": None,
        "balance": None,
        "currency": "USD",
        "limit": None,
    }
    row = rows_of(ec.balances_content("es", [odd]))[0]
    assert row.label == "Cuenta Corriente ·· ????" and row.value == "—"


def test_portuguese_is_written_in_portuguese_and_anything_else_is_spanish():
    pt = ec.balances_content("pt", [ACCOUNT, CREDIT])
    assert pt.subject == "Seu resumo de saldos · quipu" and [s.title for s in pt.sections] == [
        "Contas",
        "Cartões",
    ]
    assert rows_of(pt)[1].detail == "Limite 35,160.64 USD"
    assert ec.content_text(pt).startswith("Olá,")
    assert [ec.language_of(x) for x in ("pt", "es", "en", None, "")] == [
        "pt",
        "es",
        "es",
        "es",
        "es",
    ]


# ------------------------------------------------------------------ the receipt, built from the REAL receipt


async def real_receipt(kind: str) -> dict:
    """The receipt as the bank builds it: the proposal from the real `propose`, the summary as the ledger
    saves it, and the `_receipt` the ledger returns. Nothing here is written by hand."""
    ledger = FakeLedger([SAVINGS, CHECKING, CARD], others=[ANA])
    if kind == "pay_service":
        ledger.bills = [LIGHT]
        proposed = await propose_service_payment(ledger, "C1", service="luz", from_last4="1111")
    else:
        arguments = {
            "own_accounts": dict(
                kind="own_accounts", amount=300, from_last4="1111", to_last4="2222"
            ),
            "pay_debt": dict(kind="pay_debt", amount=300, from_last4="1111", to_last4="3333"),
            "third_party": dict(
                kind="third_party", amount=300, from_last4="1111", to_customer_id="C2"
            ),
        }[kind]
        proposed = await propose(ledger, LIMITS, "C1", **arguments)
    assert proposed["status"] == "proposed", proposed
    saved = ledger.saved[0]
    transfer = {key: saved[key] for key in ("transfer_id", "kind", "amount", "currency")}
    transfer["summary"] = {"origin": saved["origin"], "destination": saved["destination"]}
    return _receipt(transfer, 4700.0, datetime(2026, 10, 5, 10, 52, 7, 123456, tzinfo=UTC))[
        "receipt"
    ]


@pytest.mark.parametrize(
    "kind, title, paid_word",
    [
        ("own_accounts", "Tu transferencia entre cuentas se realizó", "Monto transferido"),
        ("pay_debt", "Tu pago se realizó", "Monto pagado"),
        ("third_party", "Tu transferencia se realizó", "Monto transferido"),
        ("pay_service", "Tu pago de servicio se realizó", "Monto pagado"),
    ],
)
async def test_each_kind_of_operation_is_told_in_its_own_words_from_the_real_receipt(
    kind, title, paid_word
):
    receipt = await real_receipt(kind)
    content = ec.transfer_receipt_content("es", receipt)
    amount = ec.money(receipt["amount"], receipt["currency"])
    assert (
        content.title == title
        and content.highlight_label == paid_word
        and content.highlight_value == amount
    )
    assert (
        amount in content.subject
        and content.subject.endswith("· quipu")
        and content.kind == "transfer_receipt"
    )
    assert content.notice and "quipu" in content.notice, (
        "the line for the one who does not recognise it"
    )
    values = {r.label: r for r in rows_of(content)}
    assert values["Desde"].value == "Cuenta Ahorro ·· 1111"
    assert values["Nuevo saldo de la cuenta de origen"].value == "4,700.00 MXN"
    assert values["Fecha"].value == "2026-10-05 10:52 UTC"
    assert re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}", values["Referencia"].value)


async def test_where_the_money_went_is_shown_the_way_the_customer_knows_it():
    own = {
        r.label: r
        for r in rows_of(ec.transfer_receipt_content("es", await real_receipt("own_accounts")))
    }
    assert own["Hacia"].value == "Cuenta Corriente ·· 2222"
    debt = {
        r.label: r
        for r in rows_of(ec.transfer_receipt_content("es", await real_receipt("pay_debt")))
    }
    assert debt["Hacia"].value == "Tarjeta Crédito ·· 3333"
    other = {
        r.label: r
        for r in rows_of(ec.transfer_receipt_content("es", await real_receipt("third_party")))
    }
    assert other["Hacia"].value.startswith("Ana S"), "a first name and an initial, never a surname"
    assert "Souza" not in other["Hacia"].value and "Lima" not in other["Hacia"].value
    bill = {
        r.label: r
        for r in rows_of(ec.transfer_receipt_content("es", await real_receipt("pay_service")))
    }
    assert (
        bill["Hacia"].value == "Empresa de luz"
        and "00012345" in bill["Hacia"].detail
        and "luz" in bill["Hacia"].detail
    )


async def test_the_reference_is_a_piece_of_the_id_never_all_of_it():
    receipt = await real_receipt("own_accounts")
    reference = ec.reference_of(receipt["transfer_id"])
    assert (
        len(reference) == 9
        and reference.replace("-", "") == receipt["transfer_id"].replace("-", "").upper()[:8]
    )
    assert receipt["transfer_id"].replace("-", "").upper() not in ec.content_text(
        ec.transfer_receipt_content("es", receipt)
    )


@pytest.mark.parametrize(
    "moment, shown",
    [
        ("2026-10-05T10:52:00+00:00", "2026-10-05 10:52 UTC"),
        ("2026-10-05T05:52:00-05:00", "2026-10-05 10:52 UTC"),
        ("2026-10-05T23:30:00-05:00", "2026-10-06 04:30 UTC"),
        ("2026-10-05T10:52:07.123456+00:00", "2026-10-05 10:52 UTC"),
        ("2026-10-05T10:52:00", "2026-10-05 10:52 UTC"),
    ],
)
def test_the_time_is_always_told_in_utc_and_says_so(moment, shown):
    assert ec.when_of(moment) == shown


async def test_without_the_new_balance_there_is_no_row_for_it_and_an_unknown_kind_is_a_transfer():
    receipt = await real_receipt("third_party")
    receipt["origin"] = {k: v for k, v in receipt["origin"].items() if k != "new_balance"}
    content = ec.transfer_receipt_content("es", receipt | {"kind": "something_new"})
    assert "Nuevo saldo de la cuenta de origen" not in {r.label for r in rows_of(content)}
    assert content.title == "Tu transferencia se realizó"


async def test_the_receipt_in_portuguese_and_with_the_name_of_the_customer():
    receipt = await real_receipt("pay_debt")
    content = ec.transfer_receipt_content("pt", receipt, first_name="Ana")
    assert (
        content.title == "Seu pagamento foi realizado" and content.highlight_label == "Valor pago"
    )
    assert {r.label for r in rows_of(content)} >= {"De", "Para", "Data", "Referência"}
    text = ec.content_text(content)
    assert text.startswith("Olá Ana,") and "Mensagem de demonstração" in text


# ------------------------------------------------------------------ the HTML carries what the text carries


async def every_content() -> list[ec.EmailContent]:
    contents = [
        ec.balances_content("es", [ACCOUNT, SAVING, CREDIT, DEBIT, LOAN]),
        ec.balances_content("pt", [ACCOUNT, CREDIT]),
    ]
    for kind in ("own_accounts", "pay_debt", "third_party", "pay_service"):
        contents.append(
            ec.transfer_receipt_content("es", await real_receipt(kind), first_name="Ana")
        )
    return contents


async def test_the_page_and_the_text_carry_every_figure_of_the_content():
    for content in await every_content():
        page, text = visible_text(compose.html_for(content)), ec.content_text(content)
        pieces = [
            content.title,
            content.intro,
            content.highlight_value,
            content.notice,
            *(s.title for s in content.sections),
        ]
        for row in rows_of(content):
            pieces += [row.label, row.value, row.detail]
        for piece in filter(None, pieces):
            assert piece in page, f"{piece!r} is missing from the HTML of {content.kind}"
            assert piece in text or piece.upper() in text, (
                f"{piece!r} is missing from the text of {content.kind}"
            )


async def test_the_page_has_the_logo_by_cid_the_preheader_the_big_figure_and_the_demo_note():
    content = ec.transfer_receipt_content("es", await real_receipt("third_party"), first_name="Ana")
    page = compose.html_for(content)
    assert 'src="cid:quipu-logo"' in page and "http://" not in page.split("<body")[1].replace(
        "http://www.w3.org", ""
    )
    assert content.preheader in page and "Hola Ana" in visible_text(page)
    assert "datos sintéticos" in visible_text(page)


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        "**bold** _italic_ `code`",
        "[click](javascript:alert(1))",
        "![x](http://evil.test/p.png)",
        "<img src=x onerror=alert(1)>",
        "&lt;b&gt; | a pipe | and # a hash",
        "{{ title }} {{ items }}",
        "Ana\n\n## injected heading\n\n- injected row",
    ],
)
async def test_a_hostile_name_or_label_is_only_ever_text(hostile):
    receipt = await real_receipt("third_party")
    receipt["destination"] = {"name": hostile, "last4": "4821"}
    receipt["origin"] = receipt["origin"] | {"product_type": hostile}
    content = ec.transfer_receipt_content("es", receipt, first_name=hostile)
    page = compose.html_for(content)
    lowered = page.lower()
    assert (
        "<script" not in lowered
        and "<img src=x" not in lowered
        and "onerror="
        not in re.sub(r"&[a-z]+;", "", lowered).replace("&lt;", "").replace("&gt;", "")
        or "&lt;" in lowered
    )
    assert 'href="javascript' not in lowered and 'src="http://evil' not in lowered
    assert "injected heading</h" not in lowered and "<li>injected row" not in lowered
    assert visible_text(page).count("{{") == 0 or "{{ title }}" in visible_text(page), (
        "a template word in data is shown, not expanded"
    )
    assert content.title in visible_text(page), "and the message around it is intact"


# ------------------------------------------------------------------ the message the mailer builds


def mailer() -> SmtpMailer:
    settings = Settings(
        _env_file=None,
        demo_inboxes="a@x.test",
        smtp_user="u",
        smtp_password="p",
        mail_from="Quipu <q@x.test>",
    )
    return SmtpMailer(settings)


def draft_of(content: ec.EmailContent | None) -> EmailDraft:
    subject = content.subject if content else "Resumen"
    body = ec.content_text(content) if content else "Hola,\n\nsaldos"
    return EmailDraft("C1", "A1", "balances", "es", subject, body, "d***@demo.bank", content)


def shape(part) -> list[str]:
    return (
        [part.get_content_type(), *(x for sub in part.iter_parts() for x in shape(sub))]
        if part.is_multipart()
        else [part.get_content_type()]
    )


def test_the_message_is_text_and_page_with_the_logo_inside_it():
    content = ec.balances_content("es", [ACCOUNT, CREDIT])
    message = mailer()._message(draft_of(content), "a@x.test")
    assert shape(message) == [
        "multipart/alternative",
        "text/plain",
        "multipart/related",
        "text/html",
        "image/png",
    ]
    parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
    assert parsed["Subject"] == content.subject and parsed["Content-Language"] == "es"
    assert parsed["Auto-Submitted"] == "auto-generated" and parsed["X-Demo-Data"] == "synthetic"
    assert parsed.get_body(("plain",)).get_content().strip() == ec.content_text(content).strip()
    assert "cid:quipu-logo" in parsed.get_body(("html",)).get_content()
    logo = next(p for p in parsed.walk() if p.get_content_type() == "image/png")
    assert logo["Content-ID"] == "<quipu-logo>" and logo.get_content()[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_message_without_content_is_exactly_what_it_always_was():
    message = mailer()._message(draft_of(None), "a@x.test")
    assert shape(message) == ["text/plain"] and message["Content-Language"] == "es"


@pytest.mark.parametrize("broken", ["html_for", "logo_png"])
def test_if_the_page_cannot_be_made_the_message_goes_as_text(monkeypatch, caplog, broken):
    def boom(*_):
        raise RuntimeError("the template is gone")

    monkeypatch.setattr(compose, broken, boom)
    content = ec.balances_content("es", [ACCOUNT])
    with caplog.at_level(logging.ERROR):
        message = mailer()._message(draft_of(content), "a@x.test")
    assert shape(message) == ["text/plain"] and "could not be made" in caplog.text
    assert "2,693.23 USD" in message.get_content(), "and it still carries the figures"


# ------------------------------------------------------------------ the gateway


@pytest.fixture
def w() -> World:
    return World()


async def test_the_balances_summary_sent_by_the_action_carries_the_content(w: World):
    w.facts.product_rows["C1"] = [ACCOUNT, CREDIT]
    view = await w.gateway.propose(
        "C1", [{"action": "send_summary_email", "params": {"topic": "balances"}}], language="es"
    )
    done = (
        await w.gateway.confirm("C1", view["batch_id"], inbox=None)
        if view["batch_id"] and view["items"][0]["status"] == "awaiting_confirmation"
        else view
    )
    assert w.effects.sent, done
    sent = w.effects.sent[0]
    assert (
        sent.content is not None and sent.content.kind == "balances" and sent.template == "balances"
    )
    assert sent.subject == "Tu resumen de saldos · quipu"
    assert (
        "2,693.23 USD" in sent.body
        and "Límite 35,160.64 USD" in sent.body
        and sent.body.endswith("sintéticos.")
    )


async def test_the_other_topics_are_still_the_plain_text_they_were(w: World):
    w.facts.billing_rows["C1"] = []
    view = await w.gateway.propose(
        "C1",
        [{"action": "send_summary_email", "params": {"topic": "payment_status"}}],
        language="es",
    )
    if view["items"][0]["status"] == "awaiting_confirmation":
        await w.gateway.confirm("C1", view["batch_id"], inbox=None)
    assert (
        w.effects.sent
        and w.effects.sent[0].content is None
        and w.effects.sent[0].subject == "Estado de tus pagos"
    )


async def test_a_receipt_goes_out_with_the_id_of_the_transfer_as_its_key(w: World):
    content = ec.transfer_receipt_content("es", await real_receipt("pay_debt"))
    assert (
        await w.gateway.send_receipt("C1", "7f3a91c2-0000-4000-8000-000000000001", content) is True
    )
    sent = w.effects.sent[0]
    assert (sent.customer_id, sent.action_id, sent.template, sent.language) == (
        "C1",
        "7f3a91c2-0000-4000-8000-000000000001",
        "transfer_receipt",
        "es",
    )
    assert (
        sent.to_masked == "c***@demo.bank"
        and sent.content is content
        and "Monto pagado" in sent.body
    )
    assert w.effects.inboxes_used == [None], (
        "the first demo inbox: a receipt asks the customer for nothing"
    )


async def test_a_customer_with_no_address_gets_no_receipt_and_nothing_breaks(w: World):
    w.facts.emails["C1"] = None
    content = ec.transfer_receipt_content("es", await real_receipt("pay_debt"))
    assert await w.gateway.send_receipt("C1", "T1", content) is False and w.effects.sent == []


@pytest.mark.parametrize("failure", ["send_permanent_failure", "send_transient_failures"])
async def test_a_mail_that_fails_is_false_and_not_an_error(w: World, failure, caplog):
    setattr(w.effects, failure, True if failure == "send_permanent_failure" else 1)
    content = ec.transfer_receipt_content("es", await real_receipt("pay_debt"))
    with caplog.at_level(logging.WARNING):
        assert await w.gateway.send_receipt("C1", "T1", content) is False
    assert "was not sent" in caplog.text and w.effects.sent == []
    if failure == "send_transient_failures":
        assert await w.gateway.send_receipt("C1", "T1", content) is True, "asked again, it goes"


# ------------------------------------------------------------------ the module that sends it after the transfer


class Gateway:
    def __init__(self, fail: bool = False):
        self.calls, self.fail = [], fail

    async def send_receipt(self, customer_id, key, content):
        if self.fail:
            raise RuntimeError("the database is down")
        self.calls.append((customer_id, key, content))
        return True


@pytest.fixture
def mail(monkeypatch):
    """The module with a gateway that records, a customer to look up, and the actions switched on."""
    gateway, who = Gateway(), {"preferred_language": "pt", "first_name": "Ana"}

    async def find_customer(customer_id):
        return who

    monkeypatch.setattr(confirmation_mail, "build_gateway", lambda: gateway)
    monkeypatch.setattr(confirmation_mail, "find_customer", find_customer)
    monkeypatch.setattr(get_settings(), "actions_enabled", True)
    return gateway, who


async def test_the_receipt_is_written_in_the_language_of_the_customer_and_with_their_name(mail):
    gateway, _ = mail
    receipt = await real_receipt("pay_debt")
    await confirmation_mail.email_the_receipt("C1", receipt)
    ((customer, key, content),) = gateway.calls
    assert (customer, key) == ("C1", receipt["transfer_id"])
    assert (
        content.language == "pt"
        and content.greeting_name == "Ana"
        and content.title == "Seu pagamento foi realizado"
    )


async def test_a_customer_not_found_or_without_language_gets_spanish_without_a_name(mail):
    gateway, who = mail
    who.clear()
    await confirmation_mail.email_the_receipt("C1", await real_receipt("own_accounts"))
    assert gateway.calls[0][2].language == "es" and gateway.calls[0][2].greeting_name == ""


async def test_with_the_actions_off_nothing_is_even_looked_up(mail, monkeypatch):
    gateway, _ = mail
    monkeypatch.setattr(get_settings(), "actions_enabled", False)
    await confirmation_mail.email_the_receipt("C1", await real_receipt("own_accounts"))
    assert gateway.calls == []


@pytest.mark.parametrize(
    "what", ["the gateway fails", "the receipt is malformed", "the customer lookup fails"]
)
async def test_nothing_that_goes_wrong_here_ever_escapes(mail, monkeypatch, caplog, what):
    gateway, _ = mail
    receipt = await real_receipt("own_accounts")
    if what == "the gateway fails":
        gateway.fail = True
    elif what == "the receipt is malformed":
        receipt = {"transfer_id": "T1"}
    else:

        async def broken(customer_id):
            raise ConnectionError("down")

        monkeypatch.setattr(confirmation_mail, "find_customer", broken)
    with caplog.at_level(logging.ERROR):
        assert await confirmation_mail.email_the_receipt("C1", receipt) is None
    assert "could not be e-mailed" in caplog.text


# ------------------------------------------------------------------ the button: the money is the money


@pytest.fixture
def sent_receipts(monkeypatch):
    seen = []

    async def record(customer_id, receipt):
        seen.append((customer_id, receipt))

    monkeypatch.setattr(http, "email_the_receipt", record)
    return seen


async def test_an_executed_transfer_answers_as_it_always_did_and_sends_its_receipt_afterwards(
    bank, sent_receipts
):
    from app.adapters.inbound.mcp import transfers as server

    ledger, _ = bank
    proposal = await server.propose(ledger, server.limits(), ME, "pay_debt", 300, "1111")
    body = {"transfer_id": proposal["confirmation"]["transfer_id"], "customer_id": ME}
    with TestClient(http.app) as client:
        response = client.post("/api/khipu/confirm", json=body)
    assert response.status_code == 200 and response.headers["content-type"] == "application/json"
    assert response.json() == {
        "status": "executed",
        "receipt": {"transfer_id": body["transfer_id"]},
    }
    assert sent_receipts == [(ME, {"transfer_id": body["transfer_id"]})]


@pytest.mark.parametrize("path", ["cancelled", "not_found", "unknown"])
async def test_nothing_that_is_not_an_executed_transfer_sends_a_receipt(bank, sent_receipts, path):
    from app.adapters.inbound.mcp import transfers as server

    ledger, _ = bank
    proposal = await server.propose(ledger, server.limits(), ME, "pay_debt", 300, "1111")
    body = {"transfer_id": proposal["confirmation"]["transfer_id"], "customer_id": ME}
    with TestClient(http.app) as client:
        if path == "cancelled":
            client.post("/api/khipu/cancel", json=body)
            assert client.post("/api/khipu/confirm", json=body).json() == {"status": "cancelled"}
        elif path == "not_found":
            assert (
                client.post(
                    "/api/khipu/confirm", json=body | {"customer_id": "CLI-OTHER"}
                ).status_code
                == 404
            )
        else:
            assert (
                client.post(
                    "/api/khipu/confirm",
                    json=body | {"transfer_id": "00000000-0000-4000-8000-000000000000"},
                ).status_code
                == 404
            )
    assert sent_receipts == []


async def test_a_blocked_transfer_sends_no_receipt(bank, sent_receipts, monkeypatch):
    ledger, _ = bank

    async def blocked(transfer_id, customer_id, recheck):
        return {"status": "blocked", "reason": "insufficient_funds"}

    monkeypatch.setattr(ledger, "execute", blocked)
    with TestClient(http.app) as client:
        done = client.post(
            "/api/khipu/confirm",
            json={"transfer_id": "00000000-0000-4000-8000-000000000001", "customer_id": ME},
        )
    assert (
        done.json() == {"status": "blocked", "reason": "insufficient_funds"} and sent_receipts == []
    )


async def test_a_confirmation_that_comes_without_a_receipt_is_answered_and_sends_nothing(
    bank, sent_receipts, monkeypatch
):
    """Whatever the ledger says, the answer to the button is never a server error because of the mail."""
    ledger, _ = bank

    async def no_receipt(transfer_id, customer_id, recheck):
        return {"status": "executed"}

    monkeypatch.setattr(ledger, "execute", no_receipt)
    with TestClient(http.app) as client:
        done = client.post(
            "/api/khipu/confirm",
            json={"transfer_id": "00000000-0000-4000-8000-000000000001", "customer_id": ME},
        )
    assert done.status_code == 200 and done.json() == {"status": "executed"} and sent_receipts == []


async def test_with_the_default_settings_the_button_sends_no_mail_at_all(bank, monkeypatch):
    """Actions off, as the tests always start: the real module runs and does nothing."""
    from app.adapters.inbound.mcp import transfers as server

    called = []
    monkeypatch.setattr(confirmation_mail, "build_gateway", lambda: called.append("gateway"))
    ledger, _ = bank
    proposal = await server.propose(ledger, server.limits(), ME, "pay_debt", 300, "1111")
    with TestClient(http.app) as client:
        done = client.post(
            "/api/khipu/confirm",
            json={"transfer_id": proposal["confirmation"]["transfer_id"], "customer_id": ME},
        )
    assert done.json()["status"] == "executed" and called == []
