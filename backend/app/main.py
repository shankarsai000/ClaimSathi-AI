"""
ClaimSathi AI – FastAPI Application (Phase 2)
Voice-first motor insurance claim intake with Gnani AI Speech APIs.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .database import init_db
from .routes import health, claims, voice


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="ClaimSathi AI – API [Phase 2]",
    description=(
        "Phase 2 API for voice-first insurance claim intake powered by "
        "Gnani Prisma ASR and Gnani Timbre TTS."
    ),
    version="0.2.0-phase2",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(claims.router, prefix="/api")
app.include_router(voice.router, prefix="/api")
