# ruff: noqa: E501  (the styles of an e-mail stay on one line each, to be read as such)
"""Reference renderer for quipu's emails: Markdown (message.md) + layout.html -> HTML and plain text.

It is a reference, not the code that goes to production: it shows what the template needs from the code
that will use it, and it is how the previews were drawn. Needs `markdown-it-py` (pure Python).

    python -m app.adapters.outbound.email_template.renderer   # draws every example into preview/

What the code that sends mail must do, and this file already does:
  * fill `{{ slot }}` and `<!-- if:slot -->` / `<!-- unless:slot -->` blocks of message.md;
  * escape every value that comes from data (a merchant name, a customer name) before it enters the
    Markdown, except the slots that are Markdown the code itself wrote (`items`, `table`, `closing`);
  * never let HTML through: raw HTML in the Markdown is switched off;
  * only `http` and `https` links become links or buttons;
  * produce the plain-text part of the message from the same Markdown.
"""

import html
import json
import re
import sys
from pathlib import Path

from markdown_it import MarkdownIt

HERE = Path(__file__).parent
MARKDOWN_SLOTS = {"items", "table", "closing"}  # already Markdown, written by code
SAFE_LINK = re.compile(r"^https?://", re.IGNORECASE)

FOOTER = {
    "es": (
        "Quipu · Tu banco, conversando.",
        "Recibiste este correo porque lo pediste en el chat.",
        "Mensaje de demostración con datos sintéticos.",
    ),
    "pt": (
        "Quipu · Seu banco, conversando.",
        "Você recebeu este e-mail porque o pediu no chat.",
        "Mensagem de demonstração com dados sintéticos.",
    ),
}

# ------------------------------------------------------------------ filling the template


def md_escape(value: object) -> str:
    """A value from data, made safe to sit inside Markdown: no emphasis, no links, no headings."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~&])", r"\\\1", str(value))


def md_unescape(value: str) -> str:
    """The reverse of md_escape, for the one place that reads a value back out of the Markdown: a URL."""
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|<>~&])", r"\1", value)


def split_pipe(text: str) -> tuple[str, str]:
    r"""`label | value` at the first `|` that is not escaped (`\|` belongs to the text)."""
    parts = re.split(r"(?<!\\)\|", text, maxsplit=1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (text.strip(), "")


def front_escape(value: object) -> str:
    """A value inside a double-quoted front-matter line."""
    return json.dumps(str(value), ensure_ascii=False)[1:-1]


def fill(template: str, ctx: dict[str, object]) -> str:
    """Resolve the blocks, then the slots. A slot with no value is an empty string."""

    def block(kind: str, text: str) -> str:
        pattern = re.compile(
            rf"<!-- {kind}:(\w+) -->\n?(.*?)<!-- end{'if' if kind == 'if' else 'unless'} -->\n?",
            re.DOTALL,
        )
        return pattern.sub(
            lambda m: m.group(2) if bool(ctx.get(m.group(1))) == (kind == "if") else "", text
        )

    text = block("unless", block("if", template))
    head, sep, body = text.partition("\n---\n")  # the front matter ends at the second ---
    if not sep:
        head, body = "", text

    def slot(escape):
        return lambda m: (
            str(ctx.get(m.group(1), ""))
            if m.group(1) in MARKDOWN_SLOTS
            else escape(ctx.get(m.group(1), ""))
        )

    pattern = re.compile(r"\{\{\s*(\w+)\s*\}\}")
    head = pattern.sub(slot(front_escape), head)
    body = pattern.sub(slot(md_escape), body)
    return head + sep + body if sep else body


def parse(text: str) -> tuple[dict[str, str], str]:
    """Front matter (`key: "value"` lines between two `---`) and the Markdown that follows."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        meta[key.strip()] = json.loads(value) if value.startswith('"') else value
    return meta, match.group(2)


# ------------------------------------------------------------------ Markdown -> email HTML

NAVY, TEAL_DARK, TEXT, MUTED, LINE = "#061319", "#17766A", "#28383F", "#5B6B70", "#E3EBEB"
md = MarkdownIt("commonmark", {"html": False}).enable("table")


def inline(token) -> str:
    out = md.renderer.renderInline(token.children or [], md.options, {})
    out = out.replace("<strong>", f'<strong style="color:{NAVY};">').replace(
        "<code>",
        '<code style="background:#EEF3F3;padding:1px 5px;border-radius:4px;font-size:90%;">',
    )
    return re.sub(
        r'<a href="([^"]*)"',
        lambda m: (
            f'<a style="color:{TEAL_DARK};text-decoration:underline;" href="{m.group(1)}"'
            if SAFE_LINK.match(html.unescape(m.group(1)))
            else "<a"
        ),
        out,
    )


def title(text: str) -> str:
    return f'<h1 style="margin:0 0 16px 0;font-size:27px;line-height:1.25;font-weight:800;color:{NAVY};">{text}</h1>'


def heading(text: str) -> str:
    return f'<h2 style="margin:28px 0 4px 0;font-size:12px;line-height:18px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:{MUTED};">{text}</h2>'


def paragraph(text: str) -> str:
    return f'<p style="margin:0 0 16px 0;">{text}</p>'


def rule() -> str:
    return f'<hr style="border:0;border-top:1px solid {LINE};margin:24px 0;">'


def rows(items: list[tuple[str, str, str]]) -> str:
    cells = []
    for label, value, detail in items:
        small = (
            f'<br><span style="font-size:13px;line-height:1.5;color:{MUTED};">{detail}</span>'
            if detail
            else ""
        )
        cells.append(
            f'<tr><td style="padding:13px 0;border-bottom:1px solid {LINE};font-size:15px;line-height:1.45;color:{TEXT};">{label}{small}</td>'
            f'<td align="right" valign="top" style="padding:13px 0 13px 18px;border-bottom:1px solid {LINE};font-size:16px;font-weight:700;color:{NAVY};white-space:nowrap;">{value}</td></tr>'
        )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 18px 0;border-collapse:collapse;">{"".join(cells)}</table>'


def highlight(label: str, value: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 22px 0;">'
        f'<tr><td bgcolor="#EAF6F4" style="background:#EAF6F4;border-left:5px solid #60C0B4;border-radius:10px;padding:18px 22px;">'
        f'<div style="font-size:12px;line-height:16px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:{TEAL_DARK};">{label}</div>'
        f'<div style="font-size:32px;line-height:1.2;font-weight:800;color:{NAVY};margin-top:6px;">{value}</div></td></tr></table>'
    )


def notice(text: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 22px 0;">'
        '<tr><td bgcolor="#FFF6E0" style="background:#FFF6E0;border-left:5px solid #E3A72F;border-radius:10px;padding:14px 20px;font-size:14px;line-height:1.55;color:#5C4300;">'
        f"{text}</td></tr></table>"
    )


def button(label: str, url: str) -> str:
    if not SAFE_LINK.match(url):
        return ""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:10px 0 24px 0;"><tr>'
        f'<td bgcolor="#60C0B4" style="background:#60C0B4;border-radius:10px;"><a href="{html.escape(url, quote=True)}" '
        f'style="display:inline-block;padding:14px 30px;font-size:16px;font-weight:700;color:{NAVY};text-decoration:none;">{label}</a></td></tr></table>'
    )


def table(tokens: list, start: int) -> tuple[str, int]:
    out, i, head = [], start, True
    while tokens[i].type != "table_close":
        t = tokens[i]
        if t.type == "tbody_open":
            head = False
        if t.type == "tr_open":
            cells = []
            i += 1
            while tokens[i].type != "tr_close":
                if tokens[i].type in ("th_open", "td_open"):
                    align = ""
                    style = tokens[i].attrGet("style") or ""
                    if "right" in style:
                        align = "right"
                    elif "center" in style:
                        align = "center"
                    text = inline(tokens[i + 1])
                    if head:
                        css = f"padding:9px 10px;background:#F1F6F6;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:{MUTED};border-bottom:1px solid {LINE};"
                    else:
                        css = f"padding:11px 10px;font-size:14px;color:{TEXT};border-bottom:1px solid {LINE};"
                    cells.append(f'<td align="{align or "left"}" style="{css}">{text}</td>')
                i += 1
            out.append(f"<tr>{''.join(cells)}</tr>")
        i += 1
    html_table = f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 20px 0;border-collapse:collapse;">{"".join(out)}</table>'
    return html_table, i


def split_item(token) -> tuple[str, str, str]:
    """`**Label**: value` and, on the next line, a detail. The label is what is in bold."""
    # the parser puts an empty text token before the bold one: it is not part of the message
    kids = [k for k in (token.children or []) if not (k.type == "text" and k.content == "")]
    label_end = next((i for i, k in enumerate(kids) if k.type == "strong_close"), -1)
    if label_end < 0 or kids[0].type != "strong_open":
        return md.renderer.renderInline(kids, md.options, {}), "", ""
    render = lambda part: md.renderer.renderInline(part, md.options, {})  # noqa: E731
    label = render(kids[1:label_end])
    rest = kids[label_end + 1 :]
    cut = next((i for i, k in enumerate(rest) if k.type == "softbreak"), len(rest))
    value = render(rest[:cut]).lstrip(":").strip()
    detail = render(rest[cut + 1 :]).strip()
    return label, value, detail


def render_body(markdown: str) -> str:
    tokens = md.parse(markdown)
    out, i, seen_title = [], 0, False
    while i < len(tokens):
        t = tokens[i]
        if t.type == "heading_open":
            text = inline(tokens[i + 1])
            out.append(title(text) if t.tag == "h1" and not seen_title else heading(text))
            seen_title = seen_title or t.tag == "h1"
            i += 3
        elif t.type == "paragraph_open":
            out.append(paragraph(inline(tokens[i + 1])))
            i += 3
        elif t.type == "bullet_list_open":
            items, i = [], i + 1
            while tokens[i].type != "bullet_list_close":
                if tokens[i].type == "inline":
                    items.append(split_item(tokens[i]))
                i += 1
            out.append(rows(items))
            i += 1
        elif t.type == "blockquote_open":
            inner = next(k for k in tokens[i:] if k.type == "inline")
            kind = re.match(r"^\[!(\w+)\]\s*(.*)$", inner.content, re.DOTALL)
            while tokens[i].type != "blockquote_close":
                i += 1
            i += 1
            if not kind:
                out.append(notice(inline(inner)))
                continue
            name, rest = kind.group(1).upper(), kind.group(2).strip()
            left, right = split_pipe(rest)
            safe = lambda s: md.renderInline(s)  # noqa: E731
            if name == "HIGHLIGHT":
                out.append(highlight(safe(left), safe(right)))
            elif name == "BUTTON":
                out.append(button(safe(left), md_unescape(right)))
            else:
                out.append(notice(safe(rest)))
        elif t.type == "table_open":
            piece, i = table(tokens, i)
            out.append(piece)
            i += 1
        elif t.type == "hr":
            out.append(rule())
            i += 1
        else:
            i += 1
    return "\n".join(out)


def plain_text(markdown: str) -> str:
    """The text/plain part: the same message, readable without HTML."""
    lines = []
    for line in markdown.splitlines():
        line = re.sub(r"^# (.*)$", lambda m: m.group(1).upper(), line)
        line = re.sub(r"^## (.*)$", lambda m: f"\n{m.group(1).upper()}", line)
        line = re.sub(r"^> \[!HIGHLIGHT\]\s*(.*?)\s*(?<!\\)\|\s*(.*)$", r"\1: \2", line)
        line = re.sub(r"^> \[!BUTTON\]\s*(.*?)\s*(?<!\\)\|\s*(.*)$", r"\1 (\2)", line)
        line = re.sub(r"^> \[!NOTICE\]\s*", "", line)
        line = re.sub(r"^\s*[-*] \*\*(.*?)\*\*:?\s*", r"- \1: ", line)
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", line)
        line = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|<>~&])", r"\1", line)
        lines.append(line.rstrip(" -:") if line.rstrip().endswith(": ") else line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def render(markdown_with_front_matter: str, logo_src: str, demo: bool = True) -> dict[str, str]:
    meta, body_md = parse(markdown_with_front_matter)
    lang = meta.get("language", "es") if meta.get("language") in FOOTER else "es"
    brand, why, demo_note = FOOTER[lang]
    footer = f'<strong style="color:{MUTED};">{brand}</strong><br>{why}' + (
        f"<br>{demo_note}" if demo else ""
    )
    layout = re.sub(
        r"<!--.*?-->\n?", "", (HERE / "layout.html").read_text(), flags=re.DOTALL
    )  # notes for us
    values = {
        "lang": lang,
        "subject": html.escape(meta.get("subject", "quipu")),
        "preheader": html.escape(meta.get("preheader", "")),
        "eyebrow": html.escape(meta.get("eyebrow", "")),
        "logo_src": html.escape(logo_src, quote=True),
        "body": render_body(body_md),
        "footer": footer,
    }
    page = re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: values.get(m.group(1), ""), layout)
    return {"html": page, "text": plain_text(body_md), "subject": meta.get("subject", "quipu")}


if __name__ == "__main__":
    out = HERE / "preview"
    out.mkdir(exist_ok=True)
    for example in sorted((HERE / "examples").glob("*.md")):
        result = render(
            example.read_text(), logo_src=str((HERE / "assets" / "logo_email.png").resolve())
        )
        (out / f"{example.stem}.html").write_text(result["html"])
        (out / f"{example.stem}.txt").write_text(result["text"])
        print("ok", example.name, "->", result["subject"])
    sys.exit(0)
