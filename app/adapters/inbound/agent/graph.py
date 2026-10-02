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
from app.adapters.inbound.agent.skills import agent_prompt, catalog, load_skills
from app.adapters.inbound.agent.tracing import callbacks
from app.adapters.outbound.llm import chat_model
from app.adapters.outbound.postgres.accounts import find_customer
from app.domain.routing import guess_skill

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
HANDOFF = (
    "Te comunico con una persona de nuestro equipo. Ya tiene tu caso, no tendrás que repetir "
    "nada. / Vou te transferir para uma pessoa da nossa equipe; ela já tem o seu caso."
)


class State(MessagesState):
    customer_id: str | None
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
    turn = {"skill": None, "tools_used": [], "case_file": None}
    if ASKS_FOR_HUMAN.search(text):
        return turn | {"route": "handoff"}
    if state.get("customer_id"):
        return turn | {"route": "router"}
    match = CUSTOMER_ID.search(text)
    if match and await find_customer(match.group(1).upper()):
        return turn | {"route": "router", "customer_id": match.group(1).upper()}
    reply = f"No encuentro el ID {match.group(1)}. {ASK_ID}" if match else ASK_ID
    return turn | {"route": "end", "messages": [AIMessage(reply)]}


async def router(state: State) -> dict:
    system = f"{agent_prompt()}\n\n## Skills\n{catalog()}"
    model = chat_model("fast").bind_tools([use_skill, request_human])
    response = await model.ainvoke([SystemMessage(system), *state["messages"]])
    for call in response.tool_calls:
        if call["name"] == "request_human":
            return {"route": "handoff"}
        if call["name"] == "use_skill" and call["args"].get("name") in load_skills():
            return {"route": "skill_agent", "skill": call["args"]["name"]}
    text = response.text.strip()
    skill = guess_skill(last_customer_text(state))
    if skill in load_skills():  # the model did not route an obvious request: code does
        log.info("router fallback -> %s (model said %r)", skill, text[:80])
        return {"route": "skill_agent", "skill": skill}
    if response.tool_calls:  # the model asked for something we cannot serve: leave a trace
        log.warning("router ignored tool calls: %s", response.tool_calls)
    if not text or "tool_call" in text:  # a tool call written as text must not reach the customer
        text = NO_ANSWER
    return {"route": "end", "messages": [AIMessage(text)]}


async def skill_agent(state: State, config: RunnableConfig) -> dict:
    skill = load_skills()[state["skill"]]
    async with client_for(skill.mcp) as client:
        tools = [*await load_tools(client, state["customer_id"]), request_human]
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
    if "request_human" in tools_used:
        return {"route": "handoff", "tools_used": tools_used}
    text = new[-1].text.strip() if new else ""
    return {"route": "end", "tools_used": tools_used, "messages": [AIMessage(text or NO_ANSWER)]}


def handoff(state: State) -> dict:
    case_file = {
        "customer_id": state.get("customer_id"),
        "request": last_customer_text(state),
        "skill": state.get("skill"),
        "tools_used": state.get("tools_used", []),
    }
    return {"route": "end", "case_file": case_file, "messages": [AIMessage(HANDOFF)]}


def next_node(state: State) -> Literal["router", "skill_agent", "handoff", "__end__"]:
    return END if state["route"] == "end" else state["route"]


def build_graph():
    graph = StateGraph(State)
    graph.add_node(guard)
    graph.add_node(router)
    graph.add_node(skill_agent)
    graph.add_node(handoff)
    graph.add_edge(START, "guard")
    for node in ("guard", "router", "skill_agent"):
        graph.add_conditional_edges(node, next_node)
    graph.add_edge("handoff", END)
    return graph.compile(checkpointer=InMemorySaver())


agent = build_graph()


async def reply(message: str, thread_id: str, customer_id: str | None = None) -> dict:
    turn: dict = {"messages": [HumanMessage(message)]}
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
        }
    return {
        "reply": state["messages"][-1].text,
        "customer_id": state.get("customer_id"),
        "skill": state.get("skill"),
        "tools_used": state.get("tools_used", []),
        "handoff": state.get("case_file"),
    }
