# ruff: noqa: E501, F811  (SQL and the sentences stay on one line; pytest fixtures are imported by name)
"""The receipt of a transfer against the real outbox: it goes out once, however many times it is asked
for, and however fast. Each test uses the customer of its own that the SQL tests of the actions build and
remove (so no demo customer is touched), and the mailer that counts what it was given.
Skipped unless Postgres is up with the ops tables."""

import asyncio
import threading
import time
import uuid

import psycopg
import pytest

from app.adapters.outbound.postgres import actions as pg
from app.application.actions import ActionGateway, PermanentError, TransientError
from app.config import get_settings
from app.domain import email_content as ec
from tests.actions_support import MemoryStore
from tests.test_actions_sql import (  # noqa: F401  (fixtures)
    Bank,
    CountingMailer,
    bank,
    mailer,
    need_database,
)
from tests.test_email_connected import real_receipt

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class SlowMailer(CountingMailer):
    """A mail server that takes its time: the window in which a second request could slip in."""

    def send(self, draft, to):
        time.sleep(0.4)
        with threading.Lock():
            return super().send(draft, to)


@pytest.fixture
def gateway(mailer: CountingMailer) -> ActionGateway:
    return ActionGateway(
        store=MemoryStore(), facts=pg.PostgresFacts(), effects=pg.PostgresEffects(mailer)
    )


def rows(key: str) -> list[tuple]:
    with psycopg.connect(get_settings().database_url) as conn:
        return conn.execute(
            "SELECT template, status, attempts, subject, body, language FROM ops.outbox WHERE action_id = %s",
            (key,),
        ).fetchall()


async def content_for(kind: str = "pay_debt") -> ec.EmailContent:
    return ec.transfer_receipt_content("es", await real_receipt(kind))


async def test_a_receipt_is_kept_in_the_outbox_as_what_the_customer_was_sent(
    bank: Bank, gateway, mailer
):
    key = str(uuid.uuid4())
    content = await content_for()
    assert await gateway.send_receipt(bank.id, key, content) is True
    ((template, status, attempts, subject, body, language),) = rows(key)
    assert (template, status, attempts, language) == ("transfer_receipt", "accepted", 1, "es")
    assert (
        subject == content.subject and body == ec.content_text(content) and "Monto pagado" in body
    )
    (tray,) = await pg.recent_messages(bank.id)
    assert (
        tray["subject"] == content.subject
        and tray["status"] == "accepted"
        and tray["destination"] == "t***@demo.bank"
    )
    assert [d.content for d in mailer.sent] == [content], (
        "the mailer was given the structured content, to make the page"
    )


async def test_asking_again_for_the_same_transfer_sends_nothing_more(bank: Bank, gateway, mailer):
    key, content = str(uuid.uuid4()), await content_for()
    assert [await gateway.send_receipt(bank.id, key, content) for _ in range(3)] == [
        True,
        True,
        True,
    ]
    assert len(mailer.sent) == 1 and len(rows(key)) == 1, (
        "one message, however many times the button was pressed"
    )


async def test_two_requests_at_the_same_moment_still_send_one(bank: Bank):
    """The double click: the second arrives while the first is still talking to the mail server."""
    slow = SlowMailer()
    gateway = ActionGateway(
        store=MemoryStore(), facts=pg.PostgresFacts(), effects=pg.PostgresEffects(slow)
    )
    key, content = str(uuid.uuid4()), await content_for()
    results = await asyncio.gather(*(gateway.send_receipt(bank.id, key, content) for _ in range(4)))
    assert results == [True] * 4 and len(slow.sent) == 1 and len(rows(key)) == 1


async def test_two_different_transfers_are_two_messages(bank: Bank, gateway, mailer):
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    await gateway.send_receipt(bank.id, first, await content_for("pay_debt"))
    await gateway.send_receipt(bank.id, second, await content_for("own_accounts"))
    assert len(mailer.sent) == 2 and len(rows(first)) == len(rows(second)) == 1


async def test_a_busy_mail_server_leaves_the_receipt_queued_and_asking_again_sends_it_once(
    bank: Bank, gateway, mailer
):
    key, content = str(uuid.uuid4()), await content_for()
    mailer.fail = TransientError("busy")
    assert await gateway.send_receipt(bank.id, key, content) is False
    assert [(status, attempts) for _, status, attempts, *_ in rows(key)] == [("queued", 1)]
    mailer.fail = None
    assert await gateway.send_receipt(bank.id, key, content) is True
    assert await gateway.send_receipt(bank.id, key, content) is True
    assert [(status, attempts) for _, status, attempts, *_ in rows(key)] == [
        ("accepted", 3)
    ] and len(mailer.sent) == 1


async def test_a_refusal_is_recorded_as_failed_and_is_not_an_error(bank: Bank, gateway, mailer):
    key = str(uuid.uuid4())
    mailer.fail = PermanentError("send_failed")
    assert await gateway.send_receipt(bank.id, key, await content_for()) is False
    assert rows(key)[0][1] == "failed" and mailer.sent == []


async def test_a_customer_with_no_address_leaves_no_trace(bank: Bank, gateway, mailer):
    with psycopg.connect(get_settings().database_url) as conn:
        conn.execute("UPDATE core.customers SET email = NULL WHERE customer_id = %s", (bank.id,))
    key = str(uuid.uuid4())
    assert await gateway.send_receipt(bank.id, key, await content_for()) is False
    assert rows(key) == [] and mailer.sent == []


async def test_the_receipt_of_one_customer_never_reaches_the_tray_of_another(bank: Bank, gateway):
    await gateway.send_receipt(bank.id, str(uuid.uuid4()), await content_for())
    assert (
        len(await pg.recent_messages(bank.id)) == 1 and await pg.recent_messages(bank.other) == []
    )
