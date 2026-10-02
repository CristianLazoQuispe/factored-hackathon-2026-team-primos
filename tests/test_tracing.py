"""What leaves for Langfuse is masked: private data is redacted, the rest stays readable."""

import json

import pytest
from langchain_core.messages import HumanMessage

from app.adapters.inbound.agent.tracing import REDACTED, mask


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        ("mi tarjeta es 4111 1111 1111 1111", "mi tarjeta es ****1111"),
        ("tarjeta 4111-1111-1111-1111.", "tarjeta ****1111."),
        ("mi cuenta 00123456789012", "mi cuenta ****9012"),
        ("mi documento es 74697281, gracias", "mi documento es ****7281, gracias"),
        ("llámame al +54 9 35 9223 6351", "llámame al +****6351"),
        ("escríbeme a juan.perez@correo.com.co", "escríbeme a <email>"),
    ],
)
def test_private_data_in_text_is_masked(text, masked):
    assert mask(data=text) == masked


@pytest.mark.parametrize(
    "text",
    [
        "soy CLI-01OSDSMM4FX2 y no reconozco un cargo",
        "el cargo TRX-001D5AGL2PV30VCFF96H de 28034000.50 COP",
        "compra de 1250.50 el 2026-10-02 01:33:00",
        "termina en 4321",
    ],
)
def test_ids_amounts_and_dates_stay_readable(text):
    assert mask(data=text) == text


def test_private_fields_are_redacted_by_key():
    row = {"customer_id": "CLI-01OSDSMM4FX2", "first_name": "Ana", "segment": "Premium"}
    assert mask(data={"rows": [row]}) == {"rows": [row | {"first_name": REDACTED}]}


def test_private_fields_are_redacted_inside_a_tool_result():
    result = json.dumps({"rows": [{"first_name": "Ana", "last_name": "Díaz", "city": "Lima"}]})
    assert json.loads(mask(data=result)) == {
        "rows": [{"first_name": REDACTED, "last_name": REDACTED, "city": "Lima"}]
    }


def test_langchain_messages_are_masked():
    state = {"messages": [HumanMessage("mi tarjeta es 4111 1111 1111 1111")]}
    assert mask(data=state)["messages"][0]["content"] == "mi tarjeta es ****1111"


def test_the_langfuse_client_is_started_with_the_mask(monkeypatch):
    from langfuse import get_client

    from app.adapters.inbound.agent.tracing import callbacks

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test-mask")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test-mask")
    assert callbacks()
    assert get_client(public_key="pk-lf-test-mask")._mask is mask
