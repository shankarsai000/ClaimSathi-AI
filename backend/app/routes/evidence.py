"""
Evidence Collection & Integrity Screening Routes for ClaimSathi AI (Phases 3 & 4).
Enforces claim ownership, authenticated media streaming, and path traversal protection (Sprint 1).
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from ..config import get_settings
from ..models import (
    CaptureSessionRequest,
    CaptureSessionResponse,
    EvidenceAssetRecord,
    ClaimRecord,
)
from ..auth import get_optional_user
from ..authorization import get_authorized_claim_or_demo, get_authorized_claim
from ..database import (
    DB_PATH,
    get_claim,
    create_capture_session,
    get_capture_session,
    get_claim_evidence,
    log_audit_event,
)
from ..evidence_engine import (
    generate_randomized_capture_instructions,
    screen_and_store_evidence,
    MAX_IMAGE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
)

router = APIRouter(prefix="/evidence", tags=["Evidence Collection & Screening"])


@router.post("/capture-session", response_model=CaptureSessionResponse, status_code=201)
async def start_live_capture_session(
    request: CaptureSessionRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Start a Guided Live Camera Capture Session (Pages 4–5 of PDF).
    Verifies that the caller owns the claim before issuing a capture session.
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
        if not current_user and is_prod:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to start a capture session.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = user_id or "USR-100001"

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
    Strictly enforces claim ownership before accepting uploads.
    """
    if capture_session_id:
        session = await get_capture_session(capture_session_id)
        if not session:
            raise HTTPException(status_code=400, detail=f"Invalid capture_session_id '{capture_session_id}'.")
        if session.get("claim_id") and session["claim_id"] != claim_id:
            raise HTTPException(status_code=400, detail="Capture session does not match target claim ID.")

    raw_bytes = await file.read()
    file_size = len(raw_bytes)

    # File size limits check
    if file_size > MAX_VIDEO_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded evidence file exceeds the maximum allowed limit of {MAX_VIDEO_SIZE_BYTES // (1024*1024)} MB.",
        )

    asset = await screen_and_store_evidence(
        claim_id=claim_id,
        user_id=claim.customer_id,
        filename=file.filename or "evidence_upload",
        file_bytes=raw_bytes,
        capture_method=capture_method,
        capture_session_id=capture_session_id,
    )
    return asset


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
    claim: ClaimRecord = Depends(get_authorized_claim_or_demo),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    Serve the preserved original media file from object storage.
    Enforces authentication, claim ownership verification, and path traversal protection.
    """
    user_id = current_user.get("sub") if current_user else claim.customer_id

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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

    # Ensure target_path is within base_storage
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
