"""Typed settings loaded from environment variables and `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Role = Literal["fast", "smart"]
DEFAULT_MODELS: dict[str, dict[Role, str]] = {
    "ollama": {"fast": "qwen3.5:4b", "smart": "qwen3.5:9b"},
    "google_genai": {"fast": "gemini-2.5-flash", "smart": "gemini-2.5-pro"},
}
MIN_SECRET_LENGTH = 32
LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db"})  # "db" = docker compose


def database_host(url: str) -> str:
    """Host of a Postgres URL. Cloud SQL sockets carry it as `?host=/cloudsql/...`."""
    parts = urlsplit(url)
    return parts.hostname or parse_qs(parts.query).get("host", [""])[0]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    jwt_secret: str = "change-me-local-only-not-for-production"
    access_token_ttl_minutes: int = 15
    operator_key: str = "change-me-local-only-operator-key"  # opens the operator console (/crm)
    demo_customer_ids: str = ""  # comma-separated; offered in the UI and can start a demo session
    public_base_url: str = "http://localhost:8080"
    cors_origins: str = "http://localhost:3000"  # comma-separated origins of the web

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-2"
    s3_bucket: str = "factored-datathon-2026-s3-157725502942-us-east-2-an"
    s3_prefix: str = "data/"
    data_dir: Path = Path("data")
    database_url: str = "postgresql://agent:agent@localhost:5432/agent"

    llm_provider: str = ""  # empty: ollama when APP_ENV=local, google_genai otherwise
    llm_model_fast: str = ""  # empty: DEFAULT_MODELS[provider]
    llm_model_smart: str = ""
    ollama_base_url: str = "http://localhost:11434"
    google_api_key: str = ""
    google_genai_use_vertexai: bool = False
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    @model_validator(mode="after")
    def database_matches_environment(self) -> "Settings":
        """Fail closed: local never touches a remote database, and cloud never falls back to a
        local one. The messages never print the URL (it holds the password)."""
        is_local_db = database_host(self.database_url) in LOCAL_DB_HOSTS
        if self.app_env == "local" and not is_local_db:
            raise ValueError(
                "APP_ENV=local only uses the local Postgres (localhost, or `db` in docker "
                "compose). DATABASE_URL points somewhere else."
            )
        if self.app_env != "local" and is_local_db:
            raise ValueError(
                f"APP_ENV={self.app_env} needs DATABASE_URL to point to Cloud SQL, not to a "
                "local database."
            )
        return self

    @model_validator(mode="after")
    def secrets_are_real_outside_local(self) -> "Settings":
        """A signing key nobody chose would let anyone mint tokens; an operator key nobody chose
        would let anyone read every chat."""
        for name, secret in (("JWT_SECRET", self.jwt_secret), ("OPERATOR_KEY", self.operator_key)):
            if self.app_env != "local" and (
                secret.startswith("change-me") or len(secret) < MIN_SECRET_LENGTH
            ):
                raise ValueError(
                    f"{name} must be a random string of at least {MIN_SECRET_LENGTH} characters "
                    "outside APP_ENV=local (for example: openssl rand -hex 32)."
                )
        return self

    @property
    def provider(self) -> str:
        return self.llm_provider or ("ollama" if self.app_env == "local" else "google_genai")

    def model(self, role: Role) -> str:
        explicit = self.llm_model_fast if role == "fast" else self.llm_model_smart
        return explicit or DEFAULT_MODELS[self.provider][role]

    @property
    def llm_configured(self) -> bool:
        if self.provider == "ollama":
            return True
        return bool(self.google_api_key or self.google_genai_use_vertexai)


@lru_cache
def get_settings() -> Settings:
    return Settings()
