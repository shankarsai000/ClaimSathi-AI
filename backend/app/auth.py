"""
Authentication, Authorization & Security Module for ClaimSathi AI (Sprint 1).
Provides:
- PBKDF2-HMAC-SHA256 password hashing with constant-time verification.
- HMAC-SHA256 JWT access token generation and strict verification.
- Production secret enforcement with startup validation.
- Secure, rate-limited OTP generation, expiration and single-use verification.
- Centralized user identity extraction and claim-level ownership verification.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional, Dict, Any, List
from fastapi import Header, HTTPException, Query, Depends, Request

from .config import get_settings


# ── In-Memory OTP Store & Rate Limiting ──────────────────────────────
# Structure: { identifier: { "code": str, "expires_at": float, "attempts": int, "used": bool } }
_ACTIVE_OTPS: Dict[str, Dict[str, Any]] = {}

# Structure: { identifier_or_ip: [timestamp1, timestamp2, ...] }
_FAILED_LOGIN_ATTEMPTS: Dict[str, List[float]] = {}


# ── Password Hashing & Verification ─────────────────────────────────
def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with 100,000 rounds."""
    if not salt:
        salt = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    digest = base64.urlsafe_b64encode(dk).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify plaintext password against stored PBKDF2 hash using constant-time comparison."""
    if not stored_hash or "$" not in stored_hash:
        return False
    parts = stored_hash.split("$")
    if len(parts) != 3:
        return False
    _, salt, _ = parts
    computed = hash_password(password, salt=salt)
    return hmac.compare_digest(computed, stored_hash)


# ── Base64URL Helpers ───────────────────────────────────────────────
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


# ── JWT Token Issuance & Strict Verification ────────────────────────
def create_access_token(
    customer_id: str,
    email: str,
    name: str,
    expires_delta_seconds: Optional[int] = None,
) -> str:
    """Create a signed JWT token for the authenticated customer."""
    settings = get_settings()
    secret = settings.get_jwt_secret()
    now = int(time.time())
    expiry = (
        now + expires_delta_seconds
        if expires_delta_seconds is not None
        else now + settings.jwt_expiry_seconds
    )

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": customer_id,
        "email": email,
        "name": name,
        "iat": now,
        "exp": expiry,
    }

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT token strictly.
    Enforces algorithm HS256, verifies signature, expiration, and required claims.
    Always raises HTTP 401 on any failure.
    """
    settings = get_settings()
    secret = settings.get_jwt_secret()

    if not token or not isinstance(token, str):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authentication token format.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=401,
            detail="Malformed authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    header_b64, payload_b64, sig_b64 = parts

    # 1. Parse and validate header
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if header.get("alg") != "HS256":
        raise HTTPException(
            status_code=401,
            detail="Unsupported token algorithm. Only HS256 is accepted.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Verify signature with constant-time comparison
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid token signature encoding.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token signature.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Parse and validate payload
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    customer_id = payload.get("sub")
    if not customer_id or not isinstance(customer_id, str):
        raise HTTPException(
            status_code=401,
            detail="Token missing valid subject (customer_id).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = int(time.time())
    exp = payload.get("exp")
    if not exp or not isinstance(exp, (int, float)) or exp < now:
        raise HTTPException(
            status_code=401,
            detail="Authentication token has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    iat = payload.get("iat")
    if iat and isinstance(iat, (int, float)) and iat > (now + 120):
        raise HTTPException(
            status_code=401,
            detail="Token issued in the future. Please check system clock.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ── OTP Management & Security Controls ──────────────────────────────
def generate_otp(identifier: str) -> str:
    """
    Generate a 6-digit OTP for phone/email login.
    In production: Generates a cryptographically random 6-digit number.
    In development/demo: Allows fixed 123456 or random.
    """
    settings = get_settings()
    clean_id = identifier.strip().lower()

    if (settings.app_env or "").lower() == "production":
        otp = f"{secrets.randbelow(900_000) + 100_000}"
    else:
        # Development / demo default for convenience
        otp = "123456"

    _ACTIVE_OTPS[clean_id] = {
        "code": otp,
        "expires_at": time.time() + settings.otp_expiry_seconds,
        "attempts": 0,
        "used": False,
    }
    return otp


def verify_otp(identifier: str, otp_code: str) -> bool:
    """
    Verify OTP with expiration, attempt limits, and single-use consumption.
    Universal '123456' is strictly blocked in production.
    """
    settings = get_settings()
    clean_id = identifier.strip().lower()
    clean_code = (otp_code or "").strip()
    is_prod = (settings.app_env or "").lower() == "production"

    record = _ACTIVE_OTPS.get(clean_id)

    if not record:
        # In development/test mode only: accept 123456 when no specific OTP session was created
        return (not is_prod) and (clean_code == "123456")

    # Check if already used (single-use guarantee)
    if record.get("used", False):
        return False

    # Check expiration (5 minutes TTL)
    if time.time() > record.get("expires_at", 0):
        _ACTIVE_OTPS.pop(clean_id, None)
        return False

    # Track attempts (max 3)
    record["attempts"] = record.get("attempts", 0) + 1
    if record["attempts"] > settings.otp_max_attempts:
        _ACTIVE_OTPS.pop(clean_id, None)
        return False

    expected = record.get("code")
    is_valid = (
        (expected and hmac.compare_digest(expected, clean_code))
        or (not is_prod and clean_code == "123456")
    )
    if is_valid:
        # Single-use consumption: mark used
        record["used"] = True
        return True

    return False


# ── Rate Limiting for Authentication ────────────────────────────────
def check_login_rate_limit(identifier: str, ip: str = "127.0.0.1"):
    """Check if identifier or IP has exceeded maximum failed login attempts."""
    settings = get_settings()
    now = time.time()
    window = settings.auth_rate_limit_window_seconds
    max_attempts = settings.auth_rate_limit_max_attempts

    key = f"{identifier.strip().lower()}:{ip}"
    attempts = _FAILED_LOGIN_ATTEMPTS.get(key, [])
    # Filter to recent window
    recent = [t for t in attempts if now - t < window]
    _FAILED_LOGIN_ATTEMPTS[key] = recent

    if len(recent) >= max_attempts:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Please wait {window} seconds before trying again.",
        )


def record_login_failure(identifier: str, ip: str = "127.0.0.1"):
    """Record a failed login attempt for rate-limiting."""
    key = f"{identifier.strip().lower()}:{ip}"
    attempts = _FAILED_LOGIN_ATTEMPTS.get(key, [])
    attempts.append(time.time())
    _FAILED_LOGIN_ATTEMPTS[key] = attempts


def reset_login_attempts(identifier: str, ip: str = "127.0.0.1"):
    """Clear failed login attempts on successful authentication."""
    key = f"{identifier.strip().lower()}:{ip}"
    _FAILED_LOGIN_ATTEMPTS.pop(key, None)


# ── Dependency: Mandatory Authenticated Customer Context ─────────────
def extract_token_from_request(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
) -> Optional[str]:
    """Extract raw JWT token from Authorization header or 'token' query param."""
    if authorization and authorization.strip().lower().startswith("bearer "):
        return authorization.strip()[7:].strip()
    if token and token.strip():
        return token.strip()
    return None


async def get_current_user(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Mandatory authentication dependency.
    Requires a valid, unexpired Bearer JWT token from header or query param.
    Never falls back to unauthenticated demo user.
    """
    raw_token = extract_token_from_request(authorization, token)
    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(raw_token)


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
) -> Optional[Dict[str, Any]]:
    """
    Optional authentication dependency for transitional / public endpoints.
    If a token is provided, it MUST be valid. Invalid or expired tokens return HTTP 401.
    If no token is provided, returns None. Never silently substitutes a demo user.
    """
    raw_token = extract_token_from_request(authorization, token)
    if not raw_token:
        return None
    return decode_access_token(raw_token)


# ── Backward Compatibility Helper for Legacy Test Suite ─────────────
async def get_optional_current_user_id(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
) -> str:
    """
    Legacy helper: If token is provided, validates it strictly.
    In development/demo mode ONLY, if no token is provided, defaults to USR-100001.
    In production, raises 401 if unauthenticated.
    """
    settings = get_settings()
    is_prod = (settings.app_env or "").lower() == "production"

    raw_token = extract_token_from_request(authorization, token)
    if raw_token:
        payload = decode_access_token(raw_token)
        return payload.get("sub", "USR-100001")

    if is_prod:
        raise HTTPException(
            status_code=401,
            detail="Authentication required in production.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "USR-100001"
