# ruff: noqa: E501  (the lines of the script that are read, and the expected texts, stay on one line each)
"""evals/chat_memory/validate.sh must run on the bash of a Mac, never touch a remote API, and not be fooled
by an agent that only repeats the question. No model and no server: the script is read, and run against
nothing. What it checks about a live agent was tried by hand against four stand-in agents."""

import re
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evals/chat_memory/validate.sh"
TEXT = SCRIPT.read_text()


def run(**env: str) -> subprocess.CompletedProcess:
    environment = {"PATH": "/usr/bin:/bin:/usr/local/bin", **env}
    return subprocess.run(
        ["bash", str(SCRIPT)], env=environment, capture_output=True, text=True, timeout=60
    )


def test_the_script_is_valid_bash():
    done = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_it_uses_nothing_the_bash_of_a_mac_cannot_read():
    """macOS ships bash 3.2. A `case` inside `$( )` cannot be parsed by it: it was in the first version."""
    assert not re.search(r"\$\(\s*case\b", TEXT), (
        "a case inside $( ): use a plain block or a function"
    )
    assert not re.search(r"\$\{[A-Za-z_0-9]+(,,|\^\^)\}", TEXT), "${var,,} and ${var^^} need bash 4"
    assert "declare -A" not in TEXT, "associative arrays need bash 4"
    assert "mapfile" not in TEXT and "readarray" not in TEXT, "they need bash 4"


@pytest.mark.parametrize(
    "api",
    [
        "https://factored-api-xyz.a.run.app",
        "http://10.0.0.5:8080",
        "http://localhost.evil.test:8080",
        "http://example.com",
    ],
)
def test_it_refuses_any_api_that_is_not_local(api):
    done = run(API=api)
    assert done.returncode == 2 and "only runs against a local API" in done.stderr
    assert "passed" not in done.stdout


def test_it_says_what_to_do_when_there_is_no_api():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # a port nobody is listening on
    done = run(API=f"http://localhost:{port}")
    assert done.returncode == 1 and "make dev" in done.stdout
    assert "Nothing else can be checked" in done.stdout


def test_the_question_of_the_second_chat_does_not_carry_the_marker_of_the_run():
    """An agent that only repeats the question would otherwise 'contain' the marker and pass."""
    line = next(line for line in TEXT.splitlines() if line.startswith('r3=$(say "$TA"'))
    assert "$MARK" not in line and "$TS" not in line


def test_remembering_needs_the_marker_of_the_first_chat_or_its_question_never_the_word_saldo_alone():
    start = TEXT.index('case "$lower" in')
    patterns = TEXT[start : TEXT.index("esac", start)].splitlines()[1].split(")")[0].split("|")
    patterns = [p.strip().strip('"*') for p in patterns]
    assert patterns and all(
        "validacion $TS" in p or "es mi saldo" in p or "meu saldo" in p for p in patterns
    ), patterns
    assert not any(p in ("saldo", "saldos") for p in patterns)


def test_every_run_starts_by_hiding_the_old_history_and_the_checks_delete_nothing():
    for who in ("TA", "TB"):
        assert (
            f'curl -s -X DELETE -H "Authorization: Bearer ${who}" "$API/api/me/conversations"'
            in TEXT
        )
    before_cleanup_hint = TEXT.split('echo "These conversations')[0]
    assert "DELETE FROM" not in before_cleanup_hint, "only the clean-up it prints deletes rows"


def test_the_docs_point_to_the_script_where_it_is():
    docs = (ROOT / "docs/documentation/technical/chat_memory.md").read_text()
    assert "evals/chat_memory/validate.sh" in docs and "validate_chat_memory.sh" not in docs
