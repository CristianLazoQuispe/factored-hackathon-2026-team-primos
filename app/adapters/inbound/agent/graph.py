"""The agent: a LangGraph graph with deterministic nodes around one skill-using LLM node.

    guard (code) ──► router (LLM: answer briefly or pick a skill) ──► skill_agent (LLM + MCP tools)
      │                   │                                               │
      └──────────────► handoff (code) ◄──── request_human ───────────────┘

- guard: identifies the customer (code validates the ID, never the LLM) and forces a handoff
  when the customer asks for a person. Mandatory escalations live here.
- router: sees only the skill catalog; off-scope questions get a short answer in one LLM call.
- skill_agent: loads SKILL.md, lists the skill's MCP tools and loops (LangChain create_agent).
- handoff: deterministic case file for a human; the agent can request it, never skip it.
Every LLM call, skill choice and tool call is a LangChain run, so Langfuse traces all of it.
"""

import json
import logging
import re
from typing import Literal

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from app.adapters.inbound.agent.mcp_bridge import client_for, load_tools
from app.adapters.inbound.agent.skills import agent_prompt, available, catalog, load_skills
from app.adapters.inbound.agent.tracing import callbacks
from app.adapters.outbound.llm import chat_model
from app.adapters.outbound.postgres.accounts import find_customer
from app.domain.action_text import detect_language
from app.domain.routing import guess_refused_action, guess_skill

log = logging.getLogger(__name__)

MAX_SKILL_STEPS = 12  # LangGraph steps inside the skill loop (~6 tool calls)
ASKS_FOR_HUMAN = re.compile(
    r"\b(humano|una persona|asesor|ejecutivo|agente humano|pessoa|atendente)\b", re.IGNORECASE
)
CUSTOMER_ID = re.compile(r"\b((?:CLI|DEMO)-[A-Z0-9-]+)\b", re.IGNORECASE)
ASK_ID = (
    "Para ayudarte necesito tu ID de cliente (por ejemplo, CLI-NRO6HF74BFQD). / "
    "Para te ajudar, preciso do seu ID de cliente."
)
NO_ANSWER = (
    "No pude procesar tu mensaje. ¿Puedes reformularlo, o prefieres hablar con una persona? / "
    "Não consegui processar sua mensagem. Pode reformular, ou prefere falar com uma pessoa?"
)
UNAVAILABLE = (
    "Estoy teniendo problemas técnicos en este momento. Te paso con una persona de nuestro "
    "equipo. / Estou com problemas técnicos agora. Vou te transferir para uma pessoa da equipe."
)
NEEDS_SIGN_IN = (
    "Para hacer cambios en tu cuenta necesito que entres con tu sesión en la web o en la app. / "
    "Para fazer alterações na sua conta, entre na sua sessão pelo site ou pelo app."
)
UNPROPOSED = (
    "No pude preparar esa acción. Dime con otras palabras qué necesitas, o te paso con una "
    "persona. / Não consegui preparar essa ação. Diga com outras palavras o que precisa, ou passo "
    "você para uma pessoa."
)
HANDOFF = (
    "Te comunico con una persona de nuestro equipo. Ya tiene tu caso, no tendrás que repetir "
    "nada. / Vou te transferir para uma pessoa da nossa equipe; ela já tem o seu caso."
)


class State(MessagesState):
    customer_id: str | None
    signed_in: bool  # the token proved the customer (not an ID typed in the chat)
    language: str | None
    actions: dict | None  # what this turn proposed, for the app to show
    refused: str | None  # an obvious request for what the bank never does, caught by code
    route: str
    skill: str | None
    tools_used: list[str]
    case_file: dict | None


@tool
def use_skill(name: str) -> str:
    """Activate one of the listed skills by name to handle the customer's request."""
    return name


@tool
def request_human(reason: str) -> str:
    """Transfer the conversation to a human agent, with a short reason."""
    return "HANDOFF_REQUESTED"


def last_customer_text(state: State) -> str:
    return next(m.text for m in reversed(state["messages"]) if isinstance(m, HumanMessage))


async def guard(state: State) -> dict:
    text = last_customer_text(state)
    turn = {"skill": None, "tools_used": [], "case_file": None, "actions": None}
    if ASKS_FOR_HUMAN.search(text):
        return turn | {"route": "handoff"}
    if state.get("customer_id"):
        return turn | {"route": "router"}
    match = CUSTOMER_ID.search(text)
    if match and await find_customer(match.group(1).upper()):
        return turn | {"route": "router", "customer_id": match.group(1).upper()}
    reply = f"No encuentro el ID {match.group(1)}. {ASK_ID}" if match else ASK_ID
    return turn | {"route": "end", "messages": [AIMessage(reply)]}


def needs_sign_in() -> dict:
    return {"route": "end", "messages": [AIMessage(NEEDS_SIGN_IN)]}


async def router(state: State) -> dict:
    signed_in = bool(state.get("signed_in"))
    usable = available(signed_in)
    refused = guess_refused_action(last_customer_text(state))
    if refused and "account_actions" in usable:  # obvious: no model turn can lose or invent it
        return {"route": "refuse", "refused": refused}
    if refused and "account_actions" in load_skills():  # asked, but only typed an ID
        return needs_sign_in()
    system = f"{agent_prompt()}\n\n## Skills\n{catalog(signed_in)}"
    model = chat_model("fast").bind_tools([use_skill, request_human])
    response = await model.ainvoke([SystemMessage(system), *state["messages"]])
    for call in response.tool_calls:
        if call["name"] == "request_human":
            return {"route": "handoff"}
        if call["name"] == "use_skill":
            name = call["args"].get("name")
            if name in usable:
                return {"route": "skill_agent", "skill": name}
            if (
                name in load_skills()
            ):  # one that changes things, for a customer who only typed an ID
                return needs_sign_in()
    text = response.text.strip()
    skill = guess_skill(last_customer_text(state))
    if skill in usable:  # the model did not route an obvious request: code does
        log.info("router fallback -> %s (model said %r)", skill, text[:80])
        return {"route": "skill_agent", "skill": skill}
    if skill in load_skills():
        return needs_sign_in()
    if response.tool_calls:  # the model asked for something we cannot serve: leave a trace
        log.warning("router ignored tool calls: %s", response.tool_calls)
    if not text or "tool_call" in text:  # a tool call written as text must not reach the customer
        text = NO_ANSWER
    return {"route": "end", "messages": [AIMessage(text)]}


def proposed_actions(new_messages: list) -> dict | None:
    """What `propose_actions` returned this turn (the last call), read back from the tool result."""
    found = None
    for message in new_messages:
        if isinstance(message, ToolMessage) and message.name == "propose_actions":
            try:
                data = json.loads(message.text)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("batch_id"):
                found = data
    return found


def action_session(state: State, config: RunnableConfig) -> tuple[str, dict[str, str]]:
    """The language of this turn and what the code tells the actions server about the session."""
    language = detect_language(last_customer_text(state), state.get("language") or "es")
    return language, {
        "language": language,
        "thread_id": config["configurable"]["thread_id"],
        "signed_in": "1" if state.get("signed_in") else "0",
    }


async def refuse(state: State, config: RunnableConfig) -> dict:
    """The customer asked for something the bank never does on its own (a transfer, a refund, a
    change of phone...). The policy answers, through the same tool and audit as any proposal."""
    language, session = action_session(state, config)
    call = {"actions": [{"action": state["refused"], "params": {}}]}
    async with client_for("actions") as client:
        result = await client.call_tool(
            "propose_actions",
            call,
            meta={**session, "customer_id": state["customer_id"]},
            raise_on_error=False,
        )
    batch = result.structured_content
    if result.is_error or not isinstance(batch, dict) or not batch.get("batch_id"):
        log.warning("the policy could not answer %s: %s", state["refused"], result.content[0].text)
        return {"route": "handoff", "language": language, "skill": "account_actions"}
    update = {"skill": "account_actions", "language": language, "actions": batch}
    update["tools_used"] = ["propose_actions"]
    if batch.get("escalate"):
        return {"route": "handoff", **update}
    return {
        "route": "end",
        **update,
        "messages": [AIMessage(" ".join(item["text"] for item in batch["items"]))],
    }


async def skill_agent(state: State, config: RunnableConfig) -> dict:
    skill = load_skills()[state["skill"]]
    if skill.needs_sign_in and not state.get("signed_in"):
        return needs_sign_in()  # the router already checked; this is the second lock
    language, session = action_session(state, config)
    async with client_for(skill.mcp) as client:
        tools = [*await load_tools(client, state["customer_id"], session), request_human]
        agent = create_agent(
            chat_model("fast"),
            tools,
            system_prompt=f"{agent_prompt(routing=False)}\n\n## Active skill\n{skill.instructions}",
        )
        result = await agent.ainvoke(
            {"messages": state["messages"]}, config | {"recursion_limit": MAX_SKILL_STEPS}
        )
    new = result["messages"][len(state["messages"]) :]
    tools_used = [m.name for m in new if isinstance(m, ToolMessage)]
    actions = proposed_actions(new)
    update = {"tools_used": tools_used, "language": language, "actions": actions}
    if "request_human" in tools_used or (actions and actions.get("escalate")):
        return {"route": "handoff", **update}  # the policy sent part of it to a person
    text = new[-1].text.strip() if new else ""
    if skill.needs_sign_in and not actions and "?" not in text and "¿" not in text:
        # A skill that can change things ended with no proposal, no question and no person. What
        # the model said ("review and confirm below") would be about something that does not exist.
        log.warning("%s ended without a proposal; not repeating %r", skill.name, text[:120])
        text = UNPROPOSED
    return {"route": "end", **update, "messages": [AIMessage(text or NO_ANSWER)]}


def handoff(state: State) -> dict:
    case_file = {
        "customer_id": state.get("customer_id"),
        "request": last_customer_text(state),
        "skill": state.get("skill"),
        "tools_used": state.get("tools_used", []),
    }
    if state.get("actions"):  # what was proposed, and what the policy sent to a person and why
        case_file["actions"] = [
            {"action": i["action"], "status": i["status"], "text": i["text"]}
            for i in state["actions"]["items"]
        ]
        case_file["unresolved"] = state["actions"].get("escalate", [])
    return {"route": "end", "case_file": case_file, "messages": [AIMessage(HANDOFF)]}


def next_node(state: State) -> Literal["router", "skill_agent", "refuse", "handoff", "__end__"]:
    return END if state["route"] == "end" else state["route"]


def build_graph():
    graph = StateGraph(State)
    graph.add_node(guard)
    graph.add_node(router)
    graph.add_node(skill_agent)
    graph.add_node(refuse)
    graph.add_node(handoff)
    graph.add_edge(START, "guard")
    for node in ("guard", "router", "skill_agent", "refuse"):
        graph.add_conditional_edges(node, next_node)
    graph.add_edge("handoff", END)
    return graph.compile(checkpointer=InMemorySaver())


agent = build_graph()


def customer_message(text: str, image: tuple[str, str] | None = None) -> HumanMessage:
    """The customer's turn. A photo rides along as an image block; routing still reads `.text`."""
    if image is None:
        return HumanMessage(text)
    data, media_type = image
    return HumanMessage(
        content=[
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}},
        ]
    )


async def reply(
    message: str,
    thread_id: str,
    customer_id: str | None = None,
    image: tuple[str, str] | None = None,
) -> dict:
    turn: dict = {"messages": [customer_message(message, image)], "signed_in": bool(customer_id)}
    if customer_id:
        turn["customer_id"] = customer_id
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "callbacks": callbacks(),
        "metadata": {"langfuse_session_id": thread_id, "langfuse_user_id": customer_id},
    }
    try:
        state = await agent.ainvoke(turn, config)
    except Exception:  # the model or a tool is down: never a bare 500, always a safe hand-off
        log.exception("agent turn failed")
        case_file = {"customer_id": customer_id, "request": message, "reason": "assistant_error"}
        return {
            "reply": UNAVAILABLE,
            "customer_id": customer_id,
            "skill": None,
            "tools_used": [],
            "handoff": case_file,
            "actions": None,
        }
    return {
        "reply": state["messages"][-1].text,
        "customer_id": state.get("customer_id"),
        "skill": state.get("skill"),
        "tools_used": state.get("tools_used", []),
        "handoff": state.get("case_file"),
        "actions": state.get("actions"),
    }
