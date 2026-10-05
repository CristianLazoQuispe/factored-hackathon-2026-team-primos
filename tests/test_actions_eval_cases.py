"""The scenarios of the action eval are well formed and split by rule. No model, no database."""

import re
from collections import Counter
from itertools import groupby

import pytest

from app.domain.actions import CATALOG
from evals.actions import world
from evals.actions.cases import CASES, DECISIONS, INJECTIONS, SEGMENTS, assign
from evals.actions.run import select

PLACEHOLDERS = re.compile(r"\{([a-z_0-9]+)\}")
SKILLS = {
    "account_actions",
    "balance_inquiry",
    "data_lookup",
    "charge_investigation",
    "profile_lookup",
}


def test_every_case_is_well_formed():
    assert len(CASES) == len({c.id for c in CASES}), "ids are unique"
    for c in CASES:
        assert c.id.split("-")[0] == c.category and re.fullmatch(r"[a-z]+-\d\d", c.id), c.id
        assert c.language in ("es", "pt") and c.fixture in world.FIXTURES, c.id
        assert c.decision in DECISIONS and c.inject in INJECTIONS and c.turns, c.id
        assert c.segment in SEGMENTS and c.split in ("regression", "heldout"), c.id
        assert (c.country == "Brazil") == (c.language == "pt"), c.id
        assert c.expect.executed and all(isinstance(alt, tuple) for alt in c.expect.executed), c.id


def test_the_actions_a_case_expects_exist_and_its_routes_are_real_skills():
    for c in CASES:
        for alternative in c.expect.executed:
            assert set(alternative) <= set(CATALOG), c.id
        for route in (c.expect.route, c.expect.avoid_route):
            assert route is None or route in SKILLS, (c.id, route)
        assert not (c.expect.route and c.expect.avoid_route), c.id


def test_a_message_only_uses_placeholders_the_run_can_fill():
    for c in CASES:
        used = set().union(*(set(PLACEHOLDERS.findall(t)) for t in c.turns))
        assert used <= {"id", "neighbor_card", "neighbor_last4", "neighbor_id"}, c.id
        if used & {"neighbor_card", "neighbor_last4", "neighbor_id"}:
            assert c.neighbor, f"{c.id} names somebody else's things but builds nobody"


def test_held_out_is_the_second_of_every_three_in_each_category_and_nothing_else():
    """The rule, written again here from scratch: it must not drift into hand-picking."""
    for _category, group in groupby(sorted(CASES, key=lambda c: c.id), key=lambda c: c.category):
        for i, c in enumerate(group):
            assert (c.split == "heldout") == (i % 3 == 1), f"{c.id} breaks the rule"


def test_the_split_does_not_depend_on_what_a_case_expects():
    """Reassigning gives the same split: moving an expectation cannot move a case."""
    again = {c.id: c.split for c in assign(list(CASES))}
    assert again == {c.id: c.split for c in CASES}


def test_there_is_enough_held_out_and_enough_of_each_kind_to_say_something():
    held = [c for c in CASES if c.split == "heldout"]
    assert 0.25 <= len(held) / len(CASES) <= 0.40 and len(held) >= 18
    assert Counter(c.language for c in CASES)["pt"] >= 12
    assert all(n >= 2 for n in Counter(c.category for c in CASES).values())
    assert len({c.segment for c in CASES}) == len(SEGMENTS)
    assert sum(c.automated for c in CASES) >= 15, "enough cases where the system should act alone"


def test_every_kind_of_trouble_the_challenge_names_has_cases():
    """Bad data, expired sessions, unauthorized access, injection, tool failures, ambiguity."""
    categories = {c.category for c in CASES}
    assert {
        "policy",
        "failure",
        "unauth",
        "inject",
        "clarify",
        "mixed",
        "human",
        "refuse",
        "inform",
    } <= categories
    assert any(c.decision == "expire" for c in CASES) and any(
        c.inject == "mail_permanent" for c in CASES
    )
    assert any(not c.signed_in for c in CASES) and any(c.neighbor for c in CASES)


def test_the_cases_that_expect_a_clarifying_question_expect_nothing_to_run():
    for c in CASES:
        if c.expect.question:
            assert c.expect.executed == ((),) and c.decision == "none", c.id


def test_a_case_that_should_be_automated_expects_no_person():
    for c in CASES:
        if c.automated:
            assert c.expect.handoff is False and c.signed_in, c.id


def test_regression_is_the_default_and_held_out_is_never_run_by_accident():
    assert {c.split for c in select(CASES, "regression", None)} == {"regression"}
    assert {c.split for c in select(CASES, "heldout", None)} == {"heldout"}
    held_id = next(c.id for c in CASES if c.split == "heldout")
    with pytest.raises(SystemExit, match="not in the 'regression' cases"):
        select(CASES, "regression", held_id)
    assert [c.id for c in select(CASES, "heldout", held_id)] == [held_id]
    with pytest.raises(SystemExit):
        select(CASES, "regression", "no-such-case")


def test_every_refuse_case_is_caught_by_the_net_of_what_the_bank_never_does():
    """The docs say these are answered by code before any model: the net itself must catch each one,
    not the fallback that routes by keywords."""
    from app.domain.routing import guess_refused_action

    refuse = [c for c in CASES if c.category == "refuse"]
    assert len(refuse) == 9
    for c in refuse:
        assert guess_refused_action(c.turns[0]), c.id
