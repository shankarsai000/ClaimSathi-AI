"""
Tests for ClaimSathi AI claim creation and validation (Phase 1).
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db

transport = ASGITransport(app=app)


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield


@pytest.mark.anyio
async def test_health_check():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["is_demo"] is True


@pytest.mark.anyio
async def test_transcribe_returns_mock():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/claims/transcribe", json={"use_mock": True, "language": "hi-en"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_mock"] is True
    assert len(data["transcript"]) > 0
    assert len(data["fields"]) == 5


@pytest.mark.anyio
async def test_create_claim_success():
    payload = {
        "policy_reference": "MOT-2024-MH-78432",
        "incident_location": "Andheri East, Mumbai",
        "incident_date": "2024-10-28",
        "vehicle_type": "car",
        "damage_description": "Left door and fender damaged in side collision",
        "transcript": "Mock transcript text",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/claims/", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("DEMO-")
    assert data["is_demo"] is True
    assert "simulated" in data["message"].lower() or "demo" in data["message"].lower()


@pytest.mark.anyio
async def test_create_claim_validation_error():
    payload = {
        "policy_reference": "",
        "incident_location": "Somewhere",
        "incident_date": "2024-10-28",
        "vehicle_type": "car",
        "damage_description": "Some damage",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/claims/", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_get_claim_not_found():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/claims/NONEXISTENT")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_list_claims():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/claims/")
    assert resp.status_code == 200
    data = resp.json()
    assert "claims" in data
    assert "total" in data
    assert data["is_demo"] is True


@pytest.mark.anyio
async def test_create_and_retrieve_claim():
    payload = {
        "policy_reference": "POL-BK-2024-DL-55123",
        "incident_location": "Connaught Place, Delhi",
        "incident_date": "2024-10-27",
        "vehicle_type": "bike",
        "damage_description": "Front mudguard broken, headlight damaged",
        "transcript": "Demo transcript",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/claims/", json=payload)
        claim_id = create_resp.json()["id"]
        detail_resp = await client.get(f"/api/claims/{claim_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["claim"]["id"] == claim_id
    assert detail["claim"]["policy_reference"] == "POL-BK-2024-DL-55123"
    assert len(detail["timeline"]) >= 1
    assert detail["is_demo"] is True
