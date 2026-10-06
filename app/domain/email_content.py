# ruff: noqa: E501  (each sentence the customer reads stays on one line, so a person can review it)
"""What an e-mail says, before it is a page: the content of the balances summary, of the receipt of a
transfer and of the receipt of an inquiry, built from verified data only.

Pure rules: no database, no template, no mail server. The same content gives the plain-text part of the
message here (`content_text`, which is also what the outbox keeps) and the HTML part in
`app/adapters/outbound/email_template`, so the two always carry the same figures.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from app.domain.action_text import money
from app.domain.actions import CARD_TYPES
from app.domain.transfers import ACCOUNT_TYPES


@dataclass(frozen=True)
class Row:
    label: str
    value: str
    detail: str = ""  # a smaller line under the label


@dataclass(frozen=True)
class Section:
    title: str
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class EmailContent:
    kind: str  # "balances" | "transfer_receipt" | "case_receipt": also the name of the template in the outbox
    language: str  # "es" | "pt"
    subject: str
    preheader: str  # the line the inbox shows beside the subject
    eyebrow: str
    title: str
    intro: str
    highlight_label: str = ""  # the big figure; none if the label is empty
    highlight_value: str = ""
    sections: tuple[Section, ...] = ()
    notice: str = ""  # a warning, in its own panel
    greeting_name: str = ""


FOOTER = {
    "es": "Mensaje de demostración con datos sintéticos.",
    "pt": "Mensagem de demonstração com dados sintéticos.",
}
HELLO = {"es": "Hola", "pt": "Olá"}


def language_of(value: object) -> str:
    """Only Spanish and Portuguese are written; anything else is Spanish."""
    return "pt" if value == "pt" else "es"


def last4(value: object) -> str:
    return str(value) if value else "????"


# ------------------------------------------------------------------ the balances summary

BALANCES = {
    "es": {
        "subject": "Tu resumen de saldos · quipu",
        "eyebrow": "Resumen de saldos",
        "title": "Estos son tus saldos",
        "intro": "Aquí tienes lo que pediste en el chat, con los datos de hoy.",
        "highlight": "Disponible en tus cuentas",
        "accounts": "Cuentas",
        "cards": "Tarjetas",
        "others": "Otros productos",
        "limit": "Límite",
        "none": "No encontramos productos para mostrarte.",
    },
    "pt": {
        "subject": "Seu resumo de saldos · quipu",
        "eyebrow": "Resumo de saldos",
        "title": "Estes são os seus saldos",
        "intro": "Aqui está o que você pediu no chat, com os dados de hoje.",
        "highlight": "Disponível nas suas contas",
        "accounts": "Contas",
        "cards": "Cartões",
        "others": "Outros produtos",
        "limit": "Limite",
        "none": "Não encontramos produtos para mostrar.",
    },
}


def _product_row(product: dict[str, Any], limit_word: str) -> Row:
    currency = product.get("currency")
    detail = f"{limit_word} {money(product['limit'], currency)}" if product.get("limit") else ""
    label = f"{product['product_type']} ·· {last4(product.get('last4'))}"
    return Row(label, money(product.get("balance"), currency), detail)


def balances_content(language: str, products: list[dict[str, Any]]) -> EmailContent:
    """The customer's products as they are now. The big figure is the money in their accounts, and only
    when all of them are in one currency: adding pesos to dollars would say something false."""
    lang = language_of(language)
    words = BALANCES[lang]
    accounts = [p for p in products if p["product_type"] in ACCOUNT_TYPES]
    cards = [p for p in products if p["product_type"] in CARD_TYPES]
    others = [p for p in products if p not in accounts and p not in cards]

    sections = tuple(
        Section(title, tuple(_product_row(p, words["limit"]) for p in group))
        for title, group in ((words["accounts"], accounts), (words["cards"], cards), (words["others"], others))
        if group
    )  # fmt: skip
    currencies = {p.get("currency") for p in accounts}
    highlight_value = ""
    if accounts and len(currencies) == 1:
        highlight_value = money(sum(p.get("balance") or 0 for p in accounts), currencies.pop())
    return EmailContent(
        kind="balances",
        language=lang,
        subject=words["subject"],
        preheader=_preheader(lang, highlight_value),
        eyebrow=words["eyebrow"],
        title=words["title"],
        intro=words["intro"] if sections else words["none"],
        highlight_label=words["highlight"] if highlight_value else "",
        highlight_value=highlight_value,
        sections=sections,
    )


def _preheader(lang: str, total: str) -> str:
    if not total:
        return "Tus saldos de hoy." if lang == "es" else "Seus saldos de hoje."
    return (
        f"Disponible en tus cuentas: {total}."
        if lang == "es"
        else f"Disponível nas suas contas: {total}."
    )


# ------------------------------------------------------------------ the receipt of a transfer

RECEIPT = {
    "es": {
        "eyebrow": "Comprobante",
        "titles": {
            "own_accounts": "Tu transferencia entre cuentas se realizó",
            "pay_debt": "Tu pago se realizó",
            "third_party": "Tu transferencia se realizó",
            "pay_service": "Tu pago de servicio se realizó",
        },
        "subjects": {
            "own_accounts": "Tu transferencia de {amount} se realizó · quipu",
            "pay_debt": "Tu pago de {amount} se realizó · quipu",
            "third_party": "Tu transferencia de {amount} se realizó · quipu",
            "pay_service": "Tu pago de servicio de {amount} se realizó · quipu",
        },
        "intro": "Confirmaste esta operación en el chat y el banco la ejecutó. Este es tu comprobante.",
        "paid": "Monto pagado",
        "sent": "Monto transferido",
        "section": "Detalle",
        "from": "Desde",
        "to": "Hacia",
        "when": "Fecha",
        "reference": "Referencia",
        "balance": "Nuevo saldo de la cuenta de origen",
        "notice": "Si no reconoces esta operación, escríbele a quipu ahora mismo para que una persona la revise.",
        "account": "Cuenta",
        "service": "Servicio",
    },
    "pt": {
        "eyebrow": "Comprovante",
        "titles": {
            "own_accounts": "Sua transferência entre contas foi realizada",
            "pay_debt": "Seu pagamento foi realizado",
            "third_party": "Sua transferência foi realizada",
            "pay_service": "Seu pagamento de serviço foi realizado",
        },
        "subjects": {
            "own_accounts": "Sua transferência de {amount} foi realizada · quipu",
            "pay_debt": "Seu pagamento de {amount} foi realizado · quipu",
            "third_party": "Sua transferência de {amount} foi realizada · quipu",
            "pay_service": "Seu pagamento de serviço de {amount} foi realizado · quipu",
        },
        "intro": "Você confirmou esta operação no chat e o banco a executou. Este é o seu comprovante.",
        "paid": "Valor pago",
        "sent": "Valor transferido",
        "section": "Detalhe",
        "from": "De",
        "to": "Para",
        "when": "Data",
        "reference": "Referência",
        "balance": "Novo saldo da conta de origem",
        "notice": "Se você não reconhece esta operação, escreva para a quipu agora para que uma pessoa a revise.",
        "account": "Conta",
        "service": "Serviço",
    },
}
PAYMENTS = (
    "pay_debt",
    "pay_service",
)  # the money goes to settle something: "paid", not "transferred"


def reference_of(transfer_id: str) -> str:
    """Eight characters of the id, in two groups: enough to quote on a call, never the whole id."""
    plain = str(transfer_id).replace("-", "").upper()[:8]
    return f"{plain[:4]}-{plain[4:]}"


def when_of(executed_at: str) -> str:
    moment = datetime.fromisoformat(executed_at)
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return f"{moment:%Y-%m-%d %H:%M} UTC"


def _party(side: dict[str, Any], words: dict[str, Any]) -> tuple[str, str]:
    """A side of the operation as (what to call it, a smaller line). A product is its type and last four
    digits; another customer is a first name and an initial; a bill is the biller and its reference."""
    number = f"·· {side['last4']}" if side.get("last4") else ""
    if side.get("service"):
        return side.get("name") or words[
            "service"
        ], f"{words['service']} {side['service']} · {side.get('reference') or ''}".strip(" ·")
    if side.get("name"):
        return side["name"], f"{words['account']} {number}".strip() if number else ""
    return f"{side.get('product_type') or words['account']} {number}".strip(), ""


def transfer_receipt_content(
    language: str, receipt: dict[str, Any], first_name: str = ""
) -> EmailContent:
    """The receipt of what the bank executed: the `receipt` that the confirmation returns, and nothing else."""
    lang = language_of(language)
    words = RECEIPT[lang]
    kind = receipt["kind"] if receipt.get("kind") in words["titles"] else "third_party"
    amount = money(receipt["amount"], receipt["currency"])
    origin, destination = receipt["origin"], receipt["destination"]
    from_name, from_detail = _party(origin, words)
    to_name, to_detail = _party(destination, words)
    rows = [
        Row(words["from"], from_name, from_detail),
        Row(words["to"], to_name, to_detail),
        Row(words["when"], when_of(receipt["executed_at"])),
        Row(words["reference"], reference_of(receipt["transfer_id"])),
    ]
    if origin.get("new_balance") is not None:
        rows.append(Row(words["balance"], money(origin["new_balance"], receipt["currency"])))
    return EmailContent(
        kind="transfer_receipt",
        language=lang,
        subject=words["subjects"][kind].format(amount=amount),
        preheader=f"{amount} · {to_name}",
        eyebrow=words["eyebrow"],
        title=words["titles"][kind],
        intro=words["intro"],
        highlight_label=words["paid"] if kind in PAYMENTS else words["sent"],
        highlight_value=amount,
        sections=(Section(words["section"], tuple(rows)),),
        notice=words["notice"],
        greeting_name=first_name,
    )


# ------------------------------------------------------------------ the receipt of an inquiry

CASE = {
    "es": {
        "eyebrow": "Consulta abierta",
        "title": "Recibimos tu consulta",
        "subject": "Recibimos tu consulta {ref} · quipu",
        "intro": "Abrimos una consulta por el cargo que no reconoces. Una persona del equipo la revisará y ya tiene todo lo que nos contaste.",
        "preheader": "Una persona del equipo te responde en {hours} horas.",
        "number": "Número de consulta",
        "section": "Lo que abrimos",
        "charge": "Cargo",
        "charge_date": "Fecha del cargo",
        "priority": "Prioridad",
        "reply": "Te responden",
        "within": "en {hours} horas",
        "priorities": {"High": "Alta", "Medium": "Media", "Low": "Baja"},
        "months": (
            "ene",
            "feb",
            "mar",
            "abr",
            "may",
            "jun",
            "jul",
            "ago",
            "sep",
            "oct",
            "nov",
            "dic",
        ),
        "notice": "Guarda este número. Si necesitas algo mientras tanto, escríbele a quipu y menciónalo.",
    },
    "pt": {
        "eyebrow": "Consulta aberta",
        "title": "Recebemos a sua consulta",
        "subject": "Recebemos a sua consulta {ref} · quipu",
        "intro": "Abrimos uma consulta sobre a cobrança que você não reconhece. Uma pessoa da equipe vai revisá-la e já tem tudo o que você nos contou.",
        "preheader": "Uma pessoa da equipe responde em {hours} horas.",
        "number": "Número da consulta",
        "section": "O que abrimos",
        "charge": "Cobrança",
        "charge_date": "Data da cobrança",
        "priority": "Prioridade",
        "reply": "Respondemos",
        "within": "em {hours} horas",
        "priorities": {"High": "Alta", "Medium": "Média", "Low": "Baixa"},
        "months": (
            "jan",
            "fev",
            "mar",
            "abr",
            "mai",
            "jun",
            "jul",
            "ago",
            "set",
            "out",
            "nov",
            "dez",
        ),
        "notice": "Guarde este número. Se precisar de algo enquanto isso, escreva para a quipu e mencione-o.",
    },
}


def charge_date(value: object, lang: str) -> str:
    """The date of the charge as `11 jun 2026`. What is not a date is shown as it came, and nothing is shown for nothing."""
    text = str(value or "").strip()
    try:
        day = date.fromisoformat(text[:10])
    except ValueError:
        return text
    return f"{day.day} {CASE[lang]['months'][day.month - 1]} {day.year}"


def case_receipt_content(
    language: str, case: dict[str, Any], tx: dict[str, Any], first_name: str = ""
) -> EmailContent:
    """The receipt of the inquiry the bank just opened: the `case` it opened and the charge it is about, and nothing else.
    The priority and the hours come from the case (the code decided them), never from the model."""
    lang = language_of(language)
    words = CASE[lang]
    ref, hours = str(case["case_ref"]), case["sla_hours"]
    priority = words["priorities"].get(str(case.get("priority")), str(case.get("priority") or ""))
    amount = money(tx["amount"], tx["currency"])
    merchant = str(tx.get("merchant") or "").strip()
    rows = [Row(words["charge"], f"{merchant} · {amount}" if merchant else amount)]
    when = charge_date(tx.get("date"), lang)
    if when:
        rows.append(Row(words["charge_date"], when))
    rows += [
        Row(words["priority"], priority),
        Row(words["reply"], words["within"].format(hours=hours)),
    ]
    return EmailContent(
        kind="case_receipt",
        language=lang,
        subject=words["subject"].format(ref=ref),
        preheader=words["preheader"].format(hours=hours),
        eyebrow=words["eyebrow"],
        title=words["title"],
        intro=words["intro"],
        highlight_label=words["number"],
        highlight_value=ref,
        sections=(Section(words["section"], tuple(rows)),),
        notice=words["notice"],
        greeting_name=first_name,
    )


# ------------------------------------------------------------------ the plain-text part


def content_text(content: EmailContent) -> str:
    """The message for a reader without HTML, and what the outbox keeps. Everything the HTML says."""
    lang = content.language
    hello = (
        f"{HELLO[lang]} {content.greeting_name}," if content.greeting_name else f"{HELLO[lang]},"
    )
    lines = [hello, "", content.title, "", content.intro]
    if content.highlight_label:
        lines += ["", f"{content.highlight_label}: {content.highlight_value}"]
    for section in content.sections:
        lines += ["", section.title.upper()]
        for row in section.rows:
            lines.append(f"• {row.label}: {row.value}")
            if row.detail:
                lines.append(f"  {row.detail}")
    if content.notice:
        lines += ["", content.notice]
    lines += ["", FOOTER[lang]]
    return "\n".join(lines)
