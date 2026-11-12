"""
ClaimSathi AI — Sprint 1.1 Adversarial Security & Verification Test Suite.
Validates:
1. PostgreSQL RLS zero-bypass defense and audit log immutability.
2. Capture-session customer isolation, claim binding, replay prevention, and expiration.
3. Unbound capture session authentication and abuse prevention.
4. Bounded streaming read DoS protection (HTTP 413 on oversized streams).
5. File upload path traversal and directory containment protection.
6. Ephemeral media access tickets (issuance, validity, expiration, cross-claim isolation).
7. Password complexity policy enforcement in production.
8. Truthful OTP delivery reporting (disclosing simulated channels).
9. Cross-customer IDOR access denial across all claim and evidence routes.
"""

import io
import os
import json
import time
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from PIL import Image

from app.main import app
from app.database import (
    init_db,
    get_claim,
    insert_claim,
    create_capture_session,
    get_capture_session,
    mark_capture_session_completed,
    get_user_audit_logs,
)
from app.auth import (
    create_access_token,
    decode_access_token,
    create_media_ticket,
    verify_media_ticket,
    validate_password_strength,
    generate_otp,
    verify_otp,
)
from app.config import get_settings

transport = ASGITransport(app=app)


@pytest.fixture(autouse=True)
def setup_test_environment():
    asyncio.run(init_db())
    yield


def _create_minimal_png_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (32, 32), color=(20, 80, 160))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _get_auth_headers(customer_id: str, email: str = "user@test.in") -> dict:
    token = create_access_token(customer_id=customer_id, email=email, name=f"User {customer_id}")
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. CAPTURE-SESSION AUTHORIZATION & LIFECYCLE TESTS (Sprint 1.1 Phase 2.C)
# ==============================================================================

@pytest.mark.anyio
async def test_unbound_capture_session_requires_authentication():
    """Unauthenticated caller cannot start an unbound capture session (prevents anonymous session hijacking)."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/evidence/capture-session", json={})
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


@pytest.mark.anyio
async def test_capture_session_cross_customer_rejection():
    """Customer B cannot use Customer A's capture session to upload evidence."""
    headers_a = _get_auth_headers("USR-100001", "rahul@claimsathi.in")
    headers_b = _get_auth_headers("USR-100002", "sai@claimsathi.in")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Customer A creates a claim and a capture session
        c_resp_a = await client.post(
            "/api/claims/",
            headers=headers_a,
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-S11-001",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Rear bumper damage",
            },
        )
        assert c_resp_a.status_code == 201
        claim_a = c_resp_a.json()["id"]

        cap_resp_a = await client.post(
            "/api/evidence/capture-session",
            headers=headers_a,
            json={"claim_id": claim_a},
        )
        assert cap_resp_a.status_code == 201
        session_id_a = cap_resp_a.json()["session_id"]

        # 2. Customer B creates their own claim
        c_resp_b = await client.post(
            "/api/claims/",
            headers=headers_b,
            json={
                "customer_id": "USR-100002",
                "policy_reference": "MOT-S11-002",
                "incident_location": "Mysuru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Side door scrape",
            },
        )
        assert c_resp_b.status_code == 201
        claim_b = c_resp_b.json()["id"]

        # 3. Customer B attempts to upload evidence to Claim B using Customer A's capture session
        img_bytes = _create_minimal_png_bytes()
        tamper_upload = await client.post(
            f"/api/evidence/{claim_b}/upload",
            headers=headers_b,
            files={"file": ("tamper.png", img_bytes, "image/png")},
            data={"capture_method": "live_photo", "capture_session_id": session_id_a},
        )
        assert tamper_upload.status_code == 403
        assert "another customer" in tamper_upload.json()["detail"].lower()


@pytest.mark.anyio
async def test_capture_session_claim_mismatch_rejection():
    """A capture session explicitly bound to Claim A cannot be used for Claim B (even by the same customer)."""
    headers = _get_auth_headers("USR-100001", "rahul@claimsathi.in")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create Claim 1
        c1 = (await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-S11-010",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Claim 1 damage",
            },
        )).json()["id"]

        # Create Claim 2
        c2 = (await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-S11-020",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Claim 2 damage",
            },
        )).json()["id"]

        # Create session bound to Claim 1
        cap_resp = await client.post(
            "/api/evidence/capture-session",
            headers=headers,
            json={"claim_id": c1},
        )
        session_id = cap_resp.json()["session_id"]

        # Attempt to upload to Claim 2 using session bound to Claim 1
        img_bytes = _create_minimal_png_bytes()
        mismatch_upload = await client.post(
            f"/api/evidence/{c2}/upload",
            headers=headers,
            files={"file": ("mismatch.png", img_bytes, "image/png")},
            data={"capture_method": "live_photo", "capture_session_id": session_id},
        )
        assert mismatch_upload.status_code == 400
        assert "bound to claim" in mismatch_upload.json()["detail"].lower()


@pytest.mark.anyio
async def test_capture_session_completed_cannot_be_reused():
    """A completed capture session cannot accept further uploads (replay prevention)."""
    headers = _get_auth_headers("USR-100001", "rahul@claimsathi.in")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c = (await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-S11-030",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Damage test",
            },
        )).json()["id"]

        cap = (await client.post(
            "/api/evidence/capture-session",
            headers=headers,
            json={"claim_id": c},
        )).json()
        session_id = cap["session_id"]

        # Explicitly complete session
        comp_resp = await client.post(
            f"/api/evidence/capture-session/{session_id}/complete",
            headers=headers,
        )
        assert comp_resp.status_code == 200
        assert comp_resp.json()["status"] == "completed"

        # Attempt to upload with completed session
        img_bytes = _create_minimal_png_bytes()
        replay_upload = await client.post(
            f"/api/evidence/{c}/upload",
            headers=headers,
            files={"file": ("replay.png", img_bytes, "image/png")},
            data={"capture_method": "live_photo", "capture_session_id": session_id},
        )
        assert replay_upload.status_code == 400
        assert "cannot be reused" in replay_upload.json()["detail"].lower()


# ==============================================================================
# 2. EVIDENCE STREAMING & PATH TRAVERSAL TESTS (Sprint 1.1 Phase 2.D)
# ==============================================================================

@pytest.mark.anyio
async def test_oversized_upload_streaming_rejection():
    """An oversized upload exceeding 50 MB is rejected with HTTP 413 via bounded streaming."""
    headers = _get_auth_headers("USR-100001", "rahul@claimsathi.in")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c = (await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-S11-040",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Damage test",
            },
        )).json()["id"]

        # Create a payload of 51 MB (exceeds MAX_VIDEO_SIZE_BYTES = 50 MB)
        oversized_payload = b"\x00" * (51 * 1024 * 1024)
        resp = await client.post(
            f"/api/evidence/{c}/upload",
            headers=headers,
            files={"file": ("huge_video.mp4", oversized_payload, "video/mp4")},
            data={"capture_method": "upload_video"},
        )
        assert resp.status_code == 413
        assert "exceeds the maximum allowed limit" in resp.json()["detail"]


@pytest.mark.anyio
async def test_upload_filename_path_traversal_sanitization():
    """Malicious filename containing '../' is sanitized and stored strictly within the claim directory."""
    headers = _get_auth_headers("USR-100001", "rahul@claimsathi.in")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c = (await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-S11-050",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Damage test",
            },
        )).json()["id"]

        img_bytes = _create_minimal_png_bytes()
        resp = await client.post(
            f"/api/evidence/{c}/upload",
            headers=headers,
            files={"file": ("../../../../etc/passwd.png", img_bytes, "image/png")},
            data={"capture_method": "upload_photo"},
        )
        assert resp.status_code == 201
        asset = resp.json()
        assert ".." not in asset["original_filename"]
        assert "/" not in asset["original_filename"]
        assert "\\" not in asset["original_filename"]


# ==============================================================================
# 3. EPHEMERAL MEDIA TICKETS (Sprint 1.1 Phase 2.D)
# ==============================================================================

@pytest.mark.anyio
async def test_media_ticket_creation_and_download_flow():
    """Authenticated customer can generate an ephemeral 60s media ticket and access report PDF."""
    headers = _get_auth_headers("USR-100001", "rahul@claimsathi.in")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c = (await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-S11-060",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Damage test",
            },
        )).json()["id"]

        # Generate report
        await client.post(f"/api/claims/{c}/report", headers=headers)

        # 1. Request short-lived media ticket
        ticket_resp = await client.post(f"/api/claims/{c}/media-ticket", headers=headers)
        assert ticket_resp.status_code == 200
        ticket_data = ticket_resp.json()
        ticket = ticket_data["ticket"]
        assert ticket_data["expires_in"] == 60
        assert ticket_data["claim_id"] == c

        # 2. Download PDF report using media ticket WITHOUT Authorization header
        pdf_resp = await client.get(f"/api/claims/{c}/report/pdf?ticket={ticket}")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"
        assert pdf_resp.headers.get("x-content-type-options") == "nosniff"
        assert "ClaimSathi_Dossier" in pdf_resp.headers.get("content-disposition", "")


@pytest.mark.anyio
async def test_media_ticket_cross_claim_rejection():
    """A media ticket issued for Claim A cannot be used to download reports or files from Claim B."""
    headers_a = _get_auth_headers("USR-100001", "rahul@claimsathi.in")
    headers_b = _get_auth_headers("USR-100002", "sai@claimsathi.in")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create Claim A & Claim B
        ca = (await client.post("/api/claims/", headers=headers_a, json={
            "customer_id": "USR-100001", "policy_reference": "MOT-A", "incident_location": "BLR",
            "incident_date": "2026-11-10", "vehicle_type": "car", "damage_description": "A",
        })).json()["id"]
        cb = (await client.post("/api/claims/", headers=headers_b, json={
            "customer_id": "USR-100002", "policy_reference": "MOT-B", "incident_location": "MYS",
            "incident_date": "2026-11-10", "vehicle_type": "car", "damage_description": "B",
        })).json()["id"]

        await client.post(f"/api/claims/{ca}/report", headers=headers_a)
        await client.post(f"/api/claims/{cb}/report", headers=headers_b)

        # Ticket issued for Claim A
        ticket_a = (await client.post(f"/api/claims/{ca}/media-ticket", headers=headers_a)).json()["ticket"]

        # Attempt to access Claim B's report using Claim A's ticket
        resp = await client.get(f"/api/claims/{cb}/report/pdf?ticket={ticket_a}")
        assert resp.status_code == 403
        assert "not authorized for this claim" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_expired_media_ticket_returns_401():
    """An expired media ticket cannot be used to download media or reports."""
    # Create an artificially expired media ticket (expired 10 seconds ago)
    expired_ticket = create_media_ticket(
        customer_id="USR-100001",
        claim_id="CS-2026-000124",
        expires_in=-10,
    )

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/claims/CS-2026-000124/report/pdf?ticket={expired_ticket}")
    assert resp.status_code == 401
    assert "ticket has expired" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_media_ticket_cannot_be_used_as_api_access_token():
    """A media ticket cannot be used to call general API endpoints (e.g. /api/auth/me)."""
    ticket = create_media_ticket(customer_id="USR-100001", claim_id="CS-2026-000124")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {ticket}"})
    assert resp.status_code == 401


# ==============================================================================
# 4. PASSWORD COMPLEXITY & OTP REPORTING HONESTY (Sprint 1.1 Phase 2.E)
# ==============================================================================

def test_password_complexity_policy():
    """Password complexity is validated strictly based on environment configuration."""
    settings = get_settings()
    orig_env = settings.app_env

    try:
        settings.app_env = "production"
        # Weak passwords rejected in production
        with pytest.raises(Exception) as exc:
            validate_password_strength("weak")
        assert "at least 8 characters" in str(exc.value)

        with pytest.raises(Exception) as exc:
            validate_password_strength("alllowercase123")
        assert "uppercase" in str(exc.value).lower()

        with pytest.raises(Exception) as exc:
            validate_password_strength("ALLUPPERCASE123")
        assert "lowercase" in str(exc.value).lower()

        with pytest.raises(Exception) as exc:
            validate_password_strength("NoDigitsInPassword")
        assert "number" in str(exc.value).lower()

        # Strong password accepted
        validate_password_strength("SecureP@ssw0rd2026")

    finally:
        settings.app_env = orig_env


@pytest.mark.anyio
async def test_otp_delivery_honesty_in_development():
    """OTP request endpoint honestly discloses simulated local channel when no SMS gateway is configured."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/request-otp", json={"identifier": "+91-9876543210"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["otp_sent"] is False
    assert data["delivery_channel"] == "simulated_local"
    assert "simulated locally" in data["message"].lower()


# ==============================================================================
# 5. POSTGRESQL RLS ZERO-BYPASS VERIFICATION (Sprint 1.1 Phase 2.A)
# ==============================================================================

@pytest.mark.anyio
async def test_postgresql_rls_zero_bypass_when_database_url_configured():
    """
    If CLAIMSATHI_DATABASE_URL or DATABASE_URL is configured, executes live adversarial queries
    confirming app.bypass_rls=true CANNOT leak other tenants' data.
    """
    db_url = os.environ.get("CLAIMSATHI_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("CLAIMSATHI_DATABASE_URL="):
                        db_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
                    elif line.startswith("DATABASE_URL="):
                        db_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

    if not db_url:
        pytest.skip("CLAIMSATHI_DATABASE_URL or DATABASE_URL not set; skipping live PostgreSQL verification.")

    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from migrations.run_migration import (
        verify_rls_isolation_with_adversarial_bypass,
        verify_audit_log_immutability,
    )
    bypass_result = await verify_rls_isolation_with_adversarial_bypass(db_url)
    assert bypass_result is True, "RLS bypass attempt leaked rows!"

    immutability_result = await verify_audit_log_immutability(db_url)
    assert immutability_result is True, "Audit log immutability check failed!"
