# ruff: noqa: E501  (each sentence the customer reads stays on one line, so a person can review it)
"""Everything the customer reads about an action, written by code, in Spanish or Portuguese.

The confirmation card shows exactly what will be done, built from the stored action and never
from the model's prose. The result is built from what the system verified. Emails are templates
filled with verified data: no model text reaches an outgoing message.
"""

import re
import unicodedata
from datetime import datetime
from typing import Any

from app.domain.actions import (
    AWAITING,
    CONFIRMATION_TTL,
    FAILED,
    SKIPPED,
    VERIFIED,
    ActionRecord,
)

LANGUAGES = ("es", "pt")
_PT = {
    "nao", "voce", "obrigado", "obrigada", "cartao", "fatura", "preciso", "quero", "meu", "minha",
    "ola", "bloquear", "cobranca", "pagamento", "gostaria", "ajuda", "compra", "uma", "isso",
    "esta", "estou", "tenho", "fiz", "reconheco", "conta", "dias", "pessoa", "atendente",
}  # fmt: skip
_ES = {
    "hola", "tarjeta", "quiero", "necesito", "mi", "cargo", "cuenta", "gracias", "pago", "cobro",
    "ayuda", "compra", "una", "esto", "esta", "estoy", "tengo", "hice", "reconozco", "dias",
    "persona", "asesor", "por", "favor", "puedes", "pueden", "que", "el", "los",
}  # fmt: skip


def _plain(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z]+", folded)


def detect_language(text: str, default: str = "es") -> str:
    """Spanish or Portuguese from the words, and `default` when it cannot tell."""
    words = _plain(text or "")
    pt, es = sum(w in _PT for w in words), sum(w in _ES for w in words)
    if pt == es:
        return default if default in LANGUAGES else "es"
    return "pt" if pt > es else "es"


def language_for_country(country: str | None) -> str:
    return "pt" if (country or "").strip().lower() in {"brazil", "brasil"} else "es"


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def money(amount: float | None, currency: str | None = None) -> str:
    if amount is None:
        return "—"
    text = f"{amount:,.2f}"
    return f"{text} {currency}" if currency else text


UI: dict[str, dict[str, str]] = {
    "es": {
        "title_confirm": "Revisa y confirma",
        "title_done": "Resultado",
        "confirm": "Confirmar",
        "cancel": "Cancelar",
        "expires": "Esta confirmación caduca en {minutes} minutos.",
        "strong": "Esta acción no se puede deshacer.",
        "inbox": "Correo de demostración",
        "card": "{kind} terminada en {last4}",
    },
    "pt": {
        "title_confirm": "Revise e confirme",
        "title_done": "Resultado",
        "confirm": "Confirmar",
        "cancel": "Cancelar",
        "expires": "Esta confirmação expira em {minutes} minutos.",
        "strong": "Esta ação não pode ser desfeita.",
        "inbox": "E-mail de demonstração",
        "card": "{kind} com final {last4}",
    },
}
CARD_KINDS = {
    "es": {
        "Tarjeta Crédito": "tarjeta de crédito",
        "Credit Card": "tarjeta de crédito",
        "Tarjeta Débito": "tarjeta de débito",
        "Debit Card": "tarjeta de débito",
    },
    "pt": {
        "Tarjeta Crédito": "cartão de crédito",
        "Credit Card": "cartão de crédito",
        "Tarjeta Débito": "cartão de débito",
        "Debit Card": "cartão de débito",
    },
}
WINDOWS = {
    "es": {"morning": "mañana", "afternoon": "tarde", "evening": "noche"},
    "pt": {"morning": "manhã", "afternoon": "tarde", "evening": "noite"},
}
TOPICS = {
    "es": {
        "balances": "resumen de saldos",
        "payment_status": "estado de pagos",
        "case_receipt": "comprobante de la consulta",
    },
    "pt": {
        "balances": "resumo de saldos",
        "payment_status": "extrato de pagamentos",
        "case_receipt": "comprovante da consulta",
    },
}
ALERTS = {
    "es": {
        ("duplicate_charge", True): "Avisarte si aparece un cobro repetido.",
        ("duplicate_charge", False): "Dejar de avisarte de cobros repetidos.",
        ("payment_due", True): "Recordarte el vencimiento de tus pagos.",
        ("payment_due", False): "Dejar de recordarte el vencimiento de tus pagos.",
    },
    "pt": {
        ("duplicate_charge", True): "Avisar você se aparecer uma cobrança repetida.",
        ("duplicate_charge", False): "Parar de avisar sobre cobranças repetidas.",
        ("payment_due", True): "Lembrar você do vencimento dos seus pagamentos.",
        ("payment_due", False): "Parar de lembrar do vencimento dos seus pagamentos.",
    },
}
LINES: dict[str, dict[str, str]] = {
    "es": {
        "block_card": "Bloquear temporalmente tu {card}.",
        "cancel_card": "Cancelar definitivamente tu {card}.",
        "open_payment_inquiry": (
            "Abrir una consulta de pago por {amount} en {merchant} ({date}). "
            "Prioridad {priority}: una persona te responde en {hours} h."
        ),
        "request_callback": "Pedir que una persona te llame por la {window}.",
        "send_summary_email": "Enviar por correo a {to} tu {topic}.",
    },
    "pt": {
        "block_card": "Bloquear temporariamente o seu {card}.",
        "cancel_card": "Cancelar definitivamente o seu {card}.",
        "open_payment_inquiry": (
            "Abrir uma consulta de pagamento de {amount} em {merchant} ({date}). "
            "Prioridade {priority}: uma pessoa responde em {hours} h."
        ),
        "request_callback": "Pedir que uma pessoa ligue para você no período da {window}.",
        "send_summary_email": "Enviar por e-mail para {to} o seu {topic}.",
    },
}
DONE: dict[str, dict[str, str]] = {
    "es": {
        "block_card": "Tu {card} quedó bloqueada. Lo comprobé en el sistema.",
        "cancel_card": "Tu {card} quedó cancelada. Lo comprobé en el sistema.",
        "open_payment_inquiry": (
            "Abrí la consulta {case_ref}. Prioridad {priority}: una persona te responde en {hours} h."
        ),
        "request_callback": "Pedí que te llamen por la {window}. Referencia {case_ref}.",
        "set_alert": "Listo. {alert}",
        "send_summary_email": (
            "El servicio de correo aceptó tu mensaje y lo entregó al buzón de demostración "
            "{delivered}. Puede tardar unos minutos en llegar."
        ),
        "send_summary_email_simulated": (
            "Guardé tu mensaje en la bandeja de demostración. No se envió a ningún correo real."
        ),
    },
    "pt": {
        "block_card": "O seu {card} foi bloqueado. Conferi no sistema.",
        "cancel_card": "O seu {card} foi cancelado. Conferi no sistema.",
        "open_payment_inquiry": (
            "Abri a consulta {case_ref}. Prioridade {priority}: uma pessoa responde em {hours} h."
        ),
        "request_callback": "Pedi que liguem para você no período da {window}. Referência {case_ref}.",
        "set_alert": "Pronto. {alert}",
        "send_summary_email": (
            "O serviço de e-mail aceitou a sua mensagem e a entregou à caixa de demonstração "
            "{delivered}. Pode levar alguns minutos."
        ),
        "send_summary_email_simulated": (
            "Guardei a sua mensagem na caixa de demonstração. Ela não foi enviada a nenhum e-mail real."
        ),
    },
}
REASONS: dict[str, dict[str, str]] = {
    "es": {
        "not_found": "No encuentro eso en tus datos.",
        "not_a_card": "Eso no es una tarjeta.",
        "already_blocked": "Esa tarjeta ya está bloqueada.",
        "card_closed": "Esa tarjeta ya está cerrada.",
        "card_suspended": "El banco suspendió esa tarjeta; una persona debe revisarla.",
        "unknown_card_status": "No reconozco el estado de esa tarjeta; una persona debe revisarla.",
        "blocked_by_bank": "El banco bloqueó esa tarjeta; una persona debe revisar por qué antes.",
        "past_due": "Tienes pagos vencidos; cancelar la tarjeta requiere hablar con una persona.",
        "outstanding_balance": "La tarjeta tiene saldo pendiente; cancelarla requiere acordarlo con una persona.",
        "already_reversed": "Ese cargo ya fue revertido; no hay nada que reclamar.",
        "was_declined": "Ese cargo fue rechazado, así que no se te cobró.",
        "still_pending": "Ese cargo sigue pendiente y suele resolverse solo en unos días.",
        "no_contact_on_file": "No tengo un correo registrado para enviarte.",
        "no_case_to_confirm": "No hay una consulta de la que enviar comprobante.",
        "money_movement_not_authorized": "No puedo mover dinero. Puedes hacerlo desde la app o con una persona.",
        "needs_human_approval": "Eso lo decide una persona del equipo; ya le paso tu caso.",
        "identity_change": "Cambiar tus datos de contacto requiere verificar tu identidad con una persona.",
        "credit_policy": "Los límites y el crédito los decide una persona según la política del banco.",
        "physical_card": "Reponer una tarjeta física lo gestiona una persona.",
        "unfreeze_needs_review": "Desbloquear una tarjeta lo revisa una persona.",
        "unknown_action": "Eso no lo puedo hacer yo; te paso con una persona.",
        "invalid_params": "No entendí bien los datos de esa acción.",
        "too_many_actions": "Son demasiadas acciones a la vez; hagamos primero las primeras.",
        "changed_since_proposal": "Algo cambió desde que lo propuse y ya no se puede hacer así.",
        "dependency_failed": "Un paso anterior no se completó.",
        "verification_failed": "No pude comprobar que se hiciera; una persona lo revisará.",
        "send_failed": "El correo no salió.",
        "temporary_error": "Hubo un problema técnico temporal.",
        "error": "Hubo un problema técnico.",
    },
    "pt": {
        "not_found": "Não encontro isso nos seus dados.",
        "not_a_card": "Isso não é um cartão.",
        "already_blocked": "Esse cartão já está bloqueado.",
        "card_closed": "Esse cartão já está encerrado.",
        "card_suspended": "O banco suspendeu esse cartão; uma pessoa precisa revisá-lo.",
        "unknown_card_status": "Não reconheço o estado desse cartão; uma pessoa precisa revisá-lo.",
        "blocked_by_bank": "O banco bloqueou esse cartão; uma pessoa precisa ver o motivo antes.",
        "past_due": "Há pagamentos em atraso; cancelar o cartão exige falar com uma pessoa.",
        "outstanding_balance": "O cartão tem saldo pendente; cancelá-lo exige combinar com uma pessoa.",
        "already_reversed": "Essa cobrança já foi estornada; não há o que contestar.",
        "was_declined": "Essa cobrança foi recusada, então nada foi cobrado.",
        "still_pending": "Essa cobrança ainda está pendente e costuma se resolver em alguns dias.",
        "no_contact_on_file": "Não tenho um e-mail cadastrado para enviar.",
        "no_case_to_confirm": "Não há uma consulta da qual enviar comprovante.",
        "money_movement_not_authorized": "Não posso movimentar dinheiro. Você pode fazer isso no app ou com uma pessoa.",
        "needs_human_approval": "Isso é decidido por uma pessoa da equipe; já passo o seu caso.",
        "identity_change": "Alterar seus dados de contato exige verificar sua identidade com uma pessoa.",
        "credit_policy": "Limites e crédito são decididos por uma pessoa conforme a política do banco.",
        "physical_card": "A reposição de cartão físico é feita por uma pessoa.",
        "unfreeze_needs_review": "O desbloqueio de um cartão é revisado por uma pessoa.",
        "unknown_action": "Isso eu não posso fazer; vou passar você para uma pessoa.",
        "invalid_params": "Não entendi bem os dados dessa ação.",
        "too_many_actions": "São ações demais de uma vez; vamos fazer as primeiras antes.",
        "changed_since_proposal": "Algo mudou desde que propus e já não dá para fazer assim.",
        "dependency_failed": "Uma etapa anterior não foi concluída.",
        "verification_failed": "Não consegui confirmar que foi feito; uma pessoa vai revisar.",
        "send_failed": "O e-mail não saiu.",
        "temporary_error": "Houve um problema técnico temporário.",
        "error": "Houve um problema técnico.",
    },
}
STATE: dict[str, dict[str, str]] = {
    "es": {
        "cancelled": "Cancelaste esta acción; no se hizo nada.",
        "superseded": "Esta propuesta fue reemplazada por una más reciente; no se hizo nada.",
        "expired": "La confirmación caducó y no se hizo nada. Si todavía lo quieres, pídemelo otra vez.",
        "skipped": "No lo hice porque un paso anterior no se completó.",
        "nothing": "No se hizo ningún cambio.",
        "failed": "No pude completarlo: {reason}",
    },
    "pt": {
        "cancelled": "Você cancelou esta ação; nada foi feito.",
        "superseded": "Esta proposta foi substituída por uma mais recente; nada foi feito.",
        "expired": "A confirmação expirou e nada foi feito. Se ainda quiser, peça de novo.",
        "skipped": "Não fiz porque uma etapa anterior não foi concluída.",
        "nothing": "Nenhuma alteração foi feita.",
        "failed": "Não consegui concluir: {reason}",
    },
}


def _t(table: dict[str, dict[str, str]], lang: str) -> dict[str, str]:
    return table.get(lang, table["es"])


def reason_text(reason: str | None, lang: str) -> str:
    texts = _t(REASONS, lang)
    return texts.get(reason or "error", texts["error"])


def card_label(view: dict[str, Any], lang: str) -> str:
    kind = _t(CARD_KINDS, lang).get(
        view.get("card_kind", ""), "cartão" if lang == "pt" else "tarjeta"
    )
    return _t(UI, lang)["card"].format(kind=kind, last4=view.get("last4") or "????")


def _fill(record: ActionRecord, lang: str) -> dict[str, str]:
    view, result = record.view, record.result or {}
    params = record.params
    return {
        "card": card_label(view, lang),
        "amount": money(view.get("amount"), view.get("currency")),
        "merchant": str(view.get("merchant") or "—"),
        "date": str(view.get("date") or "—"),
        "priority": str(result.get("priority") or view.get("priority") or "—"),
        "hours": str(result.get("sla_hours") or view.get("sla_hours") or "—"),
        "case_ref": str(result.get("case_ref") or "—"),
        "window": _t(WINDOWS, lang).get(params.get("window", ""), "—"),
        "to": str(view.get("to") or "—"),
        "delivered": str(result.get("delivered_to") or "—"),
        "topic": _t(TOPICS, lang).get(params.get("topic", ""), "—"),
        "alert": _t(ALERTS, lang).get((params.get("kind"), params.get("enabled", True)), ""),
    }


def describe(record: ActionRecord, lang: str) -> str:
    """The line on the confirmation card: what will be done."""
    if record.action == "set_alert":
        return _t(ALERTS, lang)[(record.params["kind"], record.params.get("enabled", True))]
    return _t(LINES, lang)[record.action].format(**_fill(record, lang))


def outcome(record: ActionRecord, lang: str) -> tuple[str, str]:
    """What happened to an action, in words, and its tone: ok, warn, error or info."""
    state = _t(STATE, lang)
    status = record.status
    if status == AWAITING:
        return describe(record, lang), "info"
    if status == VERIFIED:
        key = record.action
        if key == "send_summary_email" and (record.result or {}).get("mode") == "simulated":
            key = "send_summary_email_simulated"  # nothing left the process: say so
        return _t(DONE, lang)[key].format(**_fill(record, lang)), "ok"
    if status == FAILED:
        return state["failed"].format(reason=reason_text(record.reason, lang)), "error"
    if status == SKIPPED:
        return state["skipped"], "warn"
    if status == "cancelled" and record.reason == "superseded":
        return state["superseded"], "warn"
    if status in ("cancelled", "expired"):
        return state[status], "warn"
    return f"{reason_text(record.reason, lang)} {state['nothing']}", "warn"  # refused, escalated


def render_batch(
    records: list[ActionRecord], lang: str, inbox_choices: list[str]
) -> dict[str, Any]:
    """The batch as the web draws it. Pure: the same records give the same card."""
    ui = _t(UI, lang)
    waiting = [r for r in records if r.status == AWAITING]
    items = []
    for record in records:
        text, tone = outcome(record, lang)
        items.append(
            {
                "action_id": record.action_id,
                "action": record.action,
                "status": record.status,
                "tone": tone,
                "text": text,
            }
        )
    emails = any(r.action == "send_summary_email" for r in waiting)
    return {
        "batch_id": records[0].batch_id if records else None,
        "language": lang,
        "state": AWAITING if waiting else "done",
        "needs_confirmation": bool(waiting),
        "strong": any(r.view.get("strong") for r in waiting),
        "title": ui["title_confirm"] if waiting else ui["title_done"],
        "confirm_label": ui["confirm"],
        "cancel_label": ui["cancel"],
        "strong_note": ui["strong"] if any(r.view.get("strong") for r in waiting) else None,
        "expires_note": (
            ui["expires"].format(minutes=int(CONFIRMATION_TTL.total_seconds() // 60))
            if waiting
            else None
        ),
        "expires_at": waiting[0].expires_at.isoformat() if waiting else None,
        "inbox_label": ui["inbox"] if emails and inbox_choices else None,
        "inbox_choices": inbox_choices if emails else [],
        "items": items,
        "escalate": [
            {"action": r.action, "reason": r.reason}
            for r in records
            if r.status == "escalated" or (r.status == FAILED and r.reason == "verification_failed")
        ],
    }


# ---------------------------------------------------------------- emails


def _date(value: Any) -> str:
    return value.date().isoformat() if isinstance(value, datetime) else str(value)


def build_email(topic: str, lang: str, data: dict[str, Any]) -> tuple[str, str]:
    """Subject and plain-text body for one topic, from verified data only."""
    es = lang != "pt"
    footer = (
        "Mensaje de demostración con datos sintéticos."
        if es
        else "Mensagem de demonstração com dados sintéticos."
    )
    lines: list[str] = []
    if topic == "balances":
        subject = "Resumen de tus saldos" if es else "Resumo dos seus saldos"
        lines.append("Estos son tus saldos:" if es else "Estes são os seus saldos:")
        for p in data["products"]:
            end = f"{p['product_type']} {'terminada en' if es else 'com final'} {p['last4'] or '????'}"
            extra = (
                f" ({'límite' if es else 'limite'} {money(p['limit'], p['currency'])})"
                if p.get("limit")
                else ""
            )
            lines.append(f"• {end}: {money(p['balance'], p['currency'])}{extra}")
    elif topic == "payment_status":
        subject = "Estado de tus pagos" if es else "Situação dos seus pagamentos"
        if not data["items"]:
            lines.append(
                "No tienes pagos pendientes registrados."
                if es
                else "Você não tem pagamentos pendentes."
            )
        for p in data["items"]:
            head = f"{p['product_type']} {p['last4'] or '????'}"
            pay = money(p["minimum_payment"], p["currency"])
            if p["state"] == "overdue":
                late = money(p["past_due_amount"], p["currency"])
                lines.append(
                    f"• {head}: {'VENCIDO' if es else 'EM ATRASO'}. "
                    f"{'Monto vencido' if es else 'Valor em atraso'} {late}; "
                    f"{'pago mínimo' if es else 'pagamento mínimo'} {pay}."
                )
            else:
                days = p["days_to_due"]
                when = (
                    f"{'vence el' if es else 'vence em'} {p['due_date']} "
                    f"({'en' if es else 'daqui a'} {days} {'días' if es else 'dias'})"
                )
                lines.append(
                    f"• {head}: {when}. {'Pago mínimo' if es else 'Pagamento mínimo'} {pay}."
                )
    elif topic == "case_receipt":
        case, tx = data["case"], data["tx"]
        subject = (
            f"Recibimos tu consulta {case['case_ref']}"
            if es
            else f"Recebemos a sua consulta {case['case_ref']}"
        )
        lines += [
            (f"Consulta: {case['case_ref']}" if es else f"Consulta: {case['case_ref']}"),
            (
                f"Cargo: {tx['merchant']} por {money(tx['amount'], tx['currency'])}, {tx['date']}"
                if es
                else f"Cobrança: {tx['merchant']} de {money(tx['amount'], tx['currency'])}, {tx['date']}"
            ),
            (
                f"Prioridad: {case['priority']}. Una persona te responde en {case['sla_hours']} horas."
                if es
                else f"Prioridade: {case['priority']}. Uma pessoa responde em {case['sla_hours']} horas."
            ),
            (
                "No necesitas hacer nada más; te avisaremos cuando haya novedades."
                if es
                else "Você não precisa fazer mais nada; avisaremos quando houver novidades."
            ),
        ]
    else:
        raise ValueError(f"unknown email topic {topic!r}")
    greeting = "Hola," if es else "Olá,"
    return subject, "\n".join([greeting, "", *lines, "", footer])
