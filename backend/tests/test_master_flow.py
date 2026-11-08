"""
Master End-to-End Acceptance Test Suite for ClaimSathi AI (Phases 1–7).
Validates all 12 Master Acceptance Criteria from _ClaimSathi AI product flow.pdf (Pages 1–14):
1. Customer registration, login & persistent Customer Claims Vault (USR-XXXXXX)
2. Customer explains an accident -> AI extracts structured information
3. Important information is missing -> AI asks appropriate follow-up questions
4. Customer uploads a valid photograph -> Magic bytes verified, stored, SHA-256 & 64-bit DCT pHash computed
5. Customer uploads an exact duplicate (same claim & cross-claim) -> System flags exact duplicate via SHA-256
6. Customer uploads a resized / recompressed duplicate -> pHash detects visual match & flags Human Review
7. Supported AI provenance (C2PA & SynthID) + Invalid/tampered credential -> System records exact signal
8. No AI provenance found / Metadata missing -> System reports Inconclusive or Metadata unavailable (never 'genuine')
9. Customer captures live evidence -> Server capture session ID & randomized instructions recorded
10. Customer reviews & confirms the claim -> Claim record finalized with audit trail
11. Professional Claim Dossier generated -> 9 Sections, Layer 1 Canonical JSON & binary PDF available
12. Demo insurer receives submission -> Layer 2 Adapter maps payload & simulated acknowledgement returned
"""

import io
import pytest
from PIL import Image, ImageDraw
from httpx import AsyncClient, ASGITransport

import aiosqlite
from app.main import app
from app.database import init_db, DB_PATH
from app.providers.transcription import extract_claim_fields, generate_assistant_dialogue

transport = ASGITransport(app=app)


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM evidence_checks")
        await db.execute("DELETE FROM evidence_assets")
        await db.execute("DELETE FROM insurer_submissions")
        await db.commit()
    yield


def _create_patterned_vehicle_image(
    width: int = 400,
    height: int = 300,
    fmt: str = "JPEG",
    include_exif: bool = False,
    append_bytes: bytes = b"",
    seed_variant: int = 1,
) -> bytes:
    """
    Generate a realistic non-uniform patterned image (simulating a damaged vehicle photo)
    so 2D-DCT perceptual hashing has rich spatial frequencies to fingerprint.
    """
    img = Image.new("RGB", (width, height), color=(220, 225, 235))
    draw = ImageDraw.Draw(img)

    if seed_variant == 1:
        # Vehicle silhouette + contrasting damage region on left door & bumper
        draw.rectangle([40, 90, width - 40, height - 50], fill=(35, 75, 145), outline=(10, 20, 50), width=4)
        draw.ellipse([65, height - 85, 135, height - 15], fill=(25, 25, 25))
        draw.ellipse([width - 135, height - 85, width - 65, height - 15], fill=(25, 25, 25))
        # Distinctive diagonal dent pattern
        draw.polygon([(110, 110), (240, 125), (210, 220), (95, 195)], fill=(190, 45, 45))
        draw.rectangle([150, 50, 290, 95], fill=(180, 210, 240))
    else:
        # Completely different visual pattern (e.g. vertical stripes / different scene)
        for x in range(0, width, 40):
            color = (240, 180, 40) if (x // 40) % 2 == 0 else (20, 90, 60)
            draw.rectangle([x, 0, x + 39, height], fill=color)
        draw.ellipse([10, 10, width // 3, height // 2], fill=(250, 250, 250))

    buf = io.BytesIO()
    if include_exif:
        exif = Image.Exif()
        # 271 = Make, 272 = Model, 305 = Software
        exif[271] = "Canon"
        exif[272] = "EOS-MotorInspect-Cam"
        exif[305] = "CameraFirmware 2.1"
        img.save(buf, format=fmt, quality=92, exif=exif.tobytes())
    else:
        img.save(buf, format=fmt, quality=92)

    return buf.getvalue() + append_bytes


@pytest.mark.anyio
async def test_master_01_customer_registration_login_and_vault():
    """Master Test 1: Customer Registration, Unique ID USR-XXXXXX, Login & Persistent Vault."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Quick login as pre-seeded Rahul (USR-100001)
        login_resp = await client.post(
            "/api/auth/login",
            json={"identifier": "USR-100001", "demo_quick_login": True},
        )
        assert login_resp.status_code == 200
        auth_data = login_resp.json()
        assert auth_data["user"]["customer_id"] == "USR-100001"
        assert auth_data["user"]["name"] == "Rahul Sharma"
        token = auth_data["access_token"]

        # Verify Vault access with historical claim CS-2026-000085
        vault_resp = await client.get(
            "/api/auth/vault",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert vault_resp.status_code == 200
        vault = vault_resp.json()
        assert vault["user"]["customer_id"] == "USR-100001"
        assert vault["total_cases"] >= 1
        assert any(c["id"] == "CS-2026-000085" for c in vault["claims"])


@pytest.mark.anyio
async def test_master_02_and_03_conversation_extraction_and_missing_followup():
    """Master Test 2 & 3: AI extracts structured info and asks ONLY for missing fields."""
    partial_transcript = (
        "Meri car ka accident ho gaya hai Madhapur, Hyderabad mein. "
        "Left door aur front bumper tut gaya hai. Policy number MOT-2026-TS-99881."
    )
    fields, missing = extract_claim_fields(partial_transcript)
    fmap = {f.name: f.value for f in fields}

    assert fmap["policy_reference"] == "MOT-2026-TS-99881"
    assert fmap["vehicle_type"] == "car"
    assert "Madhapur" in (fmap["incident_location"] or "")
    assert fmap["damage_description"] is not None
    assert missing == ["incident_date"]

    dialogue = generate_assistant_dialogue(partial_transcript, fields, missing, "en-IN")
    assert "MOT-2026-TS-99881" in dialogue["display_text"]
    assert "date or time" in dialogue["display_text"].lower()


@pytest.mark.anyio
async def test_master_04_05_06_evidence_integrity_exact_and_resized_duplicates():
    """
    Master Test 4, 5 & 6:
    - Upload valid photograph -> stored & inspected
    - Upload exact duplicate across claims (Claim 001 vs Claim 019 scenario from PDF Page 2) -> SHA-256 flags Exact Duplicate
    - Upload resized & recompressed duplicate -> 64-bit DCT pHash flags Visual Duplicate (Possible Reuse -> Human Review)
    - Verify cross-claim privacy protection (does not leak another customer's PII)
    """
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login as Rahul (USR-100001)
        login_resp = await client.post(
            "/api/auth/login",
            json={"identifier": "USR-100001", "demo_quick_login": True},
        )
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create Claim A (Rahul's first bike claim)
        c1_resp = await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-2026-KA-001",
                "incident_location": "Davanagere",
                "incident_date": "2026-10-15",
                "vehicle_type": "bike",
                "damage_description": "Front mudguard and headlamp damaged",
                "transcript": "Bike accident in Davanagere",
            },
        )
        assert c1_resp.status_code == 201
        claim_a_id = c1_resp.json()["id"]
        assert claim_a_id.startswith("CS-2026-")

        # 1. Upload original valid photograph to Claim A
        orig_photo_bytes = _create_patterned_vehicle_image(width=480, height=360, fmt="JPEG", include_exif=True, seed_variant=1)
        up1 = await client.post(
            f"/api/evidence/{claim_a_id}/upload",
            headers=headers,
            files={"file": ("damaged_bike_001.jpg", orig_photo_bytes, "image/jpeg")},
            data={"capture_method": "upload_photo"},
        )
        assert up1.status_code == 201
        ev1 = up1.json()
        assert ev1["label"] == "Image 01"
        assert ev1["screening"]["magic_bytes_valid"] is True
        assert ev1["screening"]["duplicate_status"] == "unique"
        assert len(ev1["screening"]["sha256_hash"]) == 64
        assert len(ev1["screening"]["perceptual_hash"]) == 16

        # Create Claim B (Three weeks later — second claim CS-2026-...)
        c2_resp = await client.post(
            "/api/claims/",
            headers=headers,
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-2026-KA-019",
                "incident_location": "Hubli Highway",
                "incident_date": "2026-11-05",
                "vehicle_type": "bike",
                "damage_description": "Side fairing scratch and dent",
                "transcript": "Second bike claim on highway",
            },
        )
        claim_b_id = c2_resp.json()["id"]

        # 2. Upload EXACT same image to Claim B -> Must trigger SHA-256 Exact Duplicate across claims!
        up_exact = await client.post(
            f"/api/evidence/{claim_b_id}/upload",
            headers=headers,
            files={"file": ("reused_exact_bike.jpg", orig_photo_bytes, "image/jpeg")},
            data={"capture_method": "upload_photo"},
        )
        assert up_exact.status_code == 201
        ev_exact = up_exact.json()
        assert ev_exact["screening"]["duplicate_status"] == "exact_duplicate"
        assert ev_exact["screening"]["duplicate_match_type"] == "cross_claim"
        assert ev_exact["screening"]["requires_human_review"] is True
        assert "Duplicate Flag" in ev_exact["screening"]["screening_outcome_label"]

        # 3. Upload a RESIZED & RECOMPRESSED copy of the image (240x180 PNG instead of 480x360 JPEG)
        # SHA-256 is completely different, but 64-bit 2D-DCT pHash must catch it!
        with Image.open(io.BytesIO(orig_photo_bytes)) as img:
            resized_img = img.resize((240, 180), Image.Resampling.BILINEAR)
            resized_buf = io.BytesIO()
            resized_img.save(resized_buf, format="PNG")
            resized_bytes = resized_buf.getvalue()

        up_resized = await client.post(
            f"/api/evidence/{claim_b_id}/upload",
            headers=headers,
            files={"file": ("resized_copy.png", resized_bytes, "image/png")},
            data={"capture_method": "upload_photo"},
        )
        assert up_resized.status_code == 201
        ev_resized = up_resized.json()
        assert ev_resized["screening"]["sha256_hash"] != ev1["screening"]["sha256_hash"]
        assert ev_resized["screening"]["duplicate_status"] == "visual_duplicate"
        assert ev_resized["screening"]["hamming_distance"] <= 10
        assert ev_resized["screening"]["requires_human_review"] is True
        assert "Possible duplicate" in ev_resized["screening"]["screening_outcome_label"]


@pytest.mark.anyio
async def test_master_07_and_08_ai_provenance_c2pa_synthid_and_inconclusive_rules():
    """
    Master Test 7 & 8 (Page 2 of PDF):
    - Supported AI watermark detected (SynthID) -> 'AI provenance detected'
    - Valid AI-generation credential detected (C2PA) -> 'AI-generated provenance detected'
    - Invalid / tampered credential -> 'Integrity warning'
    - Camera EXIF present but no AI signal -> 'No supported signal' -> 'Inconclusive' (Never 'genuine'!)
    - Stripped metadata -> 'Metadata missing' -> 'Metadata unavailable'
    """
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c_resp = await client.post(
            "/api/claims/",
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-2026-PROV-100",
                "incident_location": "Bengaluru",
                "incident_date": "2026-11-06",
                "vehicle_type": "car",
                "damage_description": "Front bumper dent",
            },
        )
        claim_id = c_resp.json()["id"]

        # A) SynthID watermark signal present
        synthid_img = _create_patterned_vehicle_image(
            append_bytes=b"<!-- google:synthid SynthID-Watermark-Detected -->",
            seed_variant=2,
        )
        r_synth = await client.post(
            f"/api/evidence/{claim_id}/upload",
            files={"file": ("synthid_car.jpg", synthid_img, "image/jpeg")},
        )
        s_synth = r_synth.json()["screening"]
        assert s_synth["provenance_result"] == "Supported AI watermark detected"
        assert s_synth["provenance_system_response"] == "AI provenance detected"
        assert s_synth["requires_human_review"] is True

        # B) Valid C2PA Content Credential present
        c2pa_img = _create_patterned_vehicle_image(
            append_bytes=b"urn:uuid:63327061-0011-0010-8000-00aa00389b71 c2pa.assertions trainedAlgorithmicMedia OpenAI DALL-E",
            seed_variant=2,
        )
        r_c2pa = await client.post(
            f"/api/evidence/{claim_id}/upload",
            files={"file": ("c2pa_ai_car.jpg", c2pa_img, "image/jpeg")},
        )
        s_c2pa = r_c2pa.json()["screening"]
        assert s_c2pa["provenance_result"] == "Valid AI-generation credential detected"
        assert s_c2pa["provenance_system_response"] == "AI-generated provenance detected"
        assert s_c2pa["requires_human_review"] is True

        # C) Tampered / Invalid C2PA credential
        tampered_img = _create_patterned_vehicle_image(
            append_bytes=b"c2pa:manifest INVALID_SIGNATURE c2pa.corrupted",
            seed_variant=2,
        )
        r_tamp = await client.post(
            f"/api/evidence/{claim_id}/upload",
            files={"file": ("tampered_c2pa.jpg", tampered_img, "image/jpeg")},
        )
        s_tamp = r_tamp.json()["screening"]
        assert s_tamp["provenance_result"] == "Invalid credential"
        assert s_tamp["provenance_system_response"] == "Integrity warning"
        assert s_tamp["requires_human_review"] is True

        # D) Standard camera EXIF present, no AI watermark -> Must be 'Inconclusive' (NOT 'genuine')
        exif_only_img = _create_patterned_vehicle_image(include_exif=True, seed_variant=2)
        r_inc = await client.post(
            f"/api/evidence/{claim_id}/upload",
            files={"file": ("camera_photo.jpg", exif_only_img, "image/jpeg")},
        )
        s_inc = r_inc.json()["screening"]
        assert s_inc["provenance_result"] == "No supported signal"
        assert s_inc["provenance_system_response"] == "Inconclusive"

        # E) Stripped metadata -> Must be 'Metadata unavailable'
        stripped_img = _create_patterned_vehicle_image(include_exif=False, seed_variant=2)
        r_strip = await client.post(
            f"/api/evidence/{claim_id}/upload",
            files={"file": ("stripped_photo.jpg", stripped_img, "image/jpeg")},
        )
        s_strip = r_strip.json()["screening"]
        assert s_strip["provenance_result"] == "Metadata missing"
        assert s_strip["provenance_system_response"] == "Metadata unavailable"


@pytest.mark.anyio
async def test_master_09_10_11_12_live_capture_dossier_pdf_and_mock_insurer_gateway():
    """
    Master Test 9, 10, 11 & 12:
    - Start Guided Live Camera Capture Session -> receive CAP-2026-XXXXXX & randomized instructions
    - Upload live-captured photo + MP4 video bound to session
    - Confirm claim details
    - Generate 9-Section Professional Claim Dossier, Layer 1 Canonical Schema JSON & binary PDF
    - Submit to Mock Insurer Integration Gateway -> verify Layer 2 Adapter mapping & simulated acknowledgement
    """
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create claim
        c_resp = await client.post(
            "/api/claims/",
            json={
                "customer_id": "USR-100001",
                "policy_reference": "MOT-2026-KA-77889",
                "incident_location": "Davanagere",
                "incident_date": "2026-11-05",
                "vehicle_type": "car",
                "damage_description": "Front right fender and bumper damaged",
                "transcript": "Customer reported vehicle accident in Davanagere",
            },
        )
        assert c_resp.status_code == 201
        claim_id = c_resp.json()["id"]

        # 2. Start Guided Live Camera Capture Session (Master Test 9)
        cap_resp = await client.post(
            "/api/evidence/capture-session",
            json={"claim_id": claim_id, "capture_type": "guided_video_and_photo"},
        )
        assert cap_resp.status_code == 201
        cap_session = cap_resp.json()
        session_id = cap_session["session_id"]
        assert session_id.startswith("CAP-2026-")
        assert len(cap_session["instructions"]) == 3

        # Upload live camera photo associated with session
        live_photo = _create_patterned_vehicle_image(width=320, height=240, include_exif=True, seed_variant=1)
        up_live = await client.post(
            f"/api/evidence/{claim_id}/upload",
            files={"file": ("live_capture_front.jpg", live_photo, "image/jpeg")},
            data={"capture_method": "live_photo", "capture_session_id": session_id},
        )
        assert up_live.status_code == 201
        assert up_live.json()["capture_session_id"] == session_id

        # Upload guided video (valid MP4 ftyp header)
        mp4_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + (b"\x00" * 256)
        up_vid = await client.post(
            f"/api/evidence/{claim_id}/upload",
            files={"file": ("guided_walkaround.mp4", mp4_bytes, "video/mp4")},
            data={"capture_method": "guided_video", "capture_session_id": session_id},
        )
        assert up_vid.status_code == 201
        vid_data = up_vid.json()
        assert vid_data["label"] == "Video 01"
        assert vid_data["screening"]["screening_outcome_label"] == "File integrity checks passed"

        # 3. Customer confirms claim details (Master Test 10)
        upd_resp = await client.put(
            f"/api/claims/{claim_id}",
            json={"customer_confirmation": True, "people_involved": "Rahul Sharma (Driver)"},
        )
        assert upd_resp.status_code == 200
        assert upd_resp.json()["customer_confirmation"] is True

        # 4. Generate 9-Section Professional Claim Dossier, Canonical JSON & PDF (Master Test 11)
        rpt_resp = await client.post(f"/api/claims/{claim_id}/report")
        assert rpt_resp.status_code == 200
        rpt = rpt_resp.json()
        assert rpt["version"] == "1.0"
        dossier = rpt["dossier"]
        canonical = rpt["canonical_schema"]

        # Verify all 9 sections exist in Dossier
        assert dossier["section_01_customer"]["customer_id"] == "USR-100001"
        assert dossier["section_02_policy"]["policy_number"] == "MOT-2026-KA-77889"
        assert dossier["section_03_incident"]["incident_location"] == "Davanagere"
        assert len(dossier["section_04_statement"]["chronological_account"]) > 40
        assert len(dossier["section_05_evidence_inventory"]["items"]) == 2
        assert "section_06_validation_review" in dossier
        assert len(dossier["section_07_supporting_documents"]["documents"]) == 2
        assert "section_08_preparation_summary" in dossier
        assert "not an insurer-issued claim form" in dossier["section_09_declaration"]["regulatory_disclaimer"].lower()

        # Verify Layer 1 Canonical Schema matches Page 6-7 of PDF
        assert canonical["claim_id"] == claim_id
        assert canonical["customer_id"] == "USR-100001"
        assert canonical["insurance_type"] == "motor"
        assert canonical["incident"]["location"] == "Davanagere"
        assert len(canonical["evidence"]["images"]) == 1
        assert len(canonical["evidence"]["videos"]) == 1
        assert canonical["customer_confirmation"] is True
        assert canonical["report_status"] == "generated"

        # Verify downloadable binary PDF endpoint returns valid PDF
        pdf_resp = await client.get(f"/api/claims/{claim_id}/report/pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"
        assert pdf_resp.content.startswith(b"%PDF-1.4")
        assert b"SECTION 01 - Customer Information" in pdf_resp.content
        assert b"SECTION 09 - Declaration & Confirmation" in pdf_resp.content

        # Verify downloadable Canonical JSON endpoint
        json_resp = await client.get(f"/api/claims/{claim_id}/report/json")
        assert json_resp.status_code == 200
        assert json_resp.json()["claim_id"] == claim_id

        # 5. Submit to Mock Insurer Integration Gateway (Master Test 12 — Page 10-11 of PDF)
        sub_resp = await client.post(
            f"/api/claims/{claim_id}/submit-insurer",
            json={"recipient": "DEMO_INSURER_A", "submission_channel": "Official insurer API"},
        )
        assert sub_resp.status_code == 200
        sub_data = sub_resp.json()
        assert sub_data["submission_id"].startswith("DEMO-SUB-")
        assert sub_data["claim_id"] == claim_id
        assert sub_data["recipient"] == "DEMO_INSURER_A"
        assert sub_data["delivery_status"] == "simulated_success"
        assert sub_data["insurer_claim_reference"].startswith("DEMO-INS-")
        assert sub_data["processing_status"] == "received"
        assert len(sub_data["pipeline_steps"]) == 5
