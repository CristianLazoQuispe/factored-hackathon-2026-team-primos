"""The memory of the chat is off unless it is asked for, and the places that name it agree."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from app.config import Settings, get_settings

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / ".github/workflows/deploy.yml"


def test_it_is_off_by_default():
    assert Settings(_env_file=None).chat_memory_enabled is False


def test_it_is_turned_on_from_the_environment(monkeypatch):
    monkeypatch.setenv("CHAT_MEMORY_ENABLED", "true")
    assert Settings(_env_file=None).chat_memory_enabled is True
    monkeypatch.setenv("CHAT_MEMORY_ENABLED", "false")
    assert Settings(_env_file=None).chat_memory_enabled is False


def test_turning_it_on_changes_nothing_else():
    on = Settings(_env_file=None, chat_memory_enabled=True).model_dump()
    off = Settings(_env_file=None).model_dump()
    assert {k for k in on if on[k] != off[k]} == {"chat_memory_enabled"}


# ------------------------------------------------- the places that must keep naming it


def test_the_example_file_documents_it_and_leaves_it_off():
    lines = (ROOT / ".env.example").read_text().splitlines()
    values = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    assert values["CHAT_MEMORY_ENABLED"] == "false"


def test_the_deploy_reads_the_repository_variable_and_hands_it_to_the_api():
    jobs = yaml.safe_load(DEPLOY.read_text())["jobs"].values()
    env = next(job["env"] for job in jobs if "ACTIONS_ENABLED" in job.get("env", {}))
    assert env["CHAT_MEMORY_ENABLED"] == "${{ vars.CHAT_MEMORY_ENABLED }}"


def test_without_a_repository_variable_the_deploy_leaves_it_off():
    script = DEPLOY.read_text()
    assert "CHAT_MEMORY_ENABLED=${CHAT_MEMORY_ENABLED:-false}" in script
    assert script.count("CHAT_MEMORY_ENABLED=") == 1, (
        "named once, in the command that deploys the API"
    )


def test_the_deploy_guide_lists_it_among_the_optional_variables():
    guide = (ROOT / "docs/documentation/technical/deploy.md").read_text()
    assert "`CHAT_MEMORY_ENABLED`" in guide


# ------------------------------------------------ a developer's .env does not change the tests


def test_every_test_starts_with_the_memory_off_whatever_the_environment_says():
    """A developer trying the memory has it on in the shell or the `.env`; the tests do not."""
    probe = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore",
         "tests/test_chat_memory_config.py::test_probe_the_memory_a_test_starts_with"],
        cwd=ROOT, env={**os.environ, "CHAT_MEMORY_ENABLED": "true", "PROBE": "1"},
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert probe.returncode == 0, probe.stdout[-1200:] + probe.stderr[-400:]
    assert "1 passed" in probe.stdout


def test_probe_the_memory_a_test_starts_with():
    if os.environ.get("PROBE") != "1":
        pytest.skip("only runs inside the session the test above starts")
    assert (
        os.environ["CHAT_MEMORY_ENABLED"] == "false" and get_settings().chat_memory_enabled is False
    )
