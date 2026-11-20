"""
Stage 1: File Integrity & Untouched Original Preservation.
Preserves the raw uploaded bytes into storage/evidence/ before any processing,
computes SHA-256 and file size, validates magic header bytes (JPEG, PNG, WEBP),
and verifies decode integrity via both Pillow and OpenCV.
"""

import hashlib
import io
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DEFAULT_EVIDENCE_STORAGE = BASE_DIR / "storage" / "evidence"


def _sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize client filename against path traversal while keeping safe basename."""
    raw_name = Path((filename or "upload.jpg").replace("\\", "/")).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name).strip("._")
    if not cleaned:
        return "upload.jpg"
    return cleaned


def _detect_magic_format(file_bytes: bytes) -> Tuple[bool, Optional[str], Optional[str]]:
    """Inspect binary magic bytes for JPEG, PNG, or WEBP."""
    if len(file_bytes) >= 3 and file_bytes[:3] == b"\xff\xd8\xff":
        return True, "JPEG", "image/jpeg"
    if len(file_bytes) >= 8 and file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return True, "PNG", "image/png"
    if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return True, "WEBP", "image/webp"
    return False, None, None


def run_stage1_file_integrity(
    file_bytes: bytes,
    filename: Optional[str],
    storage_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Execute Stage 1 File Integrity check:
    1. Persist untouched original bytes to storage/evidence/.
    2. Compute SHA-256 hex digest and exact file size.
    3. Verify non-zero size, JPEG/PNG/WEBP magic bytes, Pillow verify, and OpenCV imdecode.
    Any failure marks stage1_passed=False and short-circuits pipeline to REJECT.
    """
    target_dir = Path(storage_dir) if storage_dir else DEFAULT_EVIDENCE_STORAGE
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_filename(filename)
    saved_path = target_dir / f"{uuid4().hex[:8]}_{safe_name}"
    saved_path.write_bytes(file_bytes)

    sha256_hex = hashlib.sha256(file_bytes).hexdigest()
    file_size = len(file_bytes)

    if file_size == 0:
        return {
            "stage1_passed": False,
            "sha256": sha256_hex,
            "file_size_bytes": 0,
            "detected_format": None,
            "detected_mime": "application/octet-stream",
            "width": None,
            "height": None,
            "saved_path": str(saved_path),
            "error_code": "EMPTY_FILE",
            "error_reason": "Zero-byte upload",
        }

    magic_ok, detected_format, detected_mime = _detect_magic_format(file_bytes)
    if not magic_ok:
        return {
            "stage1_passed": False,
            "sha256": sha256_hex,
            "file_size_bytes": file_size,
            "detected_format": None,
            "detected_mime": "application/octet-stream",
            "width": None,
            "height": None,
            "saved_path": str(saved_path),
            "error_code": "INVALID_MAGIC_BYTES",
            "error_reason": "Invalid MIME/header signature (only JPEG, PNG, WEBP images supported)",
        }

    try:
        import cv2
        import numpy as np

        with Image.open(io.BytesIO(file_bytes)) as verify_img:
            verify_img.verify()
        with Image.open(io.BytesIO(file_bytes)) as img:
            rgb_img = img.convert("RGB")
            width, height = rgb_img.size

        arr = np.frombuffer(file_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None or bgr.size == 0:
            raise ValueError("OpenCV imdecode returned empty array")
    except Exception as exc:
        return {
            "stage1_passed": False,
            "sha256": sha256_hex,
            "file_size_bytes": file_size,
            "detected_format": detected_format,
            "detected_mime": detected_mime,
            "width": None,
            "height": None,
            "saved_path": str(saved_path),
            "error_code": "DECODE_FAILURE",
            "error_reason": f"Corrupted image bytes failed decoding: {exc}",
        }

    return {
        "stage1_passed": True,
        "sha256": sha256_hex,
        "file_size_bytes": file_size,
        "detected_format": detected_format,
        "detected_mime": detected_mime,
        "width": int(width),
        "height": int(height),
        "saved_path": str(saved_path),
        "error_code": None,
        "error_reason": None,
    }
