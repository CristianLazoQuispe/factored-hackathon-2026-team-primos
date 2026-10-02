"""What the operator console sees: a mirror of every chat, kept in this process.

Like the agent's own memory it is lost when the instance stops, and it is only whole because the
API runs as a single instance (`--max-instances 1`).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Conversation:
    thread_key: str
    customer_id: str | None
    status: str = "bot"  # bot | waiting (the agent handed off) | human (an operator answers)
    case_file: dict | None = None
    messages: list[dict] = field(default_factory=list)

    def add(self, role: str, text: str) -> None:
        """`role` is customer, assistant or operator."""
        self.messages.append({"role": role, "text": text, "at": datetime.now(UTC).isoformat()})


conversations: dict[str, Conversation] = {}
