"""
Phase 3 Acceptance Test:
1. Voice intake with one required field missing.
2. Follow-up question answered by user.
3. User edits/corrects a field during review.
4. Claim confirmation and ticket generation.
5. Verification that final ticket preserves the original transcript and all user-corrected values.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db
from app.providers.transcription import extract_claim_fields

transport = ASGITransport(app=app)


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield


@pytest.mark.anyio
async def test_end_to_end_acceptance_workflow():
    """
    Simulate full user acceptance journey:
    - Fictional Hinglish voice transcription with missing incident date.
    - System detects missing date and asks follow-up.
    - User answers date and edits damage description.
    - Ticket created and verified.
    """
    # 1. Original Hinglish spoken claim (Incident date omitted)
    fictional_transcript = (
        "Dekhiye, meri bike ka accident hua hai. Policy number POL-BK-2024-DL-55123. "
        "Main Connaught Place Delhi ke paas tha jab ek car ne mujhe side se hit kiya. "
        "Front mudguard tut gaya aur headlight bhi."
    )

    # 2. Extract fields
    fields, missing = extract_claim_fields(fictional_transcript)

    # Verify that 'incident_date' is detected as missing
    assert "incident_date" in missing, "Incident date must be detected as missing"
    field_dict = {f.name: f.value for f in fields}
    assert field_dict["policy_reference"] == "POL-BK-2024-DL-55123"
    assert field_dict["vehicle_type"] == "bike"
    assert "Connaught Place" in (field_dict["incident_location"] or "")
    assert field_dict["incident_date"] is None

    # 3. User fills the missing incident date via follow-up question
    user_filled_date = "28-10-2026"
    field_dict["incident_date"] = user_filled_date

    # 4. User corrects/refines the damage description during review
    user_corrected_damage = "Front mudguard shattered, LED headlight broken, handle misaligned"
    field_dict["damage_description"] = user_corrected_damage

    # Also user refines vehicle type to specific model
    user_corrected_vehicle = "Honda CB Hornet 160R (Bike)"
    field_dict["vehicle_type"] = user_corrected_vehicle

    # 5. User confirms the claim -> calls POST /api/claims/
    create_payload = {
        "policy_reference": field_dict["policy_reference"],
        "incident_location": field_dict["incident_location"],
        "incident_date": field_dict["incident_date"],
        "vehicle_type": field_dict["vehicle_type"],
        "damage_description": field_dict["damage_description"],
        "transcript": fictional_transcript,
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create ticket
        create_resp = await client.post("/api/claims/", json=create_payload)
        assert create_resp.status_code == 201
        created_data = create_resp.json()
        ticket_id = created_data["id"]
        assert ticket_id.startswith("DEMO-")

        # Retrieve ticket details -> calls GET /api/claims/{id}
        get_resp = await client.get(f"/api/claims/{ticket_id}")
        assert get_resp.status_code == 200
        detail = get_resp.json()

    saved_claim = detail["claim"]
    timeline = detail["timeline"]

    # 6. Verify Acceptance Criteria:
    # A) Original transcription is strictly preserved
    assert saved_claim["transcript"] == fictional_transcript, "Original transcript must remain unmodified"

    # B) User's filled-in missing value is preserved
    assert saved_claim["incident_date"] == user_filled_date, "User's supplied incident date must be preserved"

    # C) User's corrected values are preserved
    assert saved_claim["damage_description"] == user_corrected_damage, "User's corrected damage must be preserved"
    assert saved_claim["vehicle_type"] == user_corrected_vehicle, "User's corrected vehicle type must be preserved"
    assert saved_claim["policy_reference"] == "POL-BK-2024-DL-55123"


@pytest.mark.anyio
async def test_telugu_voice_conversational_acceptance():
    """
    Test Telugu conversational intake:
    - User speaks in Telugu script with phonetic policy, vehicle, location, damage.
    - System extracts all 4 details and marks ONLY incident_date as missing.
    - Assistant dialogue acknowledges policy MOT-2024-TS-98765, car, and Madhapur,
      and asks ONLY for incident_date.
    - User answers date via voice ("నిన్న సాయంత్రం 5:30").
    - Complete claim created and verified.
    """
    from app.providers.transcription import generate_assistant_dialogue

    telugu_transcript = (
        "చూడండి, నా కార్ యాక్సిడెంట్ అయ్యింది. పాలసీ నంబర్ ఎంఓటీ టు థౌజండ్ ట్వంటీ ఫోర్ టీఎస్ "
        "నైన్ ఎయిట్ సెవెన్ సిక్స్ ఫైవ్. నేను హైదరాబాద్ లో మధురాపూర్ దగ్గర డ్రైవ్ చేస్తున్నప్పుడు "
        "ఒక ఆటో వచ్చి సైడ్ లో హిట్ చేసింది. లెఫ్ట్ డోర్ అండ్ బంపర్ ఫుల్ గా డ్యామేజ్ అయ్యింది."
    )

    fields, missing = extract_claim_fields(telugu_transcript)
    field_map = {f.name: f.value for f in fields}

    # Verify extracted values
    assert field_map["policy_reference"] == "MOT-2024-TS-98765"
    assert field_map["vehicle_type"] == "car"
    assert "Madhapur" in (field_map["incident_location"] or "")
    assert field_map["damage_description"] is not None

    # CRITICAL: Verify that ONLY incident_date is missing! Never ask given details again!
    assert missing == ["incident_date"], f"Expected only incident_date missing, got: {missing}"

    # Verify assistant dialogue acknowledges captured details and asks only for date
    dialogue = generate_assistant_dialogue(
        transcript=telugu_transcript,
        fields=fields,
        missing_fields=missing,
        detected_language="te-IN",
    )
    assert "MOT-2024-TS-98765" in dialogue["display_text"]
    assert "తేదీ లేదా సమయం చెప్పండి" in dialogue["display_text"]
    assert dialogue["language"] == "te-IN"

    # User answers date via voice
    field_map["incident_date"] = "Ninna evening 5:30 PM"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/claims/",
            json={
                "policy_reference": field_map["policy_reference"],
                "incident_location": field_map["incident_location"],
                "incident_date": field_map["incident_date"],
                "vehicle_type": field_map["vehicle_type"],
                "damage_description": field_map["damage_description"],
                "transcript": telugu_transcript,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"].startswith("DEMO-")

        # Fetch detail and verify timeline
        get_resp = await client.get(f"/api/claims/{data['id']}")
        assert get_resp.status_code == 200
        detail = get_resp.json()
        timeline = detail["timeline"]
        assert len(timeline) >= 3
        assert detail["claim"]["policy_reference"] == "MOT-2024-TS-98765"
        assert any("Claim Created" in e["title"] for e in timeline)
        assert any("Transcript Processed" in e["title"] for e in timeline)
        assert any("Fields Confirmed" in e["title"] for e in timeline)

