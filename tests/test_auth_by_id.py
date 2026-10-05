"""Signing in with the ID of a customer: POST /api/auth/token with a listed ID and that same ID.

The IDs that can sign in are the ones in DEMO_CUSTOMER_IDS. The eight demo emails keep working
(tests/test_auth.py); this file is about the IDs.
"""

import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound import auth, http
from app.adapters.inbound.auth import customer_from_token, reset_login_attempts
from app.config import get_settings
from app.domain.finances import NoSpending

SECRET = "s" * 40
LUCIA_EMAIL = "demo-mx-duplicate@demo.bank"


@pytest.fixture(autouse=True)
def fresh_login_window():
    reset_login_attempts()


@pytest.fixture
def cloud(monkeypatch):
    """The deployed configuration: real signing key and a list of IDs that may sign in."""
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "cloud")
    monkeypatch.setattr(settings, "jwt_secret", SECRET)
    monkeypatch.setattr(settings, "demo_customer_ids", "CLI-A, CLI-B")
    return settings


def login(client, user, password, field="user"):
    return client.post("/api/auth/token", json={field: user, "password": password})


def test_a_listed_id_with_its_own_id_as_password_gets_a_token_for_that_customer(cloud):
    with TestClient(http.app) as client:
        ok = login(client, "CLI-A", "CLI-A")
    assert ok.status_code == 200 and ok.json()["customer_id"] == "CLI-A"
    assert customer_from_token(ok.json()["access_token"]) == "CLI-A"


def test_the_old_field_name_and_the_eight_emails_still_work(cloud):
    with TestClient(http.app) as client:
        old_name = login(client, "CLI-A", "CLI-A", field="email")
        by_email = login(client, LUCIA_EMAIL, LUCIA_EMAIL)
    assert old_name.status_code == 200 and old_name.json()["customer_id"] == "CLI-A"
    assert by_email.status_code == 200 and by_email.json()["customer_id"] == "DEMO-MX-DUPLICATE"


def test_the_id_and_its_password_ignore_case_and_spaces_and_the_token_has_the_listed_id(cloud):
    with TestClient(http.app) as client:
        ok = login(client, "  cli-b ", "cli-b")
    assert ok.status_code == 200 and ok.json()["customer_id"] == "CLI-B"  # as it is listed


def test_an_id_that_is_not_listed_cannot_sign_in_even_with_its_own_id_as_password(cloud):
    with TestClient(http.app) as client:
        unlisted = login(client, "CLI-Z", "CLI-Z")
        wrong = login(client, "CLI-A", "no")
    assert unlisted.status_code == 401 and wrong.status_code == 401
    assert (
        unlisted.json()["detail"] == wrong.json()["detail"]
    )  # it does not say which part was wrong


@pytest.mark.parametrize("password", ["", "no", "CLI-B", LUCIA_EMAIL])
def test_a_listed_id_needs_its_own_id_as_password(cloud, password):
    with TestClient(http.app) as client:
        refused = login(client, "CLI-A", password)
    assert refused.status_code == 401


def test_three_wrong_passwords_lock_that_id_in_any_case_and_leave_the_others_open(cloud):
    with TestClient(http.app) as client:
        for _ in range(2):
            assert login(client, "CLI-A", "no").status_code == 401
        locked = login(client, "cli-a", "no")  # the lock is on the person, not on how they type it
        still = login(client, "CLI-A", "CLI-A")  # not even the right password
        sibling = login(client, "CLI-B", "CLI-B")
    assert locked.status_code == 423 and still.status_code == 423
    assert sibling.status_code == 200


def test_a_successful_sign_in_clears_the_failures_before_the_lock(cloud):
    with TestClient(http.app) as client:
        for _ in range(2):
            assert login(client, "CLI-A", "no").status_code == 401
        assert login(client, "CLI-A", "CLI-A").status_code == 200
        assert (
            login(client, "CLI-A", "no").status_code == 401
        )  # the first miss again, not the third


def test_invented_ids_do_not_fill_the_table_of_failures(cloud):
    with TestClient(http.app) as client:
        for n in range(6):
            assert login(client, f"CLI-NOPE{n}", "x").status_code == 401
    assert auth._account_failures == {}


@pytest.fixture
def open_to_all(cloud, monkeypatch):
    """`*` in the list, and a database where only CLI-REAL exists besides the listed IDs."""
    monkeypatch.setattr(cloud, "demo_customer_ids", "CLI-A, *")
    looked_up = []

    async def find_customer(customer_id):
        looked_up.append(customer_id)
        return {"customer_id": customer_id} if customer_id == "CLI-REAL" else None

    monkeypatch.setattr(http, "find_customer", find_customer)
    return looked_up


def test_with_a_star_in_the_list_any_customer_in_the_database_signs_in_with_their_id(open_to_all):
    with TestClient(http.app) as client:
        ok = login(client, " cli-real ", "cli-real")
        listed = login(client, "CLI-A", "CLI-A")
    assert ok.status_code == 200 and ok.json()["customer_id"] == "CLI-REAL"
    assert customer_from_token(ok.json()["access_token"]) == "CLI-REAL"
    assert listed.status_code == 200 and open_to_all == ["CLI-REAL"]  # a listed ID needs no lookup


def test_with_a_star_an_id_that_is_not_in_the_database_or_a_wrong_password_is_still_refused(
    open_to_all,
):
    with TestClient(http.app) as client:
        unknown = login(client, "CLI-GHOST", "CLI-GHOST")
        wrong = login(client, "CLI-REAL", "no")
        star = login(client, "*", "*")
        not_an_id = login(client, "admin", "admin")
    assert [r.status_code for r in (unknown, wrong, star, not_an_id)] == [401] * 4
    assert unknown.json()["detail"] == wrong.json()["detail"]
    assert open_to_all == ["CLI-GHOST"]  # only a login that proved its password reaches the table


def test_an_id_added_to_the_list_can_sign_in_without_restarting(cloud, monkeypatch):
    with TestClient(http.app) as client:
        assert login(client, "CLI-C", "CLI-C").status_code == 401
        monkeypatch.setattr(cloud, "demo_customer_ids", "CLI-A, CLI-B, CLI-C")
        assert login(client, "CLI-C", "CLI-C").status_code == 200


def test_the_token_of_an_id_sign_in_is_what_the_finances_screen_reads(cloud, monkeypatch):
    asked = []

    async def finances(spending, store, customer_id, days):
        asked.append(customer_id)
        raise NoSpending

    monkeypatch.setattr(http, "own_finances", finances)
    with TestClient(http.app) as client:
        token = login(client, "CLI-A", "CLI-A").json()["access_token"]
        screen = client.get("/api/me/finances", headers={"Authorization": f"Bearer {token}"})
    assert asked == ["CLI-A"] and screen.status_code == 404
