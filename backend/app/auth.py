"""
Authentication & Security Utilities for ClaimSathi AI (Phase 1 — Customer Platform).
Provides PBKDF2-HMAC-SHA256 password hashing and HMAC-SHA256 JWT token signing/verification.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException

JWT_SECRET = os.environ.get("CLAIMSATHI_JWT_SECRET", "claimsathi-mvp-secret-key-2026-secure")
JWT_EXPIRY_SECONDS = 86400 * 7  # 7 days

# In-memory OTP store for demo / local testing (also accepts 123456 universal test OTP)
_ACTIVE_OTPS: Dict[str, str] = {}


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256."""
    if not salt:
        salt = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    digest = base64.urlsafe_b64encode(dk).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2 hash."""
    if not stored_hash or "$" not in stored_hash:
        return False
    parts = stored_hash.split("$")
    if len(parts) != 3:
        return False
    _, salt, _ = parts
    computed = hash_password(password, salt=salt)
    return hmac.compare_digest(computed, stored_hash)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(customer_id: str, email: str, name: str) -> str:
    """Create a signed JWT token for the authenticated customer."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": customer_id,
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + JWT_EXPIRY_SECONDS,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """Verify and decode a JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token structure")
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid token signature")
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("Token expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired authentication token: {exc}")


def generate_otp(identifier: str) -> str:
    """Generate a 6-digit OTP for phone/email login."""
    otp = "123456"
    _ACTIVE_OTPS[identifier.strip().lower()] = otp
    return otp


def verify_otp(identifier: str, otp_code: str) -> bool:
    """Verify OTP code (accepts generated OTP or 123456 in MVP demo)."""
    clean_id = identifier.strip().lower()
    clean_code = (otp_code or "").strip()
    if clean_code == "123456":
        return True
    expected = _ACTIVE_OTPS.get(clean_id)
    return bool(expected and hmac.compare_digest(expected, clean_code))


async def get_optional_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    """Extract customer_id from Bearer token if provided; defaults to USR-100001 for unauthenticated demo calls."""
    if not authorization:
        return "USR-100001"
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        try:
            payload = decode_access_token(token)
            return payload.get("sub", "USR-100001")
        except HTTPException:
            return "USR-100001"
    return "USR-100001"


async def get_required_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Require a valid Bearer JWT token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer authentication token.")
    token = authorization[7:].strip()
    return decode_access_token(token)

