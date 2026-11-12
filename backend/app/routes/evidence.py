"""
Evidence Collection & Integrity Screening Routes for ClaimSathi AI (Phases 3 & 4).
Enforces claim ownership, authenticated media streaming, capture session isolation,
bounded streaming reads, and path traversal protection (Sprint 1.1).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
import aiosqlite
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile

from ..config import get_settings
from ..models import (
    CaptureSessionRequest,
    CaptureSessionResponse,
    EvidenceAssetRecord,
    ClaimRecord,
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
)
from ..evidence_engine import (
    generate_randomized_capture_instructions,
    screen_and_store_evidence,
    MAX_IMAGE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
)

router = APIRouter(prefix="/evidence", tags=["Evidence Collection & Screening"])

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
