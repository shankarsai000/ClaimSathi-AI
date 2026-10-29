from fastapi import APIRouter
from ..models import HealthResponse
from ..config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    settings = get_settings()
    has_key = bool(settings.gnani_api_key_id and settings.gnani_api_key_id.strip())
    return HealthResponse(
        status="healthy",
        version="0.2.0-phase2",
        environment=settings.app_env,
        gnani_configured=has_key,
        gnani_stt_model=settings.gnani_stt_model,
        gnani_tts_model=settings.gnani_tts_model,
        is_demo=True,
    )
