"""Deterministic safety net for the router: obvious intents, in Spanish and Portuguese.

The LLM router decides first. Only when it fails to pick a skill (it answers in prose, asks for
permission, or emits an empty or malformed reply) does the code check these patterns, so an
obvious request is never lost to a model's bad turn. Patterns stay narrow on purpose: no match
means "leave it to the model", never a guess. Pure function.
"""

import re

_RULES = (
    (
        "money_movement",
        re.compile(
            r"\bkhip[eé]\w*|\bquip[eé]a\w*|\btransf(i[eé]r|erir|ira)\w*"
            r"|transfer[eê]ncia (de|para)"
            r"|\b(env[ií]a(r|le|me)?|manda(r|le)?) .{0,20}"
            r"\b(pesos|d[oó]lares|reais|mxn|cop|ars|usd|\d)"
            r"|(?<!que )\b(pagar?|paga|pague|abonar?|abona) .{0,25}(tarjeta|cart[aã]o|pr[eé]stamo"
            r"|empr[eé]stimo|cr[eé]dito|deuda|d[ií]vida)"
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
