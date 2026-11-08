"""
Evidence Collection & Integrity Screening Routes for ClaimSathi AI (Phases 3 & 4).
Provides:
- POST /api/evidence/capture-session
- POST /api/evidence/{claim_id}/upload
- GET  /api/evidence/{claim_id}
- GET  /api/evidence/{claim_id}/file/{evidence_id}
"""

from pathlib import Path
from typing import Optional, List
import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from ..models import (
    CaptureSessionRequest,
    CaptureSessionResponse,
    EvidenceAssetRecord,
)
from ..auth import get_optional_current_user_id
from ..database import (
    DB_PATH,
    get_claim,
    create_capture_session,
    get_capture_session,
    get_claim_evidence,
)
from ..evidence_engine import (
    generate_randomized_capture_instructions,
    screen_and_store_evidence,
)

router = APIRouter(prefix="/evidence", tags=["Evidence Collection & Screening"])


@router.post("/capture-session", response_model=CaptureSessionResponse, status_code=201)
async def start_live_capture_session(
    request: CaptureSessionRequest,
    user_id: str = Depends(get_optional_current_user_id),
):
    """
    Start a Guided Live Camera Capture Session (Page 4–5 of PDF).
    Generates a server-side capture session ID and randomized vehicle angle instructions.
    """
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
    user_id: str = Depends(get_optional_current_user_id),
):
    """
    Upload or submit live-captured media for a claim and run the 4-check Evidence Integrity Engine:
    - Magic-byte file signature & malware verification
    - SHA-256 exact duplicate detection across all claims
    - 64-bit 2D-DCT Perceptual Hash (pHash) visual similarity detection across all claims
    - C2PA Content Credentials, SynthID watermark & EXIF metadata screening
    """
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")

    if capture_session_id:
        session = await get_capture_session(capture_session_id)
        if not session:
            raise HTTPException(status_code=400, detail=f"Invalid capture_session_id '{capture_session_id}'.")

    raw_bytes = await file.read()
    asset = await screen_and_store_evidence(
        claim_id=claim_id,
        user_id=claim.customer_id or user_id,
        filename=file.filename or "evidence_upload",
        file_bytes=raw_bytes,
        capture_method=capture_method,
        capture_session_id=capture_session_id,
    )
    return asset


@router.get("/{claim_id}", response_model=List[EvidenceAssetRecord])
async def list_claim_evidence(
    claim_id: str,
    user_id: str = Depends(get_optional_current_user_id),
):
    """List all uploaded and screened evidence records for a claim."""
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")
    return await get_claim_evidence(claim_id, requesting_user_id=user_id)


@router.get("/{claim_id}/file/{evidence_id}")
async def serve_evidence_media_file(claim_id: str, evidence_id: str):
    """Serve the preserved original media file from object storage."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT storage_path, detected_mime, original_filename FROM evidence_assets WHERE claim_id = ? AND evidence_id = ?",
            (claim_id, evidence_id),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Evidence file not found.")
        path = Path(row["storage_path"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="Stored media file missing on disk.")
        return Response(
            content=path.read_bytes(),
            media_type=row["detected_mime"],
            headers={"Content-Disposition": f'inline; filename="{row["original_filename"]}"'},
        )

