"""Outgoing email: nothing leaves in simulated mode, only the closed list is reachable in smtp."""

import smtplib

import pytest

from app.adapters.outbound import mailer
from app.application.actions import EmailDraft, PermanentError, TransientError
from app.config import Settings

DRAFT = EmailDraft(
    "C1", "A1", "balances", "es", "Resumen de tus saldos", "Hola,\n\nsaldos", "d***@demo.bank"
)
INBOXES = "jccamascah@gmail.com, otra.persona@gmail.com"


def smtp_settings(**override) -> Settings:
    values = dict(
        mail_mode="smtp", smtp_user="quipu@example.test", smtp_password="app-password",
        mail_from="Quipu <quipu@example.test>", demo_inboxes=INBOXES,
    )  # fmt: skip
    return Settings(_env_file=None, **(values | override))


class FakeSMTP:
    """Stands in for smtplib.SMTP and records what the mailer did."""

    log: list[tuple] = []
    fail_with: Exception | None = None
    refused: dict = {}

    def __init__(self, host: str, port: int, timeout: float):
        FakeSMTP.log.append(("connect", host, port, timeout))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self, context):
        FakeSMTP.log.append(("starttls",))

    def login(self, user, password):
        FakeSMTP.log.append(("login", user, password))

    def send_message(self, message):
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with
        FakeSMTP.log.append(("send", message))
        return FakeSMTP.refused


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.log, FakeSMTP.fail_with, FakeSMTP.refused = [], None, {}
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)


def test_simulated_mode_never_opens_a_connection():
    box = mailer.SimulatedMailer(["jccamascah@gmail.com"])
    assert box.send(DRAFT, box.resolve(None)).startswith("simulated")
    assert FakeSMTP.log == []


def test_inboxes_are_offered_masked_and_resolve_back():
    box = mailer.SimulatedMailer(["jccamascah@gmail.com", "otra.persona@gmail.com"])
    assert box.choices() == ["j***@gmail.com", "o***@gmail.com"]
    assert box.resolve("o***@gmail.com") == "otra.persona@gmail.com"
    assert box.resolve(None) == "jccamascah@gmail.com"


def test_an_address_outside_the_list_is_refused_not_used():
    box = mailer.SimulatedMailer(["jccamascah@gmail.com"])
    for outsider in ("attacker@evil.test", "jccamascah@gmail.com", "x***@gmail.com"):
        with pytest.raises(PermanentError):
            box.resolve(outsider)  # the real address is never accepted as a choice either


def test_two_inboxes_that_mask_the_same_are_a_configuration_error():
    with pytest.raises(ValueError):
        mailer.SimulatedMailer(["ana@gmail.com", "alba@gmail.com"])


def test_smtp_sends_over_tls_with_login_to_the_chosen_inbox_only():
    box = mailer.SmtpMailer(smtp_settings())
    reply = box.send(DRAFT, box.resolve("o***@gmail.com"))
    assert [step[0] for step in FakeSMTP.log] == ["connect", "starttls", "login", "send"]
    assert FakeSMTP.log[0][1:3] == ("smtp.gmail.com", 587)
    assert FakeSMTP.log[2][1:] == ("quipu@example.test", "app-password")
    message = FakeSMTP.log[3][1]
    assert (
        message["To"] == "otra.persona@gmail.com"
        and message["From"] == "Quipu <quipu@example.test>"
    )
    assert message["Subject"] == "Resumen de tus saldos" and message["Content-Language"] == "es"
    assert message["Auto-Submitted"] == "auto-generated" and message["X-Demo-Data"] == "synthetic"
    assert "saldos" in message.get_content()
    assert "o***@gmail.com" in reply and "otra.persona" not in reply


def test_smtp_without_a_resolved_inbox_sends_nothing():
    with pytest.raises(PermanentError):
        mailer.SmtpMailer(smtp_settings()).send(DRAFT, None)
    assert FakeSMTP.log == []


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (smtplib.SMTPResponseException(451, b"try later"), TransientError),
        (smtplib.SMTPResponseException(421, b"closing"), TransientError),
        (smtplib.SMTPServerDisconnected("gone"), TransientError),
        (TimeoutError("slow"), TransientError),
        (ConnectionRefusedError("no route"), TransientError),
        (smtplib.SMTPAuthenticationError(535, b"bad credentials"), PermanentError),
        (smtplib.SMTPResponseException(550, b"no such user"), PermanentError),
        (smtplib.SMTPRecipientsRefused({"x@y.test": (550, b"no")}), PermanentError),
        (smtplib.SMTPNotSupportedError("no starttls"), PermanentError),
    ],
)
def test_errors_are_split_into_worth_retrying_and_not(error: Exception, kind: type):
    FakeSMTP.fail_with = error
    box = mailer.SmtpMailer(smtp_settings())
    with pytest.raises(kind):
        box.send(DRAFT, box.resolve(None))


def test_a_recipient_the_server_refused_is_a_failure_even_if_nothing_was_raised():
    FakeSMTP.refused = {"jccamascah@gmail.com": (550, b"no")}
    box = mailer.SmtpMailer(smtp_settings())
    with pytest.raises(PermanentError):
        box.send(DRAFT, box.resolve(None))


def test_the_factory_picks_the_mode_from_the_settings(monkeypatch):
    mailer.get_mailer.cache_clear()
    monkeypatch.setattr(mailer, "get_settings", lambda: smtp_settings(mail_mode="simulated"))
    assert mailer.get_mailer().mode == "simulated"
    mailer.get_mailer.cache_clear()
    monkeypatch.setattr(mailer, "get_settings", lambda: smtp_settings())
    assert mailer.get_mailer().mode == "smtp"
    mailer.get_mailer.cache_clear()


@pytest.mark.parametrize("missing", ["smtp_user", "smtp_password", "mail_from", "demo_inboxes"])
def test_a_real_mail_server_will_not_start_without_everything_it_needs(missing: str):
    with pytest.raises(ValueError, match="MAIL_MODE=smtp also needs"):
        smtp_settings(**{missing: ""})


def test_simulated_is_the_default_and_needs_nothing():
    assert Settings(_env_file=None).mail_mode == "simulated"
    assert Settings(_env_file=None).actions_enabled is False
