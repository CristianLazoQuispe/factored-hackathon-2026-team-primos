# ruff: noqa: E501  (the names and the subprocess call stay on one line each)
"""Tests and evals write only to the development database, never to one that may be shared."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import get_settings
from evals.actions import world

PROXY = "postgresql://agent:SECRET@localhost:5433/agent"  # Cloud SQL through the proxy
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(monkeypatch):
    def use(url: str, allow: str | None = None) -> None:
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.delenv("ALLOW_TEST_DATABASE", raising=False)
        if allow:
            monkeypatch.setenv("ALLOW_TEST_DATABASE", allow)
        get_settings.cache_clear()

    yield use
    get_settings.cache_clear()


def test_the_development_database_is_the_one_every_developer_has(database):
    database(world.DEVELOPMENT_DATABASE)
    assert world.DEVELOPMENT_DATABASE == "postgresql://agent:agent@localhost:5432/agent"
    assert world.is_development_database()


@pytest.mark.parametrize(
    "url",
    [
        PROXY,
        "postgresql://agent:agent@localhost:5432/other",
        "postgresql://agent:agent@localhost:5433/agent",
    ],
)
def test_any_other_database_is_not_one_to_write_to(database, url):
    database(url)
    assert not world.is_development_database()


def test_a_developer_can_say_that_another_database_is_theirs(database):
    database(PROXY, allow="1")
    assert world.is_development_database()
    database(PROXY, allow="yes")
    assert not world.is_development_database(), "only an explicit 1 counts"


def test_building_a_customer_in_another_database_is_refused_before_connecting(
    database, monkeypatch
):
    database(PROXY)

    def never(*args, **kwargs):
        raise AssertionError("it connected")

    monkeypatch.setattr(world.psycopg, "connect", never)
    with pytest.raises(SystemExit, match="ALLOW_TEST_DATABASE"):
        world.build("single", "Plus", "México", "es")


def test_the_cleanup_does_nothing_in_another_database_and_does_not_connect(database, monkeypatch):
    database(PROXY)

    def never(*args, **kwargs):
        raise AssertionError("it connected")

    monkeypatch.setattr(world.psycopg, "connect", never)
    world.purge()  # returns quietly


def test_a_session_started_with_the_proxy_database_never_points_at_it():
    """The probe runs in a new session with DATABASE_URL set to a shared-looking database, and asserts
    that the session was given the unreachable one. The port is one nothing listens on."""
    shared = "postgresql://agent:agent@127.0.0.1:5999/agent"
    env = {k: v for k, v in os.environ.items() if k != "ALLOW_TEST_DATABASE"} | {
        "DATABASE_URL": shared,
        "PROBE": "1",
    }
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore",
         "tests/test_database_guard.py::test_probe_what_a_session_is_given"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-500:]
    assert "1 passed" in done.stdout


def test_probe_what_a_session_is_given():
    if os.environ.get("PROBE") != "1":
        pytest.skip("only runs inside the session the test above starts")
    assert get_settings().database_url == world.UNREACHABLE, get_settings().database_url
