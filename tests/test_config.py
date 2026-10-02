import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "APP_ENV",
        "DATABASE_URL",
        "LLM_PROVIDER",
        "LLM_MODEL_FAST",
        "LLM_MODEL_SMART",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


CLOUD_SQL = "postgresql://app:s3cret@/agent?host=/cloudsql/proj:us-central1:main"
SECRET = "x" * 32  # a signing key that is not the placeholder


def settings(**overrides: str) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_local_defaults_to_ollama() -> None:
    s = settings(app_env="local")
    assert (s.provider, s.model("fast"), s.model("smart")) == ("ollama", "qwen3.5:4b", "qwen3.5:9b")
    assert s.llm_configured


def test_cloud_defaults_to_gemini_and_echoes_without_key() -> None:
    s = settings(app_env="cloud", database_url=CLOUD_SQL, jwt_secret=SECRET)
    assert (s.provider, s.model("fast")) == ("google_genai", "gemini-2.5-flash")
    assert not s.llm_configured


def test_explicit_provider_and_model_win() -> None:
    s = settings(app_env="local", llm_provider="google_genai", llm_model_fast="gemini-flash-lite")
    assert (s.provider, s.model("fast"), s.model("smart")) == (
        "google_genai",
        "gemini-flash-lite",
        "gemini-2.5-pro",
    )


def test_local_uses_the_local_database_including_the_compose_host() -> None:
    assert settings(app_env="local").database_url.endswith("localhost:5432/agent")
    settings(app_env="local", database_url="postgresql://agent:agent@db:5432/agent")


def test_local_refuses_a_remote_database() -> None:
    with pytest.raises(ValueError, match="only uses the local Postgres"):
        settings(app_env="local", database_url=CLOUD_SQL)
    with pytest.raises(ValueError, match="only uses the local Postgres"):
        settings(app_env="local", database_url="postgresql://u:p@10.1.2.3:5432/agent")


def test_cloud_refuses_the_local_default_and_never_prints_the_password() -> None:
    with pytest.raises(ValueError, match="needs DATABASE_URL to point to Cloud SQL") as error:
        settings(
            app_env="cloud", jwt_secret=SECRET
        )  # DATABASE_URL not set: falls back to localhost
    assert "agent:agent" not in str(error.value)
    with pytest.raises(ValueError, match="Cloud SQL"):
        settings(
            app_env="cloud",
            database_url="postgresql://u:pw@127.0.0.1:5432/agent",
            jwt_secret=SECRET,
        )


def test_cloud_accepts_a_cloud_sql_socket_or_private_ip() -> None:
    assert settings(app_env="cloud", database_url=CLOUD_SQL, jwt_secret=SECRET)
    assert settings(
        app_env="cloud", database_url="postgresql://u:p@10.1.2.3:5432/agent", jwt_secret=SECRET
    )


def test_cloud_refuses_the_placeholder_or_a_short_signing_key() -> None:
    for weak in ("change-me", "change-me-local-only-not-for-production", "short", "x" * 31):
        with pytest.raises(ValueError, match="JWT_SECRET must be a random string"):
            settings(app_env="cloud", database_url=CLOUD_SQL, jwt_secret=weak)
    settings(app_env="local")  # the placeholder is fine on a laptop
