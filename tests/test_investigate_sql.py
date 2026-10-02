"""Reviewed SQL against the real demo data. Skipped unless Postgres is up (`make demo-data`)."""

import pytest

from app.adapters.outbound import postgres
from app.adapters.outbound.postgres.investigation import PostgresWarehouse
from app.application.investigate import investigate_charge, investigate_matching

pytestmark = pytest.mark.anyio


def db_is_up() -> bool:
    try:
        postgres.ping()
        return True
    except Exception:
        return False


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def need_demo_data():
    if not db_is_up():
        pytest.skip("Postgres with the demo data is not running")


async def test_duplicate_charge_is_found_four_seconds_apart():
    report = await investigate_charge(
        PostgresWarehouse(), "DEMO-MX-DUPLICATE", "DEMO-MX-DUPLICATE-DUP-B"
    )
    assert report["duplicate"]["duplicate_of"] == "DEMO-MX-DUPLICATE-DUP-A"
    assert report["duplicate"]["seconds_apart"] == 4


async def test_pending_reversed_and_foreign_scenarios():
    warehouse = PostgresWarehouse()
    pending = await investigate_charge(warehouse, "DEMO-CO-PENDING", "DEMO-CO-PENDING-PENDING")
    assert pending["pending"]["is_pending"] and pending["fx"]["is_foreign"]
    reversed_ = await investigate_charge(warehouse, "DEMO-AR-REVERSED", "DEMO-AR-REVERSED-REVERSED")
    assert reversed_["pending"]["is_reversed"] and reversed_["duplicate"] == {"found": False}


async def test_another_customers_charge_is_invisible():
    report = await investigate_charge(PostgresWarehouse(), "DEMO-MX-FX", "DEMO-MX-DUPLICATE-DUP-A")
    assert "error" in report


async def test_search_counts_back_from_the_customers_last_transaction():
    rows = await PostgresWarehouse().search("DEMO-CO-AMBIGUOUS", 3, "amazon", None, None)
    assert [r["transaction_id"] for r in rows] == ["DEMO-CO-AMBIGUOUS-SAMEDAY-3"]
    assert await PostgresWarehouse().search("DEMO-CO-AMBIGUOUS", 90, "%", None, None) == []


async def test_matching_charges_find_the_duplicate_pair_in_one_call():
    report = await investigate_matching(
        PostgresWarehouse(), "DEMO-MX-DUPLICATE", 30, "uber", None, None
    )
    twins = [c for c in report["charges"] if c["duplicate"]["found"]]
    assert len(twins) == 2 and {c["duplicate"]["duplicate_of"] for c in twins} == {"#1", "#2"}
    assert all(c["duplicate"]["seconds_apart"] == 4 for c in twins)
    assert "DEMO-MX-DUPLICATE-DUP" not in str(report)  # no internal ids in what the model sees


async def test_findings_name_the_pair_even_when_the_model_sets_no_merchant():
    # without a merchant filter the newest 3 charges include an unrelated one (#1)
    report = await investigate_matching(
        PostgresWarehouse(), "DEMO-MX-DUPLICATE", 30, None, None, None
    )
    (finding,) = [f for f in report["findings"] if f["kind"] == "duplicate"]
    assert finding["seconds_apart"] == 4 and finding["merchant_name"] == "Uber Trip"
    assert len(finding["charges"]) == 2 and finding["amount"] == 312.4
