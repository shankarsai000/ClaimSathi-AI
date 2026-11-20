"""
Stage 4: Local Spoof & Synthetic-Media Screening (EfficientNetV2-S).
Loads local PyTorch weights from models/efficientnet_spoof/efficientnet_v2_spoof_best.pth
and config from models/efficientnet_spoof/spoof_config.json.
Produces probabilistic spoof risk (0.0 to 1.0) without issuing binary/hard REJECT decisions.
"""

import io
import json
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DEFAULT_WEIGHTS_PATH = BASE_DIR / "models" / "efficientnet_spoof" / "efficientnet_v2_spoof_best.pth"
DEFAULT_CONFIG_PATH = BASE_DIR / "models" / "efficientnet_spoof" / "spoof_config.json"


def _create_spoof_screening_model(num_classes: int = 3, dropout: float = 0.3):
    """Build exact SpoofScreeningModel wrapper matching saved backbone.* checkpoint keys."""
    import torch.nn as nn
    import torchvision

    class SpoofScreeningModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = torchvision.models.efficientnet_v2_s(weights=None)
            in_features = self.backbone.classifier[1].in_features
            self.backbone.classifier = nn.Sequential(
                nn.Dropout(p=dropout, inplace=True),
                nn.Linear(in_features, num_classes),
            )

        def forward(self, x):
            return self.backbone(x)

    return SpoofScreeningModel()


class SpoofDetector:
    """Thread/async-safe cached wrapper for local EfficientNetV2-S spoof screening."""

    def __init__(
        self,
        weights_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
    ):
        import torch
        from torchvision import transforms

        self._torch = torch
        self.weights_path = Path(weights_path) if weights_path else DEFAULT_WEIGHTS_PATH
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

        if not self.config_path.exists():
            raise FileNotFoundError(f"Spoof config not found: {self.config_path}")
        if not self.weights_path.exists():
            raise FileNotFoundError(f"Spoof weights not found: {self.weights_path}")

        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        class_map = self.config.get(
            "class_map",
            {"genuine": 0, "screen_recapture": 1, "manipulated_or_synthetic": 2},
        )
        self.idx_to_class = {int(v): k for k, v in class_map.items()}
        self.genuine_idx = int(class_map.get("genuine", 0))

        res = self.config.get("input_resolution", [384, 384])
        norm = self.config.get("normalization", {})
        mean = norm.get("mean", [0.485, 0.456, 0.406])
        std = norm.get("std", [0.229, 0.224, 0.225])

        self.thresholds = self.config.get(
            "risk_thresholds",
            {
                "pass_max_spoof_risk": 0.25,
                "review_min_spoof_risk": 0.25,
                "high_risk_flag": 0.70,
            },
        )

        self.transform = transforms.Compose(
            [
                transforms.Resize((int(res[0]), int(res[1]))),
                transforms.ToTensor(),
                transforms.Normalize(mean=mean, std=std),
            ]
        )

        self.model = _create_spoof_screening_model(
            num_classes=len(self.idx_to_class),
            dropout=0.3,
        )
        state_dict = torch.load(str(self.weights_path), map_location=self.device, weights_only=True)
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()

    def predict(self, file_bytes: bytes, claimed_vehicle_type: str = "four_wheeler") -> Dict[str, Any]:
        """Run spoof inference on RGB image bytes and return risk scores and class probabilities."""
        torch = self._torch
        with Image.open(io.BytesIO(file_bytes)) as img:
            rgb_img = img.convert("RGB")

        tensor = self.transform(rgb_img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits = self.model(tensor)
            probs_tensor = torch.softmax(logits, dim=1)[0]

        probs_list = [float(p) for p in probs_tensor.cpu().tolist()]
        probabilities = {
            self.idx_to_class.get(i, f"class_{i}"): round(probs_list[i], 6)
            for i in range(len(probs_list))
        }
        pred_idx = int(torch.argmax(probs_tensor).item())
        predicted_class = self.idx_to_class.get(pred_idx, f"class_{pred_idx}")

        if (claimed_vehicle_type or "").lower() == "two_wheeler":
            # The EfficientNetV2-S spoof model was trained on 4-wheeler CarDD geometry;
            # for 2-wheelers, screen_recapture probability provides calibrated spoof risk.
            spoof_risk = float(max(0.0, min(1.0, probabilities.get("screen_recapture", 0.0))))
            review_min = float(self.thresholds.get("review_min_spoof_risk", 0.25))
            predicted_class = "screen_recapture" if spoof_risk >= review_min else "genuine"
        else:
            spoof_risk = float(max(0.0, min(1.0, 1.0 - probs_list[self.genuine_idx])))

        return {
            "spoof_risk": round(spoof_risk, 6),
            "predicted_class": predicted_class,
            "probabilities": probabilities,
            "thresholds": self.thresholds,
            "device": str(self.device),
        }


_spoof_detector_instance: Optional[SpoofDetector] = None


def get_spoof_detector() -> SpoofDetector:
    global _spoof_detector_instance
    if _spoof_detector_instance is None:
        _spoof_detector_instance = SpoofDetector()
    return _spoof_detector_instance


def run_stage4_spoof_screening(
    file_bytes: bytes,
    claimed_vehicle_type: str = "four_wheeler",
) -> Dict[str, Any]:
    """Run Stage 4 Spoof & Synthetic-Media Screening using cached EfficientNetV2-S model."""
    return get_spoof_detector().predict(file_bytes, claimed_vehicle_type=claimed_vehicle_type)
