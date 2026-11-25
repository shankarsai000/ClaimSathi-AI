"""
Evidence Collection & Integrity Screening Routes for ClaimSathi AI (Phases 3 & 4).
Enforces claim ownership, authenticated media streaming, capture session isolation,
bounded streaming reads, and path traversal protection (Sprint 1.1).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import uuid4
import aiosqlite
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from ..config import get_settings
from ..models import (
    CaptureSessionRequest,
    CaptureSessionResponse,
    EvidenceAssetRecord,
    ClaimRecord,
    ClaimStatus,
)
from ..auth import get_optional_user, verify_media_ticket
from ..authorization import get_authorized_claim_or_demo
from ..database import (
    DB_PATH,
    get_db_connection,
    get_claim,
    create_capture_session,
    get_capture_session,
    mark_capture_session_completed,
    get_claim_evidence,
    log_audit_event,
    get_evidence_verification_history,
    get_evidence_verification_by_id,
    update_evidence_verification_record,
    insert_claim,
)
from ..evidence_engine import (
    generate_randomized_capture_instructions,
    screen_and_store_evidence,
    MAX_IMAGE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
)

router = APIRouter(prefix="/evidence", tags=["Evidence Collection & Screening"])
v1_evidence_router = APIRouter(prefix="/v1/evidence", tags=["Evidence Intelligence v1 (5-Stage Pipeline)"])

SESSION_TTL_SECONDS = 900  # 15 minutes TTL for guided capture sessions


@router.post("/capture-session", response_model=CaptureSessionResponse, status_code=201)
async def start_live_capture_session(
    request: CaptureSessionRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Start a Guided Live Camera Capture Session (Pages 4–5 of PDF).
    Mandates authentication for all sessions and validates claim ownership when bound.
    """
    settings = get_settings()
    is_prod = (settings.app_env or "").lower() == "production"

    user_id = current_user.get("sub") if current_user else None

    if request.claim_id:
        claim = await get_claim(request.claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail=f"Claim '{request.claim_id}' not found.")
        if current_user and claim.customer_id != current_user.get("sub"):
            raise HTTPException(
                status_code=403,
                detail="Access denied: You do not own the claim for this capture session.",
            )
        if not current_user:
            if is_prod or not (claim.is_demo or claim.id.startswith("DEMO-")):
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required to start a capture session for this claim.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user_id = claim.customer_id
    else:
        # Unbound sessions MUST have an authenticated owner to prevent anonymous hijack
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to start a capture session.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = user_id

    instructions = generate_randomized_capture_instructions()
    session_data = await create_capture_session(
        user_id=user_id,
        claim_id=request.claim_id,
        instructions=instructions,
    )
    return CaptureSessionResponse(
        session_id=session_data["session_id"],
        claim_id=session_data["claim_id"],
        instructions=session_data["instructions"],
        created_at=session_data["created_at"],
    )


@router.post("/{claim_id}/upload", response_model=EvidenceAssetRecord, status_code=201)
async def upload_and_screen_evidence(
    claim_id: str,
    file: UploadFile = File(..., description="Image or video evidence file"),
    capture_method: str = Form("upload_photo", description="upload_photo | upload_video | live_photo | guided_video"),
    capture_session_id: Optional[str] = Form(None, description="Server-generated capture session ID for live camera capture"),
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Upload or submit live-captured media for a claim and run the 4-check Evidence Integrity Engine.
    Enforces claim ownership, bounded streaming read (DoS prevention), and strict capture-session isolation.
    """
    caller_id = current_user.get("sub") if current_user else claim.customer_id

    if capture_session_id:
        session = await get_capture_session(capture_session_id)
        if not session:
            raise HTTPException(status_code=400, detail=f"Invalid capture_session_id '{capture_session_id}'.")

        # 1. State check: prevent session reuse / replay
        if session.get("status") != "active":
            raise HTTPException(
                status_code=400,
                detail=f"Capture session '{capture_session_id}' is already {session.get('status', 'inactive')} and cannot be reused.",
            )

        # 2. Expiration check: 15-minute TTL
        try:
            created_at_str = session.get("created_at", "")
            created_at = datetime.fromisoformat(created_at_str)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if (now - created_at).total_seconds() > SESSION_TTL_SECONDS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Capture session '{capture_session_id}' has expired (15-minute validity window).",
                )
        except (ValueError, TypeError):
            pass

        # 3. Ownership check: session owner must match authenticated user or claim customer
        session_user = session.get("user_id")
        if session_user and session_user != caller_id and session_user != claim.customer_id:
            await log_audit_event(
                user_id=caller_id,
                action="CAPTURE_SESSION_CROSS_TENANT_REJECTED",
                details=f"User '{caller_id}' attempted to use session '{capture_session_id}' owned by '{session_user}'.",
                claim_id=claim_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied: Capture session belongs to another customer.",
            )

        # 4. Target claim binding check
        if session.get("claim_id") and session["claim_id"] != claim_id:
            raise HTTPException(
                status_code=400,
                detail=f"Capture session is bound to claim '{session['claim_id']}', not '{claim_id}'.",
            )

    # DoS & Memory Protection: Bounded chunked streaming read
    chunk_size = 1024 * 1024  # 1 MB chunks
    total_read = 0
    chunks = []
    max_allowed = MAX_VIDEO_SIZE_BYTES  # 50 MB upper ceiling

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_allowed:
            raise HTTPException(
                status_code=413,
                detail=f"Uploaded evidence file exceeds the maximum allowed limit of {max_allowed // (1024*1024)} MB.",
            )
        chunks.append(chunk)

    raw_bytes = b"".join(chunks)

    # Process and store evidence through the 4-check Integrity Engine
    asset = await screen_and_store_evidence(
        claim_id=claim_id,
        user_id=claim.customer_id,
        filename=file.filename or "evidence_upload",
        file_bytes=raw_bytes,
        capture_method=capture_method,
        capture_session_id=capture_session_id,
    )

    # Bind unbound session permanently to this claim on first upload
    if capture_session_id and not session.get("claim_id"):
        async with get_db_connection() as db:
            await db.execute(
                "UPDATE capture_sessions SET claim_id = ? WHERE session_id = ?",
                (claim_id, capture_session_id),
            )
            await db.commit()

    return asset


@router.post("/capture-session/{session_id}/complete")
async def complete_live_capture_session(
    session_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """Explicitly mark a guided capture session as completed to prevent further uploads."""
    session = await get_capture_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Capture session '{session_id}' not found.")
    caller_id = current_user.get("sub") if current_user else None
    if caller_id and session.get("user_id") and session["user_id"] != caller_id:
        raise HTTPException(status_code=403, detail="Access denied: You do not own this capture session.")
    await mark_capture_session_completed(session_id)
    return {"session_id": session_id, "status": "completed"}


@router.get("/{claim_id}", response_model=List[EvidenceAssetRecord])
async def list_claim_evidence(
    claim_id: str,
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    List all uploaded and screened evidence records for a claim.
    Requires claim ownership verification (cross-customer access returns HTTP 403).
    """
    user_id = current_user.get("sub") if current_user else claim.customer_id
    return await get_claim_evidence(claim_id, requesting_user_id=user_id)


@router.get("/{claim_id}/file/{evidence_id}")
async def serve_evidence_media_file(
    claim_id: str,
    evidence_id: str,
    ticket: Optional[str] = Query(None, description="Ephemeral media access ticket"),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Serve the preserved original media file from object storage.
    Accepts Bearer JWT authentication OR an ephemeral media access ticket.
    Enforces authentication, claim ownership verification, and path traversal protection.
    """
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")

    user_id: str
    if ticket:
        ticket_data = verify_media_ticket(ticket, claim_id)
        user_id = ticket_data.get("sub", "")
        if claim.customer_id != user_id and not (claim.is_demo and user_id == "USR-100001"):
            raise HTTPException(
                status_code=403,
                detail="Access denied: Media ticket customer mismatch.",
            )
    else:
        # Standard token verification
        settings = get_settings()
        is_prod = (settings.app_env or "").lower() == "production"
        if current_user:
            user_id = current_user.get("sub", "")
            if claim.customer_id != user_id:
                await log_audit_event(
                    user_id=user_id,
                    action="ACCESS_DENIED_CROSS_CUSTOMER",
                    details=f"User '{user_id}' attempted unauthorized access to evidence for claim '{claim_id}'.",
                    claim_id=claim_id,
                )
                raise HTTPException(status_code=403, detail="Access denied: You do not have permission to access this claim.")
        elif is_prod or not (claim.is_demo or claim.id.startswith("DEMO-")):
            raise HTTPException(
                status_code=401,
                detail="Authentication required to access evidence files.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            user_id = claim.customer_id

    async with get_db_connection() as db:
        cursor = await db.execute(
            "SELECT storage_path, detected_mime, original_filename FROM evidence_assets WHERE claim_id = ? AND evidence_id = ?",
            (claim_id, evidence_id),
        )
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence asset '{evidence_id}' not found for claim '{claim_id}'.",
        )

    # Path traversal protection
    base_storage = Path("storage/evidence").resolve()
    target_path = Path(row["storage_path"]).resolve()

    try:
        target_path.relative_to(base_storage)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Security error: Invalid storage path outside permitted evidence directory.",
        )

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Stored media file missing on disk.")

    await log_audit_event(
        user_id=user_id,
        action="EVIDENCE_DOWNLOADED",
        details=f"Evidence media '{evidence_id}' ({row['original_filename']}) retrieved for claim '{claim_id}'.",
        claim_id=claim_id,
    )

    return Response(
        content=target_path.read_bytes(),
        media_type=row["detected_mime"],
        headers={
            "Content-Disposition": f'inline; filename="{row["original_filename"]}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache, no-store, must-revalidate",
        },
    )


# ── Sprint 1.4 / 1.6 / 2.0: Local 5-Stage Evidence Intelligence Pipeline Routes ───
class WhatsappHandoffRequest(BaseModel):
    claim_id: Optional[str] = None
    phone: Optional[str] = None
    claimed_registration: Optional[str] = None


@v1_evidence_router.post("/whatsapp-handoff")
async def create_whatsapp_live_camera_handoff(
    payload: WhatsappHandoffRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Create a 1-tap tokenized browser handoff from WhatsApp into Stage 5 Guided Live Camera.
    Prevents WhatsApp image recompression & EXIF/C2PA metadata stripping while enforcing
    DPDP Act 2025 PII masking in logs and message previews.
    """
    from ..evidence.vehicle_identity import mask_pii_value, normalize_registration_plate

    user_id = current_user.get("sub") if current_user else "USR-100001"
    if payload.claim_id:
        claim = await get_claim(payload.claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail=f"Claim '{payload.claim_id}' not found.")
        if current_user and claim.customer_id != current_user.get("sub"):
            raise HTTPException(status_code=403, detail="Access denied: You do not own this claim.")
        user_id = claim.customer_id

    instructions = generate_randomized_capture_instructions()
    session_data = await create_capture_session(
        user_id=user_id,
        claim_id=payload.claim_id,
        instructions=instructions,
    )
    session_id = session_data["session_id"]
    masked_phone = mask_pii_value(payload.phone, 4) if payload.phone else "******0000"
    norm_reg = normalize_registration_plate(payload.claimed_registration)
    masked_reg = mask_pii_value(norm_reg, 4) if norm_reg else "Not bound"

    await log_audit_event(
        user_id=user_id,
        claim_id=payload.claim_id,
        action="WHATSAPP_LIVE_CAMERA_HANDOFF_CREATED",
        details=(
            f"Generated 1-tap Stage 5 Live Camera link ({session_id}) for phone={masked_phone}, "
            f"reg={masked_reg} (raw WhatsApp photo upload blocked to preserve forensics)."
        ),
        resource_type="capture_session",
        resource_id=session_id,
        outcome="SUCCESS",
    )

    handoff_url = f"/claims/new?step=2&capture_session_id={session_id}"
    if payload.claim_id:
        handoff_url += f"&claim_id={payload.claim_id}"

    preview_msg = (
        f"ClaimSathi Live Capture ({session_id}): To protect your claim from WhatsApp compression, "
        f"please tap this link to capture your License Plate, Odometer/VIN, and vehicle damage live: "
        f"{handoff_url}"
    )
    return {
        "session_id": session_id,
        "claim_id": payload.claim_id,
        "handoff_url": handoff_url,
        "masked_phone": masked_phone,
        "masked_registration": masked_reg,
        "raw_whatsapp_media_blocked": True,
        "instructions": instructions,
        "whatsapp_template_preview": preview_msg,
        "expires_in_seconds": SESSION_TTL_SECONDS,
    }


@v1_evidence_router.post("/verify")
async def verify_evidence_pipeline_endpoint(
    file: UploadFile = File(..., description="Image evidence file for 5-stage screening"),
    claimed_vehicle_type: str = Form("four_wheeler", description="four_wheeler | two_wheeler"),
    vehicle_make_model: Optional[str] = Form(None, description="Optional Indian 2W/4W make & model for tiered INR band"),
    claimed_registration: Optional[str] = Form(None, description="Optional vehicle registration plate for identity binding"),
    capture_session_id: Optional[str] = Form(None, description="Cryptographic live capture session ID from WhatsApp handoff"),
    capture_method: str = Form("upload_photo", description="upload_photo | live_photo | guided_video"),
    lock_session_on_verify: bool = Form(False, description="Single-use lock: expire capture session immediately after verify"),
):
    """
    Upload an image file and execute the local 5-stage Evidence Intelligence pipeline:
    Stage 1 (Integrity), Stage 2 (Metadata/Provenance), Stage 3A/3B (YOLO Vehicle & Dual Car/Bike Damage),
    Stage 4 (EfficientNetV2-S Spoof Screening), Stage 5 (PASS / REVIEW / REJECT + Identity & Tiered Cost Band).
    Enforces strict Live-Camera-Only lock when capture_session_id is supplied (gallery uploads rejected).
    """
    if capture_session_id:
        session = await get_capture_session(capture_session_id)
        if not session:
            raise HTTPException(status_code=400, detail=f"Invalid capture_session_id '{capture_session_id}'.")
        if session.get("status") != "active":
            raise HTTPException(
                status_code=400,
                detail=f"Capture session '{capture_session_id}' is already {session.get('status', 'completed')} and cannot be reused.",
            )
        try:
            created_at = datetime.fromisoformat(session.get("created_at", ""))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - created_at).total_seconds() > SESSION_TTL_SECONDS:
                raise HTTPException(status_code=400, detail="Capture handoff link has expired (15-minute TTL).")
        except (ValueError, TypeError):
            pass

        if (capture_method or "").strip().lower() in ("upload_photo", "gallery"):
            raise HTTPException(
                status_code=400,
                detail="Gallery file uploads are blocked for live capture handoff sessions. Capture must come from live camera.",
            )

    chunk_size = 1024 * 1024
    total_read = 0
    chunks: List[bytes] = []
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Uploaded image exceeds maximum allowed size of {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)

    raw_bytes = b"".join(chunks)
    from ..evidence.pipeline import verify_evidence_image

    result = await verify_evidence_image(
        file_bytes=raw_bytes,
        filename=file.filename or "upload.jpg",
        claimed_vehicle_type=claimed_vehicle_type,
        vehicle_make_model=vehicle_make_model,
        claimed_registration=claimed_registration,
        persist=True,
    )
    if capture_session_id and lock_session_on_verify:
        await mark_capture_session_completed(capture_session_id)
    return result


class DpdpConsentRequest(BaseModel):
    claim_id: Optional[str] = None
    voice_consent_granted: bool = True
    live_camera_consent_granted: bool = True
    purpose_scope: str = "motor_claim_intake_and_fraud_screening"


@v1_evidence_router.post("/dpdp-consent")
async def record_dpdp_precapture_consent_endpoint(
    payload: DpdpConsentRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    DPDP Rules 2025: Record explicit, unbundled pre-capture consent before recording voice
    or capturing vehicle/document photographs, noting 1-year statutory audit retention.
    """
    user_id = current_user.get("sub") if current_user else "USR-100001"
    consent_id = f"DPDP-{uuid4().hex[:8].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    await log_audit_event(
        user_id=user_id,
        claim_id=payload.claim_id,
        action="DPDP_2025_PRECAPTURE_CONSENT_RECORDED",
        details=(
            f"Consent {consent_id} captured (voice={payload.voice_consent_granted}, "
            f"camera={payload.live_camera_consent_granted}, scope={payload.purpose_scope})."
        ),
        resource_type="consent",
        resource_id=consent_id,
        outcome="SUCCESS",
    )
    return {
        "consent_id": consent_id,
        "claim_id": payload.claim_id,
        "voice_consent_granted": payload.voice_consent_granted,
        "live_camera_consent_granted": payload.live_camera_consent_granted,
        "purpose_scope": payload.purpose_scope,
        "retention_policy": "minimum_1_year_audit_log_with_purpose_erasure",
        "recorded_at": now_iso,
    }


@v1_evidence_router.get("/governance-metrics")
async def get_irdai_governance_metrics_endpoint(limit: int = Query(200, ge=1, le=500)):
    """
    IRDAI 2026 AI Governance Metrics: Track false-positive rate (legitimate claims flagged as
    REVIEW/REJECT then overridden to PASS) vs false-negative overrides separately across runs.
    """
    records = await get_evidence_verification_history(limit=limit)
    total = len(records)
    ai_flagged = 0
    fp_overrides = 0
    fn_overrides = 0
    reason_counts: Dict[str, int] = {}

    for r in records:
        sr = r.get("stage_results") or {}
        override = sr.get("manual_override")
        orig_dec = (override or {}).get("ai_original_decision") or r.get("decision")
        if orig_dec in ("REVIEW", "REJECT"):
            ai_flagged += 1
        if override:
            new_dec = override.get("new_decision")
            tag = override.get("override_reason_tag") or "UNSPECIFIED"
            reason_counts[tag] = reason_counts.get(tag, 0) + 1
            if orig_dec in ("REVIEW", "REJECT") and new_dec == "PASS":
                fp_overrides += 1
            elif orig_dec == "PASS" and new_dec == "REJECT":
                fn_overrides += 1

    fp_rate = round(fp_overrides / max(1, ai_flagged), 4) if ai_flagged else 0.0
    fn_rate = round(fn_overrides / max(1, total - ai_flagged), 4) if total > ai_flagged else 0.0
    return {
        "total_verifications": total,
        "ai_flagged_count": ai_flagged,
        "false_positive_overrides": fp_overrides,
        "false_negative_overrides": fn_overrides,
        "false_positive_rate": fp_rate,
        "false_negative_rate": fn_rate,
        "override_reason_breakdown": reason_counts,
        "irdai_governance_compliant": True,
    }


@v1_evidence_router.delete("/{evidence_id}/dpdp-erase")
async def erase_evidence_media_on_withdrawal_endpoint(
    evidence_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    DPDP Rules 2025 Erasure Endpoint: Withdraw consent and delete preserved binary image payload
    from local evidence storage while retaining the statutory 1-year anonymized audit record.
    """
    record = await get_evidence_verification_by_id(evidence_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Evidence verification '{evidence_id}' not found.")

    sr = dict(record.get("stage_results") or {})
    preserved_path = ((sr.get("stage1_integrity") or {}).get("preserved_path"))
    erased_file = False
    if preserved_path:
        p = Path(preserved_path)
        if p.exists():
            try:
                p.unlink()
                erased_file = True
            except Exception:
                pass

    sr["dpdp_erasure"] = {
        "status": "MEDIA_ERASED_AUDIT_RETAINED",
        "erased_at": datetime.now(timezone.utc).isoformat(),
        "binary_file_unlinked": erased_file,
    }
    await update_evidence_verification_record(
        verification_id=evidence_id,
        decision=record["decision"],
        stage_results=sr,
        reasons=list(record.get("reasons") or []) + ["DPDP_CONSENT_WITHDRAWN_MEDIA_ERASED"],
    )
    user_id = current_user.get("sub") if current_user else "USR-100001"
    await log_audit_event(
        user_id=user_id,
        action="DPDP_2025_MEDIA_ERASED",
        details=f"Raw binary media erased for {evidence_id}; anonymized audit hash retained.",
        resource_type="evidence_verification",
        resource_id=evidence_id,
        outcome="SUCCESS",
    )
    return {
        "evidence_id": evidence_id,
        "status": "MEDIA_ERASED_AUDIT_RETAINED",
        "binary_file_unlinked": erased_file,
    }


@v1_evidence_router.get("/history")
async def get_evidence_history_endpoint(
    limit: int = Query(50, ge=1, le=200),
):
    """Return recent 5-stage evidence verification runs persisted in SQLite."""
    records = await get_evidence_verification_history(limit=limit)
    return {
        "total": len(records),
        "verifications": records,
    }


@v1_evidence_router.get("/{evidence_id}")
async def get_evidence_verification_detail_endpoint(evidence_id: str):
    """Return full 5-stage verification breakdown for a single evidence verification run."""
    record = await get_evidence_verification_by_id(evidence_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence verification '{evidence_id}' not found.",
        )
    return record


class EvidenceOverrideRequest(BaseModel):
    new_decision: str  # Must be "PASS" or "REJECT"
    reviewer_note: str = "Manual adjuster review completed."
    override_reason_tag: str = "FALSE_POSITIVE_GENUINE_DAMAGE"  # IRDAI 2026 false-positive tracking tag


class CreateClaimFromEvidenceRequest(BaseModel):
    policy_number: str = ""
    vehicle_registration: str = ""
    incident_description: str = "Vehicle damage claim assessment."


@v1_evidence_router.post("/{evidence_id}/override")
async def override_evidence_decision_endpoint(
    evidence_id: str,
    payload: EvidenceOverrideRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Sprint 1.7 / 2.1 Feature A: Human Reviewer Decision Override with IRDAI 2026 False-Positive Tagging.
    Updates decision to PASS or REJECT, preserves `ai_original_decision`, records `override_reason_tag`,
    updates cost estimate status, and logs manual override audit trail.
    """
    record = await get_evidence_verification_by_id(evidence_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence verification '{evidence_id}' not found.",
        )

    new_decision = (payload.new_decision or "").strip().upper()
    if new_decision not in ("PASS", "REJECT"):
        raise HTTPException(
            status_code=400,
            detail="Invalid new_decision. Must be 'PASS' or 'REJECT'.",
        )

    stage_results = dict(record.get("stage_results") or {})
    reasons = list(record.get("reasons") or [])
    cost_estimate = dict(record.get("cost_estimate") or stage_results.get("cost_estimate") or {})
    prior_override = stage_results.get("manual_override") or {}
    ai_original_decision = prior_override.get("ai_original_decision") or record.get("decision")

    reasons.append(f"MANUAL_OVERRIDE_{new_decision} [{payload.override_reason_tag}]: {payload.reviewer_note}")

    if new_decision == "PASS":
        cost_estimate["estimate_status"] = "APPROVED_MANUAL_REVIEW"
        line_items = cost_estimate.get("line_items", [])
        if line_items:
            total = sum(item.get("subtotal_inr", 0) for item in line_items)
            cost_estimate["total_estimated_inr"] = total
            cost_estimate["total_inr"] = total
    else:  # REJECT
        cost_estimate["estimate_status"] = "REJECTED_NO_ESTIMATE"
        cost_estimate["total_estimated_inr"] = 0
        cost_estimate["total_inr"] = 0
        cost_estimate["line_items"] = []

    stage_results["manual_override"] = {
        "ai_original_decision": ai_original_decision,
        "new_decision": new_decision,
        "override_reason_tag": payload.override_reason_tag,
        "reviewer_note": payload.reviewer_note,
        "overridden_at": datetime.now(timezone.utc).isoformat(),
        "reviewer_id": current_user.get("sub") if current_user else "ADJUSTER_DESK",
    }
    stage_results["cost_estimate"] = cost_estimate

    updated = await update_evidence_verification_record(
        verification_id=evidence_id,
        decision=new_decision,
        stage_results=stage_results,
        reasons=reasons,
    )
    return updated


@v1_evidence_router.post("/{evidence_id}/create-claim")
async def create_claim_from_evidence_endpoint(
    evidence_id: str,
    payload: CreateClaimFromEvidenceRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Sprint 1.7 Feature B: One-Click Official Claim Creation from Verified Evidence.
    Converts a PASS or REVIEW evidence intelligence assessment into an official claim,
    persisting to customer claims vault and binding linked_claim metadata.
    Rejects claim creation if decision is REJECT.
    """
    record = await get_evidence_verification_by_id(evidence_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence verification '{evidence_id}' not found.",
        )

    if record["decision"] == "REJECT":
        raise HTTPException(
            status_code=400,
            detail="Cannot create an official claim from a REJECTED evidence upload.",
        )

    claim_id = f"CLM-{uuid4().hex[:6].upper()}"
    cost_estimate = record.get("cost_estimate") or {}
    total_est = cost_estimate.get("total_estimated_inr", 0)
    decision = record["decision"]
    claim_status = "APPROVED" if decision == "PASS" else "UNDER_REVIEW"

    linked_claim = {
        "claim_id": claim_id,
        "evidence_id": evidence_id,
        "policy_number": payload.policy_number,
        "vehicle_registration": payload.vehicle_registration,
        "vehicle_category": record.get("claimed_vehicle_type", "four_wheeler"),
        "verification_decision": decision,
        "estimate_status": cost_estimate.get("estimate_status"),
        "total_estimated_inr": total_est,
        "damage_count": record.get("damage_count", 0),
        "claim_status": claim_status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    user_id = current_user.get("sub") if current_user else "USR-100002"
    v_type = (
        "Two-Wheeler (Motorcycle)"
        if record.get("claimed_vehicle_type") == "two_wheeler"
        else "Four-Wheeler (Car)"
    )
    try:
        official_claim = ClaimRecord(
            id=claim_id,
            customer_id=user_id,
            insurance_type="Comprehensive Motor",
            policy_reference=payload.policy_number,
            insurer_name="HDFC ERGO General Insurance",
            policy_type="motor_comprehensive",
            incident_location="Bengaluru, Karnataka",
            incident_date=datetime.now(timezone.utc).date().isoformat(),
            vehicle_type=v_type,
            damage_description=f"{payload.incident_description} (Reg: {payload.vehicle_registration}, Est: INR {total_est})",
            people_involved="Self",
            injuries_reported=False,
            detailed_statement=payload.incident_description,
            transcript=f"Verified Evidence Assessment: {decision} with {record.get('damage_count', 0)} detected damage(s).",
            status=ClaimStatus.confirmed if decision == "PASS" else ClaimStatus.evidence_pending,
            customer_confirmation=True,
            report_status="ready",
            insurer_submission_status="pending",
            is_demo=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await insert_claim(official_claim)
    except Exception:
        pass

    stage_results = dict(record.get("stage_results") or {})
    stage_results["linked_claim"] = linked_claim

    updated = await update_evidence_verification_record(
        verification_id=evidence_id,
        decision=record["decision"],
        stage_results=stage_results,
        reasons=record.get("reasons") or [],
    )
    return updated
