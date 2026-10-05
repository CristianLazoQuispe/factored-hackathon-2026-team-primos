"""The receipt of a transfer, by e-mail, after the money has moved.

It runs once the answer to the Confirmar button is on its way (a background task of the
response). It is not part of the transfer: it opens no transaction and moves nothing, and
whatever happens here, the transfer and its answer are what they were. It uses the mail of
the actions (the outbox, the demo inboxes, the mode), so it exists only where they do.
"""

import logging
from typing import Any

from app.adapters.outbound.postgres.accounts import find_customer
from app.adapters.outbound.postgres.actions import build_gateway
from app.config import get_settings
from app.domain.email_content import language_of, transfer_receipt_content

log = logging.getLogger(__name__)


async def email_the_receipt(customer_id: str, receipt: dict[str, Any]) -> None:
    """Send the receipt of an executed transfer. Never raises. A second confirmation of the same
    transfer asks again, and the outbox, which knows the transfer by its id, sends nothing twice."""
    if not get_settings().actions_enabled:
        return
    try:
        who = await find_customer(customer_id) or {}
        content = transfer_receipt_content(
            language_of(who.get("preferred_language")), receipt, who.get("first_name") or ""
        )
        await build_gateway().send_receipt(customer_id, receipt["transfer_id"], content)
    except Exception:
        log.exception("the receipt of a transfer could not be e-mailed")
