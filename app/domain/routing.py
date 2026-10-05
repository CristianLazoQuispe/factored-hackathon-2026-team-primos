"""Deterministic safety net for the router: obvious intents, in Spanish and Portuguese.

The LLM router decides first. Only when it fails to pick a skill (it answers in prose, asks for
permission, or emits an empty or malformed reply) does the code check these patterns, so an
obvious request is never lost to a model's bad turn. Patterns stay narrow on purpose: no match
means "leave it to the model", never a guess. Pure function.
"""

import re

_RULES = (
    (
        "account_actions",
        re.compile(
            r"\b(bloque\w*|cancel\w*|congel\w*)\b.{0,25}\b(tarjeta|cart[aã]o)"
            r"|(perd[ií]|extravi\w*|robaron|me robar\w*|roubar\w*)\b"
            r".{0,30}\b(tarjeta|cart[aã]o)"
            r"|\b(tarjeta|cart[aã]o)\b.{0,30}\b(robad\w*|perdid\w*|roubad\w*|extraviad\w*)"
            r"|(env[ií]\w*|mand\w*|envie)\b.{0,30}\b(correo|e-?mail)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "money_movement",
        re.compile(
            r"\bkhip[eé]\w*|\bquip[eé]a\w*|\btransf(i[eé]r|ira)\w*"
            r"|transfer[eê]ncia (de|para)"
            r"|\b(env[ií]a(r|le|me)?|manda(r|le)?) .{0,20}"
            r"\b(pesos|d[oó]lares|reais|mxn|cop|ars|usd|\d)"
            r"|(?<!que )\b(pagar?|paga|pague|abonar?|abona) .{0,25}(tarjeta|cart[aã]o|pr[eé]stamo"
            r"|empr[eé]stimo|cr[eé]dito|deuda|d[ií]vida|recibo|factura|fatura|servicio|servi[cç]o"
            r"|\bluz\b|\b[aá]gua\b|tel[eé]fono|telefone|celular|internet|\bcable\b)"
            r"|\b(recibos?|facturas?|faturas?) (pendientes?|por pagar|a pagar|de (la |el )?"
            r"(luz|agua|tel[eé]fono|internet|cable))|(mis|meus|minhas) (recibos|facturas|faturas)\b"
            r"|p[aá]sa(r|me)? .{0,25}\b(a|para) (mi|minha|meu) (cuenta|conta|ahorro|corriente)",
            re.IGNORECASE,
        ),
    ),
    (
        "charge_investigation",
        re.compile(
            r"no reconozco|n[aã]o reconhe[cç]o"
            r"|(cargo|cobro|cobran[cç]a|compra)s? (raro|rara|extra[nñ][oa]|estranh[oa]|duplicad[oa]"
            r"|doble|indebid[oa]|indevid[oa])"
            r"|(cobr|carg)\w*.{0,30}\b(dos|duas|2) (veces|vezes)",
            re.IGNORECASE,
        ),
    ),
    (
        "balance_inquiry",
        re.compile(
            r"\bsaldo\b|\b(deuda|debo|d[ií]vida|devo)\b|(pago|pagamento) m[ií]nimo"
            r"|fecha (l[ií]mite )?de pago|cu[aá]ndo (vence|tengo que pagar)|quando vence"
            r"|l[ií]mite de cr[eé]dito|tasa de inter[eé]s|taxa de juros"
            r"|(mi|meu) perfil|(mis|meus) (datos|dados)",
            re.IGNORECASE,
        ),
    ),
    (
        "data_lookup",
        re.compile(
            r"cu[aá]nto (he |ha )?(gast|pagu|compr)"
            r"|cu[aá]nt[oa]s? (quejas|reclamos|compras|transacciones|movimientos|veces)"
            r"|(mis|meus|minhas) (quejas|reclamos|compras|gastos|movimientos|transferencias"
            r"|reclama[cç][oõ]es)"
            r"|[uú]ltim[oa]s (movimientos|compras|transacciones|transa[cç][oõ]es)"
            r"|en qu[eé] gasto|tipo de cambio|taxa de c[aâ]mbio|a cu[aá]nto est[aá] el d[oó]lar"
            r"|quanto (eu )?gastei|quantas? (reclama|compras|transa)",
            re.IGNORECASE,
        ),
    ),
)


def guess_skill(text: str) -> str | None:
    for skill, pattern in _RULES:
        if pattern.search(text or ""):
            return skill
    return None


# What the bank never does on its own, recognised by code. The customer has to ask for it ("quiero",
# "necesito", "hazme"...): a question about fees or about their own data is not a request. When one
# matches, the answer does not depend on a model's turn.
_ASKS = (
    r"(?:quiero|quisiera|necesito|puedes|podr[ií]as|podr[ií]an|ay[uú]dame\s+a|haz(?:me)?|hagan|"
    r"realiza\w*|solicito|quero|queria|gostaria|preciso|pode|poderia|fa[cç]a|fazer|realize)"
)
_REFUSED = (
    (
        "transfer_money",
        rf"\b{_ASKS}\b.{{0,40}}\b(?:transferir|transferencia|transfer[eê]ncia|girar)",
    ),
    (
        "transfer_money",
        rf"\b{_ASKS}\b.{{0,30}}\b(?:enviar|mandar|envie|mande)\s+(?:dinero|plata|dinheiro)",
    ),
    (
        "make_payment",
        rf"\b{_ASKS}\b.{{0,25}}\bpagar\s+(?:mi|la|el|mis|las|los|meu|minha|a|o|\d)",
    ),
    (
        "make_payment",
        rf"\b(?:{_ASKS}\b.{{0,25}}\b)?(?:hacer|realizar|fazer|hazme|haz|hagan|realice)"
        r"\s+(?:un|el|o|um)\s+pag\w+",
    ),
    ("refund", r"\b(?:devu[eé]lv\w+|reembols\w+|reintegr\w+|rest[ií]tu\w+|estorn\w+)"),
    (
        "change_phone",
        r"\b(?:cambi\w+|actualiz\w+|modific\w+|mud\w+|alter\w+)\b.{0,30}"
        r"\b(?:tel[eé]fono|celular|telefone)",
    ),
    (
        "change_email",
        r"\b(?:cambi\w+|actualiz\w+|modific\w+|mud\w+|alter\w+)\b.{0,30}\b(?:correo|e-?mail)",
    ),
    (
        "change_address",
        r"\b(?:cambi\w+|actualiz\w+|modific\w+|mud\w+|alter\w+)\b.{0,30}"
        r"\b(?:direcci[oó]n|domicilio|endere[cç]o)",
    ),
    ("raise_limit", r"\b(?:aument\w+|ampli\w+|sub[eai]\w*|elev\w+)\b.{0,30}\bl[ií]mite"),
    (
        "reissue_card",
        r"\b(?:nueva\s+tarjeta|novo\s+cart[aã]o|segunda\s+via|reponer\w*|reposici[oó]n|"
        r"reemplaz\w+\s+(?:mi|la)\s+tarjeta)",
    ),
)
_REFUSED_RULES = tuple((name, re.compile(rx, re.IGNORECASE)) for name, rx in _REFUSED)


def guess_refused_action(text: str) -> str | None:
    """The action the customer asks for that the bank never does on its own, or None. Narrow on
    purpose: no match means "leave it to the model", never a guess."""
    for name, pattern in _REFUSED_RULES:
        if pattern.search(text or ""):
            return name
    return None
