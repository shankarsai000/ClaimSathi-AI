"""
Transcription providers for ClaimSathi AI (Phase 2 & 3).
Includes Gnani Prisma ASR integration (Prisma v2.5 and v3.0),
intelligent multilingual Indic & English field extraction,
and Mock fallback.
"""

from abc import ABC, abstractmethod
import logging
import re
from typing import Optional, Tuple, Dict, Any
import httpx
from fastapi import HTTPException
from ..config import get_settings
from ..models import ClaimField, FieldConfidence

logger = logging.getLogger("claimsathi.transcription")


class TranscriptionProvider(ABC):
    """Abstract interface for speech-to-text providers."""

    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "recording.wav",
        content_type: str = "audio/wav",
        language_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convert audio bytes to transcript and metadata."""
        ...

    @abstractmethod
    def get_provider_name(self) -> str:
        ...


class GnaniPrismaProvider(TranscriptionProvider):
    """
    Live integration with Gnani Prisma Speech-to-Text REST API.
    Supports both Prisma v2.5 and Prisma v3.0 request modes.
    Endpoint: https://api.vachana.ai/stt/v3
    """

    def __init__(self):
        self.settings = get_settings()

    def get_provider_name(self) -> str:
        model = self.settings.gnani_stt_model
        return f"Gnani Prisma ({model}) [LIVE]"

    def _is_v3_mode(self) -> bool:
        model = (self.settings.gnani_stt_model or "").lower()
        return "v3" in model or "v3.0" in model

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "recording.wav",
        content_type: str = "audio/wav",
        language_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        api_key = self.settings.gnani_api_key_id
        if not api_key or not api_key.strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Gnani API Key is not configured. Please set GNANI_API_KEY_ID in backend/.env "
                    "or enable Demo Mode to test with simulated speech."
                ),
            )

        endpoint = self.settings.gnani_stt_endpoint
        target_lang = language_code or self.settings.gnani_stt_language_code or "indic-auto"

        # Headers - NEVER log or leak api_key
        headers = {
            "X-API-Key-ID": api_key.strip(),
        }

        # Handle Prisma v2.5 vs Prisma v3.0 request modes
        data: Dict[str, str] = {}
        if self._is_v3_mode():
            # Prisma v3.0 mode: model is prisma-v3.0, supports writing_mode and indic-auto
            data["model"] = "prisma-v3.0"
            data["language_code"] = target_lang
            if self.settings.gnani_stt_writing_mode:
                data["writing_mode"] = self.settings.gnani_stt_writing_mode
        else:
            # Prisma v2.5 mode: language_code only, do not send unsupported v3 parameters
            data["language_code"] = "hi-IN" if target_lang == "indic-auto" else target_lang

        files = {
            "audio_file": (filename, audio_bytes, content_type),
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    headers=headers,
                    data=data,
                    files=files,
                )
        except httpx.TimeoutException:
            logger.error("Gnani Prisma STT request timed out.")
            raise HTTPException(
                status_code=504,
                detail="The Gnani Speech-to-Text service timed out (30s). Please try recording again.",
            )
        except httpx.RequestError as exc:
            logger.error(f"Gnani Prisma STT network connection error: {exc.__class__.__name__}")
            raise HTTPException(
                status_code=502,
                detail=f"Unable to connect to Gnani Speech API: {exc.__class__.__name__}. Check network connectivity.",
            )

        # Inspect HTTP Status
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Authentication failed with Gnani Speech API. Please verify your GNANI_API_KEY_ID in backend/.env.",
            )
        elif response.status_code == 402:
            raise HTTPException(
                status_code=402,
                detail="Insufficient credits on your Gnani AI account. Please top up your credits on the Gnani portal.",
            )
        elif response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Gnani Speech API rate limit exceeded. Please wait a moment before trying again.",
            )
        elif response.status_code >= 500:
            raise HTTPException(
                status_code=502,
                detail=f"Gnani Speech API returned an upstream server error (HTTP {response.status_code}). Please retry.",
            )
        elif response.status_code != 200:
            error_body = response.text
            try:
                err_json = response.json()
                detail_msg = err_json.get("message") or err_json.get("error") or error_body
            except Exception:
                detail_msg = error_body
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Gnani Speech API rejected the audio request: {detail_msg}",
            )

        # Parse success response
        try:
            res_json = response.json()
        except Exception:
            raise HTTPException(
                status_code=502,
                detail="Invalid response format received from Gnani Speech API.",
            )

        transcript = res_json.get("transcript", "").strip()
        model_name = res_json.get("model") or ("prisma-v3.0" if self._is_v3_mode() else "prisma-v2.5")
        detected_language = res_json.get("detected_language_code") or res_json.get("language_code")

        request_metadata = {
            "request_id": res_json.get("request_id"),
            "processing_time": res_json.get("processing_time"),
            "end_to_end_latency": res_json.get("end_to_end_latency"),
            "mode": "prisma-v3.0" if self._is_v3_mode() else "prisma-v2.5",
            "audio_filename": filename,
            "bytes_received": len(audio_bytes),
        }

        return {
            "transcript": transcript,
            "model": model_name,
            "detected_language": detected_language,
            "is_mock": False,
            "request_metadata": request_metadata,
        }


class MockTranscriptionProvider(TranscriptionProvider):
    """
    Simulated transcription provider for Demo Mode and automated testing.
    Returns realistic Hinglish/Telugu transcripts.
    """

    MOCK_SCENARIOS = [
        {
            "transcript": (
                "Haan, mera ek accident ho gaya tha kal. Main apni car drive kar raha tha "
                "Andheri East mein, Mumbai mein. Saamne se ek auto aaya aur side mein lag "
                "gaya. Left door aur fender mein bahut damage hua hai. Meri policy number "
                "hai MOT-2024-MH-78432."
            ),
            "model": "mock-prisma-v2.5",
            "detected_language": "hi-IN",
        },
        {
            "transcript": (
                "Dekhiye, meri bike ka accident hua hai. Policy number POL-BK-2024-DL-55123. "
                "Main Connaught Place ke paas tha jab ek car ne mujhe side se hit kiya. "
                "Front mudguard tut gaya aur headlight bhi."
            ),
            "model": "mock-prisma-v2.5",
            "detected_language": "hi-IN",
        },
        {
            "transcript": (
                "Chudandi, naa car accident aindi. Policy number MOT-2024-TS-98765. "
                "Nenu Hyderabad lo Madhapur deggara drive chestunnappudu oka auto vachi side lo hit chesindi. "
                "Left door and bumper full ga damage aindi."
            ),
            "model": "mock-prisma-v3.0",
            "detected_language": "te-IN",
        },
    ]

    async def transcribe(
        self,
        audio_bytes: bytes = b"",
        filename: str = "mock.wav",
        content_type: str = "audio/wav",
        language_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        import random
        scenario = random.choice(self.MOCK_SCENARIOS)
        return {
            "transcript": scenario["transcript"],
            "model": scenario["model"],
            "detected_language": scenario["detected_language"],
            "is_mock": True,
            "request_metadata": {
                "request_id": "DEMO-MOCK-TRANSCRIPT-001",
                "processing_time": 0.12,
                "end_to_end_latency": 0.15,
                "mode": "demo_simulated",
            },
        }

    def get_provider_name(self) -> str:
        return "MockTranscription [DEMO]"

    def get_mock_scenario(self, index: int | None = None) -> dict:
        import random
        if index is not None and 0 <= index < len(self.MOCK_SCENARIOS):
            return self.MOCK_SCENARIOS[index]
        return random.choice(self.MOCK_SCENARIOS)

    def extract_fields(self, scenario: dict) -> Tuple[list[ClaimField], list[str]]:
        transcript = scenario.get("transcript", "")
        return extract_claim_fields(transcript)


# ── Multilingual Field Questions ─────────────────────────────
FIELD_QUESTIONS = {
    "policy_reference": {
        "label": "Policy Reference",
        "question": "Aapka policy number kya hai? / మీ పాలసీ నంబర్ చెప్పండి. (What is your policy number?)",
    },
    "incident_location": {
        "label": "Incident Location",
        "question": "Accident kahan hua tha? / యాక్సిడెంట్ ఎక్కడ జరిగింది? (Where did the accident happen?)",
    },
    "incident_date": {
        "label": "Incident Date",
        "question": "Accident kab hua? Date bataiye. / ఎప్పుడు యాక్సిడెంట్ అయింది? తేదీ చెప్పండి. (When did the accident happen?)",
    },
    "vehicle_type": {
        "label": "Vehicle Type",
        "question": "Aapki gaadi ka type kya hai – car, bike, auto? / మీ వెహికల్ టైప్ ఏంటి? (What type of vehicle?)",
    },
    "damage_description": {
        "label": "Damage Description",
        "question": "Gaadi mein kya damage hua hai? / వెహికల్ కి ఎలాంటి డ్యామేజ్ అయింది? (Describe the damage.)",
    },
}


def parse_indic_phonetic_policy(text: str) -> Optional[str]:
    """
    Parse policy numbers that are spoken and transcribed phonetically
    in Telugu, Hindi, or other Indic scripts.
    e.g. 'పాలసీ నంబర్ ఎంఓటీ టు థౌజండ్ ట్వంటీ ఫోర్ టీఎస్ నైన్ ఎయిట్ సెవెన్ సిక్స్ ఫైవ్'
         -> 'MOT-2024-TS-98765'
    """
    # Look for policy keyword in Telugu, Hindi, or English
    has_policy_kw = any(k in text.lower() for k in ["పాలసీ", "పాలిసీ", "పాలసి", "पॉलिसी", "पालिसी", "policy"])
    if not has_policy_kw:
        return None

    # Extract text after policy keyword
    m = re.search(r"(?:పాలసీ|పాలిసీ|పాలసి|पॉलिसी|पालिसी|policy)\s*(?:నంబర్|నెంబర్|నెం|नंबर|number|no\.?)?\s*[:\-]?\s*([^\.]+)", text, re.IGNORECASE)
    if not m:
        return None

    seg = m.group(1).strip()

    # Multi-word number substitutions
    subs = [
        ("టు థౌజండ్ ట్వంటీ ఫోర్", "2024"),
        ("టూ థౌజండ్ ట్వంటీ ఫోర్", "2024"),
        ("టూ థౌసండ్ ట్వంటీ ఫోర్", "2024"),
        ("టు థౌజండ్ ట్వంటీ ఫైవ్", "2025"),
        ("టూ థౌజండ్ ట్వంటీ ఫైవ్", "2025"),
        ("రెండు వేల ఇరవై నాలుగు", "2024"),
        ("రెండు వేల ఇరవై ఐదు", "2025"),
        ("टू थाउजेंड ट्वेंटी फोर", "2024"),
        ("दो हजार चौबीस", "2024"),
        # Letters & state abbreviations
        ("ఎంఓటీ", "MOT"), ("ఎంఓటి", "MOT"), ("ఎమ్ఓటీ", "MOT"), ("ఎమ్ఒటి", "MOT"), ("एमओटी", "MOT"),
        ("టీఎస్", "TS"), ("టిఎస్", "TS"), ("टीएस", "TS"),
        ("ఎంహెచ్", "MH"), ("एमएच", "MH"),
        ("డిఎల్", "DL"), ("डीएल", "DL"),
        ("ఎపి", "AP"), ("ఏపీ", "AP"), ("एपी", "AP"),
        ("కెఎ", "KA"), ("केए", "KA"),
        ("టిఎన్", "TN"), ("TN", "TN"),
        ("పిఒఎల్", "POL"), ("పివోఎల్", "POL"), ("పీవోఎల్", "POL"), ("पीओएल", "POL"),
        # Individual single digits
        ("నైన్", "9"), ("ఎయిట్", "8"), ("సెవెన్", "7"), ("సిక్స్", "6"), ("ఫైవ్", "5"),
        ("ఫోర్", "4"), ("త్రీ", "3"), ("టూ", "2"), ("టు", "2"), ("వన్", "1"), ("జీరో", "0"),
        ("తొమ్మిది", "9"), ("ఎనిమిది", "8"), ("ఏడు", "7"), ("ఆరు", "6"), ("ఐదు", "5"),
        ("నాలుగు", "4"), ("మూడు", "3"), ("రెండు", "2"), ("ఒకటి", "1"), ("సున్నా", "0"),
        ("नाइन", "9"), ("एट", "8"), ("सेवन", "7"), ("सिक्स", "6"), ("फाइव", "5"),
        ("फोर", "4"), ("थ्री", "3"), ("टू", "2"), ("वन", "1"), ("जीरो", "0"),
    ]

    for k, v in subs:
        seg = seg.replace(k, f" {v} ")

    # Single phonetic English alphabet letters in Telugu
    letter_map = {
        "ఎం": "M", "ఎమ్": "M", "ఓ": "O", "ఒ": "O", "టీ": "T", "టి": "T", "ఎస్": "S",
        "పి": "P", "పీ": "P", "ఎల్": "L", "బి": "B", "బీ": "B", "కె": "K", "డి": "D", "డీ": "D",
        "ఆర్": "R", "ఎన్": "N", "హెచ్": "H", "ఎ": "A", "ఏ": "A", "సి": "C", "సీ": "C",
    }
    for k, v in letter_map.items():
        seg = seg.replace(k, f" {v} ")

    tokens = [t for t in re.split(r"[\s\-]+", seg) if t and re.match(r"^[A-Za-z0-9]+$", t)]

    # Group consecutive single digits: ['MOT', '2024', 'TS', '9', '8', '7', '6', '5'] -> ['MOT', '2024', 'TS', '98765']
    grouped = []
    digit_buffer = ""
    for t in tokens:
        if len(t) == 1 and t.isdigit():
            digit_buffer += t
        else:
            if digit_buffer:
                grouped.append(digit_buffer)
                digit_buffer = ""
            grouped.append(t)
    if digit_buffer:
        grouped.append(digit_buffer)

    if grouped and len(grouped) >= 2:
        return "-".join(grouped)

    return None


def extract_claim_fields(transcript: str) -> Tuple[list[ClaimField], list[str]]:
    """
    Intelligently extract structured claim fields from English, Hinglish, Telugu (Tenglish),
    and other Indic language transcripts.
    Identifies missing/uncertain fields and assigns follow-up questions.
    """
    text = transcript or ""
    text_lower = text.lower()

    fields_dict: Dict[str, Tuple[Optional[str], FieldConfidence]] = {}

    # ── 1. Policy Reference ──
    # A) Check explicit Latin policy like: policy number POL-BK-2024-DL-55123 or MOT-2024-TS-98765
    policy_explicit = re.search(
        r"policy\s*(?:number|no\.?|reference)?\s*(?:hai|is)?\s*[:\-]?\s*([A-Za-z0-9\-]+)",
        text,
        re.IGNORECASE,
    )
    if policy_explicit and len(policy_explicit.group(1).strip()) >= 5:
        fields_dict["policy_reference"] = (
            policy_explicit.group(1).strip().upper(),
            FieldConfidence.HIGH,
        )
    else:
        # B) Check standard alphanumeric pattern with hyphens (e.g. MOT-2024-MH-78432)
        policy_pattern = re.search(
            r"\b((?=[A-Za-z0-9\-]*\d)(?=[A-Za-z0-9\-]*[A-Za-z])[A-Za-z0-9]{2,5}(?:-[A-Za-z0-9]{2,6}){1,4})\b",
            text,
        )
        if policy_pattern:
            fields_dict["policy_reference"] = (
                policy_pattern.group(1).strip().upper(),
                FieldConfidence.HIGH,
            )
        else:
            # C) Check Telugu/Hindi phonetic policy (e.g. ఎంఓటీ టు థౌజండ్ ట్వంటీ ఫోర్ టీఎస్ నైన్ ఎయిట్ సెవెన్ సిక్స్ ఫైవ్)
            indic_policy = parse_indic_phonetic_policy(text)
            if indic_policy:
                fields_dict["policy_reference"] = (indic_policy, FieldConfidence.HIGH)
            elif any(k in text_lower for k in ["policy", "పాలసీ", "पॉलिसी"]):
                fields_dict["policy_reference"] = (None, FieldConfidence.LOW)
            else:
                fields_dict["policy_reference"] = (None, FieldConfidence.MISSING)

    # ── 2. Vehicle Type ──
    # Check possessive phrasing first: "naa car", "meri car", "apni bike", etc.
    possessive_match = re.search(
        r"(?:meri|apni|mera|apna|my|naa|maa|మా|నా)\s+(bike|motorcycle|scooter|activa|car|gaadi|gadi|truck|auto|rickshaw|కార్|కారు|బైక్|బైకు|ఆటో|లారీ)",
        text_lower,
    )
    if possessive_match:
        v = possessive_match.group(1)
        if v in ["bike", "motorcycle", "scooter", "activa", "బైక్", "బైకు"]:
            fields_dict["vehicle_type"] = ("bike", FieldConfidence.HIGH)
        elif v in ["car", "gaadi", "gadi", "కార్", "కారు"]:
            fields_dict["vehicle_type"] = ("car", FieldConfidence.HIGH)
        elif v in ["truck", "లారీ"]:
            fields_dict["vehicle_type"] = ("truck", FieldConfidence.HIGH)
        elif v in ["auto", "rickshaw", "ఆటో"]:
            fields_dict["vehicle_type"] = ("auto_rickshaw", FieldConfidence.HIGH)
    # Check direct vehicle keywords in English, Telugu, Hindi
    elif any(k in text_lower for k in ["car", "motor car", "gaadi", "gadi", "sedan", "suv", "కార్", "కారు", "మోటార్ కారు", "कार", "गाड़ी"]):
        fields_dict["vehicle_type"] = ("car", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["bike", "motorcycle", "scooter", "activa", "two wheeler", "బైక్", "బైకు", "మోటార్ సైకిల్", "స్కూటర్", "యాక్టివా", "बाइक"]):
        fields_dict["vehicle_type"] = ("bike", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["truck", "lorry", "లారీ", "ట్రక్", "ట్రక్కు", "ट्रक"]):
        fields_dict["vehicle_type"] = ("truck", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["auto", "rickshaw", "auto-rickshaw", "ఆటో", "ఆటో రిక్షా", "రిక్షా", "ऑटो"]):
        fields_dict["vehicle_type"] = ("auto_rickshaw", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["bus", "బస్సు", "बस"]):
        fields_dict["vehicle_type"] = ("bus", FieldConfidence.HIGH)
    else:
        fields_dict["vehicle_type"] = (None, FieldConfidence.MISSING)

    # ── 3. Incident Location ──
    # Check Indian cities and major areas in English & Telugu
    known_locations = [
        # Hyderabad / Telangana
        ("హైదరాబాద్", "మధురాపూర్", "Madhapur, Hyderabad"),
        ("హైదరాబాదు", "మధురాపూర్", "Madhapur, Hyderabad"),
        ("హైదరాబాద్", "మాదాపూర్", "Madhapur, Hyderabad"),
        ("హైదరాబాదు", "మాదాపూర్", "Madhapur, Hyderabad"),
        ("hyderabad", "madhapur", "Madhapur, Hyderabad"),
        ("hyderabad", "hitec city", "Hitec City, Hyderabad"),
        ("హైదరాబాద్", "హైటెక్ సిటీ", "Hitec City, Hyderabad"),
        ("hyderabad", "gachibowli", "Gachibowli, Hyderabad"),
        ("హైదరాబాద్", "గచ్చిబౌలి", "Gachibowli, Hyderabad"),
        ("hyderabad", "banjara hills", "Banjara Hills, Hyderabad"),
        ("హైదరాబాద్", "బంజారా హిల్స్", "Banjara Hills, Hyderabad"),
        ("hyderabad", "secunderabad", "Secunderabad, Hyderabad"),
        ("హైదరాబాద్", "సికింద్రాబాద్", "Secunderabad, Hyderabad"),
        ("hyderabad", "", "Hyderabad"),
        ("హైదరాబాద్", "", "Hyderabad"),
        ("హైదరాబాదు", "", "Hyderabad"),
        ("madhapur", "", "Madhapur, Hyderabad"),
        ("మధురాపూర్", "", "Madhapur, Hyderabad"),
        ("మాదాపూర్", "", "Madhapur, Hyderabad"),
        ("gachibowli", "", "Gachibowli, Hyderabad"),
        ("గచ్చిబౌలి", "", "Gachibowli, Hyderabad"),
        ("kukatpally", "", "Kukatpally, Hyderabad"),
        ("కూకట్‌పల్లి", "", "Kukatpally, Hyderabad"),
        ("warangal", "", "Warangal"),
        ("వరంగల్", "", "Warangal"),
        # Andhra Pradesh
        ("vijayawada", "benz circle", "Benz Circle, Vijayawada"),
        ("విజయవాడ", "బెంజ్ సర్కిల్", "Benz Circle, Vijayawada"),
        ("vijayawada", "", "Vijayawada"),
        ("విజయవాడ", "", "Vijayawada"),
        ("visakhapatnam", "", "Visakhapatnam"),
        ("విశాఖపట్నం", "", "Visakhapatnam"),
        ("vizag", "", "Vizag"),
        ("వైజాగ్", "", "Vizag"),
        # Mumbai / Maharashtra
        ("mumbai", "andheri east", "Andheri East, Mumbai"),
        ("mumbai", "andheri", "Andheri East, Mumbai"),
        ("ముంబై", "అంధేరి", "Andheri East, Mumbai"),
        ("मुंबई", "अंधेरी", "Andheri East, Mumbai"),
        ("mumbai", "", "Mumbai"),
        ("ముంబై", "", "Mumbai"),
        ("मुंबई", "", "Mumbai"),
        ("andheri", "", "Andheri East, Mumbai"),
        ("pune", "hinjewadi", "Hinjewadi Road, Pune"),
        ("పూణే", "హింజేవాడి", "Hinjewadi Road, Pune"),
        ("pune", "", "Pune"),
        ("పూణే", "", "Pune"),
        # Delhi
        ("delhi", "connaught place", "Connaught Place, Delhi"),
        ("ఢిల్లీ", "కన్నాట్ ప్లేస్", "Connaught Place, Delhi"),
        ("दिल्ली", "कनॉट प्लेस", "Connaught Place, Delhi"),
        ("delhi", "", "Delhi"),
        ("ఢిల్లీ", "", "Delhi"),
        ("connaught place", "", "Connaught Place, Delhi"),
        # Other Metros
        ("bangalore", "", "Bangalore"),
        ("bengaluru", "", "Bengaluru"),
        ("బెంగళూరు", "", "Bengaluru"),
        ("chennai", "", "Chennai"),
        ("చెన్నై", "", "Chennai"),
        ("kolkata", "", "Kolkata"),
    ]

    matched_loc = None
    for city_term, area_term, resolved_name in known_locations:
        has_city = city_term.lower() in text_lower or city_term in text
        has_area = (area_term.lower() in text_lower or area_term in text) if area_term else True
        if has_city and has_area:
            matched_loc = resolved_name
            break

    if matched_loc:
        fields_dict["incident_location"] = (matched_loc, FieldConfidence.HIGH)
    else:
        # Check prepositions in English, Hindi, and Telugu
        loc_re = re.search(
            r"([\w\s\u0C00-\u0C7F\u0900-\u097F]{3,30}?)\s+(?:mein|me|road pe|ke paas|near|lo|deggara|దగ్గర|లో|में|के पास)\b",
            text,
            re.IGNORECASE,
        )
        if loc_re and len(loc_re.group(1).strip()) > 2:
            fields_dict["incident_location"] = (loc_re.group(1).strip().title(), FieldConfidence.MEDIUM)
        else:
            fields_dict["incident_location"] = (None, FieldConfidence.MISSING)

    # ── 4. Incident Date ──
    # Check compound expressions in English, Telugu, Hindi
    if any(k in text_lower for k in ["ninna evening", "నిన్న సాయంత్రం", "నిన్న సాయంకాలం", "kal shaam", "yesterday evening"]):
        fields_dict["incident_date"] = ("yesterday evening", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["ninna afternoon", "నిన్న మధ్యాహ్నం", "kal dopahar", "yesterday afternoon"]):
        fields_dict["incident_date"] = ("yesterday afternoon", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["ninna morning", "నిన్న ఉదయం", "kal subah", "yesterday morning"]):
        fields_dict["incident_date"] = ("yesterday morning", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["ninna night", "నిన్న రాత్రి", "kal raat", "yesterday night"]):
        fields_dict["incident_date"] = ("yesterday night", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["kal", "yesterday", "ninna", "నిన్న"]):
        fields_dict["incident_date"] = ("yesterday", FieldConfidence.MEDIUM)
    elif any(k in text_lower for k in ["aaj subah", "today morning", "ee roju udayam", "ఈ రోజు ఉదయం", "ఈరోజు ఉదయం"]):
        fields_dict["incident_date"] = ("today morning", FieldConfidence.MEDIUM)
    elif any(k in text_lower for k in ["aaj", "today", "ee roju", "eeraju", "ఈ రోజు", "ఈరోజు"]):
        fields_dict["incident_date"] = ("today", FieldConfidence.MEDIUM)
    else:
        # Check standard date formats or time expressions (e.g. 5:30 PM, 28th Oct, etc.)
        date_re = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", text)
        time_re = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM|గంటలకు|బజే))\b", text)
        if date_re and time_re:
            fields_dict["incident_date"] = (f"{date_re.group(1)} {time_re.group(1)}", FieldConfidence.HIGH)
        elif date_re:
            fields_dict["incident_date"] = (date_re.group(1), FieldConfidence.HIGH)
        elif time_re:
            fields_dict["incident_date"] = (time_re.group(1), FieldConfidence.MEDIUM)
        else:
            fields_dict["incident_date"] = (None, FieldConfidence.MISSING)

    # ── 5. Damage Description ──
    damage_indicators = [
        # English / Hinglish
        "damage", "tut gaya", "pichak gaya", "crushed", "broken", "hit", "leak",
        "fender", "door", "bonnet", "bumper", "headlight", "mudguard", "radiator", "scratch",
        # Telugu
        "డ్యామేజ్", "డామేజ్", "లెఫ్ట్ డోర్", "రైట్ డోర్", "డోర్", "బంపర్", "మడ్ గార్డ్", "మడ్‌గార్డ్",
        "హెడ్‌లైట్", "బోనెట్", "హిట్", "గుద్దింది", "పగిలిపోయింది", "ఇరిగిపోయింది", "యాక్సిడెంట్",
        "బాగా డ్యామేజ్",
        # Hindi
        "डैमेज", "नुकसान", "टूट गया", "पिचक गया", "टक्कर", "दरवाजा", "बंपर"
    ]
    found_damages = [ind for ind in damage_indicators if ind in text_lower or ind in text]
    if found_damages:
        # Extract sentence or clause containing damage
        clauses = re.split(r"[।\.\n,]", text)
        damage_clauses = [c.strip() for c in clauses if any(d in c.lower() or d in c for d in found_damages)]
        desc = "; ".join(damage_clauses) if damage_clauses else "Damage reported: " + ", ".join(found_damages[:3])
        fields_dict["damage_description"] = (desc[:200], FieldConfidence.HIGH)
    else:
        if any(k in text_lower for k in ["accident", "యాక్సిడెంట్", "एक्सीडेंट"]):
            fields_dict["damage_description"] = ("Accident reported, details pending", FieldConfidence.LOW)
        else:
            fields_dict["damage_description"] = (None, FieldConfidence.MISSING)

    # Assemble ClaimField list and identify missing
    fields: list[ClaimField] = []
    missing_fields: list[str] = []

    for name, meta in FIELD_QUESTIONS.items():
        val, conf = fields_dict.get(name, (None, FieldConfidence.MISSING))
        follow_up = meta["question"] if conf in (FieldConfidence.MISSING, FieldConfidence.LOW) else None
        if conf == FieldConfidence.MISSING:
            missing_fields.append(name)
        fields.append(
            ClaimField(
                name=name,
                label=meta["label"],
                value=val,
                confidence=conf,
                is_edited=False,
                follow_up_question=follow_up,
            )
        )

    return fields, missing_fields


def generate_assistant_dialogue(
    transcript: str,
    fields: list[ClaimField],
    missing_fields: list[str],
    detected_language: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate a natural, human-like voice assistant response in the speaker's language.
    Acknowledges already extracted fields and asks ONLY for missing fields.
    Never asks for details that were already provided.
    """
    text = transcript or ""

    # Detect language/script: Telugu, Hindi, or English
    has_telugu = any(0x0C00 <= ord(c) <= 0x0C7F for c in text) or (detected_language or "").startswith("te")
    has_hindi = any(0x0900 <= ord(c) <= 0x097F for c in text) or (detected_language or "").startswith("hi")

    if has_telugu:
        lang = "te-IN"
    elif has_hindi:
        lang = "hi-IN"
    else:
        lang = "en-IN"

    fmap = {f.name: f.value for f in fields if f.value and f.confidence != FieldConfidence.MISSING}
    pol = fmap.get("policy_reference")
    veh = fmap.get("vehicle_type")
    loc = fmap.get("incident_location")
    date = fmap.get("incident_date")
    dam = fmap.get("damage_description")

    # CASE A: All 5 fields are completely filled
    if not missing_fields:
        if lang == "te-IN":
            dialogue = (
                f"ధన్యవాదాలు! మీ క్లెయిమ్ కి సంబంధించిన వివరాలు విజయవంతంగా నమోదయ్యాయి: "
                f"పాలసీ {pol or 'వెరిఫైడ్'}, {veh or 'వాహనం'}, లొకేషన్ {loc or 'నమోదైంది'}, తేదీ {date or 'నమోదైంది'}. "
                f"దయచేసి క్లెయిమ్ టికెట్ ని కన్ఫర్మ్ చేయండి."
            )
        elif lang == "hi-IN":
            dialogue = (
                f"धन्यवाद! आपके क्लेम के सभी विवरण दर्ज हो चुके हैं: "
                f"पॉलिसी {pol or 'सत्यापित'}, गाड़ी {veh or 'वाहन'}, स्थान {loc or 'दर्ज'}, तारीख {date or 'दर्ज'}। "
                f"कृपया क्लेम टिकट कन्फर्म करें।"
            )
        else:
            dialogue = (
                f"Thank you! All claim details have been recorded: "
                f"Policy {pol or 'verified'}, vehicle {veh or 'car'}, location {loc or 'verified'}, and date {date or 'recorded'}. "
                f"Please review and confirm your claim ticket."
            )
        return {
            "display_text": dialogue,
            "speech_text": dialogue,
            "language": lang,
        }

    # CASE B: One or more fields are missing -> acknowledge captured fields and ask ONLY missing
    next_missing = missing_fields[0]

    if lang == "te-IN":
        ack_parts = []
        if pol:
            ack_parts.append(f"పాలసీ నంబర్ {pol}")
        if veh:
            ack_parts.append(f"{veh}")
        if loc:
            ack_parts.append(f"{loc}")
        if dam:
            ack_parts.append("డ్యామేజ్ వివరాలు")

        if ack_parts:
            ack = f"మీ {', '.join(ack_parts)} గుర్తించబడ్డాయి."
        else:
            ack = "మీరు చెప్పిన సమాచారం నమోదైంది."

        questions_te = {
            "incident_date": "యాక్సిడెంట్ ఏ రోజు లేదా ఏ సమయానికి జరిగింది? తేదీ లేదా సమయం చెప్పండి.",
            "policy_reference": "మీ పాలసీ నంబర్ చెప్పండి.",
            "incident_location": "యాక్సిడెంట్ ఏ ప్రాంతంలో లేదా నగరంలో జరిగింది?",
            "vehicle_type": "మీ వాహనం రకం ఏంటి - కార్, బైక్ లేదా ఇతర వాహనమా?",
            "damage_description": "వాహనానికి ఎలాంటి నష్టం లేదా డ్యామేజ్ జరిగింది?",
        }
        q = questions_te.get(next_missing, "దయచేసి మిగిలిన వివరాలు చెప్పండి.")
        full_dialogue = f"{ack} {q}"

    elif lang == "hi-IN":
        ack_parts = []
        if pol:
            ack_parts.append(f"पॉलिसी {pol}")
        if veh:
            ack_parts.append(f"गाड़ी {veh}")
        if loc:
            ack_parts.append(f"स्थान {loc}")
        if dam:
            ack_parts.append("डैमेज की जानकारी")

        if ack_parts:
            ack = f"आपकी {', '.join(ack_parts)} की जानकारी दर्ज हो चुकी है।"
        else:
            ack = "आपकी जानकारी दर्ज कर ली गई है।"

        questions_hi = {
            "incident_date": "हादसा कब हुआ था? कृपया तारीख या समय बताएं।",
            "policy_reference": "कृपया अपना पॉलिसी नंबर बताएं।",
            "incident_location": "हादसा किस जगह या शहर में हुआ था?",
            "vehicle_type": "आपकी गाड़ी का प्रकार क्या है - कार, बाइक या अन्य?",
            "damage_description": "गाड़ी में क्या नुकसान हुआ है? कृपया बताएं।",
        }
        q = questions_hi.get(next_missing, "कृपया बाकी जानकारी बताएं।")
        full_dialogue = f"{ack} {q}"

    else:
        ack_parts = []
        if pol:
            ack_parts.append(f"policy {pol}")
        if veh:
            ack_parts.append(f"vehicle {veh}")
        if loc:
            ack_parts.append(f"location at {loc}")
        if dam:
            ack_parts.append("damage details")

        if ack_parts:
            ack = f"I have noted your {', '.join(ack_parts)}."
        else:
            ack = "I have received your initial claim intake."

        questions_en = {
            "incident_date": "When did this accident happen? Please state the date or time.",
            "policy_reference": "What is your policy reference number?",
            "incident_location": "Where did the accident take place? Please state the location or city.",
            "vehicle_type": "What type of vehicle was involved?",
            "damage_description": "Please describe the damage to your vehicle.",
        }
        q = questions_en.get(next_missing, "Please provide the missing details.")
        full_dialogue = f"{ack} {q}"

    return {
        "display_text": full_dialogue,
        "speech_text": full_dialogue,
        "language": lang,
    }
