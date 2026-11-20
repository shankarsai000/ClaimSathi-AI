"""
ClaimSathi AI — Sprint 1.4 Automated Batch & API Verification Suite.
Validates the complete Local 5-Stage Evidence Intelligence & Fraud-Risk Screening Engine
across all 19 local test samples, SQLite persistence (data/claimsathi.db), and FastAPI v1 endpoints.
"""

import asyncio
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.database import init_db
from app.evidence.pipeline import verify_evidence_image
from app.main import app

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_ZIP = BASE_DIR / "claimsathi_local_test_samples.zip"
DATASET_DIR = BASE_DIR / "ml" / "datasets" / "claimsathi_local_test_samples"
BIKE_DATASET_ZIP = BASE_DIR / "claimsathi_bike_test_samples.zip"
BIKE_DATASET_DIR = BASE_DIR / "ml" / "datasets" / "claimsathi_bike_test_samples"
REPORT_PATH = BASE_DIR / "storage" / "reports" / "sprint_1_4_verification_report.json"
BIKE_REPORT_PATH = BASE_DIR / "storage" / "reports" / "sprint_1_6_bike_verification_report.json"
DATA_DB_PATH = BASE_DIR / "data" / "claimsathi.db"

transport = ASGITransport(app=app)


@pytest.fixture(autouse=True)
def setup_environment():
    """Ensure SQLite database is initialized and sample datasets are extracted."""
    asyncio.run(init_db())
    if not (DATASET_DIR / "test_manifest.json").exists() and DATASET_ZIP.exists():
        DATASET_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(DATASET_ZIP, "r") as zf:
            zf.extractall(DATASET_DIR)
    if not (BIKE_DATASET_DIR / "bike_test_manifest.json").exists() and BIKE_DATASET_ZIP.exists():
        BIKE_DATASET_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(BIKE_DATASET_ZIP, "r") as zf:
            zf.extractall(BIKE_DATASET_DIR)
    yield


@pytest.mark.asyncio
async def test_batch_manifest_5_stage_verification():
    """
    Execute every sample in ml/datasets/claimsathi_local_test_samples/test_manifest.json
    through the 5-stage pipeline, print a formatted summary table, save JSON report,
    and assert 100% expected_decision == actual_decision accuracy.
    """
    manifest_path = DATASET_DIR / "test_manifest.json"
    assert manifest_path.exists(), f"Missing manifest at {manifest_path}"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest) >= 19

    batch_records = []
    mismatches = []

    print("\n")
    print("=" * 124)
    print(
        f"{'file':<50} | {'expected':<8} | {'actual':<8} | {'spoof_risk':<10} | "
        f"{'vehicle':<7} | {'damages':<7} | {'status'}"
    )
    print("-" * 124)

    for entry in manifest:
        rel_file = entry["file"]
        expected = entry["expected_decision"]
        sample_path = DATASET_DIR / rel_file
        assert sample_path.exists(), f"Sample file missing: {sample_path}"

        raw_bytes = sample_path.read_bytes()
        result = await verify_evidence_image(
            file_bytes=raw_bytes,
            filename=Path(rel_file).name,
            persist=True,
        )

        actual = result["decision"]
        spoof_risk = result["spoof_risk"]
        veh_det = result["vehicle_detected"]
        dmg_cnt = result["damage_count"]
        matched = actual == expected
        status_label = "MATCH" if matched else "MISMATCH"

        if not matched:
            mismatches.append((rel_file, expected, actual, result["reasons"]))

        print(
            f"{rel_file:<50} | {expected:<8} | {actual:<8} | {spoof_risk:<10.4f} | "
            f"{str(veh_det):<7} | {dmg_cnt:<7} | {status_label}"
        )

        batch_records.append(
            {
                "file": rel_file,
                "expected_decision": expected,
                "actual_decision": actual,
                "spoof_risk": spoof_risk,
                "predicted_spoof_class": result["predicted_spoof_class"],
                "vehicle_detected": veh_det,
                "damage_count": dmg_cnt,
                "damages_detected": (result["stage_results"].get("stage3b_damage") or {}).get(
                    "detected_damage_types", []
                ),
                "cost_estimate": result.get("cost_estimate"),
                "reasons": result["reasons"],
                "status": status_label,
                "verification_id": result["id"],
                "processing_time_ms": result["processing_time_ms"],
                "stage_results": result["stage_results"],
            }
        )

    print("=" * 124)
    matched_count = sum(1 for r in batch_records if r["status"] == "MATCH")
    print(f"Summary: {matched_count}/{len(batch_records)} samples matched expected decision.")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report_payload = {
        "sprint": "1.4",
        "total_samples": len(batch_records),
        "matched_samples": matched_count,
        "accuracy": round(matched_count / len(batch_records), 4) if batch_records else 0.0,
        "results": batch_records,
    }
    REPORT_PATH.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    assert REPORT_PATH.exists()

    assert not mismatches, f"Decision mismatches found: {mismatches}"


@pytest.mark.asyncio
async def test_api_v1_evidence_endpoints_and_sqlite_persistence():
    """
    Test FastAPI v1 routes:
      - POST /api/v1/evidence/verify (PASS, REVIEW, REJECT including 0-byte file)
      - GET /api/v1/evidence/history
      - GET /api/v1/evidence/{evidence_id}
    And confirm persistence in data/claimsathi.db.
    """
    cases = [
        ("01_genuine_pass/genuine_car_01.jpg", "PASS"),
        ("02_screen_recapture_review/screen_spoof_01.jpg", "REVIEW"),
        ("04_no_vehicle_review/non_vehicle_texture_01.jpg", "REVIEW"),
        ("05_corrupted_reject/corrupted_payload.jpg", "REJECT"),
        ("05_corrupted_reject/empty_file.jpg", "REJECT"),
    ]

    created_ids = []
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for rel_file, expected in cases:
            sample_path = DATASET_DIR / rel_file
            resp = await client.post(
                "/api/v1/evidence/verify",
                files={"file": (sample_path.name, sample_path.read_bytes(), "image/jpeg")},
            )
            assert resp.status_code == 200, f"Unexpected status {resp.status_code} for {rel_file}: {resp.text}"
            body = resp.json()
            assert body["decision"] == expected, f"{rel_file}: expected {expected}, got {body}"
            created_ids.append(body["id"])

        # History endpoint (must resolve /history cleanly rather than hitting /{evidence_id})
        hist_resp = await client.get("/api/v1/evidence/history?limit=20")
        assert hist_resp.status_code == 200
        hist_data = hist_resp.json()
        assert hist_data["total"] >= len(created_ids)
        returned_ids = {item["id"] for item in hist_data["verifications"]}
        for cid in created_ids:
            assert cid in returned_ids

        # Detail endpoint
        detail_resp = await client.get(f"/api/v1/evidence/{created_ids[0]}")
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["id"] == created_ids[0]
        assert detail_data["decision"] == "PASS"
        assert "stage_results" in detail_data

        # Nonexistent ID returns 404
        missing_resp = await client.get("/api/v1/evidence/00000000-0000-0000-0000-000000000000")
        assert missing_resp.status_code == 404

    # Verify SQLite logging in data/claimsathi.db
    assert DATA_DB_PATH.exists(), f"Missing {DATA_DB_PATH}"
    con = sqlite3.connect(str(DATA_DB_PATH))
    try:
        cur = con.cursor()
        for cid in created_ids:
            row = cur.execute("SELECT decision FROM evidence_verifications WHERE id = ?", (cid,)).fetchone()
            assert row is not None, f"Verification ID {cid} missing from data/claimsathi.db"
    finally:
        con.close()


@pytest.mark.asyncio
async def test_exif_editing_software_triggers_review_not_reject():
    """
    Verify Stage 2 EXIF Software tag detection:
    Adding Software='Adobe Photoshop 2026' to a genuine car image triggers REVIEW (never REJECT).
    """
    genuine_path = DATASET_DIR / "01_genuine_pass" / "genuine_car_01.jpg"
    with Image.open(genuine_path) as img:
        exif = img.getexif()
        exif[0x0131] = "Adobe Photoshop 2026"  # EXIF Software tag
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif.tobytes())
        edited_bytes = buf.getvalue()

    result = await verify_evidence_image(
        file_bytes=edited_bytes,
        filename="photoshopped_car.jpg",
        persist=False,
    )
    assert result["decision"] == "REVIEW"
    stage2 = result["stage_results"]["stage2_metadata"]
    assert stage2["has_exif"] is True
    assert stage2["editing_software_detected"] is True
    assert stage2["metadata_risk_score"] >= 0.45
    assert any("EDITING_SOFTWARE_TAG_DETECTED" in r for r in result["reasons"])


@pytest.mark.asyncio
async def test_track_a_damage_cost_estimator_inr():
    """
    Verify Track A Deterministic INR Cost Estimator:
    - 01_genuine_pass/genuine_car_01.jpg -> APPROVED_AUTO_ESTIMATE, Severe glass shatter (6500*2.2 + 1500 = 15800 INR).
    - 02_screen_recapture_review/screen_spoof_01.jpg -> PROVISIONAL_PENDING_REVIEW.
    - 05_corrupted_reject/*.jpg -> REJECTED_NO_ESTIMATE, overall_severity='None', total_estimated_inr=0.
    """
    genuine_path = DATASET_DIR / "01_genuine_pass" / "genuine_car_01.jpg"
    genuine_res = await verify_evidence_image(
        file_bytes=genuine_path.read_bytes(),
        filename=genuine_path.name,
        persist=False,
    )
    est_pass = genuine_res["cost_estimate"]
    assert est_pass["currency"] == "INR"
    assert est_pass["estimate_status"] == "APPROVED_AUTO_ESTIMATE"
    assert est_pass["overall_severity"] == "Severe"
    assert len(est_pass["line_items"]) == 1
    assert est_pass["line_items"][0]["damage_type"] == "glass shatter"
    assert est_pass["line_items"][0]["Diagnostic_multiplier"] == 2.2
    assert est_pass["line_items"][0]["subtotal_inr"] == 15800
    assert est_pass["total_estimated_inr"] == 15800

    review_path = DATASET_DIR / "02_screen_recapture_review" / "screen_spoof_01.jpg"
    review_res = await verify_evidence_image(
        file_bytes=review_path.read_bytes(),
        filename=review_path.name,
        persist=False,
    )
    est_review = review_res["cost_estimate"]
    assert est_review["estimate_status"] == "PROVISIONAL_PENDING_REVIEW"
    assert est_review["total_estimated_inr"] > 0

    for reject_rel in ("05_corrupted_reject/corrupted_payload.jpg", "05_corrupted_reject/empty_file.jpg"):
        reject_path = DATASET_DIR / reject_rel
        reject_res = await verify_evidence_image(
            file_bytes=reject_path.read_bytes(),
            filename=reject_path.name,
            persist=False,
        )
        est_reject = reject_res["cost_estimate"]
        assert est_reject["estimate_status"] == "REJECTED_NO_ESTIMATE"
        assert est_reject["overall_severity"] == "None"
        assert est_reject["line_items"] == []
        assert est_reject["total_estimated_inr"] == 0
        assert est_reject["total_inr"] == 0


@pytest.mark.asyncio
async def test_bike_manifest_5_stage_verification():
    """
    Sprint 1.6: Load ml/datasets/claimsathi_bike_test_samples/bike_test_manifest.json
    and run each sample with claimed_vehicle_type='two_wheeler':
      - All 01_genuine_bike_pass/* images return PASS and a valid INR cost estimate (> 0 INR).
      - All 02_screen_recapture_bike_review/* images return REVIEW.
    """
    manifest_path = BIKE_DATASET_DIR / "bike_test_manifest.json"
    assert manifest_path.exists(), f"Missing bike manifest at {manifest_path}"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest) >= 8

    bike_records = []
    mismatches = []

    print("\n")
    print("=" * 134)
    print(
        f"{'bike_file':<52} | {'expected':<8} | {'actual':<8} | {'spoof_risk':<10} | "
        f"{'det_cat':<12} | {'damages':<7} | {'est_inr':<8} | {'status'}"
    )
    print("-" * 134)

    for entry in manifest:
        rel_file = entry["file"]
        expected = entry["expected_decision"]
        sample_path = BIKE_DATASET_DIR / rel_file
        assert sample_path.exists(), f"Bike sample missing: {sample_path}"

        result = await verify_evidence_image(
            file_bytes=sample_path.read_bytes(),
            filename=Path(rel_file).name,
            claimed_vehicle_type="two_wheeler",
            persist=True,
        )

        actual = result["decision"]
        spoof_risk = result["spoof_risk"]
        det_cat = result["detected_vehicle_category"]
        dmg_cnt = result["damage_count"]
        est_inr = (result.get("cost_estimate") or {}).get("total_estimated_inr", 0)
        matched = actual == expected
        status_label = "MATCH" if matched else "MISMATCH"

        if not matched:
            mismatches.append((rel_file, expected, actual, result["reasons"]))

        if expected == "PASS":
            assert result["claimed_vehicle_type"] == "two_wheeler"
            assert result["vehicle_category_mismatch"] is False
            assert result["cost_estimate"]["estimate_status"] == "APPROVED_AUTO_ESTIMATE"
            assert est_inr > 0, f"Expected > 0 INR estimate for genuine bike pass {rel_file}"
        elif expected == "REVIEW":
            assert result["claimed_vehicle_type"] == "two_wheeler"
            assert result["vehicle_category_mismatch"] is False

        print(
            f"{rel_file:<52} | {expected:<8} | {actual:<8} | {spoof_risk:<10.4f} | "
            f"{det_cat:<12} | {dmg_cnt:<7} | {est_inr:<8} | {status_label}"
        )

        bike_records.append(
            {
                "file": rel_file,
                "expected_decision": expected,
                "actual_decision": actual,
                "claimed_vehicle_type": result["claimed_vehicle_type"],
                "detected_vehicle_category": det_cat,
                "vehicle_category_mismatch": result["vehicle_category_mismatch"],
                "spoof_risk": spoof_risk,
                "damage_count": dmg_cnt,
                "cost_estimate": result.get("cost_estimate"),
                "reasons": result["reasons"],
                "status": status_label,
            }
        )

    print("=" * 134)
    matched_count = sum(1 for r in bike_records if r["status"] == "MATCH")
    print(f"Bike Manifest Summary: {matched_count}/{len(bike_records)} samples matched expected decision.")

    BIKE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BIKE_REPORT_PATH.write_text(
        json.dumps(
            {
                "sprint": "1.6",
                "total_samples": len(bike_records),
                "matched_samples": matched_count,
                "accuracy": round(matched_count / len(bike_records), 4) if bike_records else 0.0,
                "results": bike_records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    assert not mismatches, f"Bike manifest decision mismatches found: {mismatches}"


@pytest.mark.asyncio
async def test_cross_vehicle_category_mismatch_rejection():
    """
    Sprint 1.6 Strict Cross-Vehicle Mismatch Rejection Test:
      1. Pass a known Car image (01_genuine_pass/genuine_car_01.jpg) with claimed_vehicle_type="two_wheeler"
         -> Assert decision == "REJECT", reasons contains "VEHICLE_CATEGORY_MISMATCH", and total_estimated_inr == 0.
      2. Pass a known Bike image (01_genuine_bike_pass/genuine_bike_01.jpg) with claimed_vehicle_type="four_wheeler"
         -> Assert decision == "REJECT", reasons contains "VEHICLE_CATEGORY_MISMATCH", and total_estimated_inr == 0.
      3. Verify the same strict rejection via POST /api/v1/evidence/verify form data.
    """
    car_path = DATASET_DIR / "01_genuine_pass" / "genuine_car_01.jpg"
    bike_path = BIKE_DATASET_DIR / "01_genuine_bike_pass" / "genuine_bike_01.jpg"
    assert car_path.exists()
    assert bike_path.exists()

    # 1. Car uploaded under a Two-Wheeler (Bike) claim
    car_as_bike = await verify_evidence_image(
        file_bytes=car_path.read_bytes(),
        filename=car_path.name,
        claimed_vehicle_type="two_wheeler",
        persist=True,
    )
    assert car_as_bike["decision"] == "REJECT"
    assert car_as_bike["claimed_vehicle_type"] == "two_wheeler"
    assert car_as_bike["detected_vehicle_category"] == "four_wheeler"
    assert car_as_bike["vehicle_category_mismatch"] is True
    assert any("VEHICLE_CATEGORY_MISMATCH" in r for r in car_as_bike["reasons"])
    assert car_as_bike["cost_estimate"]["estimate_status"] == "REJECTED_NO_ESTIMATE"
    assert car_as_bike["cost_estimate"]["total_estimated_inr"] == 0

    # 2. Bike uploaded under a Four-Wheeler (Car) claim
    bike_as_car = await verify_evidence_image(
        file_bytes=bike_path.read_bytes(),
        filename=bike_path.name,
        claimed_vehicle_type="four_wheeler",
        persist=True,
    )
    assert bike_as_car["decision"] == "REJECT"
    assert bike_as_car["claimed_vehicle_type"] == "four_wheeler"
    assert bike_as_car["detected_vehicle_category"] == "two_wheeler"
    assert bike_as_car["vehicle_category_mismatch"] is True
    assert any("VEHICLE_CATEGORY_MISMATCH" in r for r in bike_as_car["reasons"])
    assert bike_as_car["cost_estimate"]["estimate_status"] == "REJECTED_NO_ESTIMATE"
    assert bike_as_car["cost_estimate"]["total_estimated_inr"] == 0

    # 3. Verify via FastAPI POST /api/v1/evidence/verify form parameter
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_car_mismatch = await client.post(
            "/api/v1/evidence/verify",
            files={"file": (car_path.name, car_path.read_bytes(), "image/jpeg")},
            data={"claimed_vehicle_type": "two_wheeler"},
        )
        assert resp_car_mismatch.status_code == 200
        body_car = resp_car_mismatch.json()
        assert body_car["decision"] == "REJECT"
        assert body_car["vehicle_category_mismatch"] is True
        assert any("VEHICLE_CATEGORY_MISMATCH" in r for r in body_car["reasons"])
        assert body_car["cost_estimate"]["estimate_status"] == "REJECTED_NO_ESTIMATE"
        assert body_car["cost_estimate"]["total_estimated_inr"] == 0

        resp_bike_mismatch = await client.post(
            "/api/v1/evidence/verify",
            files={"file": (bike_path.name, bike_path.read_bytes(), "image/jpeg")},
            data={"claimed_vehicle_type": "four_wheeler"},
        )
        assert resp_bike_mismatch.status_code == 200
        body_bike = resp_bike_mismatch.json()
        assert body_bike["decision"] == "REJECT"
        assert body_bike["vehicle_category_mismatch"] is True
        assert any("VEHICLE_CATEGORY_MISMATCH" in r for r in body_bike["reasons"])
        assert body_bike["cost_estimate"]["estimate_status"] == "REJECTED_NO_ESTIMATE"
        assert body_bike["cost_estimate"]["total_estimated_inr"] == 0


@pytest.mark.asyncio
async def test_sprint_1_7_reviewer_override_and_official_claim_creation():
    """
    Sprint 1.7 Feature A & B End-to-End Verification:
      1. Upload a REVIEW case (screen recapture).
      2. Call POST /api/v1/evidence/{id}/override with 'PASS' -> check APPROVED_MANUAL_REVIEW.
      3. Call POST /api/v1/evidence/{id}/create-claim -> check linked_claim object and claim_id.
      4. Call POST /api/v1/evidence/{id}/override with 'REJECT' -> check REJECTED_NO_ESTIMATE & 0 INR.
      5. Call POST /api/v1/evidence/{id}/create-claim on REJECT -> check HTTP 400 error.
    """
    review_sample = DATASET_DIR / "02_screen_recapture_review" / "screen_spoof_01.jpg"
    assert review_sample.exists()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initial upload -> returns REVIEW
        upload_resp = await client.post(
            "/api/v1/evidence/verify",
            files={"file": (review_sample.name, review_sample.read_bytes(), "image/jpeg")},
            data={"claimed_vehicle_type": "four_wheeler"},
        )
        assert upload_resp.status_code == 200
        record = upload_resp.json()
        ev_id = record["id"]
        assert record["decision"] == "REVIEW"
        assert record["cost_estimate"]["estimate_status"] == "PROVISIONAL_PENDING_REVIEW"
        assert record["cost_estimate"]["total_estimated_inr"] > 0

        # 2. Reviewer Manual Override to PASS
        override_pass_resp = await client.post(
            f"/api/v1/evidence/{ev_id}/override",
            json={
                "new_decision": "PASS",
                "reviewer_note": "Certified physical vehicle inspection verified.",
            },
        )
        assert override_pass_resp.status_code == 200
        pass_data = override_pass_resp.json()
        assert pass_data["decision"] == "PASS"
        assert pass_data["cost_estimate"]["estimate_status"] == "APPROVED_MANUAL_REVIEW"
        assert pass_data["cost_estimate"]["total_estimated_inr"] > 0
        assert any("MANUAL_OVERRIDE_PASS" in r for r in pass_data["reasons"])
        assert "manual_override" in pass_data["stage_results"]
        assert pass_data["stage_results"]["manual_override"]["new_decision"] == "PASS"

        # 3. Create Official Claim from verified evidence
        create_claim_resp = await client.post(
            f"/api/v1/evidence/{ev_id}/create-claim",
            json={
                "policy_number": "POL-IND-2026-8841",
                "vehicle_registration": "KA-01-MJ-2026",
                "incident_description": "Frontal bumper impact collision.",
            },
        )
        assert create_claim_resp.status_code == 200
        claim_data = create_claim_resp.json()
        linked = claim_data.get("linked_claim") or claim_data["stage_results"].get("linked_claim")
        assert linked is not None
        assert linked["claim_id"].startswith("CLM-")
        assert linked["policy_number"] == "POL-IND-2026-8841"
        assert linked["vehicle_registration"] == "KA-01-MJ-2026"
        assert linked["total_estimated_inr"] > 0
        assert linked["claim_status"] == "APPROVED"

        # 4. Override to REJECT
        override_reject_resp = await client.post(
            f"/api/v1/evidence/{ev_id}/override",
            json={
                "new_decision": "REJECT",
                "reviewer_note": "Re-evaluation determined visual tampering.",
            },
        )
        assert override_reject_resp.status_code == 200
        reject_data = override_reject_resp.json()
        assert reject_data["decision"] == "REJECT"
        assert reject_data["cost_estimate"]["estimate_status"] == "REJECTED_NO_ESTIMATE"
        assert reject_data["cost_estimate"]["total_estimated_inr"] == 0
        assert reject_data["cost_estimate"]["line_items"] == []

        # 5. Attempt claim creation on REJECT -> must return 400
        fail_claim_resp = await client.post(
            f"/api/v1/evidence/{ev_id}/create-claim",
            json={
                "policy_number": "POL-IND-2026-8841",
                "vehicle_registration": "KA-01-MJ-2026",
            },
        )
        assert fail_claim_resp.status_code == 400
        assert "Cannot create an official claim from a REJECTED" in fail_claim_resp.json()["detail"]


@pytest.mark.asyncio
async def test_sprint_1_8_wizard_ai_engine_flow():
    """
    Sprint 1.8 Wizard Integration Test:
      Step 1: Upload a Car photo with claimed_vehicle_type='two_wheeler'
              -> verify REJECT (VEHICLE_CATEGORY_MISMATCH).
              -> confirm claim creation with this evidence_id is blocked with HTTP 400.
      Step 2: Upload a genuine Bike photo with claimed_vehicle_type='two_wheeler'
              -> verify PASS and positive INR cost estimate.
      Step 3: Submit official claim referencing the verified evidence_id
              -> verify valid claim created with the exact AI total_estimated_inr and linked_claim attached.
    """
    car_sample = DATASET_DIR / "01_genuine_pass" / "genuine_car_01.jpg"
    bike_sample = BIKE_DATASET_DIR / "01_genuine_bike_pass" / "genuine_bike_01.jpg"
    assert car_sample.exists()
    assert bike_sample.exists()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Car uploaded when claiming a Bike claim -> REJECT (VEHICLE_CATEGORY_MISMATCH)
        mismatch_resp = await client.post(
            "/api/v1/evidence/verify",
            files={"file": (car_sample.name, car_sample.read_bytes(), "image/jpeg")},
            data={"claimed_vehicle_type": "two_wheeler"},
        )
        assert mismatch_resp.status_code == 200
        mismatch_data = mismatch_resp.json()
        assert mismatch_data["decision"] == "REJECT"
        assert mismatch_data["vehicle_category_mismatch"] is True
        mismatch_ev_id = mismatch_data["id"]

        # Confirm claim creation with rejected evidence is blocked by backend
        blocked_claim_resp = await client.post(
            "/api/claims/",
            json={
                "policy_reference": "POL-BIKE-2026-9911",
                "incident_location": "Bengaluru Outer Ring Road",
                "incident_date": "2026-11-18",
                "vehicle_type": "Two-Wheeler (Motorcycle)",
                "damage_description": "Skid accident on wet road.",
                "evidence_id": mismatch_ev_id,
            },
        )
        assert blocked_claim_resp.status_code == 400
        assert "Cannot submit a claim with REJECTED evidence" in blocked_claim_resp.json()["detail"]

        # Step 2: Upload genuine Bike photo with claimed_vehicle_type='two_wheeler' -> PASS
        bike_resp = await client.post(
            "/api/v1/evidence/verify",
            files={"file": (bike_sample.name, bike_sample.read_bytes(), "image/jpeg")},
            data={"claimed_vehicle_type": "two_wheeler"},
        )
        assert bike_resp.status_code == 200
        bike_data = bike_resp.json()
        assert bike_data["decision"] == "PASS"
        assert bike_data["vehicle_category_mismatch"] is False
        assert bike_data["cost_estimate"]["total_estimated_inr"] > 0
        valid_ev_id = bike_data["id"]
        expected_inr = bike_data["cost_estimate"]["total_estimated_inr"]

        # Step 3: Submit claim from verified evidence
        success_claim_resp = await client.post(
            "/api/claims/",
            json={
                "policy_reference": "POL-BIKE-2026-9911",
                "incident_location": "Bengaluru Outer Ring Road",
                "incident_date": "2026-11-18",
                "vehicle_type": "Two-Wheeler (Motorcycle)",
                "damage_description": "Skid accident on wet road.",
                "evidence_id": valid_ev_id,
            },
        )
        assert success_claim_resp.status_code == 201
        created_claim = success_claim_resp.json()
        assert created_claim["id"] is not None

        # Verify linked_claim on evidence verification record
        check_ev_resp = await client.get(f"/api/v1/evidence/{valid_ev_id}")
        assert check_ev_resp.status_code == 200
        ev_detail = check_ev_resp.json()
        linked = ev_detail.get("linked_claim") or ev_detail["stage_results"].get("linked_claim")
        assert linked is not None
        assert linked["claim_id"] == created_claim["id"]
        assert linked["total_estimated_inr"] == expected_inr
        assert linked["claim_status"] == "APPROVED"


@pytest.mark.asyncio
async def test_sprint_1_8_code_mixed_slot_extraction():
    """
    Sprint 1.8: Test multi-slot extraction from code-mixed Indic utterances:
    - claimed_vehicle_type ('two_wheeler' vs 'four_wheeler')
    - vehicle_registration (normalized Indian format)
    - damage_keywords
    - detected_language
    """
    from app.providers.transcription import extract_multimodal_slots

    # Case 1: Hinglish Bike
    text_1 = "Mera bike KA-17-EA-4021 ka headlamp aur fairing break ho gaya near main road"
    slots_1 = extract_multimodal_slots(text_1)
    assert slots_1["claimed_vehicle_type"] == "two_wheeler"
    assert slots_1["vehicle_registration"] == "KA-17-EA-4021"
    assert "headlamp" in slots_1["damage_keywords"]
    assert "fairing" in slots_1["damage_keywords"]
    assert slots_1["detected_language"] in ("hi-Latn", "hi-IN")

    # Case 2: Kanglish Car
    text_2 = "Nanna car KA-01-MJ-2026 front bumper dent mattu scratch aagide"
    slots_2 = extract_multimodal_slots(text_2)
    assert slots_2["claimed_vehicle_type"] == "four_wheeler"
    assert slots_2["vehicle_registration"] == "KA-01-MJ-2026"
    assert "bumper" in slots_2["damage_keywords"]
    assert "dent" in slots_2["damage_keywords"]
    assert slots_2["detected_language"] in ("kn-Latn", "kn-IN")

    # Case 3: Hinglish Car Glass Shatter
    text_3 = "Mere car KA-05-NB-9012 ka front glass shatter ho gaya aur दरवाजे pe dent hai"
    slots_3 = extract_multimodal_slots(text_3)
    assert slots_3["claimed_vehicle_type"] == "four_wheeler"
    assert slots_3["vehicle_registration"] == "KA-05-NB-9012"
    assert "glass" in slots_3["damage_keywords"]
    assert "shatter" in slots_3["damage_keywords"]


@pytest.mark.asyncio
async def test_sprint_1_8_multimodal_evidence_narration_endpoint():
    """
    Sprint 1.8: Test POST /api/voice/narrate-evidence for PASS, REVIEW, and REJECT with category mismatch.
    Ensures concise (<40 words, no markdown/symbols) natural spoken Indic narration for TTS.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. REJECT with Category Mismatch (Bike Claim + Car Photo) in Hinglish
        resp_mismatch = await client.post(
            "/api/voice/narrate-evidence",
            json={
                "decision": "REJECT",
                "claimed_vehicle_type": "two_wheeler",
                "detected_vehicle_category": "four_wheeler",
                "vehicle_category_mismatch": True,
                "total_estimated_inr": 0,
                "language": "hi-IN",
            },
        )
        assert resp_mismatch.status_code == 200
        data_mismatch = resp_mismatch.json()
        assert "bike" in data_mismatch["spoken_narration"].lower()
        assert "car" in data_mismatch["spoken_narration"].lower()
        assert "reject" in data_mismatch["spoken_narration"].lower()
        words = data_mismatch["spoken_narration"].split()
        assert len(words) < 40
        assert not any(sym in data_mismatch["spoken_narration"] for sym in ["#", "*", "{", "}", "[", "]"])

        # 2. PASS with Approved Estimate in Kanglish
        resp_pass = await client.post(
            "/api/voice/narrate-evidence",
            json={
                "decision": "PASS",
                "claimed_vehicle_type": "two_wheeler",
                "total_estimated_inr": 8500,
                "language": "kn-IN",
            },
        )
        assert resp_pass.status_code == 200
        data_pass = resp_pass.json()
        assert "8500" in data_pass["spoken_narration"]
        assert "approve" in data_pass["spoken_narration"].lower()
        assert len(data_pass["spoken_narration"].split()) < 40

        # 3. REVIEW Provisional in English
        resp_review = await client.post(
            "/api/voice/narrate-evidence",
            json={
                "decision": "REVIEW",
                "claimed_vehicle_type": "four_wheeler",
                "total_estimated_inr": 12000,
                "language": "en-IN",
            },
        )
        assert resp_review.status_code == 200
        data_review = resp_review.json()
        assert "12000" in data_review["spoken_narration"]
        assert "review" in data_review["spoken_narration"].lower()
        assert len(data_review["spoken_narration"].split()) < 40


@pytest.mark.asyncio
async def test_sprint_1_8_extract_text_slot_integration():
    """
    Sprint 1.8: Test POST /api/claims/extract-text returns multimodal extracted slots.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/claims/extract-text",
            json={"text": "Mera bike KA-17-EA-4021 ka headlamp toot gaya near MG Road"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["claimed_vehicle_type"] == "two_wheeler"
        assert data["vehicle_registration"] == "KA-17-EA-4021"
        assert "headlamp" in data["damage_keywords"]
        assert data["assistant_dialogue"] is not None
        assert data["assistant_speech_text"] is not None


@pytest.mark.asyncio
async def test_sprint_1_8_v1_voice_extract_slots_and_narrate_evidence():
    """
    Sprint 1.8 Phase 2/4:
    Test POST /api/v1/voice/extract-slots and POST /api/v1/voice/narrate-evidence
    across Hinglish 2W, Kanglish 4W, compact reg normalization, and mismatch rejection narration.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Hinglish 2W slot extraction
        r1 = await client.post(
            "/api/v1/voice/extract-slots",
            json={
                "text": "Mera scooty MH12DE1433 ka mudguard aur indicator break ho gaya",
                "language": "hinglish",
            },
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["claimed_vehicle_type"] == "two_wheeler"
        assert d1["vehicle_registration"] == "MH-12-DE-1433"
        assert "mudguard" in d1["damage_keywords"]
        assert "indicator" in d1["damage_keywords"]
        assert len(d1["reply_text"].split()) < 35
        assert not any(sym in d1["reply_text"] for sym in ["*", "#"])

        # 2. Kanglish 4W slot extraction
        r2 = await client.post(
            "/api/v1/voice/extract-slots",
            json={
                "text": "Nanna car KA 01 MJ 2026 front bumper dent mattu door scratch aagide",
                "language": "kanglish",
            },
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["claimed_vehicle_type"] == "four_wheeler"
        assert d2["vehicle_registration"] == "KA-01-MJ-2026"
        assert "bumper" in d2["damage_keywords"]
        assert "scratch" in d2["damage_keywords"]
        assert len(d2["reply_text"].split()) < 35

        # 3. v1/voice/narrate-evidence PASS with string list of damages (Hinglish 2W)
        n_pass = await client.post(
            "/api/v1/voice/narrate-evidence",
            json={
                "decision": "PASS",
                "claimed_vehicle_type": "two_wheeler",
                "detected_vehicle_category": "two_wheeler",
                "vehicle_category_mismatch": False,
                "total_estimated_inr": 5340,
                "damages": ["broken_fairing"],
                "language": "hinglish",
            },
        )
        assert n_pass.status_code == 200
        np_data = n_pass.json()
        assert np_data["narration_text"] == np_data["spoken_narration"]
        assert "5340" in np_data["narration_text"]
        assert "broken fairing" in np_data["narration_text"].lower()
        assert len(np_data["narration_text"].split()) < 40

        # 4. v1/voice/narrate-evidence REJECT mismatch (Kanglish)
        n_rej = await client.post(
            "/api/v1/voice/narrate-evidence",
            json={
                "decision": "REJECT",
                "claimed_vehicle_type": "two_wheeler",
                "detected_vehicle_category": "four_wheeler",
                "vehicle_category_mismatch": True,
                "total_estimated_inr": 0,
                "damages": [],
                "language": "kanglish",
            },
        )
        assert n_rej.status_code == 200
        nr_data = n_rej.json()
        assert "bike" in nr_data["narration_text"].lower()
        assert "car" in nr_data["narration_text"].lower()
        assert "reject" in nr_data["narration_text"].lower()
        assert len(nr_data["narration_text"].split()) < 40



