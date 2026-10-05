# ruff: noqa: E501  (the made-up values and the expected pieces of HTML stay on one line each)
"""The email template: it renders, nothing from data can break out of it, every slot is documented."""

import re
from pathlib import Path

import pytest

from app.adapters.outbound.email_template import renderer as r

HERE = Path(r.__file__).parent
LOGO = str(HERE / "assets" / "logo_email.png")
EXAMPLES = sorted((HERE / "examples").glob("*.md"))
TEMPLATE = (HERE / "message.md").read_text()


def generic(**rest) -> dict:
    return {"kind": "generic", "language": "es", "subject": "Asunto", "preheader": "Pre", "eyebrow": "Etiqueta",
            "title": "Título", "intro": "Texto.", **rest}  # fmt: skip


def render(**rest) -> dict:
    return r.render(r.fill(TEMPLATE, generic(**rest)), LOGO)


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.stem)
def test_every_example_renders_complete(example):
    out = r.render(example.read_text(), LOGO)
    assert (
        "{{" not in out["html"]
        and "[!" not in out["html"]
        and "<!-- " not in out["html"].split("</head>")[1]
    )
    assert "quipu" in out["html"] and 'width="220"' in out["html"]
    assert "**" not in out["text"] and "[!" not in out["text"] and out["text"].strip()


def test_a_value_from_data_cannot_bring_html():
    out = render(
        first_name="<img src=x onerror=alert(1)>",
        intro="Comercio: <script>alert(1)</script> y **negrita** [x](http://evil.test)",
    )
    body = out["html"]
    assert (
        "<script" not in body
        and "<img src=x" not in body
        and "onerror" not in re.sub(r"&lt;.*?&gt;", "", body)
    )
    assert "&lt;script&gt;" in body, "shown as text, not run"
    assert (
        "http://evil.test" not in body.replace("&amp;", "&")
        or "<a " not in body.split("evil.test")[0][-200:]
    )


def test_a_value_cannot_open_bold_or_a_link_or_a_heading():
    out = render(intro="# no soy un título **ni negrita** [ni enlace](https://x.test)")
    body = out["html"].split('bgcolor="#F4F8F8"')[0]  # the footer's own bold is not the message's
    assert "<h2" not in body.split("Título")[1]
    assert body.count("<strong") == 0 and 'href="https://x.test"' not in body


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<b>x</b>",
        "ftp://x.test",
        "//x.test",
        "mailto:a@b.test",
    ],
)
def test_only_http_and_https_make_a_button(url):
    out = render(button_label="Entrar", button_url=url)
    assert (
        "Entrar" not in out["html"].split("Texto.")[1]
        or 'href="' not in out["html"].split("Texto.")[1]
    )


def test_an_https_url_makes_a_button_and_is_quoted():
    out = render(button_label="Entrar", button_url='https://x.test/a?b=1&c="2"')
    assert 'href="https://x.test/a?b=1&amp;c=&quot;2&quot;"' in out["html"]


def test_the_subject_and_the_preheader_are_text_in_the_page():
    out = r.render(
        r.fill(TEMPLATE, generic(subject="<b>Hola</b> & adiós", preheader='"x" <i>')), LOGO
    )
    assert "<title>&lt;b&gt;Hola&lt;/b&gt; &amp; adiós</title>" in out["html"]
    assert "<i>" not in out["html"]


def test_a_quote_in_the_subject_does_not_break_the_front_matter():
    out = r.render(r.fill(TEMPLATE, generic(subject='Tu "resumen" de saldos')), LOGO)
    assert out["subject"] == 'Tu "resumen" de saldos'


def test_blocks_appear_only_when_their_slot_has_a_value():
    plain = render()["text"]
    assert "Hola," in plain and "Hola Ana" not in plain
    assert "Hola Ana," in render(first_name="Ana")["text"]
    html = render(highlight_label="Monto", highlight_value="10 USD")["html"]
    assert "10 USD" in html and "Monto" in html
    assert "10 USD" not in render()["html"]
    assert render()["html"].count("border-left:5px") == 0


def test_items_become_rows_with_the_value_on_the_right():
    items = "- **Cuenta ·· 1**: 5.00 USD\n- **Tarjeta ·· 2**: 7.00 USD\n  Límite 9.00 USD"
    html = render(items=items)["html"]
    assert html.count('align="right" valign="top"') == 2
    assert "Límite 9.00 USD" in html


def test_markdown_slots_are_trusted_only_because_the_code_wrote_them():
    """`items` is Markdown by design; the values the code puts inside it must be escaped by the code."""
    item = f"- **{r.md_escape('Uber * Trip')}**: {r.md_escape('-312.40 MXN')}"
    html = render(items=item)["html"]
    assert "Uber * Trip" in html and html.count("<em") == 0


def test_the_footer_follows_the_language():
    assert (
        "Tu banco, conversando" in r.render(r.fill(TEMPLATE, generic(language="es")), LOGO)["html"]
    )
    assert (
        "Seu banco, conversando" in r.render(r.fill(TEMPLATE, generic(language="pt")), LOGO)["html"]
    )
    assert "Tu banco" in r.render(r.fill(TEMPLATE, generic(language="fr")), LOGO)["html"], (
        "unknown: Spanish"
    )


def test_the_demo_note_goes_only_with_demo_mail():
    text = r.fill(TEMPLATE, generic())
    assert "datos sintéticos" in r.render(text, LOGO, demo=True)["html"]
    assert "datos sintéticos" not in r.render(text, LOGO, demo=False)["html"]


def test_the_plain_text_is_readable():
    text = r.render((HERE / "examples" / "balances.md").read_text(), LOGO)["text"]
    assert "ESTOS SON TUS SALDOS" in text and "Cuenta Corriente ·· 1650: 2,693.23 USD" in text
    assert "Hablar con quipu (https://example.com/chat)" in text


def test_every_slot_of_the_template_is_documented():
    readme = (HERE / "README.md").read_text()
    slots = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", TEMPLATE))
    missing = {s for s in slots if f"`{s}`" not in readme}
    assert not missing, f"slots without documentation: {sorted(missing)}"


def test_the_logo_is_twice_what_is_shown_and_light():
    import struct

    data = (HERE / "assets" / "logo_email.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])  # the IHDR chunk
    assert width == 440 and 150 < height < 190 and len(data) < 60_000


def test_a_url_with_special_characters_reaches_the_button_whole():
    out = render(button_label="Entrar", button_url="https://x.test/a_b*c?d=1&e=2#f(g)")
    assert 'href="https://x.test/a_b*c?d=1&amp;e=2#f(g)"' in out["html"]


def test_a_bar_inside_a_label_does_not_cut_it():
    out = render(highlight_label="Entradas | salidas", highlight_value="10 USD")
    assert "Entradas | salidas" in out["html"] and "10 USD" in out["html"]
    out = render(button_label="Sí | no", button_url="https://x.test")
    assert "Sí | no" in out["html"]


def test_the_internal_notes_of_the_layout_do_not_travel_in_the_email():
    html = render()["html"]
    assert "<!--" not in html and "Header: the logo" not in html


def test_the_plain_text_reads_the_figure_and_the_button_as_sentences():
    text = render(
        highlight_label="Monto",
        highlight_value="10 USD",
        button_label="Entrar",
        button_url="https://x.test",
    )["text"]
    assert "Monto: 10 USD" in text and "Entrar (https://x.test)" in text and "|" not in text


def test_raw_html_is_refused_even_in_the_slots_the_code_writes():
    """The second barrier: if the code forgets to escape a value inside `items` or `table`, it still
    cannot become HTML."""
    out = render(
        items="- **<script>x</script>**: <b>y</b>",
        table="| A |\n|---|\n| <img src=x onerror=alert(1)> |",
    )
    body = out["html"]
    assert "<script" not in body and "<b>y" not in body and "<img src=x" not in body
    assert "&lt;script&gt;" in body
