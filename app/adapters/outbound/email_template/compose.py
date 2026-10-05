"""From the content of a message (app/domain/email_content.py) to the HTML the customer sees,
with the template of this folder. The plain-text part is not made here: the domain makes it from
the same content, so both carry the same figures.

Everything that comes from data (a name, an amount, a merchant) is escaped before it enters the
Markdown. Raw HTML is refused by the renderer even if the code forgets. See README.md.
"""

from functools import cache
from pathlib import Path

from app.adapters.outbound.email_template import renderer
from app.domain.email_content import EmailContent

HERE = Path(__file__).parent
LOGO_CID = (
    "quipu-logo"  # `<img src="cid:quipu-logo">` in the HTML, and the image attached to the message
)


@cache
def template() -> str:
    return (HERE / "message.md").read_text()


@cache
def logo_png() -> bytes:
    return (HERE / "assets" / "logo_email.png").read_bytes()


def items_markdown(content: EmailContent) -> str:
    """The sections as rows: `- **label**: value`, and a smaller line when there is a detail."""
    escape = renderer.md_escape
    blocks = []
    for section in content.sections:
        lines = [f"## {escape(section.title)}"]
        for row in section.rows:
            line = f"- **{escape(row.label)}**: {escape(row.value)}"
            lines.append(f"{line}\n  {escape(row.detail)}" if row.detail else line)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def html_for(content: EmailContent) -> str:
    """The message as a page. The logo is `cid:quipu-logo`: the mailer attaches it."""
    slots = {
        "kind": content.kind,
        "language": content.language,
        "subject": content.subject,
        "preheader": content.preheader,
        "eyebrow": content.eyebrow,
        "title": content.title,
        "first_name": content.greeting_name,
        "intro": content.intro,
        "highlight_label": content.highlight_label,
        "highlight_value": content.highlight_value,
        "items": items_markdown(content),
        "notice": content.notice,
    }
    filled = renderer.fill(template(), slots)
    return renderer.render(filled, logo_src=f"cid:{LOGO_CID}", demo=True)["html"]
