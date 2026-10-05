"""FastAPI entrypoint: the chat API and its speech routes, the operator console's API and the
Telegram webhook. The web is a separate service."""

import asyncio
import base64
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AliasChoices, BaseModel, Field
from telegram import Update

from app.adapters.inbound.agent import reply
from app.adapters.inbound.auth import (
    account_locked,
    allow_login,
    claimed_customer,
    clear_failures,
    customer_from_login,
    issue_token,
    operator,
    register_failure,
    token_customer,
)
from app.adapters.inbound.conversations import Conversation, conversations
from app.adapters.inbound.finances_schema import OwnFinances
from app.adapters.inbound.mcp import transfers as khipu
from app.adapters.inbound.telegram import build_application
from app.adapters.outbound import llm, postgres, speech
from app.adapters.outbound.postgres import chat_memory as memory_store
from app.adapters.outbound.postgres.accounts import find_customer, list_customers
from app.adapters.outbound.postgres.actions import build_gateway, recent_messages
from app.adapters.outbound.postgres.audit import record_decision
from app.adapters.outbound.postgres.finances import PostgresFinances
from app.adapters.outbound.postgres.readonly import ReadOnlyPostgres
from app.adapters.outbound.postgres.spending import PostgresSpending
from app.application.actions import ActionGateway, NotFound
from app.application.finances import FinancesUnavailable, own_finances
from app.application.run_sql import run_scoped_sql
from app.application.transfers import cancel as cancel_transfer
from app.application.transfers import execute as execute_transfer
from app.config import get_settings
from app.domain import chat_memory as memory_rules
from app.domain.finances import NoSpending, UnknownCustomer

# Our own loggers at LOG_LEVEL; libraries stay at the default (warnings and errors).
logging.basicConfig(format="%(levelname)s:     %(name)s: %(message)s")
logging.getLogger("app").setLevel(get_settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Voice: load both models before taking traffic, or the first spoken message waits about ten
    # seconds for each. There are none where voice is not installed (CI, no `make models`).
    if speech.MODELS.exists():
        await asyncio.gather(run_in_threadpool(speech.whisper), run_in_threadpool(speech.kokoro))
    app.state.telegram = None
    if settings.telegram_bot_token:
        app.state.telegram = build_application()
        await app.state.telegram.initialize()
    yield
    if app.state.telegram:
        await app.state.telegram.shutdown()


app = FastAPI(title="Factored 2026", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],  # echoes what the browser asks for, so `Authorization` is allowed
)


IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_IMAGE_BYTES = 4_000_000  # decoded; a phone photo of a statement fits, a base64 dump does not


class ChatRequest(BaseModel):
    message: str
    image: str | None = None  # base64, no data-url prefix; kept for this turn only
    image_type: str | None = None  # image/jpeg, image/png or image/webp
    customer_id: str | None = None  # optional: the token decides; only local may use this alone
    thread_id: str | None = None  # one per conversation; a new one is created when missing


def attached_image(image: str | None, image_type: str | None) -> tuple[str, str] | None:
    """The photo on this turn, or None. Both fields together, a known type, and at most 4 MB."""
    if image is None and image_type is None:
        return None
    if not image or image_type not in IMAGE_TYPES:
        raise HTTPException(400, "La imagen tiene que ser jpeg, png o webp.")
    try:
        raw = base64.b64decode(image, validate=True)
    except ValueError:
        raise HTTPException(400, "La imagen no se pudo leer.") from None
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "La imagen pasa de 4 MB.")
    return image, image_type


class ChatResponse(BaseModel):
    reply: str | None  # None: a person has this chat and answers through the operator console
    thread_id: str
    customer_id: str | None
    skill: str | None
    tools_used: list[str]
    handoff: dict | None
    actions: dict | None = None  # what the agent proposes; nothing runs until the customer confirms
    confirmation: dict | None = None  # a money movement waiting for the Confirmar button


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": get_settings().app_env}


@app.get("/health/ready")
def ready(response: Response) -> dict:
    """Readiness: every dependency the agent needs. 503 if any is down (used by `make smoke`)."""
    checks = {}
    for name, ping in {"db": postgres.ping, "llm": llm.ping}.items():
        try:
            checks[name] = ping()
        except Exception as error:  # report every failing dependency, not just the first
            checks[name] = f"error: {error}"
    if any(not status.startswith("ok") for status in checks.values()):
        response.status_code = 503
    return checks


def demo_ids() -> list[str]:
    return [i.strip() for i in get_settings().demo_customer_ids.split(",") if i.strip()]


@app.get("/api/demo-customers")
async def demo_customers() -> list[dict]:
    """Customers listed in DEMO_CUSTOMER_IDS: the IDs that can sign in (password: the same ID)."""
    ids = demo_ids()
    return await list_customers(ids) if ids else []


class TokenRequest(BaseModel):
    # The ID of a customer in DEMO_CUSTOMER_IDS, or one of the eight demo emails. `email` is the old
    # name of the field and is still accepted.
    user: str = Field(validation_alias=AliasChoices("user", "email"))
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    customer_id: str


@app.post("/api/auth/token")
async def demo_token(body: TokenRequest, request: Request) -> TokenResponse:
    """Demo login: a customer ID from DEMO_CUSTOMER_IDS (or one of eight emails) plus its password,
    which is that same ID (or email), then the same short-lived bearer token. With `*` in that
    list, the ID of any customer in the database signs in the same way.

    A wrong login and a wrong password get the same 401. Three wrong passwords lock that account
    for 15 minutes (423), even with the right password afterwards. Eight attempts per minute per
    client; the ninth is 429. A real deployment swaps this for the bank's identity provider;
    everything downstream only trusts the token.
    """
    origin = request.client.host if request.client else "unknown"
    if not allow_login(origin):
        raise HTTPException(429, "Demasiados intentos. Espera un minuto.")
    if account_locked(body.user):
        raise HTTPException(423, "Cuenta bloqueada. Espera 15 minutos.")
    # scrypt is slow on purpose: off the event loop, as when this route was a plain function.
    customer_id = await run_in_threadpool(customer_from_login, body.user, body.password)
    if customer_id is None:
        claimed = await run_in_threadpool(claimed_customer, body.user, body.password)
        if claimed and await find_customer(claimed):
            customer_id = claimed
    if customer_id is None:
        if register_failure(body.user):
            raise HTTPException(423, "Cuenta bloqueada. Espera 15 minutos.")
        raise HTTPException(401, "ID o contraseña incorrectos.")
    clear_failures(body.user)
    token, expires_in = issue_token(customer_id)
    return TokenResponse(access_token=token, expires_in=expires_in, customer_id=customer_id)


class SqlRequest(BaseModel):
    customer_id: str
    sql: str


@app.post("/api/dev/dwh/sql")
async def dev_dwh_sql(request: SqlRequest) -> dict:
    """Local-only: run SQL through the same guard the agent's `run_sql` tool uses (scoped to
    `customer_id`, read-only). For testing the DWH layer without an LLM."""
    if get_settings().app_env != "local":
        raise HTTPException(404)
    return await run_scoped_sql(ReadOnlyPostgres(), request.customer_id, request.sql)


def resolve_customer(proven: str | None, claimed: str | None) -> str | None:
    """The customer of a request: the one the token proves, never one the body claims."""
    if proven:
        if claimed and claimed != proven:
            raise HTTPException(403, "customer_id does not match the token.")
        return proven
    if get_settings().app_env == "local":  # local stub: curl and Swagger work without a token
        return claimed
    raise HTTPException(401, "Bearer token required.", headers={"WWW-Authenticate": "Bearer"})


def thread_key(customer_id: str | None, thread_id: str) -> str:
    """The conversation key includes the customer: nobody can continue someone else's thread."""
    return f"{customer_id}:{thread_id}" if customer_id else thread_id


def memory_on() -> bool:
    return get_settings().chat_memory_enabled


def remembered(message: str, picture: object) -> str:
    """What the memory keeps of the customer's turn: the text, or a note that a photo came."""
    return message if message.strip() or not picture else "[foto]"


@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    background: BackgroundTasks,
    token_customer_id: Annotated[str | None, Depends(token_customer)],
) -> ChatResponse:
    customer_id = resolve_customer(token_customer_id, request.customer_id)
    picture = attached_image(request.image, request.image_type)
    thread_id = request.thread_id or uuid4().hex
    key = thread_key(customer_id, thread_id)
    conversation = conversations.setdefault(key, Conversation(key, customer_id))
    # The photo stays on this turn. The conversation mirror only keeps the text.
    conversation.add("customer", request.message)
    # The memory is per customer: there is none without one.
    keeping = memory_on() and customer_id is not None
    text = remembered(request.message, picture)
    if conversation.status != "bot":  # a person has this chat: the agent stays out of it
        if keeping:
            background.add_task(memory_store.record_turn, customer_id, thread_id, text, "")
        return ChatResponse(
            reply=None,
            thread_id=thread_id,
            customer_id=customer_id,
            skill=None,
            tools_used=[],
            handoff=None,
        )
    extra = {}
    if keeping:  # only when there is something to tell: with it off, the call is what it always was
        past = await memory_store.past_for_agent(customer_id, thread_id)
        if summary := memory_rules.summary_for_agent(past):
            extra["memory"] = summary
    result = await reply(request.message, key, customer_id, image=picture, **extra)
    conversation.customer_id = result["customer_id"]
    conversation.add("assistant", result["reply"])
    if result["handoff"]:
        conversation.status, conversation.case_file = "waiting", result["handoff"]
    if keeping:
        actions = result.get("actions")
        confirmation = result.get("confirmation")
        waiting = actions or ({"confirmation": confirmation} if confirmation else None)
        outcome = memory_rules.outcome_of(handed_off=bool(result["handoff"]), actions=waiting)
        language = (actions or {}).get("language")
        background.add_task(
            memory_store.record_turn,
            customer_id,
            thread_id,
            text,
            result["reply"] or "",
            skill=result["skill"],
            outcome=outcome,
            language=language,
        )
    return ChatResponse(thread_id=thread_id, **result)


class KhipuRequest(BaseModel):
    transfer_id: UUID  # `confirmation.transfer_id` of a chat reply
    customer_id: str | None = None  # local only, like the chat's: the token decides


def khipu_customer(proven: str | None, claimed: str | None) -> str:
    customer = resolve_customer(proven, claimed)
    if customer is None:
        raise HTTPException(400, "customer_id is required without a token (local only).")
    return customer


@app.post("/api/khipu/confirm")
async def khipu_confirm(
    request: KhipuRequest, token_customer_id: Annotated[str | None, Depends(token_customer)]
) -> dict:
    """The Confirmar button: the only way a proposed money movement is executed. No model runs
    here. Every rule is checked again with both accounts locked; pressing twice executes once and
    answers with the same receipt. `status` is executed, blocked, expired or cancelled."""
    customer = khipu_customer(token_customer_id, request.customer_id)
    transfer_id = str(request.transfer_id)
    result = await execute_transfer(khipu.ledger, khipu.limits(), customer, transfer_id)
    executed = result["status"] == "executed"
    await record_decision(
        "confirm_transfer",
        {"customer_id": customer, "transfer_id": transfer_id},
        "allowed" if executed else "blocked",
        result.get("reason") or result["status"],
        executed=executed,
    )
    if result["status"] == "not_found":
        raise HTTPException(404, "unknown_transfer")
    return result


@app.post("/api/khipu/cancel")
async def khipu_cancel(
    request: KhipuRequest, token_customer_id: Annotated[str | None, Depends(token_customer)]
) -> dict:
    """The Cancelar button: the proposal can no longer be confirmed."""
    customer = khipu_customer(token_customer_id, request.customer_id)
    transfer_id = str(request.transfer_id)
    result = await cancel_transfer(khipu.ledger, customer, transfer_id)
    await record_decision(
        "cancel_transfer",
        {"customer_id": customer, "transfer_id": transfer_id},
        "allowed",
        result["status"],
        executed=result["status"] == "cancelled",
    )
    if result["status"] == "not_found":
        raise HTTPException(404, "unknown_transfer")
    return result


@app.get("/api/me/finances")
async def my_finances(
    token_customer_id: Annotated[str | None, Depends(token_customer)],
    days: Annotated[int, Query(ge=7, le=365)] = 90,
    customer_id: str | None = None,  # local only, like the chat's: the token decides
) -> OwnFinances:
    """The "Mis finanzas" screen: the customer's own spending, and nothing internal to the bank.

    The customer is the one the token proves; `days` counts back from the dataset's last day.
    """
    customer = resolve_customer(token_customer_id, customer_id)
    if customer is None:
        raise HTTPException(400, "customer_id is required without a token (local only).")
    try:
        return await own_finances(PostgresSpending(), PostgresFinances(), customer, days)
    except UnknownCustomer:
        raise HTTPException(404, "unknown_customer") from None
    except NoSpending:
        raise HTTPException(404, "no_spending_in_period") from None
    except FinancesUnavailable:
        raise HTTPException(503, "finances_unavailable") from None


def gateway() -> ActionGateway:
    """The action gateway. While actions are off its routes answer 404, as if they did not exist."""
    if not get_settings().actions_enabled:
        raise HTTPException(404, "actions_disabled")
    return build_gateway()


class ActionDecision(BaseModel):
    thread_id: str | None = None  # the chat the card came from: a person who picks it up sees this
    customer_id: str | None = None  # local only, like the chat's: the token decides
    inbox: str | None = None  # one of the demo inboxes the card offered


def action_customer(proven: str | None, claimed: str | None) -> str:
    customer = resolve_customer(proven, claimed)
    if customer is None:
        raise HTTPException(400, "customer_id is required without a token (local only).")
    return customer


def note_outcome(customer_id: str, thread_id: str | None, view: dict) -> None:
    """Put what happened in the chat the operator console mirrors, and give the chat to a person
    when the policy or a failed check says an action needs one."""
    conversation = conversations.get(thread_key(customer_id, thread_id)) if thread_id else None
    if conversation is None:
        return
    text = " · ".join(item["text"] for item in view["items"])
    if not conversation.messages or conversation.messages[-1]["text"] != text:
        conversation.add("assistant", text)
    if view["escalate"] and conversation.status == "bot":
        conversation.status = "waiting"
        conversation.case_file = {
            "customer_id": customer_id,
            "request": "action_outcome",
            "actions": [
                {"action": i["action"], "status": i["status"], "text": i["text"]}
                for i in view["items"]
            ],
            "unresolved": view["escalate"],
        }


async def remember_decision(customer_id: str, thread_id: str | None, view: dict) -> None:
    """Keep in the history what came of the card the customer pressed. Never breaks the answer."""
    if not (memory_on() and thread_id):
        return
    text = " · ".join(item["text"] for item in view["items"])
    outcome = memory_rules.outcome_after(
        [item["status"] for item in view["items"]], escalated=bool(view["escalate"])
    )
    await memory_store.append_message(customer_id, thread_id, "assistant", text, outcome=outcome)


@app.post("/api/actions/{batch_id}/confirm")
async def confirm_actions(
    batch_id: str,
    body: ActionDecision,
    token_customer_id: Annotated[str | None, Depends(token_customer)],
) -> dict:
    """The customer confirms what the agent proposed. Only this route runs it, never the chat, and
    only for the customer the token proves. Asking again returns the same result."""
    customer = action_customer(token_customer_id, body.customer_id)
    try:
        view = await gateway().confirm(customer, batch_id, inbox=body.inbox)
    except NotFound:
        raise HTTPException(404, "unknown_batch") from None
    note_outcome(customer, body.thread_id, view)
    await remember_decision(customer, body.thread_id, view)
    return view


@app.post("/api/actions/{batch_id}/cancel")
async def cancel_actions(
    batch_id: str,
    body: ActionDecision,
    token_customer_id: Annotated[str | None, Depends(token_customer)],
) -> dict:
    customer = action_customer(token_customer_id, body.customer_id)
    try:
        view = await gateway().cancel(customer, batch_id)
    except NotFound:
        raise HTTPException(404, "unknown_batch") from None
    note_outcome(customer, body.thread_id, view)
    await remember_decision(customer, body.thread_id, view)
    return view


@app.get("/api/me/outbox")
async def my_outbox(
    token_customer_id: Annotated[str | None, Depends(token_customer)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    customer_id: str | None = None,  # local only, like the chat's: the token decides
) -> list[dict]:
    """What the system sent this customer, newest first: the simulated phone of the demo."""
    customer = action_customer(token_customer_id, customer_id)
    gateway()  # 404 while actions are off
    return await recent_messages(customer, limit)


def memory_customer(proven: str | None, claimed: str | None) -> str:
    """The customer whose history it is: the one the token proves. 404 while the memory is off."""
    customer = resolve_customer(proven, claimed)
    if customer is None:
        raise HTTPException(400, "customer_id is required without a token (local only).")
    if not memory_on():
        raise HTTPException(404, "chat_memory_disabled")
    return customer


@app.get("/api/me/conversations")
async def my_conversations(
    token_customer_id: Annotated[str | None, Depends(token_customer)],
    customer_id: str | None = None,  # local only, like the chat's: the token decides
) -> list[dict]:
    """The customer's earlier conversations, the most recent first. Only theirs."""
    customer = memory_customer(token_customer_id, customer_id)
    return await memory_store.list_conversations(customer)


@app.get("/api/me/conversations/{conversation_id}")
async def my_conversation(
    conversation_id: str,
    token_customer_id: Annotated[str | None, Depends(token_customer)],
    customer_id: str | None = None,
) -> dict:
    """One earlier conversation with its messages. Not found if it is not the customer's."""
    customer = memory_customer(token_customer_id, customer_id)
    found = await memory_store.read_conversation(customer, conversation_id)
    if found is None:
        raise HTTPException(404, "unknown_conversation")
    return found


@app.delete("/api/me/conversations")
async def forget_my_conversations(
    token_customer_id: Annotated[str | None, Depends(token_customer)],
    customer_id: str | None = None,
) -> dict:
    """Forget everything kept of this customer's conversations. The chat open on their screen is
    not touched; the next message starts it again."""
    customer = memory_customer(token_customer_id, customer_id)
    return {"deleted": await memory_store.delete_history(customer)}


class Transcript(BaseModel):
    text: str
    language: str  # the one Whisper heard: `es`, `pt`, ...


@app.post("/api/speech/transcribe")
async def transcribe(
    request: Request, token_customer_id: Annotated[str | None, Depends(token_customer)]
) -> Transcript:
    """What the customer said into the microphone: the body is the recording. The web then sends
    the text through /api/chat, like a typed message."""
    resolve_customer(token_customer_id, None)
    text, language = await run_in_threadpool(speech.transcribe, await request.body())
    return Transcript(text=text, language=language)


class SpeechRequest(BaseModel):
    text: str
    language: str


@app.post("/api/speech/synthesize")
def synthesize(
    request: SpeechRequest, token_customer_id: Annotated[str | None, Depends(token_customer)]
) -> Response:
    """The agent's reply read aloud (WAV), in the language the customer spoke."""
    resolve_customer(token_customer_id, None)
    return Response(speech.synthesize(request.text, request.language), media_type="audio/wav")


@app.get("/api/chat/{thread_id}/operator")
def operator_messages(
    thread_id: str,
    token_customer_id: Annotated[str | None, Depends(token_customer)],
    after: int = 0,
) -> dict:
    """What the operator wrote in the customer's own chat since message number `after`. The web
    polls it; `next` is the `after` of its next call."""
    key = thread_key(resolve_customer(token_customer_id, None), thread_id)
    messages = conversations[key].messages if key in conversations else []
    return {
        "next": len(messages),
        "messages": [m for m in messages[after:] if m["role"] == "operator"],
    }


@app.get("/api/crm/conversations", dependencies=[Depends(operator)])
def crm_conversations() -> list[dict]:
    """Every chat this instance has seen, newest first, the ones waiting for a person on top."""
    newest_first = reversed(conversations.values())
    return [asdict(c) for c in sorted(newest_first, key=lambda c: c.status != "waiting")]


class OperatorReply(BaseModel):
    thread_key: str
    text: str


class Release(BaseModel):
    thread_key: str


def known_conversation(key: str) -> Conversation:
    if key not in conversations:  # the instance restarted since the console loaded its list
        raise HTTPException(404, "This chat is no longer in memory.")
    return conversations[key]


@app.post("/api/crm/reply", dependencies=[Depends(operator)])
async def crm_reply(request: OperatorReply) -> dict:
    """The operator answers the customer and, by doing so, takes the chat from the agent."""
    conversation = known_conversation(request.thread_key)
    conversation.add("operator", request.text)
    conversation.status = "human"
    customer = conversation.customer_id
    prefix = f"{customer}:" if customer else None
    if memory_on() and prefix and request.thread_key.startswith(prefix):
        thread_id = request.thread_key[len(prefix) :]
        await memory_store.append_message(customer, thread_id, "operator", request.text)
    return asdict(conversation)


@app.post("/api/crm/release", dependencies=[Depends(operator)])
def crm_release(request: Release) -> dict:
    """The operator gives the chat back to the agent."""
    conversation = known_conversation(request.thread_key)
    conversation.status = "bot"
    return asdict(conversation)


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict:
    telegram = request.app.state.telegram
    if telegram is None:
        raise HTTPException(503, "Telegram is not configured")
    if x_telegram_bot_api_secret_token != get_settings().telegram_webhook_secret:
        raise HTTPException(403, "Invalid secret")
    await telegram.process_update(Update.de_json(await request.json(), telegram.bot))
    return {"ok": True}
