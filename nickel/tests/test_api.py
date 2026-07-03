"""Integration-тесты FastAPI (без Neo4j/Qdrant)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_platform_db, monkeypatch):
    monkeypatch.setenv("SKIP_OLLAMA_HEALTH", "true")
    from api.main import app

    return TestClient(app)


def test_live_endpoint(client):
    r = client.get("/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ontology_public(client):
    r = client.get("/api/v1/ontology")
    assert r.status_code == 200
    data = r.json()
    assert "node_types" in data
    assert "relations" in data


def test_auth_setup_and_token(client, tmp_platform_db):
    r = client.post(
        "/api/v1/auth/setup",
        json={"email": "jury@test.local", "name": "Jury"},
    )
    assert r.status_code == 200
    api_key = r.json()["api_key"]
    assert len(api_key) >= 32

    r2 = client.post("/api/v1/auth/token", json={"api_key": api_key})
    assert r2.status_code == 200
    token = r2.json()["access_token"]

    r3 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 200
    assert r3.json()["email"] == "jury@test.local"


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded", "unavailable")
    assert "components" in body or "neo4j" in body
