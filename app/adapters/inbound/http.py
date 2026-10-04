"""FastAPI entrypoint: the chat API and its speech routes, the operator console's API and the
Telegram webhook. The web is a separate service."""

import asyncio
import base64
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Update

from app.adapters.inbound.agent import reply
from app.adapters.inbound.auth import (
    account_locked,
    allow_login,
    clear_failures,
    customer_from_login,
    issue_token,
    operator,
    register_failure,
    token_customer,
)
from app.adapters.inbound.conversations import Conversation, conversations
from app.adapters.inbound.telegram import build_application
from app.adapters.outbound import llm, postgres, speech
from app.adapters.outbound.postgres.accounts import list_customers
from app.adapters.outbound.postgres.readonly import ReadOnlyPostgres
from app.application.run_sql import run_scoped_sql
from app.config import get_settings

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
    """Customers listed in DEMO_CUSTOMER_IDS. The chat signs in with email and password instead."""
    ids = demo_ids()
    return await list_customers(ids) if ids else []


class TokenRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    customer_id: str


@app.post("/api/auth/token")
def demo_token(body: TokenRequest, request: Request) -> TokenResponse:
    """Demo login: one of eight emails plus its password, then the same short-lived bearer token.

    A wrong email and a wrong password get the same 401. Three wrong passwords lock that account
    for 15 minutes (423), even with the right password afterwards. Eight attempts per minute per
    client; the ninth is 429. A real deployment swaps this for the bank's identity provider;
    everything downstream only trusts the token.
    """
    origin = request.client.host if request.client else "unknown"
    if not allow_login(origin):
        raise HTTPException(429, "Demasiados intentos. Espera un minuto.")
    if account_locked(body.email):
        raise HTTPException(423, "Cuenta bloqueada. Espera 15 minutos.")
    customer_id = customer_from_login(body.email, body.password)
    if customer_id is None:
        if register_failure(body.email):
            raise HTTPException(423, "Cuenta bloqueada. Espera 15 minutos.")
        raise HTTPException(401, "Correo o contraseña incorrectos.")
    clear_failures(body.email)
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


@app.post("/api/chat")
async def chat(
    request: ChatRequest, token_customer_id: Annotated[str | None, Depends(token_customer)]
) -> ChatResponse:
    customer_id = resolve_customer(token_customer_id, request.customer_id)
    picture = attached_image(request.image, request.image_type)
    thread_id = request.thread_id or uuid4().hex
    key = thread_key(customer_id, thread_id)
    conversation = conversations.setdefault(key, Conversation(key, customer_id))
    # The photo stays on this turn. The conversation mirror only keeps the text.
    conversation.add("customer", request.message)
    if conversation.status != "bot":  # a person has this chat: the agent stays out of it
        return ChatResponse(
            reply=None,
            thread_id=thread_id,
            customer_id=customer_id,
            skill=None,
            tools_used=[],
            handoff=None,
        )
    result = await reply(request.message, key, customer_id, image=picture)
    conversation.customer_id = result["customer_id"]
    conversation.add("assistant", result["reply"])
    if result["handoff"]:
        conversation.status, conversation.case_file = "waiting", result["handoff"]
    return ChatResponse(thread_id=thread_id, **result)


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
def crm_reply(request: OperatorReply) -> dict:
    """The operator answers the customer and, by doing so, takes the chat from the agent."""
    conversation = known_conversation(request.thread_key)
    conversation.add("operator", request.text)
    conversation.status = "human"
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
