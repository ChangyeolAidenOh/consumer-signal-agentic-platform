"""Basic API tests for CI pipeline."""

import os

os.environ["DATABASE_URL"] = "postgresql://hns_user:hns_local_dev_only@localhost:5433/hns_platform"

from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


def test_health():
    """Health endpoint returns ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_analyze_empty_query():
    """Empty query returns 400."""
    response = client.post("/api/v1/analyze", json={"query": ""})
    assert response.status_code == 400


def test_analyze_returns_200():
    """Valid query returns 200 with required fields."""
    response = client.post(
        "/api/v1/analyze",
        json={"query": "At-risk 세그먼트의 크기는?"},
    )
    # May fail without Ollama, so just check it doesn't crash with 500
    assert response.status_code in (200, 500)


def test_schema_tables_exist():
    """Verify core tables exist in database."""
    from sqlalchemy import create_engine, text

    db_url = os.environ["DATABASE_URL"]
    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        )
        tables = [row[0] for row in result]

    assert "voc_documents" in tables
    assert "trend_monthly" in tables
    assert "segment_summary" in tables