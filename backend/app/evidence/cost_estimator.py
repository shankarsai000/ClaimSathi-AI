"""
Track A: Lightweight Deterministic Vehicle Damage Severity & INR Cost Estimator (MVP).
Uses Stage 3B (CarDD YOLOv8s) damage detections and Stage 5 verification decision to compute
itemized Indian market repair estimates in INR without external pricing APIs.
"""

from typing import Any, Dict, List, Tuple

INDIAN_REPAIR_RATES_INR: Dict[str, Dict[str, int]] = {
    # Four-Wheeler (CarDD) classes
    "scratch": {"part_cost": 1500, "labor_cost": 500},
    "dent": {"part_cost": 2500, "labor_cost": 800},
    "crack": {"part_cost": 3500, "labor_cost": 1000},
    "lamp broken": {"part_cost": 4000, "labor_cost": 600},
    "tire flat": {"part_cost": 3000, "labor_cost": 400},
    "glass shatter": {"part_cost": 6500, "labor_cost": 1500},
    # Two-Wheeler (Bike) classes
    "bike_scratch": {"part_cost": 600, "labor_cost": 250},
    "bike_dent": {"part_cost": 1200, "labor_cost": 400},
    "broken_headlamp": {"part_cost": 1800, "labor_cost": 350},
    "broken_fairing": {"part_cost": 2200, "labor_cost": 500},
}

DEFAULT_RATE_INR: Dict[str, int] = {"part_cost": 2000, "labor_cost": 600}

_SEVERITY_RANK_TO_LABEL: Dict[int, str] = {
    0: "None",
    1: "Minor",
    2: "Moderate",
    3: "Severe",
}


def _classify_severity(area_ratio: float) -> Tuple[str, float, int]:
    """Map bounding-box area ratio (bbox_area / image_area) to severity tier & multiplier."""
    if area_ratio < 0.03:
        return "Minor", 1.0, 1
    if area_ratio <= 0.10:
        return "Moderate", 1.5, 2
    return "Severe", 2.2, 3


def estimate_damage_cost(damages: List[Dict[str, Any]], decision: str) -> Dict[str, Any]:
    """
    Compute itemized INR repair cost estimate from Stage 3B detections and Stage 5 verdict.
    - REJECT -> total_estimated_inr=0, line_items=[], REJECTED_NO_ESTIMATE
    - REVIEW -> computed line items if damages exist, PROVISIONAL_PENDING_REVIEW
    - PASS   -> computed line items if damages exist, APPROVED_AUTO_ESTIMATE
    """
    decision_upper = (decision or "").upper()
    if decision_upper == "REJECT":
        return {
            "currency": "INR",
            "estimate_status": "REJECTED_NO_ESTIMATE",
            "overall_severity": "None",
            "line_items": [],
            "total_estimated_inr": 0,
            "total_inr": 0,
        }

    estimate_status = (
        "APPROVED_AUTO_ESTIMATE"
        if decision_upper == "PASS"
        else "PROVISIONAL_PENDING_REVIEW"
    )

    line_items: List[Dict[str, Any]] = []
    highest_rank = 0

    for d in damages or []:
        damage_type = str(d.get("class_name", "")).strip().lower()
        rates = INDIAN_REPAIR_RATES_INR.get(damage_type, DEFAULT_RATE_INR)
        part_cost = int(rates["part_cost"])
        labor_cost = int(rates["labor_cost"])

        area_ratio = float(d.get("area_ratio", 0.0))
        severity, multiplier, rank = _classify_severity(area_ratio)
        if rank > highest_rank:
            highest_rank = rank

        subtotal_inr = int(round((part_cost * multiplier) + labor_cost))
        line_items.append(
            {
                "damage_type": damage_type,
                "confidence": round(float(d.get("confidence", 0.0)), 4),
                "area_ratio": round(area_ratio, 6),
                "severity": severity,
                "base_part_inr": part_cost,
                "labor_inr": labor_cost,
                "Diagnostic_multiplier": multiplier,
                "multiplier": multiplier,
                "subtotal_inr": subtotal_inr,
            }
        )

    total_estimated_inr = sum(item["subtotal_inr"] for item in line_items)
    overall_severity = _SEVERITY_RANK_TO_LABEL.get(highest_rank, "None")

    return {
        "currency": "INR",
        "estimate_status": estimate_status,
        "overall_severity": overall_severity,
        "line_items": line_items,
        "total_estimated_inr": total_estimated_inr,
        "total_inr": total_estimated_inr,
    }
