"""The pure side of the actions: signals, priority, payment state, language, texts and emails."""

import re
from datetime import date
from pathlib import Path

import pytest

from app.domain import action_text as text
from app.domain import actions as domain
from tests.actions_support import AS_OF, tx

# ---------------------------------------------------------------- risk, priority, payments


@pytest.mark.parametrize(
    ("charge", "signals", "priority", "hours"),
    [
        (dict(duplicates=0), [], "Low", 72),
        (dict(duplicates=1), ["duplicate_charge"], "Medium", 24),
        (dict(duplicates=0, country="Argentina"), ["foreign_transaction"], "Medium", 24),
        (dict(duplicates=0, is_fraud=True), ["possible_fraud"], "High", 4),
        (dict(duplicates=0, fraud_score=70.0), ["possible_fraud"], "High", 4),
        (dict(duplicates=0, fraud_score=69.9), [], "Low", 72),
        (dict(duplicates=1, is_fraud=True), ["possible_fraud", "duplicate_charge"], "High", 4),
        (dict(duplicates=0, status="Pending", age_days=5), ["pending_charge"], "Low", 72),
    ],
)
def test_signals_decide_priority_and_sla(charge: dict, signals: list, priority: str, hours: int):
    found = domain.risk_signals(tx(**charge))
    assert found == signals
    assert domain.case_priority(found) == (priority, hours)


@pytest.mark.parametrize(
    ("row", "state", "days"),
    [
        (
            {"due_date": date(2026, 7, 20), "minimum_payment": 100, "past_due_amount": 0},
            "current",
            32,
        ),
        (
            {"due_date": date(2026, 6, 23), "minimum_payment": 100, "past_due_amount": 0},
            "due_soon",
            5,
        ),
        (
            {"due_date": date(2026, 6, 24), "minimum_payment": 100, "past_due_amount": 0},
            "current",
            6,
        ),
        (
            {"due_date": date(2026, 6, 18), "minimum_payment": 100, "past_due_amount": 0},
            "due_soon",
            0,
        ),
        (
            {"due_date": date(2026, 6, 10), "minimum_payment": 100, "past_due_amount": 0},
            "overdue",
            -8,
        ),
        (
            {"due_date": date(2026, 7, 1), "minimum_payment": 100, "past_due_amount": 50},
            "overdue",
            13,
        ),
    ],
)
def test_payment_state_is_computed_not_estimated(row: dict, state: str, days: int):
    result = domain.payment_status(row, AS_OF)
    assert (result["state"], result["days_to_due"]) == (state, days)


def test_the_catalog_and_the_never_automated_list_do_not_overlap():
    assert not set(domain.CATALOG) & set(domain.NEVER_AUTOMATED)
    assert domain.decide("transfer_money", None, domain.Facts()).verdict is domain.Verdict.DENY
    assert domain.decide("nonsense", None, domain.Facts()).verdict is domain.Verdict.ESCALATE


def test_parameters_reject_extra_fields_and_trim_whitespace():
    params, bad = domain.parse_params("block_card", {"product_id": "  P1 "})
    assert bad is None and params.product_id == "P1"
    assert domain.parse_params("block_card", {"product_id": "P1", "x": 1})[1] == "invalid_params"
    assert domain.parse_params("inquiry_that_does_not_exist", {}) == (None, None)


# ---------------------------------------------------------------- language, masking, money


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Hola, no reconozco un cargo en mi tarjeta", "es"),
        ("Quiero bloquear mi tarjeta por favor", "es"),
        ("Olá, não reconheço uma cobrança no meu cartão", "pt"),
        ("Preciso bloquear meu cartão, você pode me ajudar?", "pt"),
        ("ok", "es"),
        ("", "es"),
    ],
)
def test_language_comes_from_the_words(message: str, expected: str):
    assert text.detect_language(message) == expected


def test_when_it_cannot_tell_it_keeps_the_conversation_language():
    assert text.detect_language("ok", default="pt") == "pt"
    assert text.detect_language("ok", default="fr") == "es"


def test_a_customer_in_brazil_defaults_to_portuguese():
    assert text.language_for_country("Brazil") == "pt"
    assert text.language_for_country("México") == "es"
    assert text.language_for_country(None) == "es"


def test_email_masking_keeps_the_domain_and_one_letter():
    assert text.mask_email("demo-mx-duplicate@demo.bank") == "d***@demo.bank"
    assert text.mask_email("") is None and text.mask_email("no-at-sign") is None


def test_money_formatting():
    assert text.money(312.4, "MXN") == "312.40 MXN"
    assert text.money(6523912.54) == "6,523,912.54"
    assert text.money(None) == "—"


# ---------------------------------------------------------------- the texts are complete


def _reason_codes() -> set[str]:
    source = Path(domain.__file__).read_text()
    codes = set(re.findall(r'_(?:deny|escalate)\("(\w+)"\)', source))
    codes |= set(re.findall(r'Decision\(Verdict\.\w+, "(\w+)"\)', source))
    codes |= {reason for _, reason in domain.NEVER_AUTOMATED.values()}
    codes |= {"invalid_params", "too_many_actions", "temporary_error", "dependency_failed"}
    codes |= {"verification_failed", "send_failed", "changed_since_proposal"}
    return codes - {"changed_since_proposal"}  # explained by the reason that changed


def test_every_reason_the_policy_can_give_has_text_in_both_languages():
    codes = _reason_codes()
    assert len(codes) > 20, "the scan found too few reasons: the pattern is out of date"
    for lang in text.LANGUAGES:
        missing = codes - set(text.REASONS[lang])
        assert not missing, f"{lang} has no text for {sorted(missing)}"


def test_every_action_has_a_confirmation_line_and_a_result_in_both_languages():
    for lang in text.LANGUAGES:
        assert set(domain.CATALOG) - {"set_alert"} <= set(text.LINES[lang])
        assert set(domain.CATALOG) <= set(text.DONE[lang])
        assert set(text.REASONS[lang]) == set(text.REASONS["es"])


def test_a_card_name_is_localised_and_unknown_kinds_still_read_well():
    view = {"card_kind": "Tarjeta Débito", "last4": "0042"}
    assert text.card_label(view, "es") == "tarjeta de débito terminada en 0042"
    assert text.card_label(view, "pt") == "cartão de débito com final 0042"
    assert (
        text.card_label({"card_kind": "Seguro", "last4": None}, "es") == "tarjeta terminada en ????"
    )


# ---------------------------------------------------------------- emails


BALANCES = {
    "products": [
        {
            "product_type": "Tarjeta Crédito",
            "last4": "2951",
            "balance": 8100.0,
            "currency": "MXN",
            "limit": 27000.0,
        },
        {
            "product_type": "Cuenta Ahorro",
            "last4": "1111",
            "balance": 500.0,
            "currency": "MXN",
            "limit": None,
        },
    ]
}
_PAYMENT = {"currency": "MXN", "past_due_amount": 0.0}
PAYMENTS = {
    "items": [
        _PAYMENT
        | {"product_type": "Tarjeta Crédito", "last4": "2951", "state": "due_soon"}
        | {"due_date": "2026-06-22", "days_to_due": 4, "minimum_payment": 450.0},
        _PAYMENT
        | {"product_type": "Préstamo Personal", "last4": "9", "state": "overdue"}
        | {"due_date": "2026-06-01", "days_to_due": -17, "minimum_payment": 900.0}
        | {"past_due_amount": 900.0},
    ]
}
RECEIPT = {
    "case": {"case_ref": "Q-1A2B3C4D", "priority": "Medium", "sla_hours": 24},
    "tx": {"merchant": "Uber Trip", "amount": 312.4, "currency": "MXN", "date": "2026-06-11"},
}


@pytest.mark.parametrize("lang", text.LANGUAGES)
@pytest.mark.parametrize(
    ("topic", "data"),
    [("balances", BALANCES), ("payment_status", PAYMENTS), ("case_receipt", RECEIPT)],
)
def test_emails_are_complete_and_say_they_are_a_demo(lang: str, topic: str, data: dict):
    subject, body = text.build_email(topic, lang, data)
    assert subject and "{" not in subject + body and "None" not in body
    assert "sintétic" in body
    assert body.startswith("Hola," if lang == "es" else "Olá,")


def test_email_contents_come_from_the_data():
    _, balances = text.build_email("balances", "es", BALANCES)
    assert "8,100.00 MXN (límite 27,000.00 MXN)" in balances
    _, payments = text.build_email("payment_status", "es", PAYMENTS)
    assert "vence el 2026-06-22 (en 4 días)" in payments and "VENCIDO" in payments
    subject, receipt = text.build_email("case_receipt", "pt", RECEIPT)
    assert subject == "Recebemos a sua consulta Q-1A2B3C4D"
    assert "Uber Trip de 312.40 MXN" in receipt and "responde em 24 horas" in receipt


def test_an_unknown_email_topic_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        text.build_email("anything", "es", {})
