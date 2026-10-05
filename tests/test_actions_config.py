"""The settings that decide whether actions exist, and the places that must keep naming them."""

from pathlib import Path

import yaml

from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]
ACTION_SETTINGS = (
    "ACTIONS_ENABLED",
    "MAIL_MODE",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "MAIL_FROM",
    "DEMO_INBOXES",
)


def test_env_example_documents_every_setting_of_the_actions():
    documented = {line.split("=")[0] for line in (ROOT / ".env.example").read_text().splitlines()}
    fields = {name.upper() for name in Settings.model_fields}
    for name in ACTION_SETTINGS:
        assert name in fields, f"{name} is not a setting any more"
        assert name in documented, f"{name} is missing from .env.example"


def test_the_example_file_leaves_actions_off_and_mail_simulated():
    values = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.example").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    assert values["ACTIONS_ENABLED"] == "false" and values["MAIL_MODE"] == "simulated"


def deploy_step() -> tuple[dict, str]:
    workflow = yaml.safe_load((ROOT / ".github/workflows/deploy.yml").read_text())
    job = workflow["jobs"]["deploy-api"]
    return job["env"], next(s for s in job["steps"] if s.get("id") == "deploy")["run"]


def test_the_deploy_passes_the_settings_and_mounts_the_mail_password_as_a_secret():
    env, script = deploy_step()
    for name in ("ACTIONS_ENABLED", "MAIL_MODE", "MAIL_FROM", "SMTP_USER", "DEMO_INBOXES"):
        assert name in env, f"deploy-api does not read the repository variable {name}"
        assert f"{name}=${{{name}" in script, f"{name} never reaches the service"
    assert "SMTP_PASSWORD=factored-smtp-password:latest" in script, "the password must be a secret"
    assert "SMTP_PASSWORD=${" not in script, "the password must never travel as a plain variable"


def test_without_a_repository_variable_the_deploy_leaves_actions_off_and_mail_simulated():
    _, script = deploy_step()
    assert "ACTIONS_ENABLED=${ACTIONS_ENABLED:-false}" in script
    assert "MAIL_MODE=${MAIL_MODE:-simulated}" in script
