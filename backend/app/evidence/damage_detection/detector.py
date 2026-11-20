"""
Stage 3B: Dual Vehicle Damage Detection (CarDD 4-Wheeler YOLOv8s + 2-Wheeler Bike YOLOv8s).
- CarDD model (models/damage_detector/cardd_damage_yolov8s.pt):
  {0: dent, 1: scratch, 2: crack, 3: glass shatter, 4: lamp broken, 5: tire flat}
- Bike model (models/damage_detector/bike_damage_yolov8s.pt):
  {0: bike_dent, 1: bike_scratch, 2: broken_fairing, 3: broken_headlamp}
Runs both models to support close-up category resolution and returns active damages
for the claimed vehicle category.
"""

import io
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from ..vehicle_detection.detector import normalize_vehicle_type

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DEFAULT_CAR_DAMAGE_WEIGHTS = BASE_DIR / "models" / "damage_detector" / "cardd_damage_yolov8s.pt"
DEFAULT_BIKE_DAMAGE_WEIGHTS = BASE_DIR / "models" / "damage_detector" / "bike_damage_yolov8s.pt"

CARDD_DAMAGE_CLASSES = {
    0: "dent",
    1: "scratch",
    2: "crack",
    3: "glass shatter",
    4: "lamp broken",
    5: "tire flat",
}

BIKE_DAMAGE_CLASSES = {
    0: "bike_dent",
    1: "bike_scratch",
    2: "broken_fairing",
    3: "broken_headlamp",
}

DAMAGE_CONF_THRESHOLD = 0.30


class DamageDetector:
    """Cached dual YOLOv8s vehicle damage detector (CarDD + Two-Wheeler Bike)."""

    def __init__(
        self,
        car_weights_path: Optional[Path] = None,
        bike_weights_path: Optional[Path] = None,
        conf_threshold: float = DAMAGE_CONF_THRESHOLD,
    ):
        from ultralytics import YOLO

        self.car_weights_path = Path(car_weights_path) if car_weights_path else DEFAULT_CAR_DAMAGE_WEIGHTS
        self.bike_weights_path = Path(bike_weights_path) if bike_weights_path else DEFAULT_BIKE_DAMAGE_WEIGHTS
        self.conf_threshold = conf_threshold

        if not self.car_weights_path.exists():
            raise FileNotFoundError(f"Car damage detector weights not found: {self.car_weights_path}")
        self.car_model = YOLO(str(self.car_weights_path))

        self.bike_model = (
            YOLO(str(self.bike_weights_path))
            if self.bike_weights_path.exists()
            else None
        )

    def _run_yolo(
        self,
        model: Any,
        rgb_img: Image.Image,
        img_area: float,
        class_map: Dict[int, str],
    ) -> Dict[str, Any]:
        if model is None:
            return {
                "damage_detected": False,
                "damage_count": 0,
                "detected_damage_types": [],
                "max_confidence": 0.0,
                "detections": [],
            }

        results = model.predict(
            source=rgb_img,
            conf=self.conf_threshold,
            verbose=False,
        )

        detections: List[Dict[str, Any]] = []
        damage_types_set = set()
        max_conf = 0.0

        for res in results:
            if res.boxes is None:
                continue
            for box in res.boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                if conf < self.conf_threshold:
                    continue
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                bbox_area = max(0.0, (x2 - x1) * (y2 - y1))
                area_ratio = bbox_area / img_area
                cls_name = class_map.get(
                    cls_id,
                    res.names.get(cls_id, f"damage_{cls_id}") if isinstance(res.names, dict) else f"damage_{cls_id}",
                )

                damage_types_set.add(cls_name)
                if conf > max_conf:
                    max_conf = conf

                detections.append(
                    {
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "confidence": round(conf, 4),
                        "bbox": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                        "area_ratio": round(area_ratio, 6),
                    }
                )

        return {
            "damage_detected": len(detections) > 0,
            "damage_count": len(detections),
            "detected_damage_types": sorted(damage_types_set),
            "max_confidence": round(max_conf, 4),
            "detections": detections,
        }

    def detect(
        self,
        file_bytes: bytes,
        claimed_vehicle_type: str = "four_wheeler",
        stage3a_category: str = "unknown",
        stage3a_four_wheeler_conf: float = 0.0,
        stage3a_two_wheeler_conf: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Run both CarDD and Bike damage detectors, resolve close-up vehicle category if Stage 3A
        was 'unknown' or low-confidence misclassified on a 2W close-up, and select active damages.
        """
        normalized_claimed = normalize_vehicle_type(claimed_vehicle_type)

        with Image.open(io.BytesIO(file_bytes)) as img:
            rgb_img = img.convert("RGB")
            img_w, img_h = rgb_img.size

        img_area = max(1.0, float(img_w * img_h))
        car_res = self._run_yolo(self.car_model, rgb_img, img_area, CARDD_DAMAGE_CLASSES)
        bike_res = self._run_yolo(self.bike_model, rgb_img, img_area, BIKE_DAMAGE_CLASSES)

        car_max_conf = float(car_res["max_confidence"])
        bike_max_conf = float(bike_res["max_confidence"])
        car_types = set(car_res["detected_damage_types"])

        resolved_category = stage3a_category or "unknown"

        # Real-data 2W close-ups (e.g., scooter apron/tail-lamp) may be misclassified by COCO as
        # a low-confidence car (<= 0.55) while bike_damage_yolov8s.pt detects genuine 2W damage.
        if (
            normalized_claimed == "two_wheeler"
            and resolved_category == "four_wheeler"
            and stage3a_two_wheeler_conf == 0.0
            and stage3a_four_wheeler_conf <= 0.55
            and bike_res["damage_detected"]
        ):
            resolved_category = "two_wheeler"

        if resolved_category == "unknown":
            if normalized_claimed == "two_wheeler":
                if bike_res["damage_detected"]:
                    resolved_category = "two_wheeler"
                elif bool(car_types - {"glass shatter"}) and car_max_conf >= 0.40:
                    resolved_category = "four_wheeler"
            else:
                if bike_max_conf > car_max_conf + 0.05 or (
                    bike_res["damage_detected"]
                    and car_max_conf < 0.50
                    and not bool(car_types & {"glass shatter", "tire flat", "lamp broken", "crack"})
                ):
                    resolved_category = "two_wheeler"
                elif car_res["damage_detected"]:
                    resolved_category = "four_wheeler"

        active_res = bike_res if normalized_claimed == "two_wheeler" else car_res

        return {
            "damage_detected": active_res["damage_detected"],
            "damage_count": active_res["damage_count"],
            "detected_damage_types": active_res["detected_damage_types"],
            "max_confidence": active_res["max_confidence"],
            "detections": active_res["detections"],
            "resolved_vehicle_category": resolved_category,
            "car_damage_max_confidence": car_max_conf,
            "bike_damage_max_confidence": bike_max_conf,
            "car_damage_types": car_res["detected_damage_types"],
            "bike_damage_types": bike_res["detected_damage_types"],
        }


_damage_detector_instance: Optional[DamageDetector] = None


def get_damage_detector() -> DamageDetector:
    global _damage_detector_instance
    if _damage_detector_instance is None:
        _damage_detector_instance = DamageDetector()
    return _damage_detector_instance


def run_stage3b_damage_detection(
    file_bytes: bytes,
    claimed_vehicle_type: str = "four_wheeler",
    stage3a_category: str = "unknown",
    stage3a_four_wheeler_conf: float = 0.0,
    stage3a_two_wheeler_conf: float = 0.0,
) -> Dict[str, Any]:
    """Run Stage 3B Dual Vehicle Damage Detection."""
    return get_damage_detector().detect(
        file_bytes=file_bytes,
        claimed_vehicle_type=claimed_vehicle_type,
        stage3a_category=stage3a_category,
        stage3a_four_wheeler_conf=stage3a_four_wheeler_conf,
        stage3a_two_wheeler_conf=stage3a_two_wheeler_conf,
    )
