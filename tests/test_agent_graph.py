"""Routes of the agent graph, with a scripted LLM and the real in-memory MCP server."""

import uuid
from datetime import datetime

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.adapters.inbound.agent import graph
from app.adapters.inbound.mcp import accounts, investigation

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class ScriptedModel(GenericFakeChatModel):
    """Replays AIMessages in order; tool binding is a no-op."""

    def bind_tools(self, tools, **kwargs):
        return self


def script(monkeypatch, *messages: AIMessage) -> None:
    model = ScriptedModel(messages=iter(messages))
    monkeypatch.setattr(graph, "chat_model", lambda role="fast": model)


def call(tool: str, **args) -> dict:
    return {"name": tool, "args": args, "id": uuid.uuid4().hex, "type": "tool_call"}


@pytest.fixture(autouse=True)
def bank(monkeypatch):
    customers = {"DEMO-MX-FX": {"customer_id": "DEMO-MX-FX"}}
    seen = []

    async def find_customer(customer_id):
        return customers.get(customer_id)

    async def fetch_balances(customer_id, product_type=None):
        seen.append(customer_id)
        return [
            {
                "product_type": "Tarjeta Crédito",
                "product_number_last4": "1234",
                "currency": "MXN",
                "current_balance": 1500.0,
            }
        ]

    monkeypatch.setattr(graph, "find_customer", find_customer)
    monkeypatch.setattr(accounts, "fetch_balances", fetch_balances)
    return seen


async def ask(message: str, customer_id: str | None = None, thread: str | None = None) -> dict:
    return await graph.reply(message, thread or uuid.uuid4().hex, customer_id)


async def test_missing_customer_id_is_asked_without_calling_the_llm(monkeypatch):
    script(monkeypatch)  # no scripted messages: any LLM call would fail
    result = await ask("¿cuál es mi saldo?")
    assert "ID de cliente" in result["reply"]
    assert result["customer_id"] is None


async def test_customer_id_typed_in_chat_is_validated_by_code(monkeypatch):
    script(monkeypatch, AIMessage("Hola, ¿en qué te ayudo con tus saldos?"))
    thread = uuid.uuid4().hex
    await ask("hola", thread=thread)
    assert "No encuentro" in (await ask("mi id es DEMO-XX-NOPE", thread=thread))["reply"]
    result = await ask("mi id es demo-mx-fx", thread=thread)
    assert result["customer_id"] == "DEMO-MX-FX"


async def test_asking_for_a_person_hands_off_without_the_llm(monkeypatch):
    script(monkeypatch)
    result = await ask("quiero hablar con una persona", customer_id="DEMO-MX-FX")
    assert result["handoff"]["request"] == "quiero hablar con una persona"


async def test_out_of_scope_is_answered_in_one_call_without_tools(monkeypatch):
    script(monkeypatch, AIMessage("Hoy solo puedo ayudarte con tus saldos."))
    result = await ask("¿me recomiendas una hipoteca?", customer_id="DEMO-MX-FX")
    assert result["reply"] == "Hoy solo puedo ayudarte con tus saldos."
    assert result["skill"] is None and result["tools_used"] == []


async def test_balance_uses_the_skill_and_only_the_session_customer(monkeypatch, bank):
    script(
        monkeypatch,
        AIMessage("", tool_calls=[call("use_skill", name="balance_inquiry")]),
        AIMessage("", tool_calls=[call("get_balances")]),
        AIMessage("Tu Tarjeta Crédito •1234 tiene 1,500.00 MXN."),
    )
    result = await ask("¿cuál es el saldo de CLI-OTRO?", customer_id="DEMO-MX-FX")
    assert result["skill"] == "balance_inquiry"
    assert result["tools_used"] == ["get_balances"]
    assert bank == ["DEMO-MX-FX"]
    assert "1,500.00 MXN" in result["reply"]


async def test_unrecognized_charge_uses_the_investigation_skill_as_the_session_customer(
    monkeypatch,
):
    seen = []

    class Warehouse:
        async def transaction(self, customer_id, transaction_id):
            seen.append(customer_id)
            return {
                "transaction_id": transaction_id,
                "transaction_date": datetime(2026, 6, 10),
                "amount": 312.4,
                "currency": "MXN",
                "merchant_name": "Uber Trip",
                "channel": "POS",
                "transaction_status": "Pending",
                "transaction_country": None,
            }

        async def duplicate_of(self, customer_id, transaction_id, window_seconds):
            return None

        async def home_country(self, customer_id):
            return None

        async def fx_rate_to_usd(self, currency, on):
            return None

    async def no_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(investigation, "warehouse", Warehouse())
    monkeypatch.setattr(investigation, "record_decision", no_audit)
    script(
        monkeypatch,
        AIMessage("", tool_calls=[call("use_skill", name="charge_investigation")]),
        AIMessage("", tool_calls=[call("investigate_charge", transaction_id="T1")]),
        AIMessage("Ese cargo todavía está pendiente."),
    )
    result = await ask("no reconozco un cargo de Uber", customer_id="DEMO-MX-FX")
    assert result["skill"] == "charge_investigation"
    assert result["tools_used"] == ["investigate_charge"]
    assert seen == ["DEMO-MX-FX"]


async def test_data_question_uses_the_dwh_skill_and_sql_runs_as_the_session_customer(monkeypatch):
    from app.adapters.inbound.mcp import dwh

    seen = []

    class Db:
        async def fetch(self, sql, max_rows):
            seen.append(sql)
            return [{"total": 1500.0}]

    async def no_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(dwh, "db", Db())
    monkeypatch.setattr(dwh, "record_decision", no_audit)
    script(
        monkeypatch,
        AIMessage("", tool_calls=[call("use_skill", name="data_lookup")]),
        AIMessage("", tool_calls=[call("describe_schema")]),
        AIMessage(
            "",
            tool_calls=[call("run_sql", sql="SELECT sum(amount) AS total FROM transactions")],
        ),
        AIMessage("Gastaste 1,500.00 MXN."),
    )
    result = await ask("¿cuánto gasté en total?", customer_id="DEMO-MX-FX")
    assert result["skill"] == "data_lookup"
    assert result["tools_used"] == ["describe_schema", "run_sql"]
    assert "customer_id = 'DEMO-MX-FX'" in seen[0]


async def test_an_empty_model_reply_never_reaches_the_customer(monkeypatch):
    script(monkeypatch, AIMessage(""))
    result = await ask("hola", customer_id="DEMO-MX-FX")
    assert result["reply"].strip() and result["skill"] is None


async def test_an_unknown_skill_name_gets_the_safe_reply_not_silence(monkeypatch):
    script(monkeypatch, AIMessage("", tool_calls=[call("use_skill", name="spending_summary")]))
    result = await ask("hola, necesito ayuda", customer_id="DEMO-MX-FX")
    assert result["reply"].strip() and result["skill"] is None


async def test_a_tool_call_written_as_text_is_not_shown_to_the_customer(monkeypatch):
    script(monkeypatch, AIMessage('{"name": "charge_investigation"}</tool_call>'))
    result = await ask("hola, ¿me ayudas?", customer_id="DEMO-MX-FX")
    assert "tool_call" not in result["reply"] and result["reply"].strip()


async def test_code_routes_an_obvious_request_when_the_model_only_talks(monkeypatch):
    script(
        monkeypatch,
        AIMessage("Necesito más información sobre el periodo. ¿Me la das?"),  # model does not route
        AIMessage("", tool_calls=[call("describe_schema")]),
        AIMessage("Tienes 2 quejas."),
    )
    result = await ask("¿cuántas quejas tengo?", customer_id="DEMO-MX-FX")
    assert result["skill"] == "data_lookup" and result["reply"] == "Tienes 2 quejas."


async def test_code_routes_when_the_model_returns_nothing(monkeypatch):
    script(
        monkeypatch,
        AIMessage(""),
        AIMessage("", tool_calls=[call("describe_schema")]),
        AIMessage("Listo."),
    )
    result = await ask("¿cuánto he gastado en compras aprobadas?", customer_id="DEMO-MX-FX")
    assert result["skill"] == "data_lookup" and result["tools_used"] == ["describe_schema"]


def test_a_skill_agent_never_sees_the_routing_section():
    from app.adapters.inbound.agent.skills import agent_prompt

    assert "use_skill" in agent_prompt() and "How to route" in agent_prompt()
    assert "use_skill" not in agent_prompt(routing=False)
    assert "Never ask for passwords" in agent_prompt(routing=False)


class DownModel:
    """A model whose provider is unavailable (like Gemini answering 503)."""

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, *args, **kwargs):
        raise RuntimeError("503 UNAVAILABLE: high demand")


async def test_a_model_outage_gives_a_safe_reply_and_a_handoff_not_a_500(monkeypatch):
    monkeypatch.setattr(graph, "chat_model", lambda role="fast": DownModel())
    result = await ask("hola", customer_id="DEMO-MX-FX")
    assert "problemas técnicos" in result["reply"]
    assert result["handoff"]["reason"] == "assistant_error"
    assert result["handoff"]["customer_id"] == "DEMO-MX-FX"


def test_gemini_calls_have_bounded_retries_and_a_timeout(monkeypatch):
    from app.adapters.outbound import llm
    from app.config import Settings

    seen = {}
    monkeypatch.setattr(llm, "init_chat_model", lambda model, **kw: seen.update(kw))
    cloud = Settings(
        _env_file=None,
        app_env="cloud",
        database_url="postgresql://u:p@/agent?host=/cloudsql/x:y:z",
        llm_provider="google_genai",
        jwt_secret="x" * 32,
    )
    monkeypatch.setattr(llm, "get_settings", lambda: cloud)
    llm.chat_model.__wrapped__("fast")
    assert (seen["max_retries"], seen["timeout"]) == (2, 30)
