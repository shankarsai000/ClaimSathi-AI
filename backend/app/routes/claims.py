"""
Claims, Dossier Generation & Mock Insurer Gateway Routes for ClaimSathi AI (Phases 1–7).
Enforces customer identity verification and claim-level ownership controls (Sprint 1).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from ..config import get_settings
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
    MotorClaimFormDetails,
    MotorAdjusterPlaceholders,
    AdjusterAssessmentUpdateRequest,
    mask_pii_value,
)
from ..auth import (
    get_optional_user,
    decode_access_token,
    create_media_ticket,
    verify_media_ticket,
)
from ..authorization import get_authorized_claim_or_demo
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
    delete_claim_record,
    get_evidence_verification_by_id,
    update_evidence_verification_record,
)
from ..dossier_engine import (
    generate_claim_dossier_and_report,
    submit_to_mock_insurer_gateway,
    render_dossier_pdf_bytes,
    render_localized_dossier_html,
)
from ..providers.conversation import process_conversational_turn
from ..providers.transcription import (
    MockTranscriptionProvider,
    detect_conversation_language,
    extract_claim_fields,
    extract_multimodal_slots,
    generate_assistant_dialogue,
    validate_and_normalize_field_answer,
)

router = APIRouter(prefix="/claims", tags=["Claims, Dossier & Insurer Gateway"])
transcription = MockTranscriptionProvider()


def _is_two_wheeler_claim(vehicle_type: Optional[str], claimed_vehicle_type: Optional[str]) -> Optional[bool]:
    if claimed_vehicle_type == "two_wheeler":
        return True
    if claimed_vehicle_type == "four_wheeler":
        return False
    vt = (vehicle_type or "").strip().lower()
    if vt in ("bike", "scooter", "motorcycle", "two_wheeler", "2w"):
        return True
    if vt in ("car", "suv", "sedan", "hatchback", "four_wheeler", "4w"):
        return False
    return None


def normalize_and_validate_motor_form(
    form: Optional[MotorClaimFormDetails],
    vehicle_type: Optional[str],
    claimed_vehicle_type: Optional[str],
) -> Optional[MotorClaimFormDetails]:
    """
    Auto-fill owner-driver defaults, stamp DPDP consent timestamp, flag 2W/4W DL mismatches,
    and enforce conditional Group B/C rules only when formal submission (dpdp_consent_granted=True) is submitted.
    """
    if form is None:
        return None

    updated = form.model_copy()

    # Auto-fill driver details when policyholder/owner was driving
    if updated.driver_was_owner is True:
        if not (updated.driver_name or "").strip() and (updated.claimant_name or "").strip():
            updated.driver_name = updated.claimant_name.strip()
        if not (updated.driver_address or "").strip() and (updated.residential_address or "").strip():
            updated.driver_address = updated.residential_address.strip()
        if not updated.driver_relationship:
            updated.driver_relationship = "owner"

    # Stamp ISO-8601 DPDP consent timestamp if granted
    if updated.dpdp_consent_granted is True and not updated.dpdp_consent_timestamp:
        updated.dpdp_consent_timestamp = datetime.now(timezone.utc).isoformat()

    # Check 2W vs 4W DL class mismatch warning (unless theft or parked unattended)
    is_2w = _is_two_wheeler_claim(vehicle_type, claimed_vehicle_type)
    if (
        updated.loss_type != "theft"
        and updated.vehicle_was_parked_unattended is not True
        and updated.driver_license_class
        and is_2w is not None
    ):
        if is_2w and updated.driver_license_class in ("LMV", "HMV"):
            updated.driver_license_mismatch_warning = (
                "DL Class Mismatch: LMV/HMV license selected for a 2-Wheeler claim (MCWG/MCWOG expected)."
            )
        elif (not is_2w) and updated.driver_license_class in ("MCWG", "MCWOG"):
            updated.driver_license_mismatch_warning = (
                "DL Class Mismatch: 2-Wheeler license (MCWG/MCWOG) selected for a 4-Wheeler claim (LMV expected)."
            )
        else:
            updated.driver_license_mismatch_warning = None

    # Enforce compulsory & conditional Group B/C fields strictly on formal confirmed form submission
    if updated.dpdp_consent_granted is True:
        if updated.truthfulness_declaration_accepted is False:
            raise HTTPException(
                status_code=422,
                detail="Truthfulness declaration must be accepted before final submission.",
            )
        if updated.other_insurance_exists is True and not (updated.other_insurance_details or "").strip():
            raise HTTPException(
                status_code=422,
                detail="Other insurance details are required when another active policy is declared.",
            )
        if updated.claim_settlement_mode == "reimbursement":
            missing_bank = [
                lbl
                for attr, lbl in (
                    ("bank_account_holder_name", "Account Holder Name"),
                    ("bank_account_number", "Bank Account Number"),
                    ("bank_ifsc_code", "Bank IFSC Code"),
                )
                if not (getattr(updated, attr) or "").strip()
            ]
            if missing_bank:
                raise HTTPException(
                    status_code=422,
                    detail=f"Reimbursement bank details required: {', '.join(missing_bank)}.",
                )
        if updated.police_fir_lodged_flag is True:
            if not (updated.fir_or_gd_number or "").strip() or not (updated.police_station_name or "").strip():
                raise HTTPException(
                    status_code=422,
                    detail="FIR/GD Number and Police Station Name are required when police FIR is lodged.",
                )
        if updated.loss_type == "theft" and updated.financier_hypothecated is True:
            if not (updated.financier_name or "").strip():
                raise HTTPException(
                    status_code=422,
                    detail="Financier name is required when the stolen vehicle is hypothecated.",
                )
        if (
            updated.loss_type != "theft"
            and updated.vehicle_was_parked_unattended is not True
            and updated.driver_was_owner is False
            and not (updated.driver_name or "").strip()
        ):
            raise HTTPException(
                status_code=422,
                detail="Driver name is required when a non-owner was driving the vehicle.",
            )

    return updated


def sanitize_claim_for_response(claim: ClaimRecord, summary_mode: bool = False) -> ClaimRecord:
    """Apply DPDP-2025 PII masking via mask_pii_value on bank/DL/mobile fields."""
    if not claim.motor_claim_form:
        return claim
    masked_form = claim.motor_claim_form.masked_copy(mask_all_sensitive=summary_mode)
    return claim.model_copy(update={"motor_claim_form": masked_form})


def _merge_motor_form(existing: MotorClaimFormDetails, incoming: MotorClaimFormDetails) -> MotorClaimFormDetails:
    base_data = existing.model_dump()
    patch_data = incoming.model_dump(exclude_unset=True)
    for k, v in patch_data.items():
        base_data[k] = v
    return MotorClaimFormDetails(**base_data)


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
    Phase 2 & 3 Stateful Multilingual Intake:
    Extracts structured claim fields and generates natural, context-aware conversational
    replies without re-asking already captured details.
    """
    text = (payload.get("text") or "").strip()
    language_hint = payload.get("language") or "indic-auto"
    known_fields = payload.get("known_fields")
    history = payload.get("history")
    expected_field = payload.get("expected_field")
    if not text:
        raise HTTPException(status_code=400, detail="Incident description text is required.")

    known_motor_slots = payload.get("known_motor_slots")
    conv = await process_conversational_turn(
        message=text,
        language=language_hint,
        known_fields=known_fields if isinstance(known_fields, dict) else None,
        history=history if isinstance(history, list) else None,
        expected_field=expected_field,
        known_motor_slots=known_motor_slots if isinstance(known_motor_slots, dict) else None,
    )
    return {
        "transcript": text,
        "detected_language": conv["assistant_language"],
        "fields": [f.model_dump() for f in conv["fields"]],
        "missing_fields": conv["missing_fields"],
        "known_fields": conv["known_fields"],
        "assistant_dialogue": conv["reply_text"],
        "assistant_speech_text": conv.get("assistant_speech_text") or conv["reply_text"],
        "assistant_language": conv["assistant_language"],
        "claimed_vehicle_type": conv.get("claimed_vehicle_type"),
        "vehicle_make_model": conv.get("vehicle_make_model"),
        "vehicle_registration": conv.get("vehicle_registration"),
        "claimed_registration": conv.get("claimed_registration"),
        "motor_slots": conv.get("motor_slots"),
        "damage_keywords": conv.get("damage_keywords", []),
        "incident_description": conv.get("incident_description"),
        "is_complete": conv["is_complete"],
        "no_speech_detected": conv.get("no_speech_detected", False),
        "reasoning_trace": (
            conv["reasoning_trace"].model_dump()
            if hasattr(conv.get("reasoning_trace"), "model_dump")
            else conv.get("reasoning_trace")
        ),
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
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
    authorization: Optional[str] = Header(None),
):
    """
    Create a claim case from extracted & confirmed fields.
    Security: Always derives customer identity strictly from the verified authentication context.
    Never trusts client-supplied customer_id in request bodies.
    """
    settings = get_settings()
    is_prod = (settings.app_env or "").lower() == "production"
    now = datetime.now(timezone.utc)
    cs_id = await generate_next_cs_claim_id()

    # Sprint 1.8: Evidence Validation Gatekeeper for Claim Creation
    ev_record = None
    if request.evidence_id:
        ev_record = await get_evidence_verification_by_id(request.evidence_id)
        if not ev_record:
            raise HTTPException(
                status_code=404,
                detail=f"Evidence verification '{request.evidence_id}' not found.",
            )
        if ev_record["decision"] == "REJECT":
            raise HTTPException(
                status_code=400,
                detail="Cannot submit a claim with REJECTED evidence.",
            )

    # If authorization header passed, ensure current_user is valid
    if current_user:
        effective_customer_id = current_user["sub"]
        primary_id = cs_id
    elif is_prod:
        raise HTTPException(
            status_code=401,
            detail="Authentication required to create an insurance claim in production.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        # Development / test mode fallback for unauthenticated Phase 1 tests
        effective_customer_id = request.customer_id or "USR-100001"
        primary_id = cs_id if request.customer_id else f"DEMO-{uuid4().hex[:8].upper()}"

    damage_desc = request.damage_description
    if ev_record:
        cost_est = ev_record.get("cost_estimate") or {}
        tot = cost_est.get("total_estimated_inr", 0)
        if tot > 0 and "Verified AI Estimate" not in damage_desc:
            damage_desc += f" (Verified AI Estimate: INR {tot:,})"

    normalized_form = normalize_and_validate_motor_form(
        request.motor_claim_form,
        vehicle_type=request.vehicle_type,
        claimed_vehicle_type=request.claimed_vehicle_type,
    )
    resolved_reg = request.claimed_registration or (
        request.policy_reference
        if request.policy_reference and not request.policy_reference.upper().startswith(("POL-", "MOT-", "CS-"))
        else None
    )

    record = ClaimRecord(
        id=primary_id,
        customer_id=effective_customer_id,
        insurance_type="motor",
        policy_reference=request.policy_reference,
        claimed_registration=resolved_reg,
        insurer_name=request.insurer_name or "Bharat General Insurance",
        policy_type=request.policy_type or "Comprehensive Motor Policy",
        incident_location=request.incident_location,
        incident_date=request.incident_date,
        vehicle_type=request.vehicle_type,
        vehicle_make_model=request.vehicle_make_model,
        damage_description=damage_desc,
        people_involved=request.people_involved or "Policyholder (Driver)",
        injuries_reported=request.injuries_reported or "No physical injuries reported",
        detailed_statement=request.detailed_statement or "",
        transcript=request.transcript,
        status=ClaimStatus.CONFIRMED,
        customer_confirmation=True,
        motor_claim_form=normalized_form or MotorClaimFormDetails(),
        insurer_adjuster_data=request.insurer_adjuster_data or MotorAdjusterPlaceholders(),
        is_demo=True,
        created_at=now,
        updated_at=now,
    )
    await insert_claim(record, conversation_turns=request.conversation_turns)

    # Bind linked_claim to evidence verification record
    if request.evidence_id and ev_record:
        cost_est = ev_record.get("cost_estimate") or {}
        linked_claim = {
            "claim_id": record.id,
            "evidence_id": request.evidence_id,
            "policy_number": record.policy_reference,
            "vehicle_registration": record.policy_reference,
            "vehicle_category": ev_record.get("claimed_vehicle_type", "four_wheeler"),
            "verification_decision": ev_record["decision"],
            "estimate_status": cost_est.get("estimate_status"),
            "total_estimated_inr": cost_est.get("total_estimated_inr", 0),
            "damage_count": ev_record.get("damage_count", 0),
            "claim_status": "APPROVED" if ev_record["decision"] == "PASS" else "UNDER_REVIEW",
            "created_at": now.isoformat(),
        }
        stage_results = dict(ev_record.get("stage_results") or {})
        stage_results["linked_claim"] = linked_claim
        await update_evidence_verification_record(
            verification_id=request.evidence_id,
            decision=ev_record["decision"],
            stage_results=stage_results,
            reasons=ev_record.get("reasons") or [],
        )

    await log_audit_event(
        user_id=effective_customer_id,
        action="CLAIM_CREATED",
        details=f"Claim {record.id} created for policy {request.policy_reference} ({request.vehicle_type})",
        claim_id=record.id,
    )
    return ClaimCreateResponse(
        id=record.id,
        claim_id=cs_id,
        status=record.status,
        message=f"Claim {record.id} created successfully. This is a simulated claim – no real insurance claim has been filed.",
        is_demo=True,
    )


@router.get("/", response_model=ClaimListResponse)
async def list_claims(
    customer_id: Optional[str] = Query(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    List claims scoped strictly to the authenticated customer.
    Never exposes other customers' claims.
    """
    settings = get_settings()
    is_prod = (settings.app_env or "").lower() == "production"

    if current_user:
        # Always scope strictly to the verified token identity
        claims = await get_all_claims(customer_id=current_user["sub"])
    elif is_prod:
        raise HTTPException(
            status_code=401,
            detail="Authentication required to list claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        # Development / test mode: only return anonymous demo claims, never other users' data
        all_claims = await get_all_claims()
        claims = [c for c in all_claims if c.id.startswith("DEMO-")]

    masked_claims = [sanitize_claim_for_response(c, summary_mode=True) for c in claims]
    return ClaimListResponse(
        claims=masked_claims,
        total=len(masked_claims),
        is_demo=True,
    )


@router.get("/stats")
async def claim_stats(
    customer_id: Optional[str] = Query(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """Dashboard statistics strictly scoped to the authenticated customer."""
    settings = get_settings()
    is_prod = (settings.app_env or "").lower() == "production"

    if current_user:
        claims = await get_all_claims(customer_id=current_user["sub"])
    elif is_prod:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        all_claims = await get_all_claims()
        claims = [c for c in all_claims if c.id.startswith("DEMO-")]

    total = len(claims)
    masked_recent = [sanitize_claim_for_response(c, summary_mode=True).model_dump() for c in claims[:6]]
    return {
        "total_claims": total,
        "recent_claims": masked_recent,
        "is_demo": True,
    }


@router.get("/{claim_id}", response_model=ClaimDetailResponse)
async def get_claim_detail(
    claim_id: str,
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Retrieve a specific claim.
    Requires claim ownership verification (cross-customer access returns HTTP 403).
    """
    user_id = current_user.get("sub") if current_user else claim.customer_id
    raw_timeline = await get_timeline(claim_id)
    timeline = [
        TimelineEvent(
            timestamp=datetime.fromisoformat(e["timestamp"]) if isinstance(e["timestamp"], str) else e["timestamp"],
            title=e["title"],
            description=e["description"],
        )
        for e in raw_timeline
    ]
    evidence = await get_claim_evidence(claim_id, requesting_user_id=user_id)
    reports = await get_claim_reports(claim_id)
    submissions = await get_claim_insurer_submissions(claim_id)

    await log_audit_event(
        user_id=user_id,
        action="CLAIM_VIEWED",
        details=f"Customer accessed claim detail for {claim_id}",
        claim_id=claim_id,
    )

    return ClaimDetailResponse(
        claim=sanitize_claim_for_response(claim, summary_mode=False),
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
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Update or confirm claim details during customer review (Step 6 of product flow).
    Strictly verifies that the caller owns the claim.
    Enforces evidence verification decision checks (Sprint 1.8).
    """
    user_id = current_user.get("sub") if current_user else claim.customer_id

    # Sprint 1.8: Evidence Validation Gatekeeper for Claim Updates
    ev_record = None
    if request.evidence_id:
        ev_record = await get_evidence_verification_by_id(request.evidence_id)
        if not ev_record:
            raise HTTPException(
                status_code=404,
                detail=f"Evidence verification '{request.evidence_id}' not found.",
            )
        if ev_record["decision"] == "REJECT":
            raise HTTPException(
                status_code=400,
                detail="Cannot submit a claim with REJECTED evidence.",
            )

    valid_cols = {
        "policy_reference", "claimed_registration", "insurer_name", "policy_type",
        "incident_location", "incident_date", "vehicle_type", "vehicle_make_model",
        "damage_description", "people_involved", "injuries_reported",
        "detailed_statement", "customer_confirmation",
    }
    updates = {k: v for k, v in request.model_dump().items() if v is not None and k in valid_cols}
    if "customer_confirmation" in updates:
        updates["customer_confirmation"] = int(bool(updates["customer_confirmation"]))

    eff_vehicle_type = updates.get("vehicle_type") or claim.vehicle_type
    if request.motor_claim_form is not None:
        merged_form = _merge_motor_form(claim.motor_claim_form or MotorClaimFormDetails(), request.motor_claim_form)
        validated_form = normalize_and_validate_motor_form(
            merged_form,
            vehicle_type=eff_vehicle_type,
            claimed_vehicle_type=request.claimed_vehicle_type,
        )
        if validated_form is not None:
            updates["motor_claim_form_json"] = json.dumps(validated_form.model_dump(), ensure_ascii=False)
            # Sync supplemental summary columns cleanly if supplied
            if validated_form.driver_name and "people_involved" not in updates:
                updates["people_involved"] = (
                    f"{validated_form.driver_name} ({validated_form.driver_relationship or 'Driver'})"
                )
    if request.insurer_adjuster_data is not None:
        updates["adjuster_assessment_json"] = json.dumps(
            request.insurer_adjuster_data.model_dump(), ensure_ascii=False
        )

    if request.evidence_id and ev_record:
        cost_est = ev_record.get("cost_estimate") or {}
        tot = cost_est.get("total_estimated_inr", 0)
        if tot > 0 and updates.get("damage_description"):
            if "Verified AI Estimate" not in updates["damage_description"]:
                updates["damage_description"] += f" (Verified AI Estimate: INR {tot:,})"

        now_iso = datetime.now(timezone.utc).isoformat()
        linked_claim = {
            "claim_id": claim_id,
            "evidence_id": request.evidence_id,
            "policy_number": updates.get("policy_reference") or claim.policy_reference,
            "vehicle_registration": updates.get("policy_reference") or claim.policy_reference,
            "vehicle_category": ev_record.get("claimed_vehicle_type", "four_wheeler"),
            "verification_decision": ev_record["decision"],
            "estimate_status": cost_est.get("estimate_status"),
            "total_estimated_inr": tot,
            "damage_count": ev_record.get("damage_count", 0),
            "claim_status": "APPROVED" if ev_record["decision"] == "PASS" else "UNDER_REVIEW",
            "created_at": now_iso,
        }
        stage_results = dict(ev_record.get("stage_results") or {})
        stage_results["linked_claim"] = linked_claim
        await update_evidence_verification_record(
            verification_id=request.evidence_id,
            decision=ev_record["decision"],
            stage_results=stage_results,
            reasons=ev_record.get("reasons") or [],
        )

    updated = await update_claim_record(claim_id, updates)
    await add_timeline_event(
        claim_id=claim_id,
        title="Customer Review & Confirmation Updated",
        description="Customer reviewed and updated claim details and evidence findings.",
        status="confirmed",
    )
    audit_fields = [k for k in updates.keys() if k not in ("motor_claim_form_json", "adjuster_assessment_json")]
    if "motor_claim_form_json" in updates and updated and updated.motor_claim_form:
        pii_note = []
        if updated.motor_claim_form.bank_account_number:
            pii_note.append(f"bank={mask_pii_value(updated.motor_claim_form.bank_account_number, 4)}")
        if updated.motor_claim_form.driver_license_number:
            pii_note.append(f"dl={mask_pii_value(updated.motor_claim_form.driver_license_number, 4)}")
        audit_fields.append(f"motor_claim_form({', '.join(pii_note) if pii_note else 'updated'})")
    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="CLAIM_UPDATED",
        details=f"Customer updated fields: {', '.join(audit_fields)}",
    )
    return sanitize_claim_for_response(updated, summary_mode=False) if updated else updated


@router.put("/{claim_id}/adjuster-assessment", response_model=ClaimRecord)
async def update_adjuster_assessment_endpoint(
    claim_id: str,
    request: AdjusterAssessmentUpdateRequest,
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Group D — Insurer Policy Master, External Registry Hooks & Licensed Surveyor Assessment.
    Adjuster/Dossier portal only; never exposed as customer inputs during intake.
    """
    user_id = current_user.get("sub") if current_user else claim.customer_id
    current_adj = claim.insurer_adjuster_data or MotorAdjusterPlaceholders()
    new_adj = MotorAdjusterPlaceholders(
        insurer_policy_master=request.insurer_policy_master or current_adj.insurer_policy_master,
        external_registry_checks=request.external_registry_checks or current_adj.external_registry_checks,
        surveyor_assessment=request.surveyor_assessment or current_adj.surveyor_assessment,
    )
    updated = await update_claim_record(
        claim_id,
        {"adjuster_assessment_json": json.dumps(new_adj.model_dump(), ensure_ascii=False)},
    )
    await add_timeline_event(
        claim_id=claim_id,
        title="Adjuster & Surveyor Assessment Updated",
        description="Insurer policy master / surveyor assessment metadata updated in adjuster portal.",
        status="confirmed",
    )
    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="ADJUSTER_ASSESSMENT_UPDATED",
        details=f"Adjuster updated Group D assessment for claim {claim_id}",
    )
    return sanitize_claim_for_response(updated, summary_mode=False) if updated else updated


@router.delete("/{claim_id}")
async def delete_claim_endpoint(
    claim_id: str,
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Sprint 1.2: Secure Claim Deletion Endpoint.
    Strictly verifies ownership via get_authorized_claim_or_demo (403 for unauthorized users).
    Cascades deletion to claim_fields, evidence_assets, evidence_checks, reports, timeline_events, insurer_submissions.
    Preserves audit_logs for immutable compliance history.
    """
    user_id = current_user.get("sub") if current_user else claim.customer_id
    success = await delete_claim_record(claim_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")

    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="CLAIM_DELETED",
        details=f"Customer {user_id} deleted claim {claim_id} and all cascaded evidence and reports.",
        resource_type="claim",
        resource_id=claim_id,
        outcome="SUCCESS",
    )
    return {
        "status": "success",
        "message": f"Claim {claim_id} and all associated records have been permanently deleted.",
        "claim_id": claim_id,
    }


@router.post("/{claim_id}/report")
async def generate_claim_report_endpoint(
    claim_id: str,
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Generate the 9-Section Professional Insurance Claim Dossier, Layer 1 Canonical Schema JSON,
    and binary PDF report (Step 7 of product flow).
    Enforces claim ownership.
    """
    user_id = current_user.get("sub") if current_user else claim.customer_id
    report_data = await generate_claim_dossier_and_report(claim_id, requesting_user_id=user_id)
    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="REPORT_GENERATED",
        details=f"Generated dossier report version {report_data.get('version', '1.0')} for claim {claim_id}",
    )
    return report_data


@router.get("/{claim_id}/report")
async def get_latest_claim_report(
    claim_id: str,
    version: Optional[str] = Query(None),
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """Retrieve the generated 9-Section Dossier & Canonical Schema JSON. Enforces claim ownership."""
    user_id = current_user.get("sub") if current_user else claim.customer_id
    reports = await get_claim_reports(claim_id)
    if not reports:
        return await generate_claim_dossier_and_report(claim_id, requesting_user_id=user_id)

    if version:
        for r in reports:
            if r["version"] == version:
                return r
    return reports[0]


@router.post("/{claim_id}/media-ticket")
async def create_claim_media_ticket(
    claim_id: str,
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Issue an ephemeral (60-second) HMAC-signed media ticket for safe media and report downloads.
    Strictly verifies that the caller owns the claim.
    """
    user_id = current_user.get("sub") if current_user else claim.customer_id
    ticket = create_media_ticket(customer_id=user_id, claim_id=claim_id, expires_in=60)
    return {
        "ticket": ticket,
        "claim_id": claim_id,
        "expires_in": 60,
    }


@router.get("/{claim_id}/report/pdf")
async def download_claim_report_pdf(
    claim_id: str,
    version: Optional[str] = Query(None),
    ticket: Optional[str] = Query(None, description="Ephemeral media ticket"),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """Download the binary PDF report for the 9-Section Dossier. Enforces claim ownership."""
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")

    if ticket:
        ticket_data = verify_media_ticket(ticket, claim_id)
        user_id = ticket_data.get("sub", "")
        if claim.customer_id != user_id and not (claim.is_demo and user_id == "USR-100001"):
            raise HTTPException(status_code=403, detail="Access denied: Media ticket customer mismatch.")
    else:
        authorized_claim = await get_authorized_claim_or_demo(claim_id, current_user)
        user_id = current_user.get("sub") if current_user else authorized_claim.customer_id

    report = await get_latest_claim_report(claim_id, version=version, claim=claim, current_user=current_user)
    pdf_path = Path(report["pdf_storage_path"])
    if pdf_path.exists():
        pdf_bytes = pdf_path.read_bytes()
    else:
        from ..models import ProfessionalClaimDossier
        dossier_obj = ProfessionalClaimDossier(**report["dossier"])
        pdf_bytes = render_dossier_pdf_bytes(dossier_obj)

    filename = f"ClaimSathi_Dossier_{claim_id}_v{report['version']}.pdf"
    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="REPORT_DOWNLOADED",
        details=f"Downloaded official English PDF dossier report for claim {claim_id}",
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache, no-store, must-revalidate",
        },
    )


@router.get("/{claim_id}/report/localized")
async def download_claim_report_localized(
    claim_id: str,
    lang: str = Query("en", description="Preferred report language: en, kn, te, hi, ta"),
    download: bool = Query(False, description="Force attachment download if true"),
    version: Optional[str] = Query(None),
    ticket: Optional[str] = Query(None, description="Ephemeral media ticket"),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Render or download the 9-Section Claim Dossier in the customer's preferred language.
    Enforces claim ownership.
    """
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")

    if ticket:
        ticket_data = verify_media_ticket(ticket, claim_id)
        user_id = ticket_data.get("sub", "")
        if claim.customer_id != user_id and not (claim.is_demo and user_id == "USR-100001"):
            raise HTTPException(status_code=403, detail="Access denied: Media ticket customer mismatch.")
    else:
        authorized_claim = await get_authorized_claim_or_demo(claim_id, current_user)
        user_id = current_user.get("sub") if current_user else authorized_claim.customer_id

    report = await get_latest_claim_report(claim_id, version=version, claim=claim, current_user=current_user)
    from ..models import ProfessionalClaimDossier
    dossier_obj = ProfessionalClaimDossier(**report["dossier"])
    html_str = render_localized_dossier_html(dossier_obj, lang=lang)
    code = (lang or "en").split("-")[0].lower()
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-cache, no-store, must-revalidate",
    }
    if download:
        headers["Content-Disposition"] = f'attachment; filename="ClaimSathi_Dossier_{claim_id}_{code.upper()}.html"'
    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="REPORT_DOWNLOADED",
        details=f"Downloaded localized ({code}) dossier report for claim {claim_id}",
    )
    return Response(
        content=html_str.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers=headers,
    )


@router.get("/{claim_id}/report/json")
async def download_claim_canonical_json(
    claim_id: str,
    version: Optional[str] = Query(None),
    ticket: Optional[str] = Query(None, description="Ephemeral media ticket"),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """Download Layer 1 — ClaimSathi Canonical Schema JSON. Enforces claim ownership."""
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")

    if ticket:
        ticket_data = verify_media_ticket(ticket, claim_id)
        user_id = ticket_data.get("sub", "")
        if claim.customer_id != user_id and not (claim.is_demo and user_id == "USR-100001"):
            raise HTTPException(status_code=403, detail="Access denied: Media ticket customer mismatch.")
    else:
        authorized_claim = await get_authorized_claim_or_demo(claim_id, current_user)
        user_id = current_user.get("sub") if current_user else authorized_claim.customer_id

    report = await get_latest_claim_report(claim_id, version=version, claim=claim, current_user=current_user)
    canonical_bytes = json.dumps(report["canonical_schema"], indent=2).encode("utf-8")
    filename = f"ClaimSathi_Canonical_{claim_id}_v{report['version']}.json"
    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="REPORT_DOWNLOADED",
        details=f"Downloaded canonical JSON schema for claim {claim_id}",
    )
    return Response(
        content=canonical_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache, no-store, must-revalidate",
        },
    )


@router.post("/{claim_id}/submit-insurer", response_model=InsurerSubmissionResponse)
async def submit_claim_to_mock_insurer(
    claim_id: str,
    request: InsurerSubmissionRequest,
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Phase 7 — Simulated Insurer Integration Gateway (Pages 10–11 of PDF).
    Enforces claim ownership before submission to carrier adapter.
    """
    user_id = current_user.get("sub") if current_user else claim.customer_id
    result = await submit_to_mock_insurer_gateway(
        claim_id=claim_id,
        recipient=request.recipient,
        requesting_user_id=user_id,
    )
    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="INSURER_SUBMISSION",
        details=f"Claim {claim_id} submitted to mock insurer {request.recipient} with ref {result.get('insurer_claim_reference')}",
    )
    return result
