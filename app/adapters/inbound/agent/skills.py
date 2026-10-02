"""Skills are folders with a SKILL.md: YAML frontmatter (name, description, mcp) + instructions.

The router only sees the catalog (name + description); the body is loaded when the skill is used,
the same progressive disclosure Claude Code uses. Adding a skill = adding a folder.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

HERE = Path(__file__).parent


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    mcp: str
    instructions: str


@cache
def agent_prompt(routing: bool = True) -> str:
    """Persona and rules. The router also gets the routing section; a skill agent, which has no
    `use_skill` tool, must not see it."""
    text = (HERE / "AGENT.md").read_text()
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
        skills[meta["name"]] = Skill(meta["name"], meta["description"], meta["mcp"], body.strip())
    return skills


def catalog() -> str:
    return "\n".join(f"- {s.name}: {s.description}" for s in load_skills().values())
