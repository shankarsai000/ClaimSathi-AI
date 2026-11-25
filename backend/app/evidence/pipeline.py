"""
5-Stage Local Evidence Intelligence & Fraud-Risk Screening Pipeline Orchestrator.

Pipeline Flow:
  Stage 1: File Integrity & Untouched Original Preservation (short-circuits to REJECT on failure)
  Stage 2: EXIF Metadata & C2PA/XMP Provenance Analysis (supporting signal only)
  Stage 3A: General Vehicle Presence & Category Detection (YOLOv8s COCO 2W vs 4W)
  Stage 3B: Dual Vehicle Damage Detection (CarDD YOLOv8s + Two-Wheeler Bike YOLOv8s)
  Stage 4: Spoof & Synthetic-Media Screening (EfficientNetV2-S @ 384x384)
  Stage 5: Probabilistic Risk Aggregation (PASS / REVIEW / REJECT, including 2W/4W Mismatch REJECT)
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from ..database import save_evidence_verification
from .cost_estimator import estimate_damage_cost
from .damage_detection.detector import run_stage3b_damage_detection
from .preprocessing.file_integrity import run_stage1_file_integrity
from .preprocessing.metadata_provenance import run_stage2_metadata_provenance
from .risk_engine.aggregator import aggregate_risk
from .spoof_detection.classifier import run_stage4_spoof_screening
from .vehicle_detection.detector import (
    normalize_vehicle_type,
    run_stage3a_vehicle_detection,
)
from .vehicle_identity import verify_vehicle_identity_binding, verify_vehicle_identity_binding_async


class EvidenceVerificationPipeline:
    """Orchestrates local 5-stage image verification, 2W/4W mismatch screening, vehicle identity, and INR cost band."""

    async def verify_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        claimed_vehicle_type: str = "four_wheeler",
        vehicle_make_model: Optional[str] = None,
        claimed_registration: Optional[str] = None,
        storage_dir: Optional[Path] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        verification_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        clean_filename = Path((filename or "upload.jpg").replace("\\", "/")).name or "upload.jpg"
        normalized_claimed = normalize_vehicle_type(claimed_vehicle_type)

        # Stage 1: File Integrity & Untouched Preservation
        stage1 = run_stage1_file_integrity(file_bytes, clean_filename, storage_dir=storage_dir)

        if not stage1["stage1_passed"]:
            stage5 = aggregate_risk(stage1=stage1, claimed_vehicle_type=normalized_claimed)
            cost_estimate = estimate_damage_cost(
                [],
                decision=stage5["decision"],
                vehicle_make_model=vehicle_make_model,
                claimed_vehicle_type=normalized_claimed,
            )
            vehicle_identity = verify_vehicle_identity_binding(
                file_bytes=file_bytes,
                filename=clean_filename,
                claimed_registration=claimed_registration,
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
            result = {
                "id": verification_id,
                "filename": clean_filename,
                "sha256": stage1["sha256"],
                "decision": stage5["decision"],
                "claimed_vehicle_type": normalized_claimed,
                "detected_vehicle_category": "unknown",
                "vehicle_category_mismatch": False,
                "spoof_risk": 0.0,
                "predicted_spoof_class": "stage1_rejected",
                "vehicle_detected": False,
                "damage_count": 0,
                "context_valid": False,
                "reasons": stage5["reasons"],
                "cost_estimate": cost_estimate,
                "vehicle_identity": vehicle_identity,
                "stage_results": {
                    "claimed_vehicle_type": normalized_claimed,
                    "detected_vehicle_category": "unknown",
                    "vehicle_category_mismatch": False,
                    "stage1_integrity": stage1,
                    "stage2_metadata": None,
                    "stage3a_vehicle": None,
                    "stage3b_damage": None,
                    "stage4_spoof": None,
                    "stage5_risk": stage5,
                    "cost_estimate": cost_estimate,
                    "vehicle_identity": vehicle_identity,
                },
                "processing_time_ms": elapsed_ms,
                "created_at": created_at,
            }
            if persist:
                await save_evidence_verification(result)
            return result

        # Stage 2: Metadata & Provenance
        stage2 = run_stage2_metadata_provenance(file_bytes)

        # Stage 3A & 3B: Vehicle Category & Dual Damage Validation
        stage3_vehicle = run_stage3a_vehicle_detection(file_bytes)
        stage3a_category = stage3_vehicle.get("detected_vehicle_category", "unknown")

        stage3_damage = run_stage3b_damage_detection(
            file_bytes=file_bytes,
            claimed_vehicle_type=normalized_claimed,
            stage3a_category=stage3a_category,
            stage3a_four_wheeler_conf=float(stage3_vehicle.get("four_wheeler_max_confidence", 0.0)),
            stage3a_two_wheeler_conf=float(stage3_vehicle.get("two_wheeler_max_confidence", 0.0)),
            stage3a_vehicle_detected=bool(stage3_vehicle.get("vehicle_detected", False)),
            stage3a_person_detected=bool(stage3_vehicle.get("person_detected", False)),
            stage3a_non_vehicle_subject_detected=bool(stage3_vehicle.get("non_vehicle_subject_detected", False)),
            stage3a_person_bboxes=stage3_vehicle.get("person_bboxes") or [],
            stage3a_vehicle_bboxes=[d["bbox"] for d in stage3_vehicle.get("detections", []) if "bbox" in d],
        )
        detected_vehicle_category = stage3_damage.get("resolved_vehicle_category", stage3a_category)

        vehicle_category_mismatch = bool(
            detected_vehicle_category in ("two_wheeler", "four_wheeler")
            and detected_vehicle_category != normalized_claimed
        )

        # Context is valid if the claimed vehicle category or its active damage detector found a match
        same_category_vehicle_detected = bool(
            stage3_vehicle.get("vehicle_detected", False)
            and (
                stage3a_category == normalized_claimed
                or stage3a_category == "unknown"
            )
        )
        context_valid = bool(
            same_category_vehicle_detected
            or stage3_damage.get("damage_detected", False)
        )

        # Stage 4: EfficientNetV2-S Spoof Screening
        stage4_spoof = run_stage4_spoof_screening(
            file_bytes,
            claimed_vehicle_type=normalized_claimed,
        )

        # Stage 5: Risk Aggregation (including Vehicle Category Mismatch REJECT rule)
        stage5 = aggregate_risk(
            stage1=stage1,
            stage2=stage2,
            stage3_vehicle=stage3_vehicle,
            stage3_damage=stage3_damage,
            context_valid=context_valid,
            stage4_spoof=stage4_spoof,
            claimed_vehicle_type=normalized_claimed,
            detected_vehicle_category=detected_vehicle_category,
            vehicle_category_mismatch=vehicle_category_mismatch,
        )

        # Track A: Make/Model Tiered INR Cost Estimator & Pixel-Level Vehicle Identity Binding
        vehicle_identity = await verify_vehicle_identity_binding_async(
            file_bytes=file_bytes,
            filename=clean_filename,
            claimed_registration=claimed_registration,
            exif_metadata=stage2,
            run_visual_ocr=bool(claimed_registration),
        )

        # Escalate PASS -> REVIEW if detected physical plate conflicts with claimed registration
        if vehicle_identity.get("plate_match_status") == "MISMATCH_FLAGGED":
            stage5_reasons = list(stage5.get("reasons") or [])
            if "VEHICLE_REGISTRATION_PLATE_MISMATCH" not in stage5_reasons:
                stage5_reasons.append("VEHICLE_REGISTRATION_PLATE_MISMATCH")
            stage5["reasons"] = stage5_reasons
            if stage5.get("decision") == "PASS":
                stage5["decision"] = "REVIEW"
                stage5["requires_human_review"] = True

        cost_estimate = estimate_damage_cost(
            damages=stage3_damage.get("detections", []),
            decision=stage5["decision"],
            vehicle_make_model=vehicle_make_model,
            claimed_vehicle_type=normalized_claimed,
        )

        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        result = {
            "id": verification_id,
            "filename": clean_filename,
            "sha256": stage1["sha256"],
            "decision": stage5["decision"],
            "claimed_vehicle_type": normalized_claimed,
            "detected_vehicle_category": detected_vehicle_category,
            "vehicle_category_mismatch": vehicle_category_mismatch,
            "spoof_risk": stage4_spoof["spoof_risk"],
            "predicted_spoof_class": stage4_spoof["predicted_class"],
            "vehicle_detected": bool(stage3_vehicle["vehicle_detected"]),
            "damage_count": int(stage3_damage["damage_count"]),
            "context_valid": context_valid,
            "reasons": stage5["reasons"],
            "cost_estimate": cost_estimate,
            "vehicle_identity": vehicle_identity,
            "stage_results": {
                "claimed_vehicle_type": normalized_claimed,
                "detected_vehicle_category": detected_vehicle_category,
                "vehicle_category_mismatch": vehicle_category_mismatch,
                "stage1_integrity": stage1,
                "stage2_metadata": stage2,
                "stage3a_vehicle": stage3_vehicle,
                "stage3b_damage": stage3_damage,
                "stage4_spoof": stage4_spoof,
                "stage5_risk": stage5,
                "cost_estimate": cost_estimate,
                "vehicle_identity": vehicle_identity,
            },
            "processing_time_ms": elapsed_ms,
            "created_at": created_at,
        }

        if persist:
            await save_evidence_verification(result)

        return result


_pipeline_instance: Optional[EvidenceVerificationPipeline] = None


def get_verification_pipeline() -> EvidenceVerificationPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = EvidenceVerificationPipeline()
    return _pipeline_instance


async def verify_evidence_image(
    file_bytes: bytes,
    filename: str,
    claimed_vehicle_type: str = "four_wheeler",
    vehicle_make_model: Optional[str] = None,
    claimed_registration: Optional[str] = None,
    storage_dir: Optional[Path] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Convenience helper to run the full 5-stage local evidence pipeline."""
    return await get_verification_pipeline().verify_bytes(
        file_bytes=file_bytes,
        filename=filename,
        claimed_vehicle_type=claimed_vehicle_type,
        vehicle_make_model=vehicle_make_model,
        claimed_registration=claimed_registration,
        storage_dir=storage_dir,
        persist=persist,
    )
