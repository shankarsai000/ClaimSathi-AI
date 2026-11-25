"""
Tests for Complete Indian Motor Insurance (2W & 4W) Claim Fields (Groups A, B, C & D).
Verifies:
1. Backward compatibility with minimal 5-slot claim payloads.
2. Complete 2W (pillion_rider_present) & 4W (occupants_count) claims, owner-driver auto-fill, DL mismatch warning, and ISO-8601 DPDP consent timestamping.
3. Conditional Group C triggers (reimbursement bank details, FIR, theft skipping driver details, third-party/injury, fire brigade) & DPDP PII masking.
4. Group A conversational voice slot extraction without breaking the 5 core intake slots.
5. Group D Adjuster Portal endpoint & 9-Section Canonical JSON / PDF Dossier generation.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.auth import create_access_token
from app.database import init_db, get_user_audit_logs

transport = ASGITransport(app=app)


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield


def _auth_headers(customer_id: str = "USR-100001", name: str = "Rahul Sharma") -> dict[str, str]:
    token = create_access_token(
        customer_id=customer_id,
        email=f"{customer_id.lower()}@claimsathi.in",
        name=name,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_backward_compatibility_minimal_five_slot_claim():
    """Old minimal 5-slot payloads must continue to succeed with safe defaults."""
    payload = {
        "policy_reference": "MOT-2026-KA-11001",
        "incident_location": "Indiranagar, Bengaluru",
        "incident_date": "2026-11-20",
        "vehicle_type": "bike",
        "damage_description": "Front mudguard scratched and indicator broken",
        "transcript": "Minimal legacy transcript",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/claims/", json=payload, headers=_auth_headers())
        assert create_resp.status_code == 201
        cid = create_resp.json()["id"]

        detail_resp = await client.get(f"/api/claims/{cid}", headers=_auth_headers())
        assert detail_resp.status_code == 200
        claim = detail_resp.json()["claim"]
        assert claim["policy_reference"] == "MOT-2026-KA-11001"
        assert claim["motor_claim_form"] is not None
        assert claim["insurer_adjuster_data"]["external_registry_checks"]["vahan_status"] == "pending_integration"


@pytest.mark.anyio
async def test_complete_2w_and_4w_claims_autofill_dl_mismatch_and_dpdp_timestamp():
    """Verify 2W pillion + owner autofill + DL mismatch warning, and 4W occupants_count + workshop + DPDP timestamp."""
    headers = _auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2W claim with LMV license class -> should auto-fill owner driver & warn on DL mismatch
        create_2w = await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "policy_reference": "KA-01-MJ-4412",
                "claimed_registration": "KA-01-MJ-4412",
                "incident_location": "Koramangala, Bengaluru",
                "incident_date": "2026-11-21",
                "vehicle_type": "bike",
                "vehicle_make_model": "Bajaj Pulsar 220",
                "claimed_vehicle_type": "two_wheeler",
                "damage_description": "Headlight and front fairing cracked",
                "transcript": "My Bajaj Pulsar 220 bike met with an accident.",
            },
        )
        assert create_2w.status_code == 201
        cid_2w = create_2w.json()["id"]

        update_2w = await client.put(
            f"/api/claims/{cid_2w}",
            headers=headers,
            json={
                "claimed_vehicle_type": "two_wheeler",
                "motor_claim_form": {
                    "claimant_name": "Rahul Sharma",
                    "registered_mobile": "+919876543210",
                    "claimant_email": "rahul.sharma@claimsathi.in",
                    "residential_address": "12 MG Road, Bengaluru",
                    "pincode": "560001",
                    "loss_type": "own_damage_accident",
                    "incident_time": "8:15 PM",
                    "vehicle_usage_type": "private_social_domestic",
                    "pillion_rider_present": True,
                    "driver_was_owner": True,
                    "driver_license_number": "KA0120200012345",
                    "driver_license_class": "LMV",
                    "driver_issuing_rto": "Koramangala KA-01",
                    "claim_settlement_mode": "cashless",
                    "workshop_name": "Bajaj Authorised Service, HSR",
                    "dpdp_consent_granted": True,
                    "truthfulness_declaration_accepted": True,
                    "insured_digital_signature": "Rahul Sharma",
                },
            },
        )
        assert update_2w.status_code == 200
        form_2w = update_2w.json()["motor_claim_form"]
        assert form_2w["pillion_rider_present"] is True
        assert form_2w["driver_name"] == "Rahul Sharma"
        assert form_2w["driver_address"] == "12 MG Road, Bengaluru"
        assert form_2w["driver_relationship"] == "owner"
        assert "LMV/HMV" in (form_2w["driver_license_mismatch_warning"] or "")
        assert form_2w["dpdp_consent_timestamp"]  # ISO-8601 stamped server-side

        # 4W claim with occupants_count
        create_4w = await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "policy_reference": "TS-09-EF-5678",
                "claimed_registration": "TS-09-EF-5678",
                "incident_location": "Madhapur, Hyderabad",
                "incident_date": "2026-11-22",
                "vehicle_type": "car",
                "vehicle_make_model": "Maruti Swift",
                "claimed_vehicle_type": "four_wheeler",
                "damage_description": "Rear bumper dented",
                "transcript": "Three people in my Maruti Swift car.",
                "motor_claim_form": {
                    "claimant_name": "Rahul Sharma",
                    "loss_type": "own_damage_accident",
                    "occupants_count": 3,
                    "driver_was_owner": True,
                    "driver_license_class": "LMV",
                    "claim_settlement_mode": "cashless",
                    "dpdp_consent_granted": True,
                    "truthfulness_declaration_accepted": True,
                },
            },
        )
        assert create_4w.status_code == 201
        cid_4w = create_4w.json()["id"]
        det_4w = await client.get(f"/api/claims/{cid_4w}", headers=headers)
        assert det_4w.status_code == 200
        assert det_4w.json()["claim"]["motor_claim_form"]["occupants_count"] == 3
        assert det_4w.json()["claim"]["motor_claim_form"]["driver_license_mismatch_warning"] is None


@pytest.mark.anyio
async def test_conditional_triggers_theft_fir_reimbursement_and_pii_masking():
    """Verify reimbursement validation + PII masking, FIR requirement, and theft skipping driver details."""
    headers = _auth_headers()
    raw_acct = "987654321012"
    raw_dl = "KA0520190098765"
    raw_mobile = "+919845012345"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        base_claim = await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "policy_reference": "KA-05-AB-9988",
                "incident_location": "Jayanagar, Bengaluru",
                "incident_date": "2026-11-23",
                "vehicle_type": "car",
                "damage_description": "Front bumper & windshield damaged",
                "transcript": "Reimbursement and FIR test.",
            },
        )
        assert base_claim.status_code == 201
        cid = base_claim.json()["id"]

        # 1. Reimbursement without bank details + DPDP consent granted -> 422
        bad_reimb = await client.put(
            f"/api/claims/{cid}",
            headers=headers,
            json={
                "motor_claim_form": {
                    "claim_settlement_mode": "reimbursement",
                    "dpdp_consent_granted": True,
                    "truthfulness_declaration_accepted": True,
                }
            },
        )
        assert bad_reimb.status_code == 422

        # 2. Complete reimbursement + FIR + third-party details -> 200 and masked in responses/summaries/logs
        ok_resp = await client.put(
            f"/api/claims/{cid}",
            headers=headers,
            json={
                "motor_claim_form": {
                    "claimant_name": "Rahul Sharma",
                    "registered_mobile": raw_mobile,
                    "driver_license_number": raw_dl,
                    "driver_license_class": "LMV",
                    "claim_settlement_mode": "reimbursement",
                    "bank_account_holder_name": "Rahul Sharma",
                    "bank_account_number": raw_acct,
                    "bank_ifsc_code": "HDFC0000123",
                    "bank_branch_name": "Jayanagar",
                    "police_fir_lodged_flag": True,
                    "fir_or_gd_number": "FIR-2026-441",
                    "police_station_name": "Jayanagar Traffic PS",
                    "fir_report_date": "2026-11-23",
                    "injury_or_third_party_flag": True,
                    "third_party_loss_type": "property_damage",
                    "third_party_injured_count": 0,
                    "third_party_damage_summary": "Compound wall scratch",
                    "dpdp_consent_granted": True,
                    "truthfulness_declaration_accepted": True,
                }
            },
        )
        assert ok_resp.status_code == 200
        # Bank account number must be masked via mask_pii_value in ALL responses
        assert ok_resp.json()["motor_claim_form"]["bank_account_number"] != raw_acct
        assert ok_resp.json()["motor_claim_form"]["bank_account_number"].endswith("1012")
        assert ok_resp.json()["masked_pii_summary"]["bank_account_number_masked"].endswith("1012")
        assert ok_resp.json()["masked_pii_summary"]["driver_license_number_masked"].endswith("8765")

        # Summary endpoints mask bank, DL, and mobile
        list_resp = await client.get("/api/claims/", headers=headers)
        assert list_resp.status_code == 200
        matched = [c for c in list_resp.json()["claims"] if c["id"] == cid][0]
        assert matched["motor_claim_form"]["bank_account_number"].endswith("1012")
        assert matched["motor_claim_form"]["driver_license_number"].endswith("8765")
        assert matched["motor_claim_form"]["registered_mobile"].endswith("2345")
        assert raw_acct not in str(matched)

        # Audit logs must NEVER contain raw bank account number or DL
        audits = await get_user_audit_logs("USR-100001", limit=15)
        audit_blob = " ".join(a["details"] for a in audits)
        assert raw_acct not in audit_blob
        assert raw_dl not in audit_blob

        # 3. Theft skips driver details even when driver_was_owner=False and driver_name is omitted
        theft_claim = await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "policy_reference": "KA-02-TH-7711",
                "incident_location": "BTM Layout, Bengaluru",
                "incident_date": "2026-11-24",
                "vehicle_type": "bike",
                "damage_description": "Vehicle stolen from apartment parking",
                "transcript": "My bike was stolen overnight.",
                "motor_claim_form": {
                    "loss_type": "theft",
                    "driver_was_owner": False,
                    "driver_name": None,
                    "non_traceable_report_status": "pending",
                    "all_original_keys_available": True,
                    "financier_hypothecated": True,
                    "financier_name": "HDFC Bank Auto Loans",
                    "police_fir_lodged_flag": True,
                    "fir_or_gd_number": "FIR-BTM-901",
                    "police_station_name": "Mico Layout PS",
                    "dpdp_consent_granted": True,
                    "truthfulness_declaration_accepted": True,
                },
            },
        )
        assert theft_claim.status_code == 201


@pytest.mark.anyio
async def test_group_a_voice_slot_extraction_and_no_form_id_prompts():
    """Voice endpoint extracts Group A slots without breaking 5 core fields or asking for pincode/IFSC."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2W utterance with Group A slots
        res_2w = await client.post(
            "/api/v1/voice/converse",
            json={
                "message": "My friend Karthik was riding my bike KA-01-MJ-4412 with a pillion rider around 7:30 PM at Silk Board junction, met with an accident with headlight damage, lodged an FIR, no injuries, parked at Whitefield Honda service center.",
                "language": "en-IN",
            },
        )
        assert res_2w.status_code == 200
        d2 = res_2w.json()
        assert d2["claimed_registration"] == "KA-01-MJ-4412"
        ms2 = d2["motor_slots"]
        assert ms2["loss_type"] == "own_damage_accident"
        assert ms2["incident_time"] == "7:30 PM"
        assert ms2["driver_was_owner"] is False
        assert ms2["driver_relationship"] == "relative_or_friend"
        assert ms2["driver_name"] == "Karthik"
        assert ms2["pillion_rider_present"] is True
        assert ms2.get("occupants_count") is None
        assert ms2["police_fir_lodged_flag"] is True
        assert ms2["injury_or_third_party_flag"] is False
        assert "whitefield honda service center" in (ms2.get("inspection_location") or "").lower()
        # Voice reply must NEVER ask aloud for long form IDs
        reply_low = d2["reply_text"].lower()
        for forbidden in ("pincode", "ifsc", "issuing rto", "license number"):
            assert forbidden not in reply_low

        # 4W utterance with occupants_count
        res_4w = await client.post(
            "/api/v1/voice/extract-slots",
            json={
                "text": "There were 4 people in my Maruti Swift car KA-03-AB-1234 yesterday night when it hit a divider near Hebbal. No FIR filed.",
                "language": "en-IN",
            },
        )
        assert res_4w.status_code == 200
        d4 = res_4w.json()
        assert d4["claimed_vehicle_type"] == "four_wheeler"
        assert d4["motor_slots"]["occupants_count"] == 4
        assert d4["motor_slots"].get("pillion_rider_present") is None
        assert d4["motor_slots"]["police_fir_lodged_flag"] is False


@pytest.mark.anyio
async def test_group_d_adjuster_portal_and_9_section_dossier_json_and_pdf():
    """Verify Adjuster Group D endpoint, cross-customer isolation, and 9-section Canonical JSON + PDF."""
    headers_a = _auth_headers("USR-100001", "Rahul Sharma")
    headers_b = _auth_headers("USR-100002", "Sai Shankar Reddy")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c_resp = await client.post(
            "/api/claims/",
            headers=headers_a,
            json={
                "policy_reference": "POL-2026-4455",
                "claimed_registration": "KA-01-XY-8899",
                "incident_location": "Whitefield, Bengaluru",
                "incident_date": "2026-11-24",
                "vehicle_type": "car",
                "vehicle_make_model": "Hyundai Creta",
                "damage_description": "Right fender and headlight damaged",
                "transcript": "Creta damaged at Whitefield.",
                "motor_claim_form": {
                    "claimant_name": "Rahul Sharma",
                    "claim_settlement_mode": "reimbursement",
                    "bank_account_holder_name": "Rahul Sharma",
                    "bank_account_number": "112233445566",
                    "bank_ifsc_code": "SBIN0001234",
                    "loss_type": "own_damage_accident",
                    "occupants_count": 2,
                    "dpdp_consent_granted": True,
                    "truthfulness_declaration_accepted": True,
                },
            },
        )
        assert c_resp.status_code == 201
        cid = c_resp.json()["id"]

        # Cross-customer access must be rejected with 403
        forbidden_adj = await client.put(
            f"/api/claims/{cid}/adjuster-assessment",
            headers=headers_b,
            json={"surveyor_assessment": {"surveyor_name": "Unauthorized"}},
        )
        assert forbidden_adj.status_code == 403

        # Adjuster update for Group D
        adj_resp = await client.put(
            f"/api/claims/{cid}/adjuster-assessment",
            headers=headers_a,
            json={
                "insurer_policy_master": {
                    "claim_reference_number": "INS-2026-991",
                    "idv_inr": 850000,
                    "ncb_percent": 20,
                    "coverage_type": "Comprehensive Zero-Dep",
                    "active_addons": ["Zero-Dep", "Consumables"],
                    "compulsory_excess_inr": 1000,
                },
                "external_registry_checks": {
                    "engine_number": "G4FLMV123456",
                    "chassis_vin_number": "MALBM51BLKM987654",
                    "vahan_status": "pending_integration",
                    "sarathi_dl_status": "pending_integration",
                    "iib_cross_claim_status": "pending_integration",
                    "edar_sync_status": "pending_integration",
                },
                "surveyor_assessment": {
                    "surveyor_name": "Ramesh Kulkarni",
                    "surveyor_irdai_license_no": "IRDAI-SLA-7742",
                    "odometer_reading_km": 24350,
                    "damage_freshness_classification": "fresh",
                    "imt_gr9_depreciation_inr": 2500,
                    "salvage_value_inr": 500,
                    "constructive_total_loss": False,
                    "net_assessed_payable_inr": 18500,
                },
            },
        )
        assert adj_resp.status_code == 200

        # Generate 9-section Dossier & verify Canonical JSON + PDF
        rep_resp = await client.post(f"/api/claims/{cid}/report", headers=headers_a)
        assert rep_resp.status_code == 200
        rep = rep_resp.json()
        canonical = rep["canonical_schema"]
        assert "user_declared_fields" in canonical
        assert "insurer_and_registry_fields" in canonical
        # Raw bank account number must NEVER appear in canonical schema or PDF
        assert "112233445566" not in str(rep)
        assert canonical["user_declared_fields"]["bank_account_number"].endswith("5566")
        assert canonical["insurer_and_registry_fields"]["insurer_policy_master"]["idv_inr"] == 850000
        assert canonical["insurer_and_registry_fields"]["external_registry_checks"]["vahan_status"] == "pending_integration"
        assert canonical["insurer_and_registry_fields"]["surveyor_assessment"]["net_assessed_payable_inr"] == 18500

        pdf_resp = await client.get(f"/api/claims/{cid}/report/pdf", headers=headers_a)
        assert pdf_resp.status_code == 200
        assert pdf_resp.content.startswith(b"%PDF")
        assert b"112233445566" not in pdf_resp.content
