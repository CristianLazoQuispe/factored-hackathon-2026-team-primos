"""Deterministic safety net for the router: obvious intents, in Spanish and Portuguese.

The LLM router decides first. Only when it fails to pick a skill (it answers in prose, asks for
permission, or emits an empty or malformed reply) does the code check these patterns, so an
obvious request is never lost to a model's bad turn. Patterns stay narrow on purpose: no match
means "leave it to the model", never a guess. Pure function.
"""

import re

_RULES = (
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
    ("balance_inquiry", re.compile(r"\bsaldo\b", re.IGNORECASE)),
    (
        "data_lookup",
        re.compile(
            r"cu[aá]nto (he |ha )?(gast|pagu|compr)"
            r"|cu[aá]nt[oa]s? (quejas|reclamos|compras|transacciones|movimientos|llamadas"
            r"|encuestas|veces)"
            r"|(mis|meus|minhas) (quejas|reclamos|encuestas|compras|gastos|movimientos"
            r"|reclama[cç][oõ]es|pesquisas)"
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
