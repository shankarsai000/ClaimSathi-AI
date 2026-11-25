"""
Stage 5: Risk Aggregation Engine (PASS / REVIEW / REJECT).
Combines outputs from Stages 1-4 into a probabilistic risk outcome.
- REJECT: Stage 1 technical/file integrity failures OR Vehicle Category Mismatch (2W vs 4W).
- REVIEW: elevated spoof risk, missing vehicle & damage context, or editing software EXIF tags.
- PASS: valid file integrity, matching vehicle/damage context, low spoof risk, and no editing flags.
Missing EXIF alone never triggers REJECT or REVIEW.
"""

from typing import Any, Dict, List


def aggregate_risk(
    stage1: Dict[str, Any],
    stage2: Dict[str, Any] | None = None,
    stage3_vehicle: Dict[str, Any] | None = None,
    stage3_damage: Dict[str, Any] | None = None,
    context_valid: bool = False,
    stage4_spoof: Dict[str, Any] | None = None,
    claimed_vehicle_type: str = "four_wheeler",
    detected_vehicle_category: str = "unknown",
    vehicle_category_mismatch: bool = False,
) -> Dict[str, Any]:
    """Aggregate Stages 1-4 signals into final decision ('PASS', 'REVIEW', 'REJECT') and reasons."""
    reasons: List[str] = []

    # 1. Stage 1 Technical / Integrity Failure -> REJECT
    if not stage1.get("stage1_passed", False):
        error_reason = stage1.get("error_reason") or "File failed Stage 1 integrity verification"
        reasons.append(error_reason)
        return {
            "decision": "REJECT",
            "reasons": reasons,
            "requires_human_review": False,
        }

    # 1B. Critical Policy Rule: Vehicle Category Mismatch (Two-Wheeler vs Four-Wheeler) -> REJECT
    if vehicle_category_mismatch:
        reasons.append(
            f"VEHICLE_CATEGORY_MISMATCH: Claimed {claimed_vehicle_type} but uploaded image contains a {detected_vehicle_category}."
        )
        return {
            "decision": "REJECT",
            "reasons": reasons,
            "requires_human_review": False,
        }

    # 1C. Non-Vehicle Person / Selfie Guard -> REJECT (prevents laptop/front-camera selfies from passing as a claim)
    if not context_valid and (stage3_vehicle or {}).get("person_detected", False):
        reasons.append(
            "NON_VEHICLE_PERSON_SELFIE_DETECTED: A person/selfie was captured instead of a motor vehicle. Please point the camera at your damaged vehicle."
        )
        return {
            "decision": "REJECT",
            "reasons": reasons,
            "requires_human_review": False,
        }

    # 1D. Non-Vehicle Object Guard -> REJECT (animals, indoor furniture, household objects without any vehicle)
    if not context_valid and (stage3_vehicle or {}).get("non_vehicle_subject_detected", False):
        obj_names = ", ".join((stage3_vehicle or {}).get("non_vehicle_subject_names") or ["non-vehicle object"])
        reasons.append(
            f"NON_VEHICLE_OBJECT_DETECTED: A non-vehicle object ({obj_names}) was detected instead of a motor vehicle. Please upload a clear photo of your damaged vehicle."
        )
        return {
            "decision": "REJECT",
            "reasons": reasons,
            "requires_human_review": False,
        }

    stage2 = stage2 or {}
    stage4_spoof = stage4_spoof or {}
    thresholds = stage4_spoof.get("thresholds", {})
    review_min_spoof_risk = float(thresholds.get("review_min_spoof_risk", 0.25))
    high_risk_flag = float(thresholds.get("high_risk_flag", 0.70))

    spoof_risk = float(stage4_spoof.get("spoof_risk", 0.0))
    predicted_class = stage4_spoof.get("predicted_class", "unknown")

    # 1E. Direct Non-Vehicle / Blank / Wall Photo Guard -> REJECT when spoof risk is below fraud threshold
    if not context_valid and spoof_risk < review_min_spoof_risk:
        reasons.append(
            "NO_VEHICLE_DETECTED_REJECTED: No bike, car, or vehicle damage was detected in this image. Please capture or upload a clear photo of your damaged vehicle."
        )
        return {
            "decision": "REJECT",
            "reasons": reasons,
            "requires_human_review": False,
        }

    review_triggered = False

    # 2. Check Stage 4 Spoof Risk Trigger
    if spoof_risk >= review_min_spoof_risk:
        review_triggered = True
        if spoof_risk >= high_risk_flag:
            reasons.append("HIGH_SPOOF_RISK")
        reasons.append(f"SPOOF_RISK_THRESHOLD_EXCEEDED ({predicted_class}: {spoof_risk:.4f})")

    # 3. Check Stage 3 Vehicle / Damage Context Validation Trigger
    if not context_valid:
        review_triggered = True
        reasons.append("NO_VEHICLE_OR_DAMAGE_DETECTED")

    # 4. Check Stage 2 Editing Software EXIF Tag Trigger (missing EXIF does NOT trigger review)
    if stage2.get("editing_software_detected", False):
        review_triggered = True
        sw = stage2.get("software_tag") or "unknown"
        reasons.append(f"EDITING_SOFTWARE_TAG_DETECTED ({sw})")

    if review_triggered:
        return {
            "decision": "REVIEW",
            "reasons": reasons,
            "requires_human_review": True,
        }

    # 5. All checks passed
    reasons.append("File integrity verified, vehicle/damage context present, and visual spoof risk within safe bounds")
    return {
        "decision": "PASS",
        "reasons": reasons,
        "requires_human_review": False,
    }
