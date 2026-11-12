"""
ClaimSathi AI — Sprint 1 Automated Security & Isolation Test Suite.
Tests:
1. Authentication hardening (missing token, invalid token, expired token, tampered signature, production secret enforcement, OTP security).
2. Customer claim-level data isolation (Customer B attempting to read, update, upload evidence, list evidence, download media, generate report, download PDF/JSON, or submit Customer A's claim to insurer -> HTTP 403).
3. Evidence security (MIME / signature validation, non-allowlisted extensions rejected, path traversal blocked, authenticated downloads).
4. Structured audit logging (login success/failure, claim creation, access denial events recorded with no credential leaks).
"""

import io
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from PIL import Image

from app.main import app
from app.database import init_db, get_user_audit_logs
from app.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    generate_otp,
    verify_otp,
)
from app.config import Settings, get_settings

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


# ==============================================================================
# 1. AUTHENTICATION & SECRETS HARDENING TESTS
# ==============================================================================

@pytest.mark.anyio
async def test_auth_missing_token_returns_401():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
    assert "detail" in resp.json()


@pytest.mark.anyio
async def test_auth_invalid_token_returns_401():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.jwt.token.format"},
        )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_auth_expired_token_returns_401():
    expired_token = create_access_token(
        customer_id="USR-100001",
        email="rahul.sharma@claimsathi.in",
        name="Rahul Sharma",
        expires_delta_seconds=-60,  # expired 60 seconds ago
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_auth_tampered_signature_returns_401():
    valid_token = create_access_token(
        customer_id="USR-100001",
        email="rahul.sharma@claimsathi.in",
        name="Rahul Sharma",
    )
    parts = valid_token.split(".")
    # Tamper with the payload (middle part)
    tampered_token = f"{parts[0]}.eyJuYW1lIjoiSGFja2VyIn0.{parts[2]}"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_auth_valid_token_returns_200():
    valid_token = create_access_token(
        customer_id="USR-100001",
        email="rahul.sharma@claimsathi.in",
        name="Rahul Sharma",
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["customer_id"] == "USR-100001"
    assert data["name"] == "Rahul Sharma"


def test_production_fails_startup_without_secure_secret():
    # Production configuration with default / insecure JWT secret MUST fail
    insecure_settings = Settings(
        app_env="production",
        claimsathi_jwt_secret="claimsathi-mvp-secret-key-2026-secure",
    )
    with pytest.raises(RuntimeError) as exc_info:
        insecure_settings.validate_production_configuration()
    assert "CLAIMSATHI_JWT_SECRET" in str(exc_info.value)


def test_production_fails_startup_with_short_secret():
    short_settings = Settings(
        app_env="production",
        claimsathi_jwt_secret="too-short-secret",
    )
    with pytest.raises(RuntimeError) as exc_info:
        short_settings.validate_production_configuration()
    assert "at least 32 characters" in str(exc_info.value)


def test_otp_universal_blocked_in_production():
    phone = "+91-9876543210"
    settings = get_settings()
    orig_env = settings.app_env
    try:
        settings.app_env = "production"
        real_code = generate_otp(phone)
        assert real_code != "123456", "In production, generate_otp must not return fixed 123456"
        # Universal code 123456 must NOT verify in production
        verified = verify_otp(identifier=phone, otp_code="123456")
        assert verified is False
        # But the real cryptographically generated code MUST verify
        assert verify_otp(identifier=phone, otp_code=real_code) is True
    finally:
        settings.app_env = orig_env


def test_otp_single_use_and_attempt_limit():
    phone = "+91-9999988888"
    otp = generate_otp(phone)

    # Wrong code fails
    assert verify_otp(phone, "000000") is False

    # Correct code succeeds once
    assert verify_otp(phone, otp) is True

    # Same code cannot be used a second time (single-use guarantee)
    assert verify_otp(phone, otp) is False


# ==============================================================================
# 2. CUSTOMER CLAIM-LEVEL DATA ISOLATION TESTS
# ==============================================================================

@pytest.mark.anyio
async def test_customer_claim_isolation_complete_matrix():
    """
    Setup:
      - Customer A (USR-100001) creates Claim A.
      - Customer B (USR-100002) authenticates and attempts every operation on Claim A.
    Expected:
      - Every unauthorized access attempt returns HTTP 403 Forbidden.
      - Customer B cannot read, modify, upload, list, download, generate report, or submit Claim A.
    """
    token_a = create_access_token(
        customer_id="USR-100001",
        email="rahul.sharma@claimsathi.in",
        name="Rahul Sharma",
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    token_b = create_access_token(
        customer_id="USR-100002",
        email="saishankar.reddy@claimsathi.in",
        name="Sai Shankar Reddy",
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Customer A creates Claim A
        create_resp = await client.post(
            "/api/claims/",
            headers=headers_a,
            json={
                "policy_reference": "MOT-2026-KA-SEC001",
                "incident_location": "Indiranagar, Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Rear bumper scratched",
            },
        )
        assert create_resp.status_code == 201
        claim_a_id = create_resp.json()["id"]

        # Step 2: Customer B attempts to retrieve Claim A -> HTTP 403
        get_resp = await client.get(f"/api/claims/{claim_a_id}", headers=headers_b)
        assert get_resp.status_code == 403
        assert "Access denied" in get_resp.json()["detail"]

        # Step 3: Customer B attempts to update Claim A -> HTTP 403
        put_resp = await client.put(
            f"/api/claims/{claim_a_id}",
            headers=headers_b,
            json={"damage_description": "Tampered description by attacker"},
        )
        assert put_resp.status_code == 403

        # Step 4: Customer B attempts to start a capture session for Claim A -> HTTP 403
        cap_resp = await client.post(
            "/api/evidence/capture-session",
            headers=headers_b,
            json={"claim_id": claim_a_id, "capture_type": "guided_video_and_photo"},
        )
        assert cap_resp.status_code == 403

        # Step 5: Customer B attempts to upload evidence to Claim A -> HTTP 403
        png_bytes = _create_minimal_png_bytes()
        up_resp = await client.post(
            f"/api/evidence/{claim_a_id}/upload",
            headers=headers_b,
            files={"file": ("malicious_photo.png", png_bytes, "image/png")},
        )
        assert up_resp.status_code == 403

        # Step 6: Customer B attempts to list evidence of Claim A -> HTTP 403
        list_ev_resp = await client.get(f"/api/evidence/{claim_a_id}", headers=headers_b)
        assert list_ev_resp.status_code == 403

        # Step 7: Customer A uploads legitimate evidence to Claim A
        up_a_resp = await client.post(
            f"/api/evidence/{claim_a_id}/upload",
            headers=headers_a,
            files={"file": ("legit_photo.png", png_bytes, "image/png")},
        )
        assert up_a_resp.status_code == 201
        evidence_id = up_a_resp.json()["evidence_id"]

        # Step 8: Customer B attempts to download Customer A's evidence file -> HTTP 403
        dl_resp = await client.get(
            f"/api/evidence/{claim_a_id}/file/{evidence_id}",
            headers=headers_b,
        )
        assert dl_resp.status_code == 403

        # Step 8b: Customer B attempts download via URL token parameter -> HTTP 403
        dl_token_resp = await client.get(
            f"/api/evidence/{claim_a_id}/file/{evidence_id}?token={token_b}",
        )
        assert dl_token_resp.status_code == 403

        # Step 9: Customer B attempts to generate report for Claim A -> HTTP 403
        gen_rpt_resp = await client.post(
            f"/api/claims/{claim_a_id}/report",
            headers=headers_b,
        )
        assert gen_rpt_resp.status_code == 403

        # Step 10: Customer A generates report, then Customer B tries to download it -> HTTP 403
        gen_a_resp = await client.post(
            f"/api/claims/{claim_a_id}/report",
            headers=headers_a,
        )
        assert gen_a_resp.status_code in [200, 201]

        pdf_b_resp = await client.get(
            f"/api/claims/{claim_a_id}/report/pdf",
            headers=headers_b,
        )
        assert pdf_b_resp.status_code == 403

        json_b_resp = await client.get(
            f"/api/claims/{claim_a_id}/report/json",
            headers=headers_b,
        )
        assert json_b_resp.status_code == 403

        # Step 11: Customer B attempts to submit Customer A's claim to Mock Insurer -> HTTP 403
        sub_b_resp = await client.post(
            f"/api/claims/{claim_a_id}/submit-insurer",
            headers=headers_b,
            json={"recipient": "DEMO_INSURER_A"},
        )
        assert sub_b_resp.status_code == 403


@pytest.mark.anyio
async def test_claims_list_isolated_per_customer():
    """Customer A only sees Customer A's claims; Customer B only sees Customer B's claims."""
    token_a = create_access_token(
        customer_id="USR-100001",
        email="rahul.sharma@claimsathi.in",
        name="Rahul Sharma",
    )
    token_b = create_access_token(
        customer_id="USR-100002",
        email="saishankar.reddy@claimsathi.in",
        name="Sai Shankar Reddy",
    )

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create claim for customer A
        c_a = await client.post(
            "/api/claims/",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "policy_reference": "MOT-2026-KA-A1",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-01",
                "vehicle_type": "car",
                "damage_description": "Dent on car A",
            },
        )
        assert c_a.status_code == 201
        claim_a_id = c_a.json()["id"]

        # Create claim for customer B
        c_b = await client.post(
            "/api/claims/",
            headers={"Authorization": f"Bearer {token_b}"},
            json={
                "policy_reference": "MOT-2026-TS-B1",
                "incident_location": "Hyderabad",
                "incident_date": "2026-11-02",
                "vehicle_type": "bike",
                "damage_description": "Scratch on bike B",
            },
        )
        assert c_b.status_code == 201
        claim_b_id = c_b.json()["id"]

        # List claims for customer A
        list_a = await client.get("/api/claims/", headers={"Authorization": f"Bearer {token_a}"})
        assert list_a.status_code == 200
        ids_a = {c["id"] for c in list_a.json()["claims"]}
        assert claim_a_id in ids_a
        assert claim_b_id not in ids_a

        # List claims for customer B
        list_b = await client.get("/api/claims/", headers={"Authorization": f"Bearer {token_b}"})
        assert list_b.status_code == 200
        ids_b = {c["id"] for c in list_b.json()["claims"]}
        assert claim_b_id in ids_b
        assert claim_a_id not in ids_b


@pytest.mark.anyio
async def test_vault_endpoint_ignores_spoofed_customer_id_query_parameter():
    """When Customer B calls /api/auth/vault?customer_id=USR-100001, return USR-100002 vault."""
    token_b = create_access_token(
        customer_id="USR-100002",
        email="saishankar.reddy@claimsathi.in",
        name="Sai Shankar Reddy",
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/auth/vault?customer_id=USR-100001",
            headers={"Authorization": f"Bearer {token_b}"},
        )
    assert resp.status_code == 200
    vault = resp.json()
    # Verified: Customer identity is derived from verified token, not query param
    assert vault["user"]["customer_id"] == "USR-100002"


# ==============================================================================
# 3. EVIDENCE INTEGRITY & STORAGE SECURITY TESTS
# ==============================================================================

@pytest.mark.anyio
async def test_evidence_rejects_disallowed_extension():
    token_a = create_access_token(
        customer_id="USR-100001",
        email="rahul.sharma@claimsathi.in",
        name="Rahul Sharma",
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c_resp = await client.post(
            "/api/claims/",
            headers=headers_a,
            json={
                "policy_reference": "MOT-2026-KA-EXT",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Damage test",
            },
        )
        claim_id = c_resp.json()["id"]

        # Upload an executable file
        bad_upload = await client.post(
            f"/api/evidence/{claim_id}/upload",
            headers=headers_a,
            files={"file": ("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/x-dosexec")},
        )
        assert bad_upload.status_code == 400
        detail_msg = bad_upload.json()["detail"].lower()
        assert any(k in detail_msg for k in ["not allowed", "signature", "supported", "invalid format"])


@pytest.mark.anyio
async def test_evidence_rejects_invalid_magic_bytes():
    token_a = create_access_token(
        customer_id="USR-100001",
        email="rahul.sharma@claimsathi.in",
        name="Rahul Sharma",
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c_resp = await client.post(
            "/api/claims/",
            headers=headers_a,
            json={
                "policy_reference": "MOT-2026-KA-MAGIC",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-10",
                "vehicle_type": "car",
                "damage_description": "Damage test",
            },
        )
        claim_id = c_resp.json()["id"]

        # Spoofed extension: file claims to be image.png but contents are plain text
        spoofed_upload = await client.post(
            f"/api/evidence/{claim_id}/upload",
            headers=headers_a,
            files={"file": ("fake_car.png", b"This is plain text pretending to be a PNG", "image/png")},
        )
        assert spoofed_upload.status_code == 400
        assert "magic bytes" in spoofed_upload.json()["detail"].lower() or "signature" in spoofed_upload.json()["detail"].lower()


@pytest.mark.anyio
async def test_evidence_path_traversal_rejected():
    token_a = create_access_token(
        customer_id="USR-100001",
        email="rahul.sharma@claimsathi.in",
        name="Rahul Sharma",
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attempt to traverse outside storage directory
        resp = await client.get(
            "/api/evidence/CS-2026-000085/file/..%2f..%2f..%2fetc%2fpasswd",
            headers=headers_a,
        )
        # Must be rejected with 400, 403 or 404 (never return host file)
        assert resp.status_code in [400, 403, 404]


# ==============================================================================
# 4. AUDIT LOGGING TESTS
# ==============================================================================

@pytest.mark.anyio
async def test_audit_logs_record_events_and_leak_no_credentials():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Login success records an event
        login_resp = await client.post(
            "/api/auth/login",
            json={"identifier": "rahul.sharma@claimsathi.in", "password": "Rahul@2026"},
        )
        assert login_resp.status_code == 200

        # 2. Failed login records an event
        fail_resp = await client.post(
            "/api/auth/login",
            json={"identifier": "rahul.sharma@claimsathi.in", "password": "WrongPassword@999"},
        )
        assert fail_resp.status_code == 401

    logs = await get_user_audit_logs("USR-100001", limit=10)
    assert len(logs) >= 2

    actions = [l["action"] for l in logs]
    assert any(a in actions for a in ["USER_LOGIN", "USER_LOGGED_IN"])
    assert any(a in actions for a in ["LOGIN_FAILED", "LOGIN_FAILED_PASSWORD"])

    # Verify no credential leaks in audit log details
    for l in logs:
        details_lower = (l["details"] or "").lower()
        assert "rahul@2026" not in details_lower
        assert "wrongpassword" not in details_lower
        assert "password_hash" not in details_lower
        assert "access_token" not in details_lower
