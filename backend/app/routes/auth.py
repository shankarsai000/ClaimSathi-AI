"""
Customer Platform & Claims Vault Routes for ClaimSathi AI (Phase 1 & Phase 6).
Provides:
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/request-otp
- GET  /api/auth/me
- GET  /api/auth/vault
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from ..models import (
    RegisterRequest,
    LoginRequest,
    OTPRequest,
    AuthResponse,
    UserProfile,
    UserConsentInput,
    VaultSummaryResponse,
)
from ..auth import (
    create_access_token,
    verify_password,
    generate_otp,
    verify_otp,
    get_optional_current_user_id,
)
from ..database import (
    create_user_account,
    get_user_by_identifier,
    get_user_profile,
    get_all_claims,
    get_claim_reports,
    get_user_audit_logs,
    log_audit_event,
)

router = APIRouter(prefix="/auth", tags=["Customer Platform & Vault"])


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register_customer(request: RegisterRequest):
    """Register a new customer with a unique Customer ID (USR-XXXXXX) and consent records."""
    existing = await get_user_by_identifier(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    profile = await create_user_account(
        name=request.name,
        email=request.email,
        phone=request.phone,
        password=request.password,
        declared_insurer=request.declared_insurer,
        consents=request.consents,
    )
    token = create_access_token(
        customer_id=profile.customer_id,
        email=profile.email,
        name=profile.name,
    )
    return AuthResponse(access_token=token, user=profile)


@router.post("/request-otp")
async def request_login_otp(request: OTPRequest):
    """Generate a 6-digit OTP for passwordless phone/email verification."""
    otp = generate_otp(request.identifier)
    return {
        "identifier": request.identifier,
        "otp_sent": True,
        "demo_otp_code": otp,
        "message": f"Verification OTP sent (Demo OTP: {otp}).",
    }


@router.post("/login", response_model=AuthResponse)
async def login_customer(request: LoginRequest):
    """
    Authenticate customer by Email, Phone, or Customer ID (e.g. USR-100001).
    Supports Password login, OTP verification, and Quick Demo Login.
    """
    if request.demo_quick_login:
        user_row = await get_user_by_identifier(request.identifier) or await get_user_by_identifier("USR-100001")
    else:
        user_row = await get_user_by_identifier(request.identifier)

    if not user_row:
        raise HTTPException(status_code=401, detail="Customer account not found. Please register or check your ID/email.")

    if not request.demo_quick_login:
        if request.otp_code:
            if not verify_otp(request.identifier, request.otp_code):
                raise HTTPException(status_code=401, detail="Invalid OTP code. Use 123456 for demo verification.")
        elif request.password:
            if not verify_password(request.password, user_row["password_hash"]):
                raise HTTPException(status_code=401, detail="Incorrect password.")
        else:
            raise HTTPException(status_code=400, detail="Please provide either a password or an OTP code.")

    profile = await get_user_profile(user_row["customer_id"])
    await log_audit_event(
        user_id=profile.customer_id,
        action="USER_LOGIN",
        details=f"Customer {profile.name} ({profile.customer_id}) authenticated into ClaimSathi Vault.",
    )
    token = create_access_token(
        customer_id=profile.customer_id,
        email=profile.email,
        name=profile.name,
    )
    return AuthResponse(access_token=token, user=profile)


@router.get("/me", response_model=UserProfile)
async def get_current_customer_profile(user_id: str = Depends(get_optional_current_user_id)):
    """Get profile and consent status for the active customer."""
    profile = await get_user_profile(user_id)
    if not profile:
        profile = await get_user_profile("USR-100001")
    return profile


@router.get("/vault", response_model=VaultSummaryResponse)
async def get_customer_claims_vault(
    customer_id: Optional[str] = Query(None),
    user_id: str = Depends(get_optional_current_user_id),
):
    """
    Customer Claims Vault (Phase 6 — Page 8 of PDF).
    Returns customer profile, all lifetime cases, generated dossier reports, and audit trail.
    """
    target_uid = customer_id or user_id
    profile = await get_user_profile(target_uid)
    if not profile:
        profile = await get_user_profile("USR-100001")
        target_uid = "USR-100001"

    claims = await get_all_claims(customer_id=target_uid)
    recent_reports = []
    for c in claims:
        rpts = await get_claim_reports(c.id)
        for r in rpts:
            recent_reports.append({
                "report_id": r["report_id"],
                "claim_id": r["claim_id"],
                "version": r["version"],
                "generated_at": r["generated_at"],
                "pdf_download_url": r["pdf_download_url"],
                "json_download_url": r["json_download_url"],
            })

    audit_logs = await get_user_audit_logs(target_uid, limit=25)
    return VaultSummaryResponse(
        user=profile,
        total_cases=len(claims),
        claims=claims,
        recent_reports=recent_reports,
        audit_logs=audit_logs,
    )

