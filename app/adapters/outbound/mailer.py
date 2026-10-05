"""Outgoing email, in one of two modes.

`simulated` (the default) sends nothing: the message is only stored in `ops.outbox`. `smtp` sends
through a real server, but only to the closed list of demo inboxes in DEMO_INBOXES: the customers'
own addresses are synthetic and never receive anything. Whatever the mode, "accepted" means the
server took the message, not that it reached a person.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from functools import cache
from typing import Protocol

from app.adapters.outbound.email_template import compose
from app.application.actions import EmailDraft, PermanentError, TransientError
from app.config import Settings, get_settings
from app.domain.action_text import mask_email

log = logging.getLogger(__name__)
SMTP_TIMEOUT_SECONDS = 15
TEMPORARY_REPLY_CODES = range(400, 500)


class Mailer(Protocol):
    mode: str

    def choices(self) -> list[str]: ...
    def resolve(self, choice: str | None) -> str | None: ...
    def send(self, draft: EmailDraft, to: str | None) -> str: ...


class _Inboxes:
    """The closed list of demo inboxes, offered masked and resolved back to the real address."""

    def __init__(self, addresses: list[str]):
        self._by_mask = {mask_email(a): a for a in addresses if mask_email(a)}
        if len(self._by_mask) != len(addresses):
            raise ValueError("DEMO_INBOXES has two addresses that look the same once masked.")

    def choices(self) -> list[str]:
        return list(self._by_mask)

    def resolve(self, choice: str | None) -> str | None:
        if not self._by_mask:
            return None
        if choice is None:
            return next(iter(self._by_mask.values()))
        if choice not in self._by_mask:
            log.warning("a demo inbox outside the list was asked for")
            raise PermanentError("send_failed")
        return self._by_mask[choice]


class SimulatedMailer(_Inboxes):
    mode = "simulated"

    def send(self, draft: EmailDraft, to: str | None) -> str:
        return "simulated: nothing was sent"


class SmtpMailer(_Inboxes):
    mode = "smtp"

    def __init__(self, settings: Settings):
        super().__init__(settings.demo_inbox_list)
        self.host, self.port = settings.smtp_host, settings.smtp_port
        self.user, self.password, self.sender = (
            settings.smtp_user,
            settings.smtp_password,
            settings.mail_from,
        )

    def _message(self, draft: EmailDraft, to: str) -> EmailMessage:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self.sender, to, draft.subject
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid(domain=self.sender.rpartition("@")[2] or "localhost")
        message["Auto-Submitted"] = "auto-generated"
        message["X-Demo-Data"] = "synthetic"
        message.set_content(draft.body)  # this clears every Content-* header, so it goes first
        self._add_page(message, draft)
        message["Content-Language"] = draft.language
        return message

    @staticmethod
    def _add_page(message: EmailMessage, draft: EmailDraft) -> None:
        """The HTML part, with the logo attached, for a message that has structured content.
        If the page cannot be made the message still goes as plain text: a receipt is never lost
        to a design."""
        if draft.content is None:
            return
        try:
            page = compose.html_for(draft.content)
            logo = compose.logo_png()
        except Exception:  # noqa: BLE001 - any failure of the template leaves the plain text, which is complete
            log.exception("the HTML of a message could not be made: it goes as plain text")
            return
        message.add_alternative(page, subtype="html")
        message.get_payload()[1].add_related(logo, "image", "png", cid=f"<{compose.LOGO_CID}>")

    def send(self, draft: EmailDraft, to: str | None) -> str:
        if not to:
            raise PermanentError("send_failed")
        message = self._message(draft, to)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(self.user, self.password)
                refused = server.send_message(message)
        except smtplib.SMTPResponseException as error:
            log.warning("smtp replied %s", error.smtp_code)
            if error.smtp_code in TEMPORARY_REPLY_CODES:
                raise TransientError(f"smtp {error.smtp_code}") from error
            raise PermanentError("send_failed") from error
        except smtplib.SMTPServerDisconnected as error:
            raise TransientError("disconnected") from error
        except smtplib.SMTPException as error:
            # Recipients refused and the like: asking again cannot help. This must come before
            # `except OSError`, because SMTPException is an OSError.
            raise PermanentError("send_failed") from error
        except OSError as error:  # no route, refused connection, timeout
            raise TransientError(type(error).__name__) from error
        if refused:
            raise PermanentError("send_failed")
        return f"smtp accepted by {self.host} for {mask_email(to)}"


@cache
def get_mailer() -> Mailer:
    settings = get_settings()
    if settings.mail_mode == "smtp":
        return SmtpMailer(settings)
    return SimulatedMailer(settings.demo_inbox_list)
