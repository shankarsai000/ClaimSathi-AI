"""
Track A: Vehicle Make/Model Tiered Damage Severity & INR Cost Estimator.
Covers India's Top 25 Two-Wheelers and Top 25 Four-Wheelers mapped to realistic OEM parts & labor
cost tiers, producing a Preliminary Repair Cost Band (Min–Max INR) with IRDAI/BFSI compliance framing.
"""

from typing import Any, Dict, List, Optional, Tuple
import re

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

BFSI_REGULATORY_DISCLAIMER = (
    "Preliminary AI Repair Cost Band for Surveyor/Adjuster Review Only. "
    "Final coverage liability and settlement rest solely with the licensed insurer/TPA under IRDAI guidelines."
)

# Tier multipliers calibrated to Indian OEM parts & authorized workshop labor schedules
MAKE_MODEL_TIER_MULTIPLIERS: Dict[str, Tuple[str, float]] = {
    "2w_commuter": ("2W Commuter Tier", 0.85),
    "2w_standard": ("2W Standard / Scooter Tier", 1.00),
    "2w_premium": ("2W Premium / EV / Cruiser Tier", 1.45),
    "4w_economy_hatch": ("4W Economy Hatchback Tier", 0.85),
    "4w_compact_sedan": ("4W Compact Hatchback / Sedan Tier", 1.00),
    "4w_midsize_suv": ("4W Midsize SUV / MPV Tier", 1.45),
    "4w_premium_suv": ("4W Premium SUV / Flagship Tier", 2.25),
    "standard_baseline": ("Standard Category Baseline", 1.00),
}

# Top 25 Two-Wheelers + Top 25 Four-Wheelers in India (~80% of Indian retail motor claims)
INDIAN_MAKE_MODEL_CATALOG: Dict[str, Tuple[str, str]] = {
    # ── Top 25 Indian Two-Wheelers ──
    "hero splendor plus": ("Hero Splendor Plus", "2w_commuter"),
    "splendor": ("Hero Splendor Plus", "2w_commuter"),
    "hero hf deluxe": ("Hero HF Deluxe", "2w_commuter"),
    "hf deluxe": ("Hero HF Deluxe", "2w_commuter"),
    "hero glamour": ("Hero Glamour", "2w_commuter"),
    "bajaj platina": ("Bajaj Platina 110", "2w_commuter"),
    "platina": ("Bajaj Platina 110", "2w_commuter"),
    "tvs sport": ("TVS Sport", "2w_commuter"),
    "honda shine 100": ("Honda Shine 100", "2w_commuter"),
    "honda cd 110": ("Honda CD 110 Dream", "2w_commuter"),
    "honda activa 6g": ("Honda Activa 6G", "2w_standard"),
    "activa": ("Honda Activa 6G", "2w_standard"),
    "honda shine 125": ("Honda CB Shine 125", "2w_standard"),
    "cb shine": ("Honda CB Shine 125", "2w_standard"),
    "honda unicorn": ("Honda Unicorn 160", "2w_standard"),
    "tvs jupiter": ("TVS Jupiter 110", "2w_standard"),
    "jupiter": ("TVS Jupiter 110", "2w_standard"),
    "suzuki access 125": ("Suzuki Access 125", "2w_standard"),
    "access 125": ("Suzuki Access 125", "2w_standard"),
    "bajaj pulsar 150": ("Bajaj Pulsar 150", "2w_standard"),
    "bajaj pulsar 220": ("Bajaj Pulsar 220F", "2w_standard"),
    "bajaj pulsar 220f": ("Bajaj Pulsar 220F", "2w_standard"),
    "pulsar 220f": ("Bajaj Pulsar 220F", "2w_standard"),
    "pulsar 220 f": ("Bajaj Pulsar 220F", "2w_standard"),
    "pulsar 220": ("Bajaj Pulsar 220F", "2w_standard"),
    "pulser 220f": ("Bajaj Pulsar 220F", "2w_standard"),
    "pulser 220": ("Bajaj Pulsar 220F", "2w_standard"),
    "impulser 220": ("Bajaj Pulsar 220F", "2w_standard"),
    "pulsar 180": ("Bajaj Pulsar 180", "2w_standard"),
    "pulsar ns200": ("Bajaj Pulsar NS200", "2w_premium"),
    "pulsar ns 200": ("Bajaj Pulsar NS200", "2w_premium"),
    "ns200": ("Bajaj Pulsar NS200", "2w_premium"),
    "ns 200": ("Bajaj Pulsar NS200", "2w_premium"),
    "pulsar rs200": ("Bajaj Pulsar RS200", "2w_premium"),
    "pulsar rs 200": ("Bajaj Pulsar RS200", "2w_premium"),
    "pulsar 125": ("Bajaj Pulsar 125", "2w_standard"),
    "pulser": ("Bajaj Pulsar 150", "2w_standard"),
    "pulsar": ("Bajaj Pulsar 150", "2w_standard"),
    "splender": ("Hero Splendor Plus", "2w_commuter"),
    "passion pro": ("Hero Passion Pro", "2w_commuter"),
    "passion plus": ("Hero Passion Plus", "2w_commuter"),
    "honda activa 5g": ("Honda Activa 5G", "2w_standard"),
    "activa 6g": ("Honda Activa 6G", "2w_standard"),
    "activa 5g": ("Honda Activa 5G", "2w_standard"),
    "activa 125": ("Honda Activa 125", "2w_standard"),
    "honda dio": ("Honda Dio", "2w_standard"),
    "dio": ("Honda Dio", "2w_standard"),
    "shine": ("Honda CB Shine 125", "2w_standard"),
    "unicorn 160": ("Honda Unicorn 160", "2w_standard"),
    "unicorn": ("Honda Unicorn 160", "2w_standard"),
    "tvs raider": ("TVS Raider 125", "2w_standard"),
    "raider": ("TVS Raider 125", "2w_standard"),
    "tvs ntorq": ("TVS Ntorq 125", "2w_standard"),
    "ntorq": ("TVS Ntorq 125", "2w_standard"),
    "tvs apache rtr 160": ("TVS Apache RTR 160", "2w_standard"),
    "apache rtr 200": ("TVS Apache RTR 200", "2w_premium"),
    "apache 200": ("TVS Apache RTR 200", "2w_premium"),
    "apache 160": ("TVS Apache RTR 160", "2w_standard"),
    "rtr 160": ("TVS Apache RTR 160", "2w_standard"),
    "rtr 200": ("TVS Apache RTR 200", "2w_premium"),
    "apache": ("TVS Apache RTR 160", "2w_standard"),
    "suzuki burgman": ("Suzuki Burgman Street", "2w_standard"),
    "yamaha fz": ("Yamaha FZ-S V3", "2w_standard"),
    "fz-s": ("Yamaha FZ-S V3", "2w_standard"),
    "fzs": ("Yamaha FZ-S V3", "2w_standard"),
    "bajaj chetak": ("Bajaj Chetak EV", "2w_premium"),
    "tvs iqube": ("TVS iQube Electric", "2w_premium"),
    "iqube": ("TVS iQube Electric", "2w_premium"),
    "royal enfield classic 350": ("Royal Enfield Classic 350", "2w_premium"),
    "classic 350": ("Royal Enfield Classic 350", "2w_premium"),
    "royal enfield bullet 350": ("Royal Enfield Bullet 350", "2w_premium"),
    "bullet 350": ("Royal Enfield Bullet 350", "2w_premium"),
    "royal enfield": ("Royal Enfield Classic 350", "2w_premium"),
    "bullet": ("Royal Enfield Bullet 350", "2w_premium"),
    "royal enfield hunter 350": ("Royal Enfield Hunter 350", "2w_premium"),
    "hunter 350": ("Royal Enfield Hunter 350", "2w_premium"),
    "meteor 350": ("Royal Enfield Meteor 350", "2w_premium"),
    "royal enfield himalayan": ("Royal Enfield Himalayan 450", "2w_premium"),
    "himalayan": ("Royal Enfield Himalayan 450", "2w_premium"),
    "ktm duke 390": ("KTM Duke 390", "2w_premium"),
    "ktm duke 200": ("KTM Duke 200", "2w_premium"),
    "duke 390": ("KTM Duke 390", "2w_premium"),
    "duke 200": ("KTM Duke 200", "2w_premium"),
    "ktm duke": ("KTM Duke 200/390", "2w_premium"),
    "duke": ("KTM Duke 200/390", "2w_premium"),
    "yamaha r15 v4": ("Yamaha R15 V4", "2w_premium"),
    "yamaha r15": ("Yamaha R15 V4", "2w_premium"),
    "r15": ("Yamaha R15 V4", "2w_premium"),
    "yamaha mt-15": ("Yamaha MT-15", "2w_premium"),
    "yamaha mt 15": ("Yamaha MT-15", "2w_premium"),
    "mt-15": ("Yamaha MT-15", "2w_premium"),
    "mt 15": ("Yamaha MT-15", "2w_premium"),
    "mt15": ("Yamaha MT-15", "2w_premium"),
    "ather 450x": ("Ather 450X", "2w_premium"),
    "ather": ("Ather 450X", "2w_premium"),
    "ola s1 pro": ("Ola S1 Pro", "2w_premium"),
    "ola s1": ("Ola S1 Pro", "2w_premium"),
    # ── Top 25 Indian Four-Wheelers ──
    "maruti alto k10": ("Maruti Suzuki Alto K10", "4w_economy_hatch"),
    "alto": ("Maruti Suzuki Alto K10", "4w_economy_hatch"),
    "maruti wagonr": ("Maruti Suzuki WagonR", "4w_economy_hatch"),
    "wagonr": ("Maruti Suzuki WagonR", "4w_economy_hatch"),
    "maruti celerio": ("Maruti Suzuki Celerio", "4w_economy_hatch"),
    "maruti s-presso": ("Maruti Suzuki S-Presso", "4w_economy_hatch"),
    "tata tiago": ("Tata Tiago", "4w_economy_hatch"),
    "tiago": ("Tata Tiago", "4w_economy_hatch"),
    "renault kwid": ("Renault Kwid", "4w_economy_hatch"),
    "kwid": ("Renault Kwid", "4w_economy_hatch"),
    "maruti swift": ("Maruti Suzuki Swift", "4w_compact_sedan"),
    "swift": ("Maruti Suzuki Swift", "4w_compact_sedan"),
    "maruti baleno": ("Maruti Suzuki Baleno", "4w_compact_sedan"),
    "baleno": ("Maruti Suzuki Baleno", "4w_compact_sedan"),
    "maruti dzire": ("Maruti Suzuki Dzire", "4w_compact_sedan"),
    "dzire": ("Maruti Suzuki Dzire", "4w_compact_sedan"),
    "maruti fronx": ("Maruti Suzuki Fronx", "4w_compact_sedan"),
    "fronx": ("Maruti Suzuki Fronx", "4w_compact_sedan"),
    "hyundai grand i10": ("Hyundai Grand i10 Nios", "4w_compact_sedan"),
    "hyundai i20": ("Hyundai i20", "4w_compact_sedan"),
    "i20": ("Hyundai i20", "4w_compact_sedan"),
    "hyundai aura": ("Hyundai Aura", "4w_compact_sedan"),
    "tata punch": ("Tata Punch", "4w_compact_sedan"),
    "punch": ("Tata Punch", "4w_compact_sedan"),
    "tata altroz": ("Tata Altroz", "4w_compact_sedan"),
    "altroz": ("Tata Altroz", "4w_compact_sedan"),
    "tata tigor": ("Tata Tigor", "4w_compact_sedan"),
    "honda amaze": ("Honda Amaze", "4w_compact_sedan"),
    "amaze": ("Honda Amaze", "4w_compact_sedan"),
    "toyota glanza": ("Toyota Glanza", "4w_compact_sedan"),
    "glanza": ("Toyota Glanza", "4w_compact_sedan"),
    "hyundai creta": ("Hyundai Creta", "4w_midsize_suv"),
    "creta": ("Hyundai Creta", "4w_midsize_suv"),
    "hyundai venue": ("Hyundai Venue", "4w_midsize_suv"),
    "venue": ("Hyundai Venue", "4w_midsize_suv"),
    "hyundai verna": ("Hyundai Verna", "4w_midsize_suv"),
    "verna": ("Hyundai Verna", "4w_midsize_suv"),
    "kia seltos": ("Kia Seltos", "4w_midsize_suv"),
    "seltos": ("Kia Seltos", "4w_midsize_suv"),
    "kia sonet": ("Kia Sonet", "4w_midsize_suv"),
    "sonet": ("Kia Sonet", "4w_midsize_suv"),
    "kia carens": ("Kia Carens", "4w_midsize_suv"),
    "maruti brezza": ("Maruti Suzuki Brezza", "4w_midsize_suv"),
    "brezza": ("Maruti Suzuki Brezza", "4w_midsize_suv"),
    "maruti ertiga": ("Maruti Suzuki Ertiga", "4w_midsize_suv"),
    "ertiga": ("Maruti Suzuki Ertiga", "4w_midsize_suv"),
    "maruti grand vitara": ("Maruti Suzuki Grand Vitara", "4w_midsize_suv"),
    "tata nexon": ("Tata Nexon", "4w_midsize_suv"),
    "nexon": ("Tata Nexon", "4w_midsize_suv"),
    "honda city": ("Honda City", "4w_midsize_suv"),
    "mahindra xuv 3xo": ("Mahindra XUV 3XO", "4w_midsize_suv"),
    "mahindra bolero": ("Mahindra Bolero", "4w_midsize_suv"),
    "bolero": ("Mahindra Bolero", "4w_midsize_suv"),
    "mahindra xuv700": ("Mahindra XUV700", "4w_premium_suv"),
    "mahindra xuv 700": ("Mahindra XUV700", "4w_premium_suv"),
    "xuv 700": ("Mahindra XUV700", "4w_premium_suv"),
    "xuv-700": ("Mahindra XUV700", "4w_premium_suv"),
    "xuv700": ("Mahindra XUV700", "4w_premium_suv"),
    "mahindra scorpio-n": ("Mahindra Scorpio-N", "4w_premium_suv"),
    "scorpio n": ("Mahindra Scorpio-N", "4w_premium_suv"),
    "scorpio": ("Mahindra Scorpio-N", "4w_premium_suv"),
    "wagon r": ("Maruti Suzuki WagonR", "4w_economy_hatch"),
    "grand i10": ("Hyundai Grand i10 Nios", "4w_compact_sedan"),
    "i 20": ("Hyundai i20", "4w_compact_sedan"),
    "toyota innova crysta": ("Toyota Innova Crysta", "4w_premium_suv"),
    "innova crysta": ("Toyota Innova Crysta", "4w_premium_suv"),
    "jeep compass": ("Jeep Compass", "4w_premium_suv"),
    "skoda slavia": ("Skoda Slavia", "4w_midsize_suv"),
    "vw virtus": ("Volkswagen Virtus", "4w_midsize_suv"),
    "virtus": ("Volkswagen Virtus", "4w_midsize_suv"),
    "slavia": ("Skoda Slavia", "4w_midsize_suv"),
    "mahindra thar": ("Mahindra Thar", "4w_premium_suv"),
    "thar": ("Mahindra Thar", "4w_premium_suv"),
    "tata harrier": ("Tata Harrier", "4w_premium_suv"),
    "harrier": ("Tata Harrier", "4w_premium_suv"),
    "tata safari": ("Tata Safari", "4w_premium_suv"),
    "safari": ("Tata Safari", "4w_premium_suv"),
    "mg hector": ("MG Hector", "4w_premium_suv"),
    "hector": ("MG Hector", "4w_premium_suv"),
    "toyota innova hycross": ("Toyota Innova HyCross", "4w_premium_suv"),
    "innova": ("Toyota Innova HyCross", "4w_premium_suv"),
    "toyota fortuner": ("Toyota Fortuner", "4w_premium_suv"),
    "fortuner": ("Toyota Fortuner", "4w_premium_suv"),
}

_INDIAN_MODEL_INDIC_ALIASES: List[Tuple[str, str]] = [
    ("పల్సర్ 220", "Bajaj Pulsar 220F"),
    ("पल्सर 220", "Bajaj Pulsar 220F"),
    ("ಪಲ್ಸರ್ 220", "Bajaj Pulsar 220F"),
    ("பல்சர் 220", "Bajaj Pulsar 220F"),
    ("పల్సర్", "Bajaj Pulsar 150"),
    ("पल्सर", "Bajaj Pulsar 150"),
    ("ಪಲ್ಸರ್", "Bajaj Pulsar 150"),
    ("பல்சர்", "Bajaj Pulsar 150"),
    ("యాక్టివా", "Honda Activa 6G"),
    ("एक्टिवा", "Honda Activa 6G"),
    ("ಆಕ್ಟಿವಾ", "Honda Activa 6G"),
    ("ஆக்டிவா", "Honda Activa 6G"),
    ("స్ప్లెండర్", "Hero Splendor Plus"),
    ("स्प्लेंडर", "Hero Splendor Plus"),
    ("ಸ್ಪ್ಲೆಂಡರ್", "Hero Splendor Plus"),
    ("ஸ்பிளெண்டர்", "Hero Splendor Plus"),
    ("బుల్లెట్", "Royal Enfield Bullet 350"),
    ("बुलेट", "Royal Enfield Bullet 350"),
    ("ಬುಲೆಟ್", "Royal Enfield Bullet 350"),
    ("புல்லட்", "Royal Enfield Bullet 350"),
    ("అపాచీ", "TVS Apache RTR 160"),
    ("अपाचे", "TVS Apache RTR 160"),
    ("ಅಪಾಚೆ", "TVS Apache RTR 160"),
    ("அப்பாச்சி", "TVS Apache RTR 160"),
    ("స్విఫ్ట్", "Maruti Suzuki Swift"),
    ("स्विफ्ट", "Maruti Suzuki Swift"),
    ("ಸ್ವಿಫ್ಟ್", "Maruti Suzuki Swift"),
    ("ஸ்விஃப்ட்", "Maruti Suzuki Swift"),
    ("క్రెటా", "Hyundai Creta"),
    ("क्रेटा", "Hyundai Creta"),
    ("ಕ್ರೆಟಾ", "Hyundai Creta"),
    ("கிரெட்டா", "Hyundai Creta"),
    ("నెక్సాన్", "Tata Nexon"),
    ("नेक्सॉन", "Tata Nexon"),
    ("ನೆಕ್ಸಾನ್", "Tata Nexon"),
    ("థార్", "Mahindra Thar"),
    ("थार", "Mahindra Thar"),
    ("ಥಾರ್", "Mahindra Thar"),
    ("ఇన్నోవా", "Toyota Innova HyCross"),
    ("इनोवा", "Toyota Innova HyCross"),
    ("ಇನ್ನೋವಾ", "Toyota Innova HyCross"),
]

_INDIC_DIGIT_TRANS = str.maketrans(
    "०१२३४५६७८९౦౧౨౩౪౫౬౭౮౯೦೧೨೩೪೫೬೭೮೯௦௧௨௩௪௫௬௭௮௯",
    "0123456789012345678901234567890123456789",
)

_OPEN_VOCAB_MODEL_RE = re.compile(
    r"(?:my\s+(?:bike|car|scooter|vehicle)\s+(?:model|name)\s*(?:is|:)?|vehicle\s+model\s*(?:is|:)?|"
    r"model\s+(?:name\s+)?(?:is|:)|my\s+(?:bike|car|scooter)\s+is\s+(?:a\s+|an\s+)?)"
    r"\s*([A-Za-z][A-Za-z0-9\s\-\.]{1,30}?)"
    r"(?=\s*(?:,|;|\.|and\b|number\b|plate\b|reg\b|registration\b|policy\b|which\b|was\b|got\b|met\b|had\b|near\b|at\b|in\b|on\b|$))",
    re.IGNORECASE,
)

_NON_MODEL_CANDIDATES = frozenset({
    "car", "bike", "scooter", "scooty", "vehicle", "two wheeler", "four wheeler",
    "damaged", "broken", "safe", "parked", "stolen", "hit", "crashed", "insured",
    "fine", "okay", "ok", "good", "bad", "new", "old", "missing", "gone", "lost",
    "red", "black", "white", "blue", "silver", "grey", "gray", "green", "yellow",
})


def _normalize_model_text(text: str) -> str:
    s = (text or "").translate(_INDIC_DIGIT_TRANS).lower().strip()
    spoken_nums = [
        ("two twenty f", "220f"),
        ("two twenty", "220"),
        ("one fifty", "150"),
        ("one sixty", "160"),
        ("one eighty", "180"),
        ("one twenty five", "125"),
        ("three fifty", "350"),
        ("four fifty", "450"),
        ("two hundred", "200"),
        ("seven hundred", "700"),
        ("six g", "6g"),
        ("five g", "5g"),
    ]
    for src, dst in spoken_nums:
        s = re.sub(rf"\b{src}\b", dst, s)
    return re.sub(r"\s+", " ", s)


def extract_vehicle_make_model(text: Optional[str]) -> Optional[str]:
    """
    Extract a canonical Indian 2W/4W vehicle make/model from conversational utterance text
    across English, phonetic STT variants, Indic scripts, and open-vocabulary model declarations.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    norm = _normalize_model_text(raw)

    # 1. Exact/phonetic catalog match (longest alias first, strict boundary)
    for alias in sorted(INDIAN_MAKE_MODEL_CATALOG.keys(), key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", norm):
            canonical_name, _tier_key = INDIAN_MAKE_MODEL_CATALOG[alias]
            return canonical_name

    # 2. Native Indic script model match (Telugu, Hindi/Marathi, Kannada, Tamil)
    raw_digits_norm = raw.translate(_INDIC_DIGIT_TRANS)
    for alias, canonical_name in sorted(_INDIAN_MODEL_INDIC_ALIASES, key=lambda x: len(x[0]), reverse=True):
        if alias in raw_digits_norm:
            return canonical_name

    # 3. Open-vocabulary explicit model declaration (e.g. "My bike model is Yamaha FZ-X")
    m_open = _OPEN_VOCAB_MODEL_RE.search(norm)
    if m_open:
        cand = re.sub(r"\s+", " ", m_open.group(1)).strip(" -.")
        cand_low = cand.lower()
        # Reject plate numbers / policy refs / generic adjectives
        is_plate_like = bool(re.match(r"^[a-z]{2}[\s\-]?\d{1,2}[\s\-]?[a-z]{0,3}[\s\-]?\d{3,4}$", cand_low))
        is_pol_like = cand_low.startswith(("pol", "mot", "ins", "cs-", "veh-"))
        if (
            len(cand) >= 3
            and not is_plate_like
            and not is_pol_like
            and cand_low not in _NON_MODEL_CANDIDATES
            and not any(tok in cand_low.split() for tok in ("number", "plate", "policy", "yesterday", "today", "accident", "damage"))
        ):
            return cand.title()
    return None


def infer_vehicle_type_from_make_model(make_model: Optional[str]) -> Optional[str]:
    """Infer 'bike' (2W) or 'car' (4W) from a resolved canonical or brand make/model string."""
    if not make_model or not make_model.strip():
        return None
    norm = make_model.strip().lower()
    for _alias, (canonical_name, tier_key) in INDIAN_MAKE_MODEL_CATALOG.items():
        if canonical_name.lower() == norm or _alias in norm:
            if tier_key.startswith("2w_"):
                return "bike"
            if tier_key.startswith("4w_"):
                return "car"
    bike_brands = ("pulsar", "splendor", "activa", "jupiter", "apache", "royal enfield", "bullet", "yamaha", "ktm", "hero", "bajaj", "tvs", "ather", "ola s1", "vespa", "aprilia", "access", "dio")
    car_brands = ("maruti", "suzuki", "hyundai", "tata", "mahindra", "kia", "toyota", "honda city", "honda amaze", "skoda", "volkswagen", "mg ", "jeep", "renault", "nissan")
    if any(b in norm for b in bike_brands):
        return "bike"
    if any(b in norm for b in car_brands):
        return "car"
    return None

_SEVERITY_RANK_TO_LABEL: Dict[int, str] = {
    0: "None",
    1: "Minor",
    2: "Moderate",
    3: "Severe",
}


def resolve_make_model_tier(
    vehicle_make_model: Optional[str] = None,
    claimed_vehicle_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolve an Indian 2W/4W make/model string to its parts & labor pricing tier.
    When vehicle_make_model is omitted or unrecognized, keeps tier_multiplier=1.0
    so default baseline estimates remain deterministic.
    """
    raw = (vehicle_make_model or "").strip()
    if not raw:
        label, mult = MAKE_MODEL_TIER_MULTIPLIERS["standard_baseline"]
        return {
            "vehicle_make_model": "Standard Category Baseline",
            "make_model_tier": label,
            "tier_key": "standard_baseline",
            "tier_multiplier": mult,
        }

    norm = raw.lower()
    for alias in sorted(INDIAN_MAKE_MODEL_CATALOG.keys(), key=len, reverse=True):
        if alias in norm:
            canonical_name, tier_key = INDIAN_MAKE_MODEL_CATALOG[alias]
            label, mult = MAKE_MODEL_TIER_MULTIPLIERS[tier_key]
            return {
                "vehicle_make_model": canonical_name,
                "make_model_tier": label,
                "tier_key": tier_key,
                "tier_multiplier": mult,
            }

    # Heuristic category fallback when explicit custom model is typed
    v_norm = (claimed_vehicle_type or "").lower()
    if "suv" in norm or "sedan" in norm or "safari" in norm or "compass" in norm:
        tier_key = "4w_midsize_suv"
    elif "2w" in v_norm or "two" in v_norm or "bike" in v_norm:
        tier_key = "2w_standard"
    else:
        tier_key = "standard_baseline"
    label, mult = MAKE_MODEL_TIER_MULTIPLIERS[tier_key]
    return {
        "vehicle_make_model": raw,
        "make_model_tier": label,
        "tier_key": tier_key,
        "tier_multiplier": mult,
    }


def _classify_severity(area_ratio: float) -> Tuple[str, float, int]:
    """Map bounding-box area ratio (bbox_area / image_area) to severity tier & multiplier."""
    if area_ratio < 0.03:
        return "Minor", 1.0, 1
    if area_ratio <= 0.10:
        return "Moderate", 1.5, 2
    return "Severe", 2.2, 3


def estimate_damage_cost(
    damages: List[Dict[str, Any]],
    decision: str,
    vehicle_make_model: Optional[str] = None,
    claimed_vehicle_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compute itemized INR repair cost band from Stage 3B detections, Stage 5 verdict,
    and optional Indian vehicle Make/Model tier.
    """
    tier_info = resolve_make_model_tier(vehicle_make_model, claimed_vehicle_type)
    tier_mult = float(tier_info["tier_multiplier"])

    decision_upper = (decision or "").upper()
    if decision_upper == "REJECT":
        return {
            "currency": "INR",
            "estimate_status": "REJECTED_NO_ESTIMATE",
            "overall_severity": "None",
            "line_items": [],
            "total_estimated_inr": 0,
            "total_inr": 0,
            "estimate_band_min_inr": 0,
            "estimate_band_max_inr": 0,
            "vehicle_make_model": tier_info["vehicle_make_model"],
            "make_model_tier": tier_info["make_model_tier"],
            "tier_multiplier": tier_mult,
            "bfsi_regulatory_disclaimer": BFSI_REGULATORY_DISCLAIMER,
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
        part_cost = int(round(rates["part_cost"] * tier_mult))
        labor_cost = int(round(rates["labor_cost"] * tier_mult))

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
    band_min_inr = int(round(total_estimated_inr * 0.85)) if total_estimated_inr > 0 else 0
    band_max_inr = int(round(total_estimated_inr * 1.20)) if total_estimated_inr > 0 else 0
    overall_severity = _SEVERITY_RANK_TO_LABEL.get(highest_rank, "None")

    return {
        "currency": "INR",
        "estimate_status": estimate_status,
        "overall_severity": overall_severity,
        "line_items": line_items,
        "total_estimated_inr": total_estimated_inr,
        "total_inr": total_estimated_inr,
        "estimate_band_min_inr": band_min_inr,
        "estimate_band_max_inr": band_max_inr,
        "vehicle_make_model": tier_info["vehicle_make_model"],
        "make_model_tier": tier_info["make_model_tier"],
        "tier_multiplier": tier_mult,
        "bfsi_regulatory_disclaimer": BFSI_REGULATORY_DISCLAIMER,
    }
