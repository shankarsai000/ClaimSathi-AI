"""
Stage 2: Metadata & Provenance Analysis.
Extracts EXIF camera/editing tags via Pillow and inspects raw bytes for C2PA/JUMBF/XMP
markers. Missing EXIF is treated strictly as a mild supporting signal (0.15), never
causing REJECT or standalone REVIEW (since messaging apps like WhatsApp strip EXIF).
"""

import io
from typing import Any, Dict, Optional

from PIL import ExifTags, Image

EDITING_SOFTWARE_KEYWORDS = (
    "photoshop",
    "gimp",
    "canva",
    "lightroom",
    "picsart",
    "snapseed",
    "affinity",
    "paint.net",
    "pixelmator",
    "midjourney",
    "dall-e",
    "stable diffusion",
    "firefly",
)

PROVENANCE_BYTE_MARKERS = (
    b"c2pa",
    b"jumbf",
    b"xmp",
)


def _clean_tag_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, bytes):
        val = val.decode("utf-8", errors="ignore")
    cleaned = str(val).replace("\x00", "").strip()
    return cleaned if cleaned else None


def run_stage2_metadata_provenance(file_bytes: bytes) -> Dict[str, Any]:
    """
    Execute Stage 2 Metadata & Provenance inspection.
    Never rejects or throws on missing/malformed EXIF headers.
    """
    tag_map: Dict[str, str] = {}
    has_exif = False

    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            exif = img.getexif()
            if exif and len(exif) > 0:
                has_exif = True
                for tag_id, value in exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    cleaned = _clean_tag_str(value)
                    if cleaned is not None:
                        tag_map[tag_name] = cleaned

                # Inspect Exif SubIFD (0x8769) where DateTimeOriginal commonly lives
                try:
                    sub_ifd = exif.get_ifd(0x8769)
                    for tag_id, value in (sub_ifd or {}).items():
                        tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                        cleaned = _clean_tag_str(value)
                        if cleaned is not None and tag_name not in tag_map:
                            tag_map[tag_name] = cleaned
                except Exception:
                    pass
    except Exception:
        has_exif = False

    make = tag_map.get("Make")
    model = tag_map.get("Model")
    if make and model:
        if make.lower() in model.lower():
            camera_make_model = model
        else:
            camera_make_model = f"{make} {model}".strip()
    else:
        camera_make_model = make or model or None

    datetime_original = tag_map.get("DateTimeOriginal") or tag_map.get("DateTime")
    software_tag = tag_map.get("Software")

    editing_software_detected = False
    if software_tag:
        sw_lower = software_tag.lower()
        editing_software_detected = any(kw in sw_lower for kw in EDITING_SOFTWARE_KEYWORDS)

    raw_lower = file_bytes.lower()
    c2pa_present = any(marker in raw_lower for marker in PROVENANCE_BYTE_MARKERS)

    # Compute supporting metadata risk score (0.0 to 1.0)
    metadata_risk_score = 0.0
    if not has_exif:
        metadata_risk_score += 0.15
    if editing_software_detected:
        metadata_risk_score += 0.45
    metadata_risk_score = min(1.0, round(metadata_risk_score, 4))

    return {
        "has_exif": has_exif,
        "camera_make_model": camera_make_model,
        "datetime_original": datetime_original,
        "software_tag": software_tag,
        "editing_software_detected": editing_software_detected,
        "c2pa_present": c2pa_present,
        "metadata_risk_score": metadata_risk_score,
        "provenance_advisory_only": True,
        "provenance_disclaimer": (
            "Advisory signal only: absence of C2PA/SynthID never proves authenticity "
            "and is stripped by messaging apps. Primary fraud shield is Stage 5 Guided Live Camera + 64-bit pHash."
        ),
    }
