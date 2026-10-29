from fastapi import APIRouter, HTTPException
from datetime import datetime
from ..models import (
    ClaimCreateRequest,
    ClaimCreateResponse,
    ClaimDetailResponse,
    ClaimListResponse,
    ClaimRecord,
    ClaimStatus,
    TimelineEvent,
    TranscriptRequest,
    TranscriptResponse,
)
from ..database import insert_claim, get_claim, get_all_claims, get_timeline, get_claim_count
from ..providers.transcription import MockTranscriptionProvider

router = APIRouter(prefix="/claims", tags=["Claims"])
transcription = MockTranscriptionProvider()


@router.post("/transcribe", response_model=TranscriptResponse)
async def transcribe_audio(request: TranscriptRequest):
    """
    Simulate voice transcription and field extraction.
    Labelled as MOCK – no real audio is processed in Phase 1.
    """
    scenario = transcription.get_mock_scenario()
    fields, missing = transcription.extract_fields(scenario)
    return TranscriptResponse(
        transcript=scenario["transcript"],
        language=request.language,
        is_mock=True,
        fields=fields,
        missing_fields=missing,
    )


@router.post("/", response_model=ClaimCreateResponse, status_code=201)
async def create_claim(request: ClaimCreateRequest):
    """
    Create a demo claim ticket from confirmed fields.
    The ticket ID is prefixed with DEMO- to make its nature explicit.
    """
    now = datetime.utcnow()
    record = ClaimRecord(
        policy_reference=request.policy_reference,
        incident_location=request.incident_location,
        incident_date=request.incident_date,
        vehicle_type=request.vehicle_type,
        damage_description=request.damage_description,
        transcript=request.transcript,
        status=ClaimStatus.CONFIRMED,
        is_demo=True,
        created_at=now,
        updated_at=now,
    )
    await insert_claim(record)
    return ClaimCreateResponse(
        id=record.id,
        status=record.status,
        message=f"Demo claim {record.id} created successfully. This is a simulated claim – no real insurance claim has been filed.",
        is_demo=True,
    )


@router.get("/", response_model=ClaimListResponse)
async def list_claims():
    """List all demo claims."""
    claims = await get_all_claims()
    return ClaimListResponse(
        claims=claims,
        total=len(claims),
        is_demo=True,
    )


@router.get("/stats")
async def claim_stats():
    """Dashboard statistics."""
    claims = await get_all_claims()
    total = len(claims)
    return {
        "total_claims": total,
        "recent_claims": [c.model_dump() for c in claims[:5]],
        "is_demo": True,
    }


@router.get("/{claim_id}", response_model=ClaimDetailResponse)
async def get_claim_detail(claim_id: str):
    """Retrieve a specific demo claim with timeline."""
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
    return ClaimDetailResponse(claim=claim, timeline=timeline, is_demo=True)
