"""
Stage 3A: General Vehicle Presence & Category Detection (YOLOv8s COCO).
Detects both Four-Wheelers (car: 2, bus: 5, truck: 7) and Two-Wheelers (bicycle: 1, motorcycle: 3)
with confidence threshold >= 0.25, determining detected_vehicle_category:
'two_wheeler', 'four_wheeler', or 'unknown'.
"""

import io
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DEFAULT_VEHICLE_WEIGHTS = BASE_DIR / "models" / "vehicle_detector" / "yolov8s.pt"

FOUR_WHEELER_CLASSES = {
    2: "car",
    5: "bus",
    7: "truck",
}
TWO_WHEELER_CLASSES = {
    1: "bicycle",
    3: "motorcycle",
}
VEHICLE_CLASS_MAP = {**FOUR_WHEELER_CLASSES, **TWO_WHEELER_CLASSES}
VEHICLE_CONF_THRESHOLD = 0.25


def normalize_vehicle_type(claimed_vehicle_type: Optional[str]) -> str:
    """Normalize user-supplied vehicle category string into 'two_wheeler' or 'four_wheeler'."""
    raw = (claimed_vehicle_type or "four_wheeler").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in ("bike", "motorcycle", "two_wheeler", "twowheeler", "2w", "scooter", "moped"):
        return "two_wheeler"
    return "four_wheeler"


class VehicleDetector:
    """Cached YOLOv8s general vehicle detector supporting 2-wheelers and 4-wheelers."""

    def __init__(self, weights_path: Optional[Path] = None, conf_threshold: float = VEHICLE_CONF_THRESHOLD):
        from ultralytics import YOLO

        self.weights_path = Path(weights_path) if weights_path else DEFAULT_VEHICLE_WEIGHTS
        self.conf_threshold = conf_threshold
        self.weights_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.weights_path.exists():
            downloaded = YOLO("yolov8s.pt")
            src = Path("yolov8s.pt")
            if src.exists() and not self.weights_path.exists():
                shutil.move(str(src), str(self.weights_path))
            self.model = downloaded if self.weights_path.exists() is False else YOLO(str(self.weights_path))
        else:
            self.model = YOLO(str(self.weights_path))

    def detect(self, file_bytes: bytes) -> Dict[str, Any]:
        """Run general vehicle detection on RGB image bytes and classify 2W vs 4W category."""
        with Image.open(io.BytesIO(file_bytes)) as img:
            rgb_img = img.convert("RGB")
            img_w, img_h = rgb_img.size

        img_area = max(1.0, float(img_w * img_h))
        results = self.model.predict(
            source=rgb_img,
            conf=self.conf_threshold,
            classes=list(VEHICLE_CLASS_MAP.keys()),
            verbose=False,
        )

        detections: List[Dict[str, Any]] = []
        detected_classes_set = set()
        max_conf = 0.0
        four_wheeler_max_conf = 0.0
        two_wheeler_max_conf = 0.0
        largest_area_ratio = 0.0

        for res in results:
            if res.boxes is None:
                continue
            for box in res.boxes:
                cls_id = int(box.cls[0].item())
                if cls_id not in VEHICLE_CLASS_MAP:
                    continue
                conf = float(box.conf[0].item())
                if conf < self.conf_threshold:
                    continue
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                bbox_area = max(0.0, (x2 - x1) * (y2 - y1))
                area_ratio = bbox_area / img_area
                cls_name = VEHICLE_CLASS_MAP[cls_id]
                category = "two_wheeler" if cls_id in TWO_WHEELER_CLASSES else "four_wheeler"

                detected_classes_set.add(cls_name)
                if conf > max_conf:
                    max_conf = conf
                if category == "two_wheeler" and conf > two_wheeler_max_conf:
                    two_wheeler_max_conf = conf
                elif category == "four_wheeler" and conf > four_wheeler_max_conf:
                    four_wheeler_max_conf = conf
                if area_ratio > largest_area_ratio:
                    largest_area_ratio = area_ratio

                detections.append(
                    {
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "category": category,
                        "confidence": round(conf, 4),
                        "bbox": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                        "area_ratio": round(area_ratio, 6),
                    }
                )

        if two_wheeler_max_conf > 0.0 and two_wheeler_max_conf >= four_wheeler_max_conf:
            detected_vehicle_category = "two_wheeler"
        elif four_wheeler_max_conf > 0.0 and four_wheeler_max_conf > two_wheeler_max_conf:
            detected_vehicle_category = "four_wheeler"
        else:
            detected_vehicle_category = "unknown"

        return {
            "vehicle_detected": len(detections) > 0,
            "detected_vehicle_category": detected_vehicle_category,
            "four_wheeler_max_confidence": round(four_wheeler_max_conf, 4),
            "two_wheeler_max_confidence": round(two_wheeler_max_conf, 4),
            "detected_classes": sorted(detected_classes_set),
            "max_confidence": round(max_conf, 4),
            "largest_area_ratio": round(largest_area_ratio, 6),
            "detections": detections,
        }


_vehicle_detector_instance: Optional[VehicleDetector] = None


def get_vehicle_detector() -> VehicleDetector:
    global _vehicle_detector_instance
    if _vehicle_detector_instance is None:
        _vehicle_detector_instance = VehicleDetector()
    return _vehicle_detector_instance


def run_stage3a_vehicle_detection(file_bytes: bytes) -> Dict[str, Any]:
    """Run Stage 3A General Vehicle Presence & Category Detection."""
    return get_vehicle_detector().detect(file_bytes)
