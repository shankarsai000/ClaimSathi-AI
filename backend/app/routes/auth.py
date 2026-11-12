"""
Customer Platform & Claims Vault Routes for ClaimSathi AI (Phase 1 & Phase 6).
Enforces strict authentication, rate-limiting, secure OTP and customer vault isolation (Sprint 1).
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..config import get_settings
from ..models import (
    RegisterRequest,
    LoginRequest,
    OTPRequest,
    AuthResponse,
    UserProfile,
    VaultSummaryResponse,
)
from ..auth import (
    create_access_token,
    verify_password,
    generate_otp,
    verify_otp,
    get_current_user,
    check_login_rate_limit,
    record_login_failure,
    reset_login_attempts,
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

    if len((request.password or "").strip()) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters long.")

    profile = await create_user_account(
        name=request.name.strip(),
        email=request.email.strip().lower(),
        phone=request.phone.strip(),
        password=request.password,
        declared_insurer=request.declared_insurer,
        consents=request.consents,
    )
    token = create_access_token(
        customer_id=profile.customer_id,
        email=profile.email,
        name=profile.name,
    )
    await log_audit_event(
        user_id=profile.customer_id,
        action="USER_REGISTERED",
        details=f"New customer registered: {profile.name} ({profile.customer_id})",
    )
    return AuthResponse(access_token=token, user=profile)


@router.post("/request-otp")
async def request_login_otp(request: OTPRequest):
    """
    Generate a 6-digit verification OTP for passwordless login.
    Rate-limited to prevent flooding.
    """
    settings = get_settings()
    is_prod = (settings.app_env or "").lower() == "production"

    check_login_rate_limit(request.identifier)
    otp = generate_otp(request.identifier)

    resp: Dict[str, Any] = {
        "identifier": request.identifier,
        "otp_sent": True,
        "message": "Verification OTP sent successfully (valid for 5 minutes).",
    }
    # Expose demo OTP code in response ONLY when not in production
    if not is_prod:
        resp["demo_otp_code"] = otp
        resp["message"] = f"Verification OTP sent (Demo OTP: {otp})."

    await log_audit_event(
        user_id=request.identifier,
        action="OTP_REQUESTED",
        details=f"Verification OTP requested for identifier {request.identifier}",
    )
    return resp


@router.post("/login", response_model=AuthResponse)
async def login_customer(request: LoginRequest):
    """
    Authenticate customer by Email, Phone, or Customer ID.
    Enforces rate-limiting, secure password checking, and single-use OTP verification.
    Demo quick login is strictly disabled in production.
    """
    settings = get_settings()
    is_prod = (settings.app_env or "").lower() == "production"

    # Enforce rate limiting on login attempts
    check_login_rate_limit(request.identifier)

    # Demo quick login handling
    if request.demo_quick_login:
        if is_prod:
            raise HTTPException(
                status_code=403,
                detail="Demo quick login is disabled in production.",
            )
        user_row = await get_user_by_identifier(request.identifier) or await get_user_by_identifier("USR-100001")
    else:
        user_row = await get_user_by_identifier(request.identifier)

    if not user_row:
        record_login_failure(request.identifier)
        await log_audit_event(
            user_id=request.identifier,
            action="LOGIN_FAILED",
            details=f"Login failed: Customer account not found for identifier '{request.identifier}'",
        )
        raise HTTPException(
            status_code=401,
            detail="Customer account not found. Please register or check your ID/email.",
        )

    if not request.demo_quick_login:
        if request.otp_code:
            if not verify_otp(request.identifier, request.otp_code):
                record_login_failure(request.identifier)
                await log_audit_event(
                    user_id=user_row["customer_id"],
                    action="LOGIN_FAILED_OTP",
                    details=f"Failed OTP verification for customer {user_row['customer_id']}",
                )
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired OTP code. Please request a new OTP.",
                )
        elif request.password:
            if not verify_password(request.password, user_row["password_hash"]):
                record_login_failure(request.identifier)
                await log_audit_event(
                    user_id=user_row["customer_id"],
                    action="LOGIN_FAILED_PASSWORD",
                    details=f"Incorrect password attempt for customer {user_row['customer_id']}",
                )
                raise HTTPException(status_code=401, detail="Incorrect password.")
        else:
            raise HTTPException(status_code=400, detail="Please provide either a password or an OTP code.")

    # Successful login: reset failed attempts
    reset_login_attempts(request.identifier)

    profile = await get_user_profile(user_row["customer_id"])
    await log_audit_event(
        user_id=profile.customer_id,
        action="USER_LOGIN",
        details=f"Customer {profile.name} ({profile.customer_id}) authenticated successfully.",
    )
    token = create_access_token(
        customer_id=profile.customer_id,
        email=profile.email,
        name=profile.name,
    )
    return AuthResponse(access_token=token, user=profile)


@router.post("/logout")
async def logout_customer(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Log out customer and record session termination in audit log."""
    customer_id = current_user.get("sub", "UNKNOWN")
    await log_audit_event(
        user_id=customer_id,
        action="USER_LOGOUT",
        details=f"Customer {customer_id} logged out successfully.",
    )
    return {"message": "Logged out successfully.", "customer_id": customer_id}


@router.get("/me", response_model=UserProfile)
async def get_current_customer_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get profile and consent status for the active customer.
    Strictly derives customer identity from verified JWT context.
    Never falls back to demo account.
    """
    customer_id = current_user.get("sub")
    profile = await get_user_profile(customer_id)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Customer profile for '{customer_id}' not found.",
        )
    return profile


@router.get("/vault", response_model=VaultSummaryResponse)
async def get_customer_claims_vault(
    customer_id: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Customer Claims Vault (Phase 6 — Page 8 of PDF).
    Strictly isolated: Always returns data for the verified authenticated customer.
    Ignores client-supplied customer_id query parameters that do not match the token.
    """
    verified_uid = current_user["sub"]
    profile = await get_user_profile(verified_uid)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Customer profile '{verified_uid}' not found.",
        )

    # Strictly fetch claims owned by this authenticated customer
    claims = await get_all_claims(customer_id=verified_uid)
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

    audit_logs = await get_user_audit_logs(verified_uid, limit=25)
    return VaultSummaryResponse(
        user=profile,
        total_cases=len(claims),
        claims=claims,
        recent_reports=recent_reports,
        audit_logs=audit_logs,
    )
