"""
ClaimSathi AI – Intelligent Insurance Claims Assistance & Evidence Integrity Platform
Complete 7-Phase API Architecture:
1. Customer Platform & Claims Vault (/api/auth)
2. Claim Intelligence Engine (/api/voice, /api/claims)
3. Evidence Integrity Engine (/api/evidence)
4. Claim Documentation Engine & Mock Insurer Gateway (/api/claims/{id}/report, /api/claims/{id}/submit-insurer)
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .database import init_db
from .routes import health, claims, voice, auth, evidence


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_production_configuration()
    await init_db()
    yield


app = FastAPI(
    title="ClaimSathi AI – Intelligent Insurance Claims & Evidence Integrity Platform",
    description=(
        "Multilingual, voice-first insurance claims platform with C2PA/SynthID provenance screening, "
        "SHA-256 & 64-bit DCT perceptual hash duplicate detection, 9-section Dossier PDF/JSON generation, "
        "Customer Claims Vault, and Mock Insurer Integration Gateway."
    ),
    version="1.0.0-mvp",
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
app.include_router(auth.router, prefix="/api")
app.include_router(claims.router, prefix="/api")
app.include_router(voice.router, prefix="/api")
app.include_router(evidence.router, prefix="/api")
