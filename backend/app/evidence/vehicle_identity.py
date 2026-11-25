"""
Vehicle Identity Binding, Pixel-Level ANPR OCR & DPDP PII Masking Utility (Sprint 2.1).
Addresses real-world motor claim identity fraud (swapped vehicles / pre-existing damage)
by extracting physical license plates directly from image pixels (Gemini Vision JSON +
local Tesseract fallback + metadata/EXIF pre-check) and binding against `claimed_registration`.
"""

import base64
import io
import json
import re
from typing import Any, Dict, List, Optional

import httpx
from PIL import Image, ImageOps

from ..config import get_settings

_INDIAN_PLATE_RE = re.compile(
    r"\b([A-Z]{2})[\s\-_]?(\d{1,2})[\s\-_]?([A-Z]{1,3})[\s\-_]?(\d{3,4})\b",
    re.IGNORECASE,
)

MANDATORY_IDENTITY_CAPTURE_PROMPTS: List[str] = [
    "1. Front/Rear License Plate (ANPR Verification)",
    "2. Odometer & Chassis/VIN Plate",
    "3. RC & Driver License Verification",
]


def normalize_registration_plate(plate: Optional[str]) -> Optional[str]:
    """Normalize an Indian vehicle registration string to canonical XX-00-XX-0000 form."""
    if not plate:
        return None
    cleaned = re.sub(r"[^A-Z0-9]", "", plate.upper())
    m = re.match(r"^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{3,4})$", cleaned)
    if not m:
        return plate.strip().upper() or None
    return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3)}-{m.group(4)}"


def mask_pii_value(value: Optional[str], visible_tail: int = 4) -> str:
    """Mask sensitive identifiers (phone, policy, registration) per DPDP Act 2025 safeguard rules."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= visible_tail:
        return "*" * len(raw)
    return ("*" * max(4, len(raw) - visible_tail)) + raw[-visible_tail:]


def _try_local_tesseract_ocr(file_bytes: bytes) -> Optional[str]:
    """Best-effort offline pixel OCR using Pillow + pytesseract if installed on the host."""
    try:
        import pytesseract  # type: ignore

        with Image.open(io.BytesIO(file_bytes)) as img:
            gray = ImageOps.autocontrast(img.convert("L"))
            raw_text = pytesseract.image_to_string(gray, config="--psm 6") or ""
        for m in _INDIAN_PLATE_RE.finditer(raw_text):
            return f"{m.group(1).upper()}-{m.group(2).zfill(2)}-{m.group(3).upper()}-{m.group(4)}"
    except Exception:
        return None
    return None


async def extract_plate_from_image_pixels(
    file_bytes: bytes,
    run_visual_ocr: bool = False,
) -> Dict[str, Any]:
    """
    Extract visible physical license plate & odometer visibility directly from image pixels:
    1. Tries offline local Tesseract OCR on high-contrast grayscale image if available.
    2. When `run_visual_ocr=True` and Gemini API key is configured, runs structured Gemini Vision
       ANPR inspection (`{"plate_number": ..., "odometer_visible": ..., "vin_visible": ...}`).
    """
    local_plate = _try_local_tesseract_ocr(file_bytes)
    if local_plate:
        return {
            "plate_number": local_plate,
            "extraction_method": "local_tesseract_ocr",
            "odometer_visible": False,
            "vin_visible": False,
        }

    if not run_visual_ocr or not file_bytes:
        return {
            "plate_number": None,
            "extraction_method": "none",
            "odometer_visible": False,
            "vin_visible": False,
        }

    settings = get_settings()
    api_key = (settings.gemini_api_key or "").strip()
    if not api_key or "your_" in api_key.lower() or "placeholder" in api_key.lower():
        return {
            "plate_number": None,
            "extraction_method": "none",
            "odometer_visible": False,
            "vin_visible": False,
        }

    mime_type = "image/png" if file_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    b64_data = base64.b64encode(file_bytes).decode("ascii")
    model_name = (settings.gemini_model or "gemini-flash-lite-latest").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    prompt = (
        "Inspect this Indian vehicle image carefully. Read any visible vehicle registration number plate "
        "(e.g. KA01MJ4412 -> KA-01-MJ-4412), and note if an odometer or chassis/VIN plate is visible. "
        'Respond ONLY as JSON: {"plate_number": "XX-00-XX-0000 or null", "odometer_visible": false, "vin_visible": false}.'
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": b64_data}},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 120,
            "responseMimeType": "application/json",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=3.5) as client:
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json=payload,
            )
        if resp.status_code == 200:
            parts = (resp.json().get("candidates") or [{}])[0].get("content", {}).get("parts") or []
            raw_json = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
            parsed = json.loads(raw_json) if raw_json.startswith("{") else {}
            norm_plate = normalize_registration_plate(parsed.get("plate_number"))
            if norm_plate and norm_plate.upper() in ("NULL", "NONE", "N/A", "UNKNOWN"):
                norm_plate = None
            return {
                "plate_number": norm_plate,
                "extraction_method": "pixel_vision_ocr" if norm_plate else "pixel_vision_checked_no_plate",
                "odometer_visible": bool(parsed.get("odometer_visible", False)),
                "vin_visible": bool(parsed.get("vin_visible", False)),
            }
    except Exception:
        pass

    return {
        "plate_number": None,
        "extraction_method": "none",
        "odometer_visible": False,
        "vin_visible": False,
    }


def extract_plate_candidates(
    file_bytes: bytes,
    filename: str = "",
    exif_metadata: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Scan filename, EXIF text comments, and printable ASCII headers inside image bytes
    for Indian vehicle registration plates (offline metadata fallback).
    """
    searchable_parts: List[str] = [filename or ""]
    if exif_metadata:
        searchable_parts.extend(f"{k} {v}" for k, v in exif_metadata.items())
    sample_bytes = (file_bytes[:65536] + b" " + file_bytes[-8192:]) if file_bytes else b""
    ascii_tokens = re.findall(rb"[A-Za-z0-9\-_ ]{6,32}", sample_bytes)
    searchable_parts.extend(tok.decode("ascii", errors="ignore") for tok in ascii_tokens[:200])

    found: List[str] = []
    seen = set()
    for text in searchable_parts:
        for m in _INDIAN_PLATE_RE.finditer(text):
            norm = f"{m.group(1).upper()}-{m.group(2).zfill(2)}-{m.group(3).upper()}-{m.group(4)}"
            if norm not in seen:
                seen.add(norm)
                found.append(norm)
    return found


async def verify_vehicle_identity_binding_async(
    file_bytes: bytes,
    filename: str,
    claimed_registration: Optional[str] = None,
    exif_metadata: Optional[Dict[str, Any]] = None,
    run_visual_ocr: bool = False,
) -> Dict[str, Any]:
    """
    Async identity binding combining pixel-level ANPR OCR with metadata/filename inspection.
    """
    pixel_res = await extract_plate_from_image_pixels(file_bytes, run_visual_ocr=run_visual_ocr)
    return _assemble_identity_result(
        file_bytes=file_bytes,
        filename=filename,
        claimed_registration=claimed_registration,
        exif_metadata=exif_metadata,
        pixel_res=pixel_res,
    )


def verify_vehicle_identity_binding(
    file_bytes: bytes,
    filename: str,
    claimed_registration: Optional[str] = None,
    exif_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Synchronous identity binding (runs local Tesseract pixel check if present + embedded metadata scan).
    """
    local_plate = _try_local_tesseract_ocr(file_bytes)
    pixel_res = {
        "plate_number": local_plate,
        "extraction_method": "local_tesseract_ocr" if local_plate else "none",
        "odometer_visible": False,
        "vin_visible": False,
    }
    return _assemble_identity_result(
        file_bytes=file_bytes,
        filename=filename,
        claimed_registration=claimed_registration,
        exif_metadata=exif_metadata,
        pixel_res=pixel_res,
    )


def _assemble_identity_result(
    file_bytes: bytes,
    filename: str,
    claimed_registration: Optional[str],
    exif_metadata: Optional[Dict[str, Any]],
    pixel_res: Dict[str, Any],
) -> Dict[str, Any]:
    norm_claimed = normalize_registration_plate(claimed_registration)
    meta_candidates = extract_plate_candidates(
        file_bytes=file_bytes,
        filename=filename,
        exif_metadata=exif_metadata,
    )
    pixel_plate = pixel_res.get("plate_number")
    extraction_method = pixel_res.get("extraction_method") or "none"

    detected_candidates: List[str] = []
    if pixel_plate:
        detected_candidates.append(pixel_plate)
    for c in meta_candidates:
        if c not in detected_candidates:
            detected_candidates.append(c)

    if not pixel_plate and detected_candidates:
        extraction_method = "embedded_tag_or_metadata"

    detected_plate = detected_candidates[0] if detected_candidates else None

    if norm_claimed and detected_plate:
        if norm_claimed.replace("-", "") == detected_plate.replace("-", ""):
            match_status = "MATCHED"
            requires_review = False
            note = f"License plate matched claimed registration ({norm_claimed}) via {extraction_method}."
        else:
            match_status = "MISMATCH_FLAGGED"
            requires_review = True
            note = (
                f"Detected plate identifier ({detected_plate}) differs from claimed registration "
                f"({norm_claimed}) — escalated for human adjuster review."
            )
    elif norm_claimed:
        match_status = "CLAIM_PLATE_RECORDED_PENDING_ANPR"
        requires_review = False
        note = (
            f"Claimed registration {norm_claimed} recorded. Complete Stage 5 Live Camera "
            "plate, odometer/VIN & RC/DL capture to finish pixel identity binding."
        )
    else:
        match_status = "UNVERIFIED_LIVE_CAPTURE_REQUIRED"
        requires_review = False
        note = (
            "No registration number bound yet. Capture License Plate, Odometer/VIN, and RC/DL "
            "via Stage 5 Guided Live Camera."
        )

    return {
        "claimed_registration": norm_claimed,
        "detected_plate_candidate": detected_plate,
        "detected_candidates": detected_candidates,
        "extraction_method": extraction_method,
        "odometer_visible": bool(pixel_res.get("odometer_visible", False)),
        "vin_visible": bool(pixel_res.get("vin_visible", False)),
        "plate_match_status": match_status,
        "identity_bound": match_status == "MATCHED",
        "requires_identity_review": requires_review,
        "identity_note": note,
        "mandatory_capture_prompts": MANDATORY_IDENTITY_CAPTURE_PROMPTS,
    }
