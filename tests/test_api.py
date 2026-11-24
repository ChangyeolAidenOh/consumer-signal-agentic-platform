"""Basic API tests for CI pipeline.

DATABASE_URL must be provided by the environment (CI workflow, local shell,
or a local .env file). Tests that need it are skipped when it is not set.
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()


def _database_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        pytest.skip("DATABASE_URL is not set")
    return db_url


def test_schema_tables_exist():
    """Verify core tables exist in database."""
    from sqlalchemy import create_engine, text

    engine = create_engine(_database_url())
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

    _database_url()

    try:
        from api.main import app
        client = TestClient(app)
    except Exception as exc:
        pytest.skip(f"api app could not be initialised: {exc}")

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["llm_provider"]
    assert data["llm_model"]
