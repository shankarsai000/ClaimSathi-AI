"""
Claim-Level Authorization & Ownership Verification Module for ClaimSathi AI (Sprint 1).
Provides reusable FastAPI dependencies that strictly enforce:
- User identity is derived exclusively from verified JWT authentication context.
- Every claim operation validates that the authenticated customer owns the claim.
- Cross-customer access attempts return HTTP 403 Forbidden.
- Nonexistent claims return HTTP 404 Not Found.
- Backward compatibility for legacy Phase 1 unauthenticated demo claims in development mode.
"""

from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException

from .config import get_settings
from .models import ClaimRecord
from .auth import get_current_user, get_optional_user
from .database import get_claim, log_audit_event


async def get_authorized_claim(
    claim_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ClaimRecord:
    """
    Mandatory claim ownership verification dependency.
    Requires authentication, looks up claim, verifies customer ownership.
    Raises 404 if claim does not exist.
    Raises 403 if authenticated customer does not own the claim.
    """
    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(
            status_code=404,
            detail=f"Claim '{claim_id}' not found.",
        )

    customer_id = current_user.get("sub")
    if not customer_id or claim.customer_id != customer_id:
        # Log unauthorized cross-customer access attempt
        await log_audit_event(
            user_id=customer_id or "ANONYMOUS",
            action="ACCESS_DENIED_CROSS_CUSTOMER",
            details=(
                f"User '{customer_id}' attempted unauthorized access to claim '{claim_id}' "
                f"owned by '{claim.customer_id}'."
            ),
            claim_id=claim_id,
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to access or modify this claim.",
        )

    return claim


async def get_authorized_claim_or_demo(
    claim_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
) -> ClaimRecord:
    """
    Claim ownership verification with legacy development demo fallback.
    - If caller is authenticated: strictly enforces claim.customer_id == current_user['sub'].
    - If caller is unauthenticated:
        - In production: raises 401 Unauthorized.
        - In development: allowed ONLY if claim ID starts with 'DEMO-' (Phase 1 legacy tests).
          Customer claims (CS-2026-...) ALWAYS require authentication.
    """
    settings = get_settings()
    is_prod = (settings.app_env or "").lower() == "production"

    claim = await get_claim(claim_id)
    if not claim:
        raise HTTPException(
            status_code=404,
            detail=f"Claim '{claim_id}' not found.",
        )

    if current_user:
        customer_id = current_user.get("sub")
        if not customer_id or claim.customer_id != customer_id:
            await log_audit_event(
                user_id=customer_id or "ANONYMOUS",
                action="ACCESS_DENIED_CROSS_CUSTOMER",
                details=(
                    f"User '{customer_id}' attempted unauthorized access to claim '{claim_id}' "
                    f"owned by '{claim.customer_id}'."
                ),
                claim_id=claim_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied: You do not have permission to access or modify this claim.",
            )
        return claim

    # Unauthenticated caller
    if is_prod:
        raise HTTPException(
            status_code=401,
            detail="Authentication required to access this claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # In development / test mode: allow ONLY if claim is a legacy anonymous demo claim
    if settings.is_development_or_test and (claim.is_demo or claim_id.startswith("DEMO-")):
        return claim

    # Customer claims (CS-2026-...) always require authentication even in dev
    raise HTTPException(
        status_code=401,
        detail="Authentication required to access customer claims.",
        headers={"WWW-Authenticate": "Bearer"},
    )

