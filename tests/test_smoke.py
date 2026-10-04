from fastapi.testclient import TestClient

from app.adapters.inbound.http import app
from app.adapters.outbound import llm, postgres


def test_health() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"


def test_ready_reports_each_failing_dependency(monkeypatch) -> None:
    def llm_down() -> str:
        raise RuntimeError("run `make llm`")

    monkeypatch.setattr(postgres, "ping", lambda: "ok")
    monkeypatch.setattr(llm, "ping", llm_down)
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"db": "ok", "llm": "error: run `make llm`"}


def test_demo_customers_are_only_the_listed_ones_in_any_environment(monkeypatch) -> None:
    from app.adapters.inbound import http
    from app.config import get_settings

    async def list_customers(ids):
        return [{"customer_id": i} for i in ids]

    monkeypatch.setattr(http, "list_customers", list_customers)
    monkeypatch.setattr(get_settings(), "demo_customer_ids", "CLI-A, CLI-B")
    with TestClient(app) as client:
        monkeypatch.setattr(get_settings(), "app_env", "local")
        assert client.get("/api/demo-customers").json() == [
            {"customer_id": "CLI-A"},
            {"customer_id": "CLI-B"},
        ]
        monkeypatch.setattr(get_settings(), "app_env", "cloud")
        assert [c["customer_id"] for c in client.get("/api/demo-customers").json()] == [
            "CLI-A",
            "CLI-B",
        ]  # the same list in the cloud: this endpoint only echoes DEMO_CUSTOMER_IDS
        monkeypatch.setattr(get_settings(), "demo_customer_ids", "")
        assert client.get("/api/demo-customers").json() == []
