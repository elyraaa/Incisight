import os
from pathlib import Path

DB_FILE = Path(__file__).parent / "test.db"
if DB_FILE.exists(): DB_FILE.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE.as_posix()}"
os.environ["TOOL_API_SECRET"] = "test-tool-secret-000000"
os.environ["ADMIN_API_SECRET"] = "test-admin-secret-00000"

import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as value: yield value

@pytest.fixture
def incident(client):
    response=client.post("/api/incidents",json={"title":"Customer Login Failure","affected_service":"Authentication Service","severity":"SEV-1","keyterms":["AuthN","PostgreSQL"]})
    assert response.status_code==201
    return response.json()

@pytest.fixture
def tool_headers(): return {"X-Tool-Secret":"test-tool-secret-000000"}

