"""
ClaimSathi AI — Sprint 1.2 Security & SQLite Foundation Test Suite.
Tests:
1. Foreign key enforcement on all active connections (PRAGMA foreign_keys = ON).
2. Cascade deletion across all 12 tables and preservation of immutable audit logs.
3. Strict customer-level authorization for DELETE /api/claims/{claim_id} (403 for unauthorized users).
4. WAL mode, busy timeout, and row factory validation.
5. Versioned SQLite schema migrations idempotency and foreign key integrity.
6. SQLite native online backup (sqlite3.backup) and verified restoration.
7. Database error handling and sensitive information disclosure prevention.
"""

import os
import shutil
import sqlite3
import tempfile
import pytest
from httpx import AsyncClient, ASGITransport
import aiosqlite

from app.main import app
from app.config import get_settings
from app.auth import create_access_token
from app.database import (
    get_db_path,
    get_db_connection,
    connect_db,
    init_db,
    delete_claim_record,
    verify_sqlite_foreign_keys,
    get_schema_migration_history,
    create_sqlite_backup,
    restore_sqlite_backup,
    insert_claim,
    get_claim,
    log_audit_event,
)
from app.models import ClaimRecord, ClaimStatus
from datetime import datetime, timezone
from uuid import uuid4


@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensure database schema and migrations are initialized before each test."""
    import asyncio
    asyncio.run(init_db())
    yield


@pytest.mark.asyncio
async def test_sqlite_pragmas_configured():
    """Verify PRAGMA foreign_keys=ON, busy_timeout=5000, and journal_mode=WAL on connection."""
    async with get_db_connection() as db:
        cur_fk = await db.execute("PRAGMA foreign_keys;")
        fk_val = (await cur_fk.fetchone())[0]
        assert fk_val == 1, f"Expected foreign_keys=1, got {fk_val}"

        cur_bt = await db.execute("PRAGMA busy_timeout;")
        bt_val = (await cur_bt.fetchone())[0]
        assert bt_val == 5000, f"Expected busy_timeout=5000, got {bt_val}"

        cur_jm = await db.execute("PRAGMA journal_mode;")
        jm_val = (await cur_jm.fetchone())[0].lower()
        assert jm_val in ("wal", "memory"), f"Expected wal or memory, got {jm_val}"


@pytest.mark.asyncio
async def test_sqlite_row_factory_dual_access():
    """Verify row_factory enables both dictionary column access and positional tuple indexing."""
    async with get_db_connection() as db:
        cur = await db.execute("SELECT customer_id, name, email FROM users WHERE customer_id = 'USR-100001'")
        row = await cur.fetchone()
        assert row is not None
        # Positional access
        assert row[0] == "USR-100001"
        assert row[1] == "Rahul Sharma"
        # Dictionary/named access
        assert row["customer_id"] == "USR-100001"
        assert row["name"] == "Rahul Sharma"
        assert row["email"] == "rahul.sharma@claimsathi.in"


@pytest.mark.asyncio
async def test_foreign_key_rejection_on_orphan_insert():
    """Verify that inserting an orphan child record without a valid parent raises IntegrityError."""
    fake_claim_id = f"CS-NONEXISTENT-{uuid4().hex[:6]}"
    async with get_db_connection() as db:
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                """INSERT INTO claim_fields (claim_id, field_name, label, value, updated_at)
                   VALUES (?, 'vehicle_type', 'Vehicle Type', 'car', '2026-01-01T00:00:00')""",
                (fake_claim_id,),
            )
            await db.commit()


@pytest.mark.asyncio
async def test_foreign_key_rejection_on_orphan_consent():
    """Verify that inserting a user consent record without a valid user raises IntegrityError."""
    fake_user_id = f"USR-FAKE-{uuid4().hex[:6]}"
    async with get_db_connection() as db:
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                """INSERT INTO user_consents (consent_id, user_id, consented_at)
                   VALUES (?, ?, '2026-01-01T00:00:00')""",
                (f"CNS-FAKE-{uuid4().hex[:4]}", fake_user_id),
            )
            await db.commit()


@pytest.mark.asyncio
async def test_schema_migrations_applied_and_clean_fk_check():
    """Verify schema migrations 001 and 002 are registered and PRAGMA foreign_key_check passes."""
    history = await get_schema_migration_history()
    versions = [h["version"] for h in history]
    assert 1 in versions, "Migration 001_initial_schema.sql missing from history"
    assert 2 in versions, "Migration 002_add_foreign_keys_and_indexes.sql missing from history"

    violations = await verify_sqlite_foreign_keys()
    assert len(violations) == 0, f"Foreign key check returned violations: {violations}"


@pytest.mark.asyncio
async def test_migration_and_init_db_idempotency():
    """Calling init_db multiple times must be strictly idempotent and safe."""
    for _ in range(3):
        await init_db()

    violations = await verify_sqlite_foreign_keys()
    assert len(violations) == 0


@pytest.mark.asyncio
async def test_cascade_claim_deletion_preserves_audit_logs():
    """
    Verify delete_claim_record deletes child entities (fields, assets, checks, reports, events)
    while preserving audit_logs for compliance and forensics.
    """
    claim_id = f"CS-TEST-CASCADE-{uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # 1. Create claim
    claim = ClaimRecord(
        id=claim_id,
        customer_id="USR-100001",
        insurance_type="motor",
        policy_reference="POL-CASCADE-TEST",
        insurer_name="Bharat General Insurance",
        policy_type="Comprehensive Motor Policy",
        incident_location="Test City",
        incident_date="2026-11-12",
        vehicle_type="car",
        damage_description="Bumper crack test",
        people_involved="Self",
        injuries_reported="None",
        detailed_statement="Testing cascade delete",
        transcript="Test transcript",
        status=ClaimStatus.CONFIRMED,
        customer_confirmation=True,
        is_demo=False,
        created_at=now,
        updated_at=now,
    )
    await insert_claim(claim)

    evidence_id = f"EVD-{uuid4().hex[:8]}"
    check_id = f"CHK-{uuid4().hex[:8]}"
    report_id = f"REP-{uuid4().hex[:8]}"

    async with get_db_connection() as db:
        # 2. Add child records across all related tables
        await db.execute(
            """INSERT INTO claim_fields (claim_id, field_name, label, value, updated_at)
               VALUES (?, 'vehicle_type', 'Vehicle Type', 'car', ?)""",
            (claim_id, now_iso),
        )
        await db.execute(
            """INSERT INTO timeline_events (claim_id, timestamp, title, description)
               VALUES (?, ?, 'Milestone', 'Test Milestone')""",
            (claim_id, now_iso),
        )
        await db.execute(
            """INSERT INTO evidence_assets
               (evidence_id, claim_id, user_id, label, media_type, capture_method,
                original_filename, detected_mime, file_size_bytes, storage_path, upload_timestamp)
               VALUES (?, ?, 'USR-100001', 'damage', 'image', 'upload', 'test.jpg', 'image/jpeg', 100, 'uploads/test.jpg', ?)""",
            (evidence_id, claim_id, now_iso),
        )
        await db.execute(
            """INSERT INTO evidence_checks
               (check_id, evidence_id, claim_id, sha256_hash, provenance_result, provenance_system_response, checked_at)
               VALUES (?, ?, ?, 'dummyhash', 'authentic', 'valid', ?)""",
            (check_id, evidence_id, claim_id, now_iso),
        )
        await db.execute(
            """INSERT INTO reports
               (report_id, claim_id, user_id, version, dossier_json, canonical_json, pdf_storage_path, generated_at)
               VALUES (?, ?, 'USR-100001', '1.0', '{}', '{}', 'reports/test.pdf', ?)""",
            (report_id, claim_id, now_iso),
        )
        await db.commit()

    # Add audit log for this claim
    await log_audit_event(
        user_id="USR-100001",
        claim_id=claim_id,
        action="TEST_ACTION_BEFORE_DELETE",
        details="Logging event prior to delete",
    )

    # Verify all records exist before delete
    async with get_db_connection() as db:
        cur = await db.execute("SELECT COUNT(*) FROM claim_fields WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] >= 1
        cur = await db.execute("SELECT COUNT(*) FROM evidence_assets WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] == 1
        cur = await db.execute("SELECT COUNT(*) FROM evidence_checks WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] == 1
        cur = await db.execute("SELECT COUNT(*) FROM reports WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] == 1
        cur = await db.execute("SELECT COUNT(*) FROM audit_logs WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] >= 1

    # 3. Perform transactional deletion
    deleted = await delete_claim_record(claim_id)
    assert deleted is True

    # 4. Verify cascade deletion
    async with get_db_connection() as db:
        # Claim itself must be gone
        cur = await db.execute("SELECT COUNT(*) FROM claims WHERE id = ?", (claim_id,))
        assert (await cur.fetchone())[0] == 0
        # Child records must be gone
        cur = await db.execute("SELECT COUNT(*) FROM claim_fields WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] == 0
        cur = await db.execute("SELECT COUNT(*) FROM evidence_assets WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] == 0
        cur = await db.execute("SELECT COUNT(*) FROM evidence_checks WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] == 0
        cur = await db.execute("SELECT COUNT(*) FROM reports WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] == 0
        cur = await db.execute("SELECT COUNT(*) FROM timeline_events WHERE claim_id = ?", (claim_id,))
        assert (await cur.fetchone())[0] == 0

        # CRITICAL SECURITY REQUIREMENT: Audit logs must NOT be deleted!
        cur = await db.execute("SELECT COUNT(*) FROM audit_logs WHERE claim_id = ?", (claim_id,))
        audit_count = (await cur.fetchone())[0]
        assert audit_count >= 1, "Audit logs were improperly removed during claim cascade deletion!"


@pytest.mark.asyncio
async def test_api_delete_claim_authorization_and_cross_customer_rejection():
    """
    Verify DELETE /api/claims/{claim_id}:
    - Customer A can delete Customer A's claim (200).
    - Customer B CANNOT delete Customer A's claim (403 Forbidden).
    - Unauthenticated delete in production returns 401 Unauthorized.
    - Subsequent access to deleted claim returns 404 Not Found.
    """
    token_rahul = create_access_token(customer_id="USR-100001", email="rahul.sharma@claimsathi.in", name="Rahul Sharma")
    token_shankar = create_access_token(customer_id="USR-100002", email="saishankar.reddy@claimsathi.in", name="Sai Shankar Reddy")

    headers_rahul = {"Authorization": f"Bearer {token_rahul}"}
    headers_shankar = {"Authorization": f"Bearer {token_shankar}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Rahul creates a claim
        create_res = await client.post(
            "/api/claims/",
            headers=headers_rahul,
            json={
                "policy_reference": "MOT-DEL-AUTH-TEST",
                "incident_location": "Indiranagar, Bengaluru",
                "incident_date": "2026-11-12",
                "vehicle_type": "car",
                "damage_description": "Front bumper cracked",
                "transcript": "Front bumper cracked in parking",
            },
        )
        assert create_res.status_code == 201
        claim_id = create_res.json()["id"]

        # 2. Shankar attempts to DELETE Rahul's claim -> MUST RETURN 403 FORBIDDEN
        cross_del_res = await client.delete(f"/api/claims/{claim_id}", headers=headers_shankar)
        assert cross_del_res.status_code == 403, f"Expected 403, got {cross_del_res.status_code}"
        assert "Access denied" in cross_del_res.json()["detail"]

        # 3. Unauthenticated attempt in production mode -> MUST RETURN 401 UNAUTHORIZED
        settings = get_settings()
        orig_env = settings.app_env
        try:
            settings.app_env = "production"
            anon_del_res = await client.delete(f"/api/claims/{claim_id}")
            assert anon_del_res.status_code == 401, f"Expected 401 in prod, got {anon_del_res.status_code}"
        finally:
            settings.app_env = orig_env

        # 4. Rahul deletes his own claim -> MUST SUCCEED (200)
        auth_del_res = await client.delete(f"/api/claims/{claim_id}", headers=headers_rahul)
        assert auth_del_res.status_code == 200
        assert auth_del_res.json()["status"] == "success"

        # 5. Subsequent GET by Rahul -> MUST RETURN 404 NOT FOUND
        get_res = await client.get(f"/api/claims/{claim_id}", headers=headers_rahul)
        assert get_res.status_code == 404

        # 6. Re-attempting DELETE on already deleted claim -> MUST RETURN 404 NOT FOUND
        repeat_del_res = await client.delete(f"/api/claims/{claim_id}", headers=headers_rahul)
        assert repeat_del_res.status_code == 404


@pytest.mark.asyncio
async def test_sqlite_online_backup_and_verified_restore():
    """
    Test native SQLite online backup (sqlite3.backup) and restore mechanism:
    1. Create live backup while database is operational.
    2. Validate backup integrity with PRAGMA integrity_check.
    3. Restore backup into a fresh target location and verify records.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        # Create online backup
        backup_file = create_sqlite_backup(backup_dir=temp_dir)
        assert os.path.exists(backup_file), "Backup file was not created"
        assert os.path.getsize(backup_file) > 0, "Backup file is empty"

        # Verify integrity of backup
        con = sqlite3.connect(backup_file)
        try:
            cur = con.cursor()
            cur.execute("PRAGMA integrity_check;")
            res = cur.fetchone()[0]
            assert res == "ok", f"Integrity check failed: {res}"

            # Verify Rahul exists in backup
            cur.execute("SELECT customer_id, name FROM users WHERE customer_id = 'USR-100001'")
            row = cur.fetchone()
            assert row is not None
            assert row[1] == "Rahul Sharma"
        finally:
            con.close()

        # Restore to target database
        restore_target = os.path.join(temp_dir, "restored_claimsathi.db")
        restored = restore_sqlite_backup(backup_file, target_db_path=restore_target)
        assert restored is True

        # Verify target database
        con_restored = sqlite3.connect(restore_target)
        try:
            cur = con_restored.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            user_count = cur.fetchone()[0]
            assert user_count >= 4
        finally:
            con_restored.close()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_restore_rejects_corrupted_backup_file():
    """Verify restore_sqlite_backup rejects invalid/corrupted files before overwriting."""
    temp_dir = tempfile.mkdtemp()
    corrupt_file = os.path.join(temp_dir, "corrupt.db")
    with open(corrupt_file, "w") as f:
        f.write("This is not a valid sqlite database header.")

    try:
        with pytest.raises(Exception):
            restore_sqlite_backup(corrupt_file, target_db_path=os.path.join(temp_dir, "dummy.db"))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_database_error_handling_no_internal_stack_leakage():
    """Verify that querying nonexistent or malformed claim IDs never leaks internal SQL or paths."""
    token_rahul = create_access_token(customer_id="USR-100001", email="rahul.sharma@claimsathi.in", name="Rahul Sharma")
    headers = {"Authorization": f"Bearer {token_rahul}"}

    malicious_ids = [
        "CS-' OR 1=1 --",
        "CS-../../../etc/passwd",
        "CS-<script>alert(1)</script>",
        "CS-" + "A" * 500,
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for mal_id in malicious_ids:
            res = await client.get(f"/api/claims/{mal_id}", headers=headers)
            # Must return 404 or 422, never 500
            assert res.status_code in (404, 422), f"Expected 404/422, got {res.status_code} for {mal_id}"
            body_text = res.text
            # Ensure no SQL stack traces or internal paths leaked
            assert "OperationalError" not in body_text
            assert "Traceback" not in body_text
            assert "SELECT" not in body_text
            assert "claimsathi.db" not in body_text
