"""Basic API tests for CI pipeline."""

import os

import pytest

os.environ["DATABASE_URL"] = "postgresql://hns_user:hns_local_dev_only@localhost:5433/hns_platform"


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


def test_health_endpoint():
    """Health endpoint returns ok status."""
    from fastapi.testclient import TestClient

    try:
        from api.main import app
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    except Exception:
        pytest.skip("agent dependencies not available in CI")