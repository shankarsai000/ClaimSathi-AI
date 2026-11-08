"""
Claims, Dossier Generation & Mock Insurer Gateway Routes for ClaimSathi AI (Phases 1–7).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from ..models import (
    ClaimCreateRequest,
    ClaimUpdateRequest,
    ClaimCreateResponse,
    ClaimDetailResponse,
    ClaimListResponse,
    ClaimRecord,
    ClaimStatus,
    TimelineEvent,
    TranscriptRequest,
    TranscriptResponse,
    InsurerSubmissionRequest,
    InsurerSubmissionResponse,
)
from ..auth import get_optional_current_user_id, decode_access_token
from ..database import (
    insert_claim,
    get_claim,
    get_all_claims,
    get_timeline,
    update_claim_record,
    generate_next_cs_claim_id,
    get_claim_evidence,
    get_claim_reports,
    get_claim_insurer_submissions,
    add_timeline_event,
    log_audit_event,
)
from ..dossier_engine import (
    generate_claim_dossier_and_report,
    submit_to_mock_insurer_gateway,
    render_dossier_pdf_bytes,
    render_localized_dossier_html,
)
from ..providers.transcription import (
    MockTranscriptionProvider,
    detect_conversation_language,
    extract_claim_fields,
    generate_assistant_dialogue,
    validate_and_normalize_field_answer,
)

router = APIRouter(prefix="/claims", tags=["Claims, Dossier & Insurer Gateway"])
transcription = MockTranscriptionProvider()


@router.post("/transcribe", response_model=TranscriptResponse)
async def transcribe_audio(request: TranscriptRequest):
    """Simulate voice transcription and field extraction (Phase 1 compatibility)."""
    scenario = transcription.get_mock_scenario()
    fields, missing = transcription.extract_fields(scenario)
    return TranscriptResponse(
        transcript=scenario["transcript"],
        language=request.language,
        is_mock=True,
        fields=fields,
        missing_fields=missing,
    )


@router.post("/extract-text")
async def extract_text_intake(payload: dict):
    """
    Phase 2 & 3 Multilingual Text Intake:
    Extracts structured claim fields and generates conversational follow-up prompts
    using the real backend NLP extraction engine.
    """
    text = (payload.get("text") or "").strip()
    language_hint = payload.get("language") or "indic-auto"
    if not text:
        raise HTTPException(status_code=400, detail="Incident description text is required.")
    resolved_lang = detect_conversation_language(text, language_hint)
    fields, missing = extract_claim_fields(text)
    dialogue_info = generate_assistant_dialogue(
        transcript=text,
        fields=fields,
        missing_fields=missing,
        detected_language=resolved_lang,
    )
    return {
        "transcript": text,
        "detected_language": dialogue_info["language"],
        "fields": [f.model_dump() for f in fields],
        "missing_fields": missing,
        "assistant_dialogue": dialogue_info["display_text"],
        "assistant_speech_text": dialogue_info["speech_text"],
        "assistant_language": dialogue_info["language"],
    }


@router.post("/validate-field-answer")
async def validate_field_answer_endpoint(payload: dict):
    """
    Strictly validate a user's follow-up answer against the expected field type
    and normalize the value into clean English for insurance company submission.
    """
    target_field = (payload.get("target_field") or "").strip()
    raw_answer = (payload.get("answer") or "").strip()
    language = payload.get("language") or "en-IN"
    if not target_field or not raw_answer:
        raise HTTPException(status_code=400, detail="target_field and answer are required.")
    return validate_and_normalize_field_answer(
        target_field=target_field,
        raw_answer=raw_answer,
        language=language,
    )


@router.post("/", response_model=ClaimCreateResponse, status_code=201)
async def create_claim(
    request: ClaimCreateRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Create a claim case from extracted & confirmed fields.
    - When authenticated or customer_id is provided, generates official ClaimSathi ID (CS-2026-000124).
    - Preserves DEMO-XXXXXXXX prefix for unauthenticated Phase 1 legacy test calls.
    """
    now = datetime.utcnow()
    cs_id = await generate_next_cs_claim_id()

    auth_customer_id: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        try:
            payload = decode_access_token(authorization[7:].strip())
            auth_customer_id = payload.get("sub")
        except Exception:
            pass

    effective_customer_id = request.customer_id or auth_customer_id or "USR-100001"
    use_cs_id = bool(request.customer_id or auth_customer_id)
    primary_id = cs_id if use_cs_id else f"DEMO-{uuid4().hex[:8].upper()}"

    record = ClaimRecord(
        id=primary_id,
        customer_id=effective_customer_id,
        insurance_type="motor",
        policy_reference=request.policy_reference,
        insurer_name=request.insurer_name or "Bharat General Insurance",
        policy_type=request.policy_type or "Comprehensive Motor Policy",
        incident_location=request.incident_location,
        incident_date=request.incident_date,
        vehicle_type=request.vehicle_type,
        damage_description=request.damage_description,
        people_involved=request.people_involved or "Policyholder (Driver)",
        injuries_reported=request.injuries_reported or "No physical injuries reported",
        detailed_statement=request.detailed_statement or "",
        transcript=request.transcript,
        status=ClaimStatus.CONFIRMED,
        customer_confirmation=True,
        is_demo=True,
        created_at=now,
        updated_at=now,
    )
    await insert_claim(record, conversation_turns=request.conversation_turns)
    return ClaimCreateResponse(
        id=record.id,
        claim_id=cs_id,
        status=record.status,
        message=f"Demo claim {record.id} created successfully. This is a simulated claim – no real insurance claim has been filed.",
        is_demo=True,
    )


@router.get("/", response_model=ClaimListResponse)
async def list_claims(customer_id: Optional[str] = Query(None)):
    """List claims (optionally filtered by customer_id)."""
    claims = await get_all_claims(customer_id=customer_id)
    return ClaimListResponse(
        claims=claims,
        total=len(claims),
        is_demo=True,
    )


@router.get("/stats")
async def claim_stats(customer_id: Optional[str] = Query(None)):
    """Dashboard statistics."""
    claims = await get_all_claims(customer_id=customer_id)
    total = len(claims)
    return {
        "total_claims": total,
        "recent_claims": [c.model_dump() for c in claims[:6]],
        "is_demo": True,
    }


@router.get("/{claim_id}", response_model=ClaimDetailResponse)
async def get_claim_detail(
    claim_id: str,
    user_id: str = Depends(get_optional_current_user_id),
):
    """Retrieve a specific claim with timeline, screened evidence, generated reports, and insurer submissions."""
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")
    raw_timeline = await get_timeline(claim_id)
    timeline = [
        TimelineEvent(
            timestamp=datetime.fromisoformat(e["timestamp"]),
            title=e["title"],
            description=e["description"],
        )
        for e in raw_timeline
    ]
    evidence = await get_claim_evidence(claim_id, requesting_user_id=user_id)
    reports = await get_claim_reports(claim_id)
    submissions = await get_claim_insurer_submissions(claim_id)
    return ClaimDetailResponse(
        claim=claim,
        timeline=timeline,
        evidence=evidence,
        reports=reports,
        insurer_submissions=submissions,
        is_demo=True,
    )


@router.put("/{claim_id}", response_model=ClaimRecord)
async def update_claim_details(
    claim_id: str,
    request: ClaimUpdateRequest,
    user_id: str = Depends(get_optional_current_user_id),
):
    """Update or confirm claim details during customer review (Step 6 of product flow)."""
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")

    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if "customer_confirmation" in updates:
        updates["customer_confirmation"] = int(bool(updates["customer_confirmation"]))

    updated = await update_claim_record(claim_id, updates)
    await add_timeline_event(
        claim_id=claim_id,
        title="Customer Review & Confirmation Updated",
        description="Customer reviewed and updated claim details and evidence findings.",
        status="confirmed",
    )
    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="CLAIM_UPDATED",
        details=f"Customer updated fields: {', '.join(updates.keys())}",
    )
    return updated


@router.post("/{claim_id}/report")
async def generate_claim_report_endpoint(
    claim_id: str,
    user_id: str = Depends(get_optional_current_user_id),
):
    """
    Generate the 9-Section Professional Insurance Claim Dossier, Layer 1 Canonical Schema JSON,
    and binary PDF report (Step 7 of product flow).
    """
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")

    report_data = await generate_claim_dossier_and_report(claim_id, requesting_user_id=user_id)
    return report_data


@router.get("/{claim_id}/report")
async def get_latest_claim_report(
    claim_id: str,
    version: Optional[str] = Query(None),
    user_id: str = Depends(get_optional_current_user_id),
):
    """Retrieve the generated 9-Section Dossier & Canonical Schema JSON (generates v1.0 if none exists yet)."""
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")

    reports = await get_claim_reports(claim_id)
    if not reports:
        return await generate_claim_dossier_and_report(claim_id, requesting_user_id=user_id)

    if version:
        for r in reports:
            if r["version"] == version:
                return r
    return reports[0]


@router.get("/{claim_id}/report/pdf")
async def download_claim_report_pdf(
    claim_id: str,
    version: Optional[str] = Query(None),
    user_id: str = Depends(get_optional_current_user_id),
):
    """Download the binary PDF report for the 9-Section Professional Insurance Claim Dossier."""
    report = await get_latest_claim_report(claim_id, version=version, user_id=user_id)
    pdf_path = Path(report["pdf_storage_path"])
    if pdf_path.exists():
        pdf_bytes = pdf_path.read_bytes()
    else:
        from ..models import ProfessionalClaimDossier
        dossier_obj = ProfessionalClaimDossier(**report["dossier"])
        pdf_bytes = render_dossier_pdf_bytes(dossier_obj)

    filename = f"ClaimSathi_Dossier_{claim_id}_v{report['version']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{claim_id}/report/localized")
async def download_claim_report_localized(
    claim_id: str,
    lang: str = Query("en", description="Preferred report language: en, kn, te, hi, ta"),
    download: bool = Query(False, description="Force attachment download if true"),
    version: Optional[str] = Query(None),
    user_id: str = Depends(get_optional_current_user_id),
):
    """
    Render or download the 9-Section Claim Dossier in the customer's preferred language
    (English, Kannada, Telugu, Hindi, Tamil) with full native Unicode font support.
    """
    report = await get_latest_claim_report(claim_id, version=version, user_id=user_id)
    from ..models import ProfessionalClaimDossier
    dossier_obj = ProfessionalClaimDossier(**report["dossier"])
    html_str = render_localized_dossier_html(dossier_obj, lang=lang)
    code = (lang or "en").split("-")[0].lower()
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="ClaimSathi_Dossier_{claim_id}_{code.upper()}.html"'
    return Response(
        content=html_str.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers=headers,
    )


@router.get("/{claim_id}/report/json")
async def download_claim_canonical_json(
    claim_id: str,
    version: Optional[str] = Query(None),
    user_id: str = Depends(get_optional_current_user_id),
):
    """Download Layer 1 — ClaimSathi Canonical Schema JSON for the claim."""
    report = await get_latest_claim_report(claim_id, version=version, user_id=user_id)
    canonical_bytes = json.dumps(report["canonical_schema"], indent=2).encode("utf-8")
    filename = f"ClaimSathi_Canonical_{claim_id}_v{report['version']}.json"
    return Response(
        content=canonical_bytes,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{claim_id}/submit-insurer", response_model=InsurerSubmissionResponse)
async def submit_claim_to_mock_insurer(
    claim_id: str,
    request: InsurerSubmissionRequest,
    user_id: str = Depends(get_optional_current_user_id),
):
    """
    Phase 7 — Simulated Insurer Integration Gateway (Pages 10–11 of PDF).
    Maps Canonical JSON via Layer 2 Insurer Adapter and returns a simulated insurer acknowledgement.
    """
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")

    result = await submit_to_mock_insurer_gateway(
        claim_id=claim_id,
        recipient=request.recipient,
        requesting_user_id=user_id,
    )
    return result
