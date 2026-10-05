"""Skills are folders with a SKILL.md: YAML frontmatter (name, description, mcp) + instructions.

The router only sees the catalog (name + description); the body is loaded when the skill is used,
the same progressive disclosure Claude Code uses. Adding a skill = adding a folder.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from app.config import get_settings

HERE = Path(__file__).parent


ACTIONS_BLOCK = re.compile(r"<!-- (if|unless):actions -->\n(.*?)<!-- endif -->\n", re.DOTALL)


def with_actions(text: str) -> str:
    """Keep the parts written for when the customer can ask for actions (`if:actions`) or for when
    they cannot (`unless:actions`), and drop the others. With actions off the prompt says what it
    said before they existed. Each marker sits on a line of its own."""
    enabled = get_settings().actions_enabled
    return ACTIONS_BLOCK.sub(lambda m: m.group(2) if (m.group(1) == "if") == enabled else "", text)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    mcp: str
    instructions: str
    needs_sign_in: bool = False  # only for a customer the token proved, not one who typed an ID


@cache
def agent_prompt(routing: bool = True) -> str:
    """Persona and rules. The router also gets the routing section; a skill agent, which has no
    `use_skill` tool, must not see it."""
    text = with_actions((HERE / "AGENT.md").read_text())
    if routing:
        return text
    before, _, rest = text.partition("## How to route")
    return before + "## Rules\n" + rest.partition("## Other rules")[2].lstrip("\n")


@cache
def load_skills() -> dict[str, Skill]:
    skills = {}
    for path in sorted((HERE / "skills").glob("*/SKILL.md")):
        _, frontmatter, body = path.read_text().split("---", 2)
        meta = yaml.safe_load(frontmatter)
        if meta.get("requires") == "actions" and not get_settings().actions_enabled:
            continue
        if not getattr(get_settings(), meta.get("setting", ""), True):  # switched off by its flag
            continue
        skills[meta["name"]] = Skill(
            meta["name"],
            meta["description"],
            meta["mcp"],
            with_actions(body).strip(),
            needs_sign_in=meta.get("requires") == "actions" or bool(meta.get("sign_in")),
        )
    return skills


def available(signed_in: bool) -> dict[str, Skill]:
    """The skills this conversation may use. A customer who only typed an ID gets no skill that
    changes anything: a customer number alone does not prove who is writing."""
    return {n: s for n, s in load_skills().items() if signed_in or not s.needs_sign_in}


def catalog(signed_in: bool = True) -> str:
    return "\n".join(f"- {s.name}: {s.description}" for s in available(signed_in).values())
