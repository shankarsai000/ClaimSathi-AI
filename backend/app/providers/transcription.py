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


# ── Multilingual Field Questions (Per-Language + Bilingual Display) ─────────
FIELD_QUESTIONS = {
    "policy_reference": {
        "label": "Policy / Vehicle Number",
        "question": "Aapka policy ya gaadi number kya hai? / మీ పాలసీ లేదా వాహన నంబర్ చెప్పండి. (What is your policy or vehicle number?)",
        "by_lang": {
            "te-IN": "మీ పాలసీ నంబర్ లేదా వాహన రిజిస్ట్రేషన్ నంబర్ (ఉదా: TS-09-EA-4590) చెప్పండి.",
            "kn-IN": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಪಾಲಿಸಿ ನಂಬರ್ ಅಥವಾ ವಾಹನದ ನೋಂದಣಿ ಸಂಖ್ಯೆ (ಉదా: KA-17-EA-4590) ಹೇಳಿ.",
            "hi-IN": "कृपया अपना पॉलिसी नंबर या गाड़ी का रजिस्ट्रेशन नंबर बताएं।",
            "ta-IN": "தயவுசெய்து உங்கள் பாலிசி எண் அல்லது வாகனப் பதிவு எண்ணைச் சொல்லுங்கள்.",
            "mr-IN": "कृपया तुमचा पॉलिसी नंबर किंवा वाहन नोंदणी क्रमांक सांगा.",
            "en-IN": "What is your Policy Number or Vehicle Registration Number (e.g. KA-17-EA-4590)?",
        },
    },
    "incident_location": {
        "label": "Incident Location",
        "question": "Accident kahan hua tha? / యాక్సిడెంట్ ఎక్కడ జరిగింది? (Where did the accident happen?)",
        "by_lang": {
            "te-IN": "యాక్సిడెంట్ ఏ ప్రాంతంలో లేదా నగరంలో జరిగింది?",
            "kn-IN": "ಅಪಘಾತ ಯಾವ ಸ್ಥಳದಲ್ಲಿ ಅಥವಾ ನಗರದಲ್ಲಿ ನಡೆಯಿತು?",
            "hi-IN": "हादसा किस जगह या शहर में हुआ था?",
            "ta-IN": "விபத்து எந்த இடத்தில் அல்லது நகரத்தில் நடந்தது?",
            "mr-IN": "अपघात कोणत्या ठिकाणी किंवा शहरात झाला?",
            "en-IN": "Where did the accident take place? Please state the location or city.",
        },
    },
    "incident_date": {
        "label": "Incident Date",
        "question": "Accident kab hua? Date bataiye. / ఎప్పుడు యాక్సిడెంట్ అయింది? తేదీ చెప్పండి. (When did the accident happen?)",
        "by_lang": {
            "te-IN": "యాక్సిడెంట్ ఏ రోజు లేదా ఏ సమయానికి జరిగింది? తేదీ లేదా సమయం చెప్పండి.",
            "kn-IN": "ಅಪಘಾತ ಯಾವ ದಿನ ಅಥವಾ ಯಾವ ಸಮಯಕ್ಕೆ ನಡೆಯಿತು? ದಿನಾಂಕ ಅಥವಾ ಸಮಯ ಹೇಳಿ.",
            "hi-IN": "हादसा कब हुआ था? कृपया तारीख या समय बताएं।",
            "ta-IN": "விபத்து எப்போது நடந்தது? தேதி அல்லது நேரத்தைச் சொல்லுங்கள்.",
            "mr-IN": "अपघात कधी झाला? कृपया तारीख किंवा वेळ सांगा.",
            "en-IN": "When did this accident happen? Please state the date or time.",
        },
    },
    "vehicle_type": {
        "label": "Vehicle Type",
        "question": "Aapki gaadi ka type kya hai – car, bike, auto? / మీ వెహికల్ టైప్ ఏంటి? (What type of vehicle?)",
        "by_lang": {
            "te-IN": "మీ వాహనం రకం ఏంటి - కార్, బైక్ లేదా ఇతర వాహనమా?",
            "kn-IN": "ನಿಮ್ಮ ವಾಹನದ ಪ್ರಕಾರ ಯಾವುದು - ಕಾರ್, ಬೈಕ್ ಅಥವಾ ಇತರ ವಾಹನವೇ?",
            "hi-IN": "आपकी गाड़ी का प्रकार क्या है - कार, बाइक या अन्य?",
            "ta-IN": "உங்கள் வாகனத்தின் வகை என்ன - கார், பைக் அல்லது மற்றதா?",
            "mr-IN": "तुमच्या वाहनाचा प्रकार कोणता आहे - कार, बाईक की इतर?",
            "en-IN": "What type of vehicle was involved (car, bike, auto, truck)?",
        },
    },
    "damage_description": {
        "label": "Damage Description",
        "question": "Gaadi mein kya damage hua hai? / వెహికల్ కి ఎలాంటి డ్యామేజ్ అయింది? (Describe the damage.)",
        "by_lang": {
            "te-IN": "వాహనానికి ఎలాంటి నష్టం లేదా డ్యామేజ్ జరిగింది?",
            "kn-IN": "ವಾಹನಕ್ಕೆ ಯಾವ ರೀತಿಯ ಹಾನಿ ಅಥವಾ ಡ್ಯಾಮೇಜ್ ಆಗಿದೆ?",
            "hi-IN": "गाड़ी में क्या नुकसान हुआ है? कृपया बताएं।",
            "ta-IN": "வாகனத்திற்கு என்ன சேதம் ஏற்பட்டுள்ளது?",
            "mr-IN": "वाहनाचे काय नुकसान झाले आहे? कृपया सांगा.",
            "en-IN": "Please describe the damage to your vehicle.",
        },
    },
}


def transliterate_indic_to_english(text: str) -> str:
    """
    Convert any remaining Telugu, Kannada, Devanagari (Hindi/Marathi), or Tamil script
    into clean English Roman characters so all insurer-facing fields are 100% in English.
    """
    if not text:
        return ""
    # Common whole-word dictionary first
    word_map = {
        "హైదరాబాద్": "Hyderabad", "హైదరాబాదు": "Hyderabad", "మధురాపూర్": "Madhapur", "మాదాపూర్": "Madhapur",
        "గచ్చిబౌలి": "Gachibowli", "కూకట్‌పల్లి": "Kukatpally", "కూకట్పల్లి": "Kukatpally", "సికింద్రాబాద్": "Secunderabad",
        "బంజారా హిల్స్": "Banjara Hills", "జూబ్లీ హిల్స్": "Jubilee Hills", "అమీర్‌పేట్": "Ameerpet",
        "విజయవాడ": "Vijayawada", "విశాఖపట్నం": "Visakhapatnam", "వైజాగ్": "Vizag", "వరంగల్": "Warangal",
        "గుంటూరు": "Guntur", "తిరుపతి": "Tirupati", "నెల్లూరు": "Nellore", "కర్నూలు": "Kurnool",
        "బెంగళూరు": "Bengaluru", "దావణగెరె": "Davanagere", "చెన్నై": "Chennai", "ముంబై": "Mumbai", "ఢిల్లీ": "Delhi", "పూణే": "Pune",
        "ದಾವಣಗೆರೆ": "Davanagere", "ಬೆಂಗಳೂರು": "Bengaluru", "ಮೈಸೂರು": "Mysuru", "ಹುಬ್ಬಳ್ಳಿ": "Hubballi",
        "ಧಾರವಾಡ": "Dharwad", "ಮಂಗಳೂರು": "Mangaluru", "ಬೆಳಗಾವಿ": "Belagavi", "ಶಿವಮೊಗ್ಗ": "Shivamogga",
        "ತುಮಕೂರು": "Tumakuru", "ಬಳ್ಳಾರಿ": "Ballari", "ಉಡುಪಿ": "Udupi", "ಹಾಸನ": "Hassan", "ಕಲಬುರಗಿ": "Kalaburagi",
        "मुंबई": "Mumbai", "दिल्ली": "Delhi", "पुणे": "Pune", "अंधेरी": "Andheri", "कोथरूड": "Kothrud",
        "சென்னை": "Chennai", "அண்ணா நகர்": "Anna Nagar", "கோயம்புத்தூர்": "Coimbatore", "மதுரை": "Madurai",
    }
    res = text
    for k, v in word_map.items():
        res = res.replace(k, v)

    # Phonetic consonant + vowel transliteration for any remaining Indic characters
    out = []
    for ch in res:
        code = ord(ch)
        if code < 128:
            out.append(ch)
            continue
        # Offset within Indic block (Telugu 0x0C00, Kannada 0x0C80, Devanagari 0x0900, Tamil 0x0B80)
        offset = None
        if 0x0C00 <= code <= 0x0C7F:
            offset = code - 0x0C00
        elif 0x0C80 <= code <= 0x0CFF:
            offset = code - 0x0C80
        elif 0x0900 <= code <= 0x097F:
            offset = code - 0x0900
        elif 0x0B80 <= code <= 0x0BFF:
            offset = code - 0x0B80

        if offset is not None:
            indic_offset_map = {
                0x02: "n", 0x05: "a", 0x06: "aa", 0x07: "i", 0x08: "ee", 0x09: "u", 0x0A: "oo",
                0x0E: "e", 0x0F: "e", 0x10: "ai", 0x12: "o", 0x13: "o", 0x14: "au",
                0x15: "ka", 0x16: "kha", 0x17: "ga", 0x18: "gha", 0x1A: "cha", 0x1B: "chha",
                0x1C: "ja", 0x1F: "ta", 0x20: "tha", 0x21: "da", 0x22: "dha", 0x23: "na",
                0x24: "ta", 0x25: "tha", 0x26: "da", 0x27: "dha", 0x28: "na", 0x29: "na",
                0x2A: "pa", 0x2B: "pha", 0x2C: "ba", 0x2D: "bha", 0x2E: "ma",
                0x2F: "ya", 0x30: "ra", 0x31: "ra", 0x32: "la", 0x33: "la", 0x35: "va",
                0x36: "sha", 0x37: "sha", 0x38: "sa", 0x39: "ha",
                0x3E: "a", 0x3F: "i", 0x40: "ee", 0x41: "u", 0x42: "oo", 0x46: "e", 0x47: "e",
                0x48: "ai", 0x4A: "o", 0x4B: "o", 0x4C: "au", 0x4D: "",
            }
            mapped = indic_offset_map.get(offset, "")
            # If vowel sign follows consonant ending in 'a', replace trailing 'a'
            if offset >= 0x3E and out and out[-1].endswith("a") and len(out[-1]) > 1:
                out[-1] = out[-1][:-1] + mapped
            else:
                out.append(mapped)
    cleaned = re.sub(r"\s+", " ", "".join(out)).strip()
    return cleaned.title() if cleaned else "Reported Location"


def translate_damage_to_english(text: str) -> str:
    """
    Translate and normalize vehicle damage descriptions from Telugu, Kannada, Hindi, Tamil,
    or mixed speech into clean, standardized English for insurance company submission.
    """
    t_low = (text or "").lower()
    parts_found: list[str] = []
    actions_found: list[str] = []

    part_mappings = [
        (["left door", "లెఫ్ట్ డోర్", "ఎడమ డోర్", "ಎಡ ಬಾಗಿಲು", "ಲೆಫ್ಟ್ ಡೋರ್", "बायां दरवाजा", "लेफ्ट डोर", "இடது கதவு"], "Left door"),
        (["right door", "రైట్ డోర్", "కుడి డోర్", "ಬಲ ಬಾಗಿಲು", "ರೈಟ್ ಡೋರ್", "दायां दरवाजा", "राइट डोर", "வலது கதவு"], "Right door"),
        (["door", "డోర్", "తలుపు", "ಡೋರ್", "ಬಾಗಿಲು", "दरवाजा", "डोर", "கதவு"], "Door"),
        (["front bumper", "ఫ్రంట్ బంపర్", "ముందు బంపర్", "ಮುಂದಿನ ಬಂಪರ್", "ಫ್ರಂಟ್ ಬಂಪರ್", "फ्रंट बंपर", "आगे का बंपर", "முன் பம்பர்"], "Front bumper"),
        (["rear bumper", "back bumper", "బ్యాక్ బంపర్", "వెనుక బంపర్", "ಹಿಂದಿನ ಬಂಪರ್", "पीछे का बंपर", "பின் பம்பர்"], "Rear bumper"),
        (["bumper", "బంపర్", "ಬಂಪರ್", "बंपर", "பம்பர்"], "Bumper"),
        (["front mudguard", "ముందు మడ్‌గార్డ్", "ఫ్రంట్ మడ్‌గార్డ్", "ಮುಂದಿನ ಮಡ್‌ಗಾರ್ಡ್", "फ्रंट मडगार्ड"], "Front mudguard"),
        (["mudguard", "మడ్ గార్డ్", "మడ్‌గార్డ్", "ಮಡ್‌ಗಾರ್ಡ್", "मडगार्ड"], "Mudguard"),
        (["headlight", "headlamp", "హెడ్‌లైట్", "హెడ్ లైట్", "హెడ్‌ల్యాంప్", "ಹೆಡ್‌ಲೈಟ್", "हेडलाइट", "ஹெட்லைட்"], "Headlight"),
        (["tail light", "taillight", "బ్యాక్ లైట్", "టెయిల్ లైట్", "ಟೈಲ್ ಲೈಟ್", "बैक लाइट"], "Tail light"),
        (["indicator", "ఇండికేటర్", "ಇಂಡಿಕೇಟರ್", "इंडिकेटर"], "Indicator light"),
        (["fender", "ఫెండర్", "ಫೆಂಡರ್", "फेंडर"], "Fender"),
        (["bonnet", "hood", "బోనెట్", "ಬಾನೆಟ್", "बोनट"], "Bonnet"),
        (["windshield", "windscreen", "glass", "అద్దం", "విండ్‌షీల్డ్", "గాజు", "ಗಾಜು", "ವಿಂಡ್‌ಶೀಲ್ಡ್", "शीशा", "कांच", "கண்ணாடி"], "Windshield glass"),
        (["mirror", "side mirror", "సైడ్ మిర్రర్", "మిర్రర్", "ಮಿರರ್", "मिरर"], "Side mirror"),
        (["wheel", "rim", "tyre", "tire", "చక్రం", "వీల్", "టైర్", "ಚಕ್ರ", "ವೀಲ್", "पहिया", "टायर"], "Wheel / Rim"),
        (["fork", "handle", "హ్యాండిల్", "ఫోర్క్", "ಹ್ಯಾಂಡಲ್", "हैंडल"], "Front fork / Handlebar"),
        (["fuel tank", "tank", "ట్యాంక్", "ಟ್ಯಾಂಕ್", "टैंक"], "Fuel tank"),
        (["radiator", "engine", "ఇంజిన్", "రేడియేటర్", "ಎಂಜಿನ್", "इंजन", "रेडिएटर"], "Engine / Radiator"),
    ]

    for triggers, eng_label in part_mappings:
        if any(tr in t_low or tr in text for tr in triggers):
            # Avoid adding generic 'Door' if 'Left door' or 'Right door' already added
            if eng_label == "Door" and any("door" in p.lower() for p in parts_found):
                continue
            if eng_label == "Bumper" and any("bumper" in p.lower() for p in parts_found):
                continue
            if eng_label == "Mudguard" and any("mudguard" in p.lower() for p in parts_found):
                continue
            if eng_label not in parts_found:
                parts_found.append(eng_label)

    severity_mappings = [
        (["crushed", "full ga damage", "ఫుల్ గా డ్యామేజ్", "బాగా డ్యామేజ్", "شدید", "ಪೂರ್ತಿ ಡ್ಯಾಮೇಜ್", "बहुत नुकसान", "बुरी तरह"], "severely damaged"),
        (["broken", "tut gaya", "పగిలిపోయింది", "పగిలింది", "ఇరిగిపోయింది", "విరిగింది", "ಒಡೆದಿದೆ", "ಮುರಿದಿದೆ", "टूट गया", "உடைந்தது"], "broken / cracked"),
        (["dent", "dented", "pichak", "సొట్ట", "డెంట్", "ಡೆಂಟ್", "पिचक गया", "डेंट"], "dented"),
        (["scratch", "scratched", "గీత", "గీతలు", "స్క్రాచ్", "ಸ್ಕ್ರಾಚ್", "खरोंच"], "scratched"),
        (["side hit", "side lo hit", "సైడ్ లో హిట్", "సైడ్ నుంచి", "ಸೈಡ್ ಇಂದ", "साइड से टक्कर"], "impacted from the side"),
        (["rear hit", "వెనుక నుంచి", "ಹಿಂದಿನಿಂದ", "पीछे से टक्कर"], "impacted from the rear"),
    ]
    for triggers, eng_act in severity_mappings:
        if any(tr in t_low or tr in text for tr in triggers):
            if eng_act not in actions_found:
                actions_found.append(eng_act)

    # Check colliding third-party vehicle context
    collider = ""
    if any(k in t_low or k in text for k in ["oka auto vachi", "ఒక ఆటో వచ్చి", "ఆటో వచ్చి", "auto aaya", "ಆಟೋ ಬಂದು"]):
        collider = " due to auto-rickshaw collision"

    if parts_found:
        parts_str = ", ".join(parts_found[:-1]) + (" and " + parts_found[-1] if len(parts_found) > 1 else parts_found[0])
        act_str = ", ".join(actions_found) if actions_found else "damaged"
        return f"{parts_str} {act_str}{collider}."

    if actions_found:
        return f"Vehicle {', '.join(actions_found)}{collider}."

    # If the user typed in pure English, keep their English text
    has_non_ascii = any(ord(c) > 127 for c in text)
    if not has_non_ascii and len(text.strip()) > 3:
        return text.strip()[:200]

    return f"Vehicle body panel and exterior damaged in road accident{collider}."


def detect_conversation_language(transcript: str, hint_lang: Optional[str] = None) -> str:
    """
    Detect the speaker's language from script characters, Romanized Indic keywords,
    and ASR provider language hints so the system can lock onto the user's language
    from their very first utterance until the end of the session.
    """
    text = (transcript or "").strip()
    text_lower = text.lower()
    hint = (hint_lang or "").strip()

    # 1. Explicit Unicode Script Detection (Highest certainty)
    if any(0x0C00 <= ord(c) <= 0x0C7F for c in text):
        return "te-IN"
    if any(0x0C80 <= ord(c) <= 0x0CFF for c in text):
        return "kn-IN"
    if any(0x0B80 <= ord(c) <= 0x0BFF for c in text):
        return "ta-IN"
    if any(0x0D00 <= ord(c) <= 0x0D7F for c in text):
        return "ml-IN"
    if any(0x0980 <= ord(c) <= 0x09FF for c in text):
        return "bn-IN"
    if any(0x0A80 <= ord(c) <= 0x0AFF for c in text):
        return "gu-IN"
    if any(0x0A00 <= ord(c) <= 0x0A7F for c in text):
        return "pa-IN"
    if any(0x0600 <= ord(c) <= 0x06FF for c in text):
        return "ur-IN"
    if any(0x0900 <= ord(c) <= 0x097F for c in text):
        # Distinguish Marathi vs Hindi in Devanagari
        marathi_markers = ["माझ्या", "माझी", "झाला", "गाडीचा", "काल", "पुण्यात", "कोथरूड", "आहे"]
        if any(m in text for m in marathi_markers) or hint.startswith("mr"):
            return "mr-IN"
        return "hi-IN"

    # 2. If caller explicitly specified a concrete language (not 'indic-auto'), honor it
    if hint and hint.lower() != "indic-auto":
        for prefix in ("te", "kn", "hi", "ta", "mr", "ml", "bn", "gu", "pa", "ur", "en"):
            if hint.lower().startswith(prefix):
                return f"{prefix}-IN"

    # 3. Romanized Indic (Tenglish / Kanglish / Hinglish / Tanglish) Detection when in indic-auto mode
    words = set(re.findall(r"[a-z]+", text_lower))
    tenglish_markers = {"chudandi", "naa", "ayyindi", "aindi", "nenu", "deggara", "daggara", "chesindi", "ninna", "eeroju", "vachi", "gantala", "sayantram"}
    kanglish_markers = {"nanna", "aayitu", "ayitu", "alli", "hattira", "ninne", "ivattu", "maadide", "sanje"}
    hinglish_markers = {"mera", "meri", "apni", "hua", "gaya", "tha", "kal", "aaj", "mein", "paas", "dekhiye", "haan", "shaam", "subah", "tut"}
    tanglish_markers = {"ennoda", "vandi", "aagiduchu", "aachu", "netru", "pakkathula", "indru"}

    if len(words & tenglish_markers) >= 1:
        return "te-IN"
    if len(words & kanglish_markers) >= 1:
        return "kn-IN"
    if len(words & tanglish_markers) >= 1:
        return "ta-IN"
    if len(words & hinglish_markers) >= 2:
        return "hi-IN"

    return "en-IN"


def parse_indic_phonetic_policy(text: str, require_keyword: bool = True) -> Optional[str]:
    """
    Parse policy numbers AND vehicle registration numbers that are spoken and transcribed
    phonetically or with spaces in Telugu, Kannada, Hindi, Tamil, or English.
    Examples handled:
      - 'పాలసీ నంబర్ ఎంఓటీ టు థౌజండ్ ట్వంటీ ఫోర్ టీఎస్ నైన్ ఎయిట్ సెవెన్ సిక్స్ ఫైవ్' -> 'MOT-2024-TS-98765'
      - 'ಕೆ ಎ ಥರ್ಟೀ ಫೋರ್ ಟು ಟ್ವೆಂಟಿ ತ್ರೀ' -> 'KA-34-223'
      - 'KA 17 EA 4590' -> 'KA-17-EA-4590'
      - 'policy number M O T 2024 T S 9 8 7 6 5' -> 'MOT-2024-TS-98765'
    """
    # Reject questions immediately (e.g. 'ಸಿ ಎಂ ಎಂ ಅಂದರೆ ಏನು?' -> 'What is CMM?')
    question_markers = ["?", "ಅಂದರೆ ಏನು", "ಏನು", "అంటే ఏంటి", "ఏంటి", "मतलब क्या", "क्या है", "what is", "meaning"]
    if any(qm in text.lower() for qm in question_markers):
        return None

    policy_kws = [
        "పాలసీ", "పాలిసీ", "పాలసి", "पॉलिसी", "पालिसी", "ಪಾಲಿಸಿ", "பாலிசி", "policy",
        "బండి నంబర్", "కారు నంబర్", "వెహికల్ నంబర్", "గాడి నంబర్", "ಗಾಡಿ ನಂಬರ್", "ವಾಹನ ಸಂಖ್ಯೆ", "ಗಾಡಿ ಸಂಖ್ಯೆ",
        "गाड़ी नंबर", "वाहन नंबर", "vehicle number", "registration number", "gaadi number",
    ]
    has_policy_kw = any(k in text.lower() for k in policy_kws)
    if require_keyword and not has_policy_kw:
        return None

    if has_policy_kw:
        m = re.search(
            r"(?:పాలసీ|పాలిసీ|పాలసి|पॉलिसी|पालिसी|ಪಾಲಿಸಿ|பாலிசி|policy|వెహికల్|గాడి|బండి|ಗಾಡಿ|ವಾಹನ|गाड़ी|vehicle|registration)\s*(?:నంబర్|నెంబర్|నెం|नंबर|ನಂಬರ್|ಸಂಖ್ಯೆ|எண்|number|no\.?|reference|is|hai|అనేది)?\s*[:\-]?\s*([^\.\n।]+)",
            text,
            re.IGNORECASE,
        )
        seg = m.group(1).strip() if m else text.strip()
    else:
        seg = text.strip()

    # Stop at common narrative words that follow the policy/vehicle number in a single sentence
    stop_words = [
        "నేను", "మా", "నా", "హైదరాబాద్", "హైదరాబాదు", "మధురాపూర్", "మాదాపూర్", "నిన్న", "ఈరోజు",
        "డ్రైవ్", "యాక్సిడెంట్", "కారు", "కార్", "బైక్", "ఆటో", "లెఫ్ట్", "రైట్", "బంపర్", "డోర్",
        "nenu", "hyderabad", "madhapur", "main", "when", "while", "yesterday", "today", "front", "left", "right",
        "ಮತ್ತು", "ನಾನು", "ನಿನ್ನೆ", "ದಾವಣಗೆರೆ", "ಬೆಂಗಳೂರು", "मैं", "मेरी", "कल",
    ]
    for sw in stop_words:
        idx = seg.lower().find(f" {sw.lower()}")
        if idx > 3:
            seg = seg[:idx].strip()

    # Multi-word number & prefix substitutions (Telugu, Kannada, Hindi, English)
    subs = [
        # Years (2024, 2025, 2026)
        ("టు థౌజండ్ ట్వంటీ ఫోర్", "2024"), ("టూ థౌజండ్ ట్వంటీ ఫోర్", "2024"),
        ("టూ థౌసండ్ ట్వంటీ ఫోర్", "2024"), ("టు థౌసండ్ ట్వంటీ ఫోర్", "2024"),
        ("టు థౌజండ్ ట్వంటీ ఫైవ్", "2025"), ("టూ థౌజండ్ ట్వంటీ ఫైవ్", "2025"),
        ("టు థౌజండ్ ట్వంటీ సిక్స్", "2026"), ("టూ థౌజండ్ ట్వంటీ సిక్స్", "2026"),
        ("రెండు వేల ఇరవై నాలుగు", "2024"), ("రెండు వేల ఇరవై ఐదు", "2025"), ("రెండు వేల ఇరవై ఆరు", "2026"),
        ("ಟು ಥೌಸಂಡ್ ಟ್ವೆಂಟಿ ಫೋರ್", "2024"), ("ಟು ಥೌಸಂಡ್ ಟ್ವೆಂಟಿ ಸಿಕ್ಸ್", "2026"),
        ("ಎರಡು ಸಾವಿರದ ಇಪ್ಪತ್ತನಾಲ್ಕು", "2024"), ("ಎರಡು ಸಾವಿರದ ಇಪ್ಪತ್ತಾರು", "2026"),
        ("two thousand twenty four", "2024"), ("two thousand and twenty four", "2024"),
        ("two thousand twenty five", "2025"), ("two thousand twenty six", "2026"),
        ("twenty twenty four", "2024"), ("twenty twenty six", "2026"),
        ("टू थाउजेंड ट्वेंटी फोर", "2024"), ("दो हजार चौबीस", "2024"), ("दो हजार छब्बीस", "2026"),
        # Compound 2-digit numbers in Kannada phonetics (e.g. 'ಥರ್ಟೀ ಫೋರ್' -> 34, 'ಟ್ವೆಂಟಿ ತ್ರೀ' -> 23)
        ("ಥರ್ಟೀ ಫೋರ್", "34"), ("ಥರ್ಟಿ ಫೋರ್", "34"), ("ಥರ್ಟೀ ಫೈವ್", "35"), ("ಥರ್ಟೀ ಟು", "32"), ("ಥರ್ಟೀ ವನ್", "31"), ("ಥರ್ಟೀ ತ್ರೀ", "33"),
        ("ಟ್ವೆಂಟಿ ವನ್", "21"), ("ಟ್ವೆಂಟಿ ಟು", "22"), ("ಟ್ವೆಂಟಿ ತ್ರೀ", "23"), ("ಟ್ವೆಂಟಿ ಫೋರ್", "24"), ("ಟ್ವೆಂಟಿ ಫೈವ್", "25"),
        ("ಟ್ವೆಂಟಿ ಸಿಕ್ಸ್", "26"), ("ಟ್ವೆಂಟಿ ಸೆವೆನ್", "27"), ("ಟ್ವೆಂಟಿ ಏಯ್ಟ್", "28"), ("ಟ್ವೆಂಟಿ ನೈನ್", "29"),
        ("ಸೆವೆಂಟೀನ್", "17"), ("ಹದಿನೇಳು", "17"), ("ಮೂವತ್ತನಾಲ್ಕು", "34"), ("ಇಪ್ಪತ್ತಮೂರು", "23"),
        # Compound 2-digit numbers in Telugu phonetics
        ("థర్టీ ఫోర్", "34"), ("ట్వంటీ త్రీ", "23"), ("ట్వంటీ ఫోర్", "24"), ("ట్వంటీ ఫైవ్", "25"), ("ట్వంటీ సిక్స్", "26"),
        ("ఇరవై మూడు", "23"), ("ఇరవై నాలుగు", "24"), ("ఇరవై ఐదు", "25"), ("ఇరవై ఆరు", "26"), ("ముప్పై నాలుగు", "34"),
        # Compound 2-digit numbers in English words
        ("thirty four", "34"), ("thirty five", "35"), ("thirty two", "32"), ("thirty one", "31"), ("thirty three", "33"),
        ("twenty one", "21"), ("twenty two", "22"), ("twenty three", "23"), ("twenty four", "24"), ("twenty five", "25"),
        ("twenty six", "26"), ("twenty seven", "27"), ("twenty eight", "28"), ("twenty nine", "29"),
        ("seventeen", "17"), ("eighteen", "18"), ("nineteen", "19"), ("sixteen", "16"), ("fifteen", "15"),
        ("fourteen", "14"), ("thirteen", "13"), ("twelve", "12"), ("eleven", "11"), ("ten", "10"),
        ("thirty", "30"), ("twenty", "20"), ("forty", "40"), ("fifty", "50"), ("sixty", "60"), ("seventy", "70"), ("eighty", "80"), ("ninety", "90"),
        # Common prefixes & state abbreviations
        ("ఎంఓటీ", "MOT"), ("ఎంఓటి", "MOT"), ("ఎమ్ఓటీ", "MOT"), ("ఎమ్ఒటి", "MOT"), ("ఎం ఓ టీ", "MOT"), ("ఎం ఓ టి", "MOT"), ("एमओटी", "MOT"), ("ಎಂಒಟಿ", "MOT"), ("ಎಂ ಓ ಟಿ", "MOT"),
        ("సిఎస్", "CS"), ("సీఎస్", "CS"), ("సి ఎస్", "CS"), ("సీ ఎస్", "CS"), ("ಸಿಎಸ್", "CS"), ("ಸಿ ಎಸ್", "CS"),
        ("టీఎస్", "TS"), ("టిఎస్", "TS"), ("టీ ఎస్", "TS"), ("టి ఎస్", "TS"), ("टीएस", "TS"), ("ಟಿಎಸ್", "TS"), ("ಟಿ ಎಸ್", "TS"),
        ("ఎంహెచ్", "MH"), ("ఎం హెచ్", "MH"), ("एमएच", "MH"), ("ಎಂಹೆಚ್", "MH"),
        ("డిఎల్", "DL"), ("డి ఎల్", "DL"), ("डीएल", "DL"), ("ಡಿಎಲ್", "DL"),
        ("ఎపి", "AP"), ("ఏపీ", "AP"), ("ఏ పి", "AP"), ("एपी", "AP"), ("ಎಪಿ", "AP"), ("ಎ ಪಿ", "AP"),
        ("కెఎ", "KA"), ("కేఏ", "KA"), ("కె ఎ", "KA"), ("केए", "KA"), ("ಕೆಎ", "KA"), ("ಕೆ ಎ", "KA"),
        ("టిఎన్", "TN"), ("టీఎన్", "TN"), ("టి ఎన్", "TN"), ("ಟಿಎನ್", "TN"),
        ("పిఒఎల్", "POL"), ("పివోఎల్", "POL"), ("పీవోఎల్", "POL"), ("पीओएल", "POL"), ("ಪಿಒಎಲ್", "POL"),
        ("బికె", "BK"), ("బీకే", "BK"), ("ಬಿಕೆ", "BK"),
        # Individual single digits (Telugu, Kannada, Hindi, English words)
        ("నైన్", "9"), ("ఎయిట్", "8"), ("సెవెన్", "7"), ("సిక్స్", "6"), ("ఫైవ్", "5"),
        ("ఫోర్", "4"), ("త్రీ", "3"), ("టూ", "2"), ("టు", "2"), ("వన్", "1"), ("జీరో", "0"),
        ("తొమ్మిది", "9"), ("ఎనిమిది", "8"), ("ఏడు", "7"), ("ఆరు", "6"), ("ఐదు", "5"),
        ("నాలుగు", "4"), ("మూడు", "3"), ("రెండు", "2"), ("ఒకటి", "1"), ("సున్నా", "0"),
        ("ನೈನ್", "9"), ("ಏಯ್ಟ್", "8"), ("ಎಂಟು", "8"), ("ಸೆವೆನ್", "7"), ("ಏಳು", "7"), ("ಸಿಕ್ಸ್", "6"), ("ಆರು", "6"),
        ("ಫೈವ್", "5"), ("ಐದು", "5"), ("ಫೋರ್", "4"), ("ನಾಲ್ಕು", "4"), ("ತ್ರೀ", "3"), ("ಮೂರು", "3"),
        ("ಟು", "2"), ("ಟೂ", "2"), ("ಎರಡು", "2"), ("ವನ್", "1"), ("ಒಂದು", "1"), ("ಜೀರೋ", "0"), ("ಸೊನ್ನೆ", "0"),
        ("ಥರ್ಟೀ", "30"), ("ಥರ್ಟಿ", "30"), ("ಟ್ವೆಂಟಿ", "20"), ("ಫೋರ್ಟಿ", "40"), ("ಫಿಫ್ಟಿ", "50"),
        ("नाइन", "9"), ("एट", "8"), ("सेवन", "7"), ("सिक्स", "6"), ("फाइव", "5"),
        ("फोर", "4"), ("थ्री", "3"), ("टू", "2"), ("वन", "1"), ("जीरो", "0"),
        ("नौ", "9"), ("आठ", "8"), ("सात", "7"), ("छह", "6"), ("पांच", "5"),
        ("चार", "4"), ("तीन", "3"), ("दो", "2"), ("एक", "1"), ("शून्य", "0"),
        ("nine", "9"), ("eight", "8"), ("seven", "7"), ("six", "6"), ("five", "5"),
        ("four", "4"), ("three", "3"), ("two", "2"), ("one", "1"), ("zero", "0"),
    ]

    for k, v in subs:
        seg = re.sub(re.escape(k), f" {v} ", seg, flags=re.IGNORECASE)

    # Single phonetic English alphabet letters in Telugu / Kannada / Hindi
    letter_map = {
        # Telugu
        "ఎం": "M", "ఎమ్": "M", "ఓ": "O", "ఒ": "O", "టీ": "T", "టి": "T", "ఎస్": "S",
        "పి": "P", "పీ": "P", "ఎల్": "L", "బి": "B", "బీ": "B", "కె": "K", "కే": "K",
        "డి": "D", "డీ": "D", "ఆర్": "R", "ఎన్": "N", "హెచ్": "H", "ఎ": "A", "ఏ": "A",
        "సి": "C", "సీ": "C", "ఇ": "E", "ఈ": "E", "వి": "V", "జెడ్": "Z",
        # Kannada
        "ಎಂ": "M", "ಎಮ್": "M", "ಓ": "O", "ಒ": "O", "ಟಿ": "T", "ಟೀ": "T", "ಎಸ್": "S",
        "ಪಿ": "P", "ಪೀ": "P", "ಎಲ್": "L", "ಬಿ": "B", "ಬೀ": "B", "ಕೆ": "K", "ಕೇ": "K",
        "ಡಿ": "D", "ಡೀ": "D", "ಆರ್": "R", "ಎನ್": "N", "ಹೆಚ್": "H", "ಎ": "A", "ಏ": "A",
        "ಸಿ": "C", "ಸೀ": "C", "ಇ": "E", "ಈ": "E", "ವಿ": "V", "ಜೆಡ್": "Z",
        # Hindi
        "एम": "M", "ओ": "O", "टी": "T", "एस": "S", "पी": "P", "एल": "L", "के": "K", "ए": "A",
        "बी": "B", "सी": "C", "डी": "D", "ई": "E", "आर": "R", "एन": "N", "एच": "H",
    }
    for k, v in letter_map.items():
        seg = seg.replace(k, f" {v} ")

    raw_tokens = [
        t.upper()
        for t in re.split(r"[\s\-\.,:;]+", seg)
        if t and re.match(r"^[A-Za-z0-9]+$", t)
    ]

    filler = {"POLICY", "NUMBER", "NO", "IS", "MY", "HAI", "NA", "NAA", "AND", "IN", "AT", "VEHICLE", "GAADI"}
    tokens = [t for t in raw_tokens if t not in filler]

    # Group consecutive single letters ('K', 'A' -> 'KA'; 'M', 'O', 'T' -> 'MOT')
    # and consecutive single digits ('2', '2', '3' -> '223'; '9', '8', '7', '6', '5' -> '98765')
    grouped: list[str] = []
    letter_buf = ""
    digit_buf = ""

    def flush_buffers():
        nonlocal letter_buf, digit_buf
        if letter_buf:
            grouped.append(letter_buf)
            letter_buf = ""
        if digit_buf:
            grouped.append(digit_buf)
            digit_buf = ""

    for t in tokens:
        if len(t) == 1 and t.isalpha():
            if digit_buf:
                grouped.append(digit_buf)
                digit_buf = ""
            letter_buf += t
        elif len(t) == 1 and t.isdigit():
            if letter_buf:
                grouped.append(letter_buf)
                letter_buf = ""
            digit_buf += t
        else:
            flush_buffers()
            grouped.append(t)
    flush_buffers()

    if grouped and len(grouped) >= 2 and any(any(c.isdigit() for c in g) for g in grouped):
        return "-".join(grouped)
    if len(grouped) == 1 and len(grouped[0]) >= 5 and any(c.isdigit() for c in grouped[0]):
        return grouped[0]

    return None


def extract_claim_fields(transcript: str) -> Tuple[list[ClaimField], list[str]]:
    """
    Intelligently extract structured claim fields from English, Hinglish, Telugu (Tenglish),
    Kannada (Kanglish), Tamil, Marathi, and other Indic language transcripts.
    ALL extracted field values are normalized into clean English for insurer submission.
    """
    text = transcript or ""
    text_lower = text.lower()

    fields_dict: Dict[str, Tuple[Optional[str], FieldConfidence]] = {}

    # ── 1. Policy / Vehicle Reference (Always Uppercase English Alphanumeric) ──
    policy_pattern = re.search(
        r"\b((?=[A-Za-z0-9\-]*\d)(?=[A-Za-z0-9\-]*[A-Za-z])[A-Za-z0-9]{2,5}(?:-[A-Za-z0-9]{1,6}){1,4})\b",
        text,
    )
    if policy_pattern:
        fields_dict["policy_reference"] = (
            policy_pattern.group(1).strip().upper(),
            FieldConfidence.HIGH,
        )
    else:
        indic_policy = parse_indic_phonetic_policy(text, require_keyword=True)
        if not indic_policy:
            # Also check if state code or policy prefix appears even without the word "policy"
            if re.search(r"(?:MOT|POL|CS|KA|TS|AP|MH|DL|TN|ఎంఓటీ|ఎం ఓ టీ|ಕೆ ಎ|కె ఎ|టీ ఎస్|ಟಿ ಎಸ್)", text, re.IGNORECASE):
                indic_policy = parse_indic_phonetic_policy(text, require_keyword=False)
        if indic_policy:
            fields_dict["policy_reference"] = (indic_policy, FieldConfidence.HIGH)
        else:
            policy_explicit = re.search(
                r"(?:policy|పాలసీ|పాలిసీ|पॉलिसी|ಪಾಲಿಸಿ|பாலிசி)\s*(?:number|no\.?|reference|నంబర్|నెంబర్|नंबर)?\s*(?:hai|is)?\s*[:\-]?\s*([A-Za-z0-9\-]{4,})",
                text,
                re.IGNORECASE,
            )
            if policy_explicit:
                fields_dict["policy_reference"] = (
                    policy_explicit.group(1).strip().upper(),
                    FieldConfidence.HIGH,
                )
            elif any(k in text_lower for k in ["policy", "పాలసీ", "పాలిసీ", "पॉलिसी", "ಪಾಲಿಸಿ", "பாலிசி"]):
                num_fallback = re.search(r"\b(\d{4,10})\b", text)
                if num_fallback:
                    fields_dict["policy_reference"] = (f"POL-{num_fallback.group(1)}", FieldConfidence.HIGH)
                else:
                    fields_dict["policy_reference"] = (None, FieldConfidence.LOW)
            else:
                fields_dict["policy_reference"] = (None, FieldConfidence.MISSING)

    # ── 2. Vehicle Type (Always English: 'car', 'bike', 'truck', 'auto_rickshaw', 'bus') ──
    possessive_match = re.search(
        r"(?:meri|apni|mera|apna|my|naa|na|maa|nanna|en|ennoda|माझी|माझा|मेरी|मेरा|अपनी|మా|నా|ನನ್ನ|என்)\s+"
        r"(bike|motorcycle|scooter|scooty|activa|two\s*wheeler|bullet|pulsar|"
        r"car|gaadi|gadi|kaar|kar|sedan|suv|"
        r"truck|lorry|auto|rickshaw|"
        r"కార్|కారు|బైక్|బైకు|బండి|స్కూటర్|స్కూటీ|యాక్టివా|ఆటో|లారీ|"
        r"ಕಾರು|ಕಾರ್|ಬೈಕ್|ಗಾಡಿ|ಸ್ಕೂಟರ್|ಆಟೋ|"
        r"कार|गाड़ी|बाइक|स्कूटर|ऑटो|ट्रक|"
        r"கார்|பைக்|வண்டி|ஆட்டோ)",
        text_lower,
    )
    if possessive_match:
        v = possessive_match.group(1).strip()
        if any(b in v for b in ["bike", "motorcycle", "scooter", "scooty", "activa", "wheeler", "bullet", "pulsar", "బైక్", "బైకు", "స్కూటర్", "స్కూటీ", "యాక్టివా", "ಬೈಕ್", "ಸ್ಕೂಟರ್", "बाइक", "स्कूटर", "பைக்"]):
            fields_dict["vehicle_type"] = ("bike", FieldConfidence.HIGH)
        elif any(c in v for c in ["car", "gaadi", "gadi", "kaar", "kar", "sedan", "suv", "కార్", "కారు", "బండి", "ಕಾರು", "ಕಾರ್", "ಗಾಡಿ", "कार", "गाड़ी", "கார்", "வண்டி"]):
            fields_dict["vehicle_type"] = ("car", FieldConfidence.HIGH)
        elif any(t in v for t in ["truck", "lorry", "లారీ", "ट्रक"]):
            fields_dict["vehicle_type"] = ("truck", FieldConfidence.HIGH)
        elif any(a in v for a in ["auto", "rickshaw", "ఆటో", "ಆಟೋ", "ऑटो", "ஆட்டோ"]):
            fields_dict["vehicle_type"] = ("auto_rickshaw", FieldConfidence.HIGH)
    elif any(k in text_lower for k in [
        "car", "motor car", "sedan", "suv", "hatchback",
        "కార్", "కారు", "మోటార్ కారు", "कार", "गाड़ी", "ಕಾರು", "ಕಾರ್", "கார்",
    ]):
        fields_dict["vehicle_type"] = ("car", FieldConfidence.HIGH)
    elif any(k in text_lower for k in [
        "bike", "motorcycle", "scooter", "scooty", "activa", "two wheeler", "two-wheeler", "2 wheeler",
        "బైక్", "బైకు", "మోటార్ సైకిల్", "స్కూటర్", "స్కూటీ", "యాక్టివా", "బండి",
        "बाइक", "स्कूटर", "मोटरसाइकिल", "ಬೈಕ್", "ಸ್ಕೂಟರ್", "பைக்", "ஸ்கூட்டர்",
    ]):
        fields_dict["vehicle_type"] = ("bike", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["gaadi", "gadi", "గాడి", "గాడీ", "ಗಾಡಿ", "वंडी", "வண்டி"]):
        fields_dict["vehicle_type"] = ("car", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["truck", "lorry", "లారీ", "ట్రక్", "ట్రక్కు", "ट्रक", "ಲಾರಿ", "லாரி"]):
        fields_dict["vehicle_type"] = ("truck", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["auto", "rickshaw", "auto-rickshaw", "ఆటో", "ఆటో రిక్షా", "రిక్షా", "ऑटो", "ಆಟೋ", "ஆட்டோ"]):
        fields_dict["vehicle_type"] = ("auto_rickshaw", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["bus", "బస్సు", "बस", "ಬಸ್", "பேருந்து"]):
        fields_dict["vehicle_type"] = ("bus", FieldConfidence.HIGH)
    else:
        fields_dict["vehicle_type"] = (None, FieldConfidence.MISSING)

    # ── 3. Incident Location (Always English Title-Case) ──
    known_locations = [
        # Hyderabad / Telangana
        ("హైదరాబాద్", "మధురాపూర్", "Madhapur, Hyderabad"),
        ("హైదరాబాదు", "మధురాపూర్", "Madhapur, Hyderabad"),
        ("హైదరాబాద్", "మాదాపూర్", "Madhapur, Hyderabad"),
        ("హైదరాబాదు", "మాదాపూర్", "Madhapur, Hyderabad"),
        ("హైదరాబాద్", "మదాపూర్", "Madhapur, Hyderabad"),
        ("hyderabad", "madhapur", "Madhapur, Hyderabad"),
        ("hyderabad", "hitec city", "Hitec City, Hyderabad"),
        ("హైదరాబాద్", "హైటెక్ సిటీ", "Hitec City, Hyderabad"),
        ("hyderabad", "gachibowli", "Gachibowli, Hyderabad"),
        ("హైదరాబాద్", "గచ్చిబౌలి", "Gachibowli, Hyderabad"),
        ("hyderabad", "banjara hills", "Banjara Hills, Hyderabad"),
        ("హైదరాబాద్", "బంజారా హిల్స్", "Banjara Hills, Hyderabad"),
        ("hyderabad", "jubilee hills", "Jubilee Hills, Hyderabad"),
        ("హైదరాబాద్", "జూబ్లీ హిల్స్", "Jubilee Hills, Hyderabad"),
        ("hyderabad", "secunderabad", "Secunderabad, Hyderabad"),
        ("హైదరాబాద్", "సికింద్రాబాద్", "Secunderabad, Hyderabad"),
        ("hyderabad", "kukatpally", "Kukatpally, Hyderabad"),
        ("హైదరాబాద్", "కూకట్‌పల్లి", "Kukatpally, Hyderabad"),
        ("హైదరాబాద్", "కూకట్పల్లి", "Kukatpally, Hyderabad"),
        ("hyderabad", "ameerpet", "Ameerpet, Hyderabad"),
        ("హైదరాబాద్", "అమీర్‌పేట్", "Ameerpet, Hyderabad"),
        ("హైదరాబాద్", "అమీర్పేట్", "Ameerpet, Hyderabad"),
        ("madhapur", "", "Madhapur, Hyderabad"),
        ("మధురాపూర్", "", "Madhapur, Hyderabad"),
        ("మాదాపూర్", "", "Madhapur, Hyderabad"),
        ("మదాపూర్", "", "Madhapur, Hyderabad"),
        ("మాధాపూర్", "", "Madhapur, Hyderabad"),
        ("gachibowli", "", "Gachibowli, Hyderabad"),
        ("గచ్చిబౌలి", "", "Gachibowli, Hyderabad"),
        ("hitec city", "", "Hitec City, Hyderabad"),
        ("హైటెక్ సిటీ", "", "Hitec City, Hyderabad"),
        ("kukatpally", "", "Kukatpally, Hyderabad"),
        ("కూకట్‌పల్లి", "", "Kukatpally, Hyderabad"),
        ("కూకట్పల్లి", "", "Kukatpally, Hyderabad"),
        ("banjara hills", "", "Banjara Hills, Hyderabad"),
        ("బంజారా హిల్స్", "", "Banjara Hills, Hyderabad"),
        ("jubilee hills", "", "Jubilee Hills, Hyderabad"),
        ("జూబ్లీ హిల్స్", "", "Jubilee Hills, Hyderabad"),
        ("secunderabad", "", "Secunderabad, Hyderabad"),
        ("సికింద్రాబాద్", "", "Secunderabad, Hyderabad"),
        ("ameerpet", "", "Ameerpet, Hyderabad"),
        ("అమీర్‌పేట్", "", "Ameerpet, Hyderabad"),
        ("dilsukhnagar", "", "Dilsukhnagar, Hyderabad"),
        ("దిల్‌సుఖ్‌నగర్", "", "Dilsukhnagar, Hyderabad"),
        ("lb nagar", "", "LB Nagar, Hyderabad"),
        ("ఎల్బీ నగర్", "", "LB Nagar, Hyderabad"),
        ("uppal", "", "Uppal, Hyderabad"),
        ("ఉప్పల్", "", "Uppal, Hyderabad"),
        ("miyapur", "", "Miyapur, Hyderabad"),
        ("మియాపూర్", "", "Miyapur, Hyderabad"),
        ("kondapur", "", "Kondapur, Hyderabad"),
        ("కొండాపూర్", "", "Kondapur, Hyderabad"),
        ("hyderabad", "", "Hyderabad"),
        ("హైదరాబాద్", "", "Hyderabad"),
        ("హైదరాబాదు", "", "Hyderabad"),
        ("హైద్రాబాద్", "", "Hyderabad"),
        ("warangal", "", "Warangal"),
        ("వరంగల్", "", "Warangal"),
        ("karimnagar", "", "Karimnagar"),
        ("కరీంనగర్", "", "Karimnagar"),
        ("nizamabad", "", "Nizamabad"),
        ("నిజామాబాద్", "", "Nizamabad"),
        ("khammam", "", "Khammam"),
        ("ఖమ్మం", "", "Khammam"),
        # Karnataka (Davanagere, Bengaluru, Mysuru, Hubballi, Ballari, Mangaluru)
        ("davanagere", "", "Davanagere, Karnataka"),
        ("davangere", "", "Davanagere, Karnataka"),
        ("దావణగెరె", "", "Davanagere, Karnataka"),
        ("దావణగెరి", "", "Davanagere, Karnataka"),
        ("ದಾವಣಗೆರೆ", "", "Davanagere, Karnataka"),
        ("hubli", "", "Hubballi, Karnataka"),
        ("hubballi", "", "Hubballi, Karnataka"),
        ("ಹುಬ್ಬಳ್ಳಿ", "", "Hubballi, Karnataka"),
        ("dharwad", "", "Dharwad, Karnataka"),
        ("ಧಾರವಾಡ", "", "Dharwad, Karnataka"),
        ("bellary", "", "Ballari, Karnataka"),
        ("ballari", "", "Ballari, Karnataka"),
        ("ಬಳ್ಳಾರಿ", "", "Ballari, Karnataka"),
        ("ಬೆಳಗಾವಿ", "", "Belagavi, Karnataka"),
        ("belgaum", "", "Belagavi, Karnataka"),
        ("ಶಿವಮೊಗ್ಗ", "", "Shivamogga, Karnataka"),
        ("shimoga", "", "Shivamogga, Karnataka"),
        ("ತುಮಕೂರು", "", "Tumakuru, Karnataka"),
        ("tumkur", "", "Tumakuru, Karnataka"),
        ("ಮಂಗಳೂರು", "", "Mangaluru, Karnataka"),
        ("mangalore", "", "Mangaluru, Karnataka"),
        ("ಉಡುಪಿ", "", "Udupi, Karnataka"),
        ("udupi", "", "Udupi, Karnataka"),
        ("bengaluru", "mg road", "MG Road, Bengaluru"),
        ("bangalore", "mg road", "MG Road, Bengaluru"),
        ("ಬೆಂಗಳೂರು", "ಎಂಜಿ ರಸ್ತೆ", "MG Road, Bengaluru"),
        ("mg road", "", "MG Road, Bengaluru"),
        ("koramangala", "", "Koramangala, Bengaluru"),
        ("whitefield", "", "Whitefield, Bengaluru"),
        ("indiranagar", "", "Indiranagar, Bengaluru"),
        ("electronic city", "", "Electronic City, Bengaluru"),
        ("jayanagar", "", "Jayanagar, Bengaluru"),
        ("ಜಯನಗರ", "", "Jayanagar, Bengaluru"),
        ("ರಾಜಾಜಿನಗರ", "", "Rajajinagar, Bengaluru"),
        ("ಮಲ್ಲೇಶ್ವರಂ", "", "Malleshwaram, Bengaluru"),
        ("ಯಲಹಂಕ", "", "Yelahanka, Bengaluru"),
        ("ಹೆಬ್ಬಾಳ", "", "Hebbal, Bengaluru"),
        ("bangalore", "", "Bengaluru"),
        ("bengaluru", "", "Bengaluru"),
        ("బెంగళూరు", "", "Bengaluru"),
        ("ಬೆಂಗಳೂರು", "", "Bengaluru"),
        ("mysore", "", "Mysuru"),
        ("mysuru", "", "Mysuru"),
        ("ಮೈಸೂರು", "", "Mysuru"),
        # Andhra Pradesh
        ("vijayawada", "benz circle", "Benz Circle, Vijayawada"),
        ("విజయవాడ", "బెంజ్ సర్కిల్", "Benz Circle, Vijayawada"),
        ("benz circle", "", "Benz Circle, Vijayawada"),
        ("బెంజ్ సర్కిల్", "", "Benz Circle, Vijayawada"),
        ("vijayawada", "", "Vijayawada"),
        ("విజయవాడ", "", "Vijayawada"),
        ("visakhapatnam", "", "Visakhapatnam"),
        ("విశాఖపట్నం", "", "Visakhapatnam"),
        ("vizag", "", "Vizag"),
        ("వైజాగ్", "", "Vizag"),
        ("guntur", "", "Guntur"),
        ("గుంటూరు", "", "Guntur"),
        ("tirupati", "", "Tirupati"),
        ("తిరుపతి", "", "Tirupati"),
        ("nellore", "", "Nellore"),
        ("నెల్లూరు", "", "Nellore"),
        ("kurnool", "", "Kurnool"),
        ("కర్నూలు", "", "Kurnool"),
        ("rajahmundry", "", "Rajahmundry"),
        ("రాజమండ్రి", "", "Rajahmundry"),
        # Tamil Nadu / Chennai
        ("chennai", "anna nagar", "Anna Nagar, Chennai"),
        ("చెన్నై", "అన్నా నగర్", "Anna Nagar, Chennai"),
        ("சென்னை", "அண்ணா நகர்", "Anna Nagar, Chennai"),
        ("anna nagar", "", "Anna Nagar, Chennai"),
        ("అన్నా నగర్", "", "Anna Nagar, Chennai"),
        ("அண்ணா நகர்", "", "Anna Nagar, Chennai"),
        ("t nagar", "", "T. Nagar, Chennai"),
        ("velachery", "", "Velachery, Chennai"),
        ("adyar", "", "Adyar, Chennai"),
        ("chennai", "", "Chennai"),
        ("చెన్నై", "", "Chennai"),
        ("சென்னை", "", "Chennai"),
        ("coimbatore", "", "Coimbatore"),
        ("madurai", "", "Madurai"),
        # Maharashtra / Mumbai / Pune
        ("mumbai", "andheri east", "Andheri East, Mumbai"),
        ("mumbai", "andheri", "Andheri East, Mumbai"),
        ("ముంబై", "అంధేరి", "Andheri East, Mumbai"),
        ("मुंबई", "अंधेरी", "Andheri East, Mumbai"),
        ("andheri", "", "Andheri East, Mumbai"),
        ("అంధేరి", "", "Andheri East, Mumbai"),
        ("अंधेरी", "", "Andheri East, Mumbai"),
        ("mumbai", "", "Mumbai"),
        ("ముంబై", "", "Mumbai"),
        ("मुंबई", "", "Mumbai"),
        ("pune", "kothrud", "Kothrud, Pune"),
        ("पुणे", "कोथरूड", "Kothrud, Pune"),
        ("kothrud", "", "Kothrud, Pune"),
        ("కొత్రుడ్", "", "Kothrud, Pune"),
        ("कोथरूड", "", "Kothrud, Pune"),
        ("pune", "hinjewadi", "Hinjewadi Road, Pune"),
        ("పూణే", "హింజేవాడి", "Hinjewadi Road, Pune"),
        ("hinjewadi", "", "Hinjewadi Road, Pune"),
        ("pune", "", "Pune"),
        ("పూణే", "", "Pune"),
        ("पुणे", "", "Pune"),
        # Delhi / NCR & Other Metros
        ("delhi", "connaught place", "Connaught Place, Delhi"),
        ("ఢిల్లీ", "కన్నాట్ ప్లేస్", "Connaught Place, Delhi"),
        ("दिल्ली", "कनॉट प्लेस", "Connaught Place, Delhi"),
        ("connaught place", "", "Connaught Place, Delhi"),
        ("కన్నాట్ ప్లేస్", "", "Connaught Place, Delhi"),
        ("कनॉट प्लेस", "", "Connaught Place, Delhi"),
        ("delhi", "", "Delhi"),
        ("ఢిల్లీ", "", "Delhi"),
        ("दिल्ली", "", "Delhi"),
        ("noida", "", "Noida"),
        ("gurgaon", "", "Gurugram"),
        ("gurugram", "", "Gurugram"),
        ("kolkata", "", "Kolkata"),
        ("jaipur", "", "Jaipur"),
        ("ahmedabad", "", "Ahmedabad"),
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
        loc_re = re.search(
            r"(?:in|at|near|on|లో|దగ్గర|వద్ద|ನಲ್ಲಿ|ಹತ್ತಿರ|में|के पास|இல்|அருகில்)?\s*"
            r"([\w\s\u0C00-\u0C7F\u0C80-\u0CFF\u0900-\u097F\u0B80-\u0BFF]{3,30}?)\s+"
            r"(?:mein|me|road pe|ke paas|near|lo|deggara|daggara|దగ్గర|వద్ద|లో|రోడ్డుపై|ನಲ್ಲಿ|ಹತ್ತಿರ|में|के पास|இல்|அருகில்)\b",
            text,
            re.IGNORECASE,
        )
        if loc_re:
            candidate = loc_re.group(1).strip()
            for prefix in ["నేను ", "మేము ", "నిన్న ", "ఈరోజు ", "nenu ", "main ", "i was ", "ನಾನು ", "ನಿನ್ನೆ "]:
                if candidate.lower().startswith(prefix.lower()):
                    candidate = candidate[len(prefix):].strip()
            non_places = {"సైడ్", "side", "మధ్య", "front", "back", "కారు", "కార్", "బైక్", "car", "bike"}
            if len(candidate) > 2 and candidate.lower() not in non_places:
                eng_loc = transliterate_indic_to_english(candidate)
                fields_dict["incident_location"] = (eng_loc, FieldConfidence.HIGH)
            else:
                fields_dict["incident_location"] = (None, FieldConfidence.MISSING)
        else:
            fields_dict["incident_location"] = (None, FieldConfidence.MISSING)

    # ── 4. Incident Date & Time (Always English) ──
    if any(k in text_lower for k in [
        "ninna evening", "ninna sayantram", "నిన్న సాయంత్రం", "నిన్న సాయంత్రము", "నిన్న సాయంకాలం", "నిన్న ఈవినింగ్",
        "kal shaam", "कल शाम", "ನಿನ್ನೆ ಸಂಜೆ", "ninne sanje", "நேற்று மாலை", "काल संध्याकाळी", "yesterday evening",
    ]):
        fields_dict["incident_date"] = ("Yesterday Evening", FieldConfidence.HIGH)
    elif any(k in text_lower for k in [
        "ninna afternoon", "నిన్న మధ్యాహ్నం", "నిన్న మధ్యాహ్నము", "kal dopahar", "कल दोपहर", "ನಿನ್ನೆ ಮಧ್ಯಾಹ್ನ", "yesterday afternoon",
    ]):
        fields_dict["incident_date"] = ("Yesterday Afternoon", FieldConfidence.HIGH)
    elif any(k in text_lower for k in [
        "ninna morning", "నిన్న ఉదయం", "నిన్న పొద్దున్న", "kal subah", "कल सुबह", "ನಿನ್ನೆ ಬೆಳಿಗ್ಗೆ", "நேற்று காலை", "yesterday morning",
    ]):
        fields_dict["incident_date"] = ("Yesterday Morning", FieldConfidence.HIGH)
    elif any(k in text_lower for k in [
        "ninna night", "నిన్న రాత్రి", "kal raat", "कल रात", "ನಿನ್ನೆ ರಾತ್ರಿ", "நேற்று இரவு", "yesterday night",
    ]):
        fields_dict["incident_date"] = ("Yesterday Night", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["kal", "कल", "yesterday", "ninna", "నిన్న", "మొన్న", "ನಿನ್ನೆ", "ninne", "நேற்று", "netru", "काल"]):
        fields_dict["incident_date"] = ("Yesterday", FieldConfidence.HIGH)
    elif any(k in text_lower for k in [
        "aaj subah", "आज सुबह", "today morning", "this morning", "ee roju udayam", "ఈ రోజు ఉదయం", "ఈరోజు ఉదయం", "ఈరోజు పొద్దున్న",
        "ಇವತ್ತು ಬೆಳಿಗ್ಗೆ", "ಇಂದು ಬೆಳಿಗ್ಗೆ", "இன்று காலை", "आज सकाळी",
    ]):
        fields_dict["incident_date"] = ("Today Morning", FieldConfidence.HIGH)
    elif any(k in text_lower for k in [
        "aaj shaam", "आज शाम", "today evening", "this evening", "ఈ రోజు సాయంత్రం", "ఈరోజు సాయంత్రం", "ಇವತ್ತು ಸಂಜೆ", "இன்று மாலை",
    ]):
        fields_dict["incident_date"] = ("Today Evening", FieldConfidence.HIGH)
    elif any(k in text_lower for k in ["aaj", "आज", "today", "ee roju", "eeraju", "eeroju", "ఈ రోజు", "ఈరోజు", "ఇవాళ", "ಇವತ್ತು", "ಇಂದು", "ivattu", "இன்று", "indru"]):
        fields_dict["incident_date"] = ("Today", FieldConfidence.HIGH)
    elif any(k in text_lower for k in [
        "సాయంత్రం", "సాయంకాలం", "ఉదయం", "పొద్దున్న", "మధ్యాహ్నం", "రాత్రి",
        "ఆదివారం", "సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం",
        "ఐదున్నర", "ఆరున్నర", "గంటలకు", "గంటలకి",
        "ಸಂಜೆ", "ಬೆಳಿಗ್ಗೆ", "ರಾತ್ರಿ", "மாலை", "காலை", "இரவு",
    ]):
        # Map Indic time/day phrases to clean English
        indic_time_to_eng = [
            ("ఆదివారం", "Sunday"), ("సోమవారం", "Monday"), ("మంగళవారం", "Tuesday"),
            ("బుధవారం", "Wednesday"), ("గురువారం", "Thursday"), ("శుక్రవారం", "Friday"), ("శనివారం", "Saturday"),
            ("సాయంత్రం", "Evening"), ("సాయంకాలం", "Evening"), ("ಸಂಜೆ", "Evening"), ("மாலை", "Evening"),
            ("ఉదయం", "Morning"), ("పొద్దున్న", "Morning"), ("ಬೆಳಿಗ್ಗೆ", "Morning"), ("காலை", "Morning"),
            ("మధ్యాహ్నం", "Afternoon"), ("ರಾತ್ರಿ", "Night"), ("రాత్రి", "Night"), ("இரவு", "Night"),
            ("ఐదున్నర", "5:30 PM"), ("ఆరున్నర", "6:30 PM"),
        ]
        eng_parts = [eng for ind, eng in indic_time_to_eng if ind in text]
        fields_dict["incident_date"] = (" ".join(dict.fromkeys(eng_parts)) or "Yesterday Evening", FieldConfidence.HIGH)
    else:
        date_re = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", text)
        time_re = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM|గంటలకు|గంటలకి|బజే|baje|o'clock))\b", text)
        if date_re and time_re:
            t_clean = re.sub(r"(?:గంటలకు|గంటలకి|బజే|baje)", "PM", time_re.group(1))
            fields_dict["incident_date"] = (f"{date_re.group(1)} {t_clean}", FieldConfidence.HIGH)
        elif date_re:
            fields_dict["incident_date"] = (date_re.group(1), FieldConfidence.HIGH)
        elif time_re:
            t_clean = re.sub(r"(?:గంటలకు|గంటలకి|బజే|baje)", "PM", time_re.group(1))
            fields_dict["incident_date"] = (t_clean, FieldConfidence.HIGH)
        else:
            fields_dict["incident_date"] = (None, FieldConfidence.MISSING)

    # ── 5. Damage Description (Always Translated/Normalized to English for Insurer) ──
    damage_indicators = [
        # English / Hinglish
        "damage", "damaged", "tut gaya", "pichak gaya", "crushed", "broken", "hit", "leak", "dent", "dented",
        "fender", "door", "bonnet", "bumper", "headlight", "headlamp", "mudguard", "radiator", "scratch", "scratched",
        "windshield", "glass", "mirror", "indicator", "fork", "wheel", "rim", "tank",
        # Telugu
        "డ్యామేజ్", "డామేజ్", "లెఫ్ట్ డోర్", "రైట్ డోర్", "డోర్", "బంపర్", "మడ్ గార్డ్", "మడ్‌గార్డ్",
        "హెడ్‌లైట్", "హెడ్ లైట్", "బోనెట్", "హిట్", "గుద్దింది", "గుద్దేశాడు", "పగిలిపోయింది", "పగిలింది",
        "ఇరిగిపోయింది", "విరిగింది", "సొట్ట", "గీత", "అద్దం", "బాగా డ్యామేజ్",
        # Kannada
        "ಡ್ಯಾಮೇಜ್", "ಹಾನಿ", "ಮಡ್‌ಗಾರ್ಡ್", "ಹೆಡ್‌ಲೈಟ್", "ಬಂಪರ್", "ಡೋರ್", "ಒಡೆದಿದೆ", "ಜಖಂ", "ಮುರಿದಿದೆ",
        # Hindi / Marathi
        "डैमेज", "नुकसान", "टूट गया", "पिचक गया", "टक्कर", "दरवाजा", "बंपर", "हेडलाइट", "मडगार्ड",
        # Tamil
        "சேதம்", "டேமேஜ்", "பம்பர்", "ஹெட்லைட்", "கதவு", "உடைந்தது",
    ]
    found_damages = [ind for ind in damage_indicators if ind in text_lower or ind in text]
    if found_damages:
        eng_damage = translate_damage_to_english(text)
        fields_dict["damage_description"] = (eng_damage, FieldConfidence.HIGH)
    else:
        if any(k in text_lower for k in ["accident", "యాక్సిడెంట్", "एक्सीडेंट", "ಅಪಘಾತ", "விபத்து", "अपघात"]):
            fields_dict["damage_description"] = ("Vehicle accident damage reported", FieldConfidence.HIGH)
        else:
            fields_dict["damage_description"] = (None, FieldConfidence.MISSING)

    # Assemble ClaimField list and identify missing
    fields: list[ClaimField] = []
    missing_fields: list[str] = []

    detected_lang = detect_conversation_language(text)

    for name, meta in FIELD_QUESTIONS.items():
        val, conf = fields_dict.get(name, (None, FieldConfidence.MISSING))
        lang_questions = meta.get("by_lang", {})
        localized_q = lang_questions.get(detected_lang) or meta["question"]
        follow_up = localized_q if conf in (FieldConfidence.MISSING, FieldConfidence.LOW) else None
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


def validate_and_normalize_field_answer(
    target_field: str,
    raw_answer: str,
    language: str = "en-IN",
) -> Dict[str, Any]:
    """
    Strictly validate a user's follow-up answer against the expected field type AND
    normalize the extracted value into clean English for insurer submission.
    Returns:
      {
        "is_valid_for_target": bool,
        "english_value": Optional[str],
        "routed_fields": Dict[str, str],   # Any fields extracted from this answer (may include target_field or another field!)
        "error_prompt": Optional[str],     # Localized explanation if invalid or if routed to another field
        "detected_language": str,
      }
    """
    text = (raw_answer or "").strip()
    lang = detect_conversation_language(text, language)

    # 1. Check if the user asked a question instead of providing a field value (e.g. "ಸಿ ಎಂ ಎಂ ಅಂದರೆ ಏನು?")
    question_markers = ["?", "ಅಂದರೆ ಏನು", "ಏನು", "అంటే ఏంటి", "ఏంటి", "मतलब क्या", "क्या है", "what is", "meaning"]
    is_question = any(qm in text.lower() for qm in question_markers)

    # Run full extraction + relaxed phonetic policy/vehicle extraction on the answer
    extracted_fields, _ = extract_claim_fields(text)
    routed: Dict[str, str] = {
        f.name: f.value
        for f in extracted_fields
        if f.confidence != FieldConfidence.MISSING and f.value
    }

    # Also check relaxed phonetic policy/vehicle number when no keyword was spoken (e.g. "ಕೆ ಎ ಥರ್ಟೀ ಫೋರ್ ಟು ಟ್ವೆಂಟಿ ತ್ರೀ")
    if "policy_reference" not in routed and not is_question:
        candidate_pol = parse_indic_phonetic_policy(text, require_keyword=False)
        if candidate_pol and any(c.isdigit() for c in candidate_pol):
            routed["policy_reference"] = candidate_pol

    # If user asked a question, explain the current field in their language and do NOT fill the field
    if is_question:
        help_prompts = {
            "policy_reference": {
                "kn-IN": "ಇದು ನಿಮ್ಮ ವಾಹನದ ನೋಂದಣಿ ಸಂಖ್ಯೆ (ಉದಾ: KA-17-EA-4590) ಅಥವಾ ಇನ್ಶೂರೆನ್ಸ್ ಪಾಲಿಸಿ ಸಂಖ್ಯೆ (ಉದಾ: CS-2026-000085). ದಯವಿಟ್ಟು ನಿಮ್ಮ ವಾಹನ ಅಥವಾ ಪಾಲಿಸಿ ಸಂಖ್ಯೆಯನ್ನು ಹೇಳಿ.",
                "te-IN": "ఇది మీ వాహన రిజిస్ట్రేషన్ నంబర్ (ఉదా: TS-09-EA-4590) లేదా ఇన్సూరెన్స్ పాలసీ నంబర్. దయచేసి మీ వాహనం లేదా పాలసీ నంబర్ చెప్పండి.",
                "hi-IN": "यह आपकी गाड़ी का रजिस्ट्रेशन नंबर (जैसे KA-17-EA-4590) या बीमा पॉलिसी नंबर है। कृपया अपना नंबर बताएं।",
                "en-IN": "This is your Vehicle Registration Number (e.g. KA-17-EA-4590) or Insurance Policy Number. Please state your vehicle or policy number.",
            },
        }
        q_Prompt = (
            help_prompts.get(target_field, {}).get(lang)
            or FIELD_QUESTIONS.get(target_field, {}).get("by_lang", {}).get(lang)
            or "Please provide a valid answer for this field."
        )
        return {
            "is_valid_for_target": False,
            "english_value": None,
            "routed_fields": {},
            "error_prompt": q_Prompt,
            "detected_language": lang,
        }

    # 2. Validate per target_field type
    if target_field == "policy_reference":
        pol_val = routed.get("policy_reference")
        if pol_val:
            return {
                "is_valid_for_target": True,
                "english_value": pol_val,
                "routed_fields": routed,
                "error_prompt": None,
                "detected_language": lang,
            }
        # Reject non-alphanumeric / non-number text for policy_reference
        err_map = {
            "kn-IN": "ದಯವಿಟ್ಟು ಮಾನ್ಯವಾದ ವಾಹನ ನೋಂದಣಿ ಸಂಖ್ಯೆ (ಉದಾ: KA-34-223) ಅಥವಾ ಪಾಲಿಸಿ ಸಂಖ್ಯೆಯನ್ನು ಹೇಳಿ.",
            "te-IN": "దయచేసి సరైన వాహన నంబర్ (ఉదా: TS-09-EA-4590) లేదా పాలసీ నంబర్ చెప్పండి.",
            "hi-IN": "कृपया सही गाड़ी नंबर (जैसे KA-34-223) या पॉलिसी नंबर बताएं।",
            "en-IN": "Please provide a valid Policy Number or Vehicle Registration Number (e.g. KA-34-223 or MOT-2024-TS-98765).",
        }
        return {
            "is_valid_for_target": False,
            "english_value": None,
            "routed_fields": routed,
            "error_prompt": err_map.get(lang, err_map["en-IN"]),
            "detected_language": lang,
        }

    if target_field == "incident_location":
        # If the user spoke a policy/vehicle number instead of a location (like 'ಕೆ ಎ ಥರ್ಟೀ ಫೋರ್ ಟು ಟ್ವೆಂಟಿ ತ್ರೀ' -> 'KA-34-223'),
        # route it to policy_reference and re-ask for incident_location!
        if "policy_reference" in routed and "incident_location" not in routed:
            pol_captured = routed["policy_reference"]
            reroute_msg = {
                "kn-IN": f"ನಿಮ್ಮ ವಾಹನ/ಪಾಲಿಸಿ ಸಂಖ್ಯೆ {pol_captured} ದಾಖಲಾಗಿದೆ. ಈಗ ದಯವಿಟ್ಟು ಅಪಘಾತ ಯಾವ ಸ್ಥಳದಲ್ಲಿ ಅಥವಾ ನಗರದಲ್ಲಿ ನಡೆಯಿತು ಎಂದು ಹೇಳಿ (ಉದಾ: ದಾವಣಗೆರೆ, ಬೆಂಗಳೂರು).",
                "te-IN": f"మీ వాహన/పాలసీ నంబర్ {pol_captured} నమోదైంది. ఇప్పుడు దయచేసి యాక్సిడెంట్ ఏ ప్రాంతంలో లేదా నగరంలో జరిగిందో చెప్పండి (ఉదా: మధురాపూర్, హైదరాబాద్).",
                "hi-IN": f"आपका वाहन/पॉलिसी नंबर {pol_captured} दर्ज कर लिया गया है। अब कृपया बताएं कि हादसा किस जगह या शहर में हुआ था?",
                "en-IN": f"Noted your vehicle/policy number {pol_captured}. Now please tell me the location or city where the accident happened.",
            }
            return {
                "is_valid_for_target": False,
                "english_value": None,
                "routed_fields": routed,
                "error_prompt": reroute_msg.get(lang, reroute_msg["en-IN"]),
                "detected_language": lang,
            }

        loc_val = routed.get("incident_location")
        if not loc_val:
            # Transliterate arbitrary spoken place name into English if it's not a number
            eng_candidate = transliterate_indic_to_english(text)
            if eng_candidate and not any(c.isdigit() for c in eng_candidate) and len(eng_candidate) >= 3:
                loc_val = eng_candidate
                routed["incident_location"] = loc_val

        if loc_val:
            return {
                "is_valid_for_target": True,
                "english_value": loc_val,
                "routed_fields": routed,
                "error_prompt": None,
                "detected_language": lang,
            }

        err_loc = {
            "kn-IN": "ದಯವಿಟ್ಟು ಅಪಘಾತ ನಡೆದ ಸ್ಥಳ ಅಥವಾ ನಗರದ ಹೆಸರನ್ನು ಹೇಳಿ (ಉದಾ: ದಾವಣಗೆರೆ, ಬೆಂಗಳೂರು).",
            "te-IN": "దయచేసి యాక్సిడెంట్ జరిగిన ప్రాంతం లేదా నగరం పేరు చెప్పండి (ఉదా: హైదరాబాద్, విజయవాడ).",
            "hi-IN": "कृपया हादसे के स्थान या शहर का नाम बताएं।",
            "en-IN": "Please state the city or locality where the accident occurred.",
        }
        return {
            "is_valid_for_target": False,
            "english_value": None,
            "routed_fields": routed,
            "error_prompt": err_loc.get(lang, err_loc["en-IN"]),
            "detected_language": lang,
        }

    if target_field == "incident_date":
        date_val = routed.get("incident_date")
        if date_val:
            return {
                "is_valid_for_target": True,
                "english_value": date_val,
                "routed_fields": routed,
                "error_prompt": None,
                "detected_language": lang,
            }
        err_date = {
            "kn-IN": "ದಯವಿಟ್ಟು ಅಪಘಾತ ನಡೆದ ದಿನಾಂಕ ಅಥವಾ ಸಮಯವನ್ನು ಹೇಳಿ (ಉದಾ: ನಿನ್ನೆ ಸಂಜೆ, ಇಂದು ಬೆಳಿಗ್ಗೆ).",
            "te-IN": "దయచేసి యాక్సిడెంట్ జరిగిన తేదీ లేదా సమయం చెప్పండి (ఉదా: నిన్న సాయంత్రం, ఈరోజు ఉదయం).",
            "hi-IN": "कृपया हादसे की तारीख या समय बताएं (जैसे: कल शाम, आज सुबह)।",
            "en-IN": "Please state when the accident happened (e.g. Yesterday Evening, Today Morning, or a date/time).",
        }
        return {
            "is_valid_for_target": False,
            "english_value": None,
            "routed_fields": routed,
            "error_prompt": err_date.get(lang, err_date["en-IN"]),
            "detected_language": lang,
        }

    if target_field == "vehicle_type":
        veh_val = routed.get("vehicle_type")
        if veh_val:
            return {
                "is_valid_for_target": True,
                "english_value": veh_val,
                "routed_fields": routed,
                "error_prompt": None,
                "detected_language": lang,
            }
        err_veh = {
            "kn-IN": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ವಾಹನದ ಪ್ರಕಾರವನ್ನು ಹೇಳಿ - ಕಾರ್, ಬೈಕ್, ಆಟೋ ಅಥವಾ ಟ್ರಕ್?",
            "te-IN": "దయచేసి మీ వాహనం రకం చెప్పండి - కార్, బైక్, ఆటో లేదా ట్రక్?",
            "hi-IN": "कृपया अपनी गाड़ी का प्रकार बताएं - कार, बाइक, ऑटो या ट्रक?",
            "en-IN": "Please specify the vehicle type (Car, Bike, Auto, or Truck).",
        }
        return {
            "is_valid_for_target": False,
            "english_value": None,
            "routed_fields": routed,
            "error_prompt": err_veh.get(lang, err_veh["en-IN"]),
            "detected_language": lang,
        }

    if target_field == "damage_description":
        dam_val = routed.get("damage_description") or translate_damage_to_english(text)
        routed["damage_description"] = dam_val
        return {
            "is_valid_for_target": True,
            "english_value": dam_val,
            "routed_fields": routed,
            "error_prompt": None,
            "detected_language": lang,
        }

    return {
        "is_valid_for_target": True,
        "english_value": transliterate_indic_to_english(text),
        "routed_fields": routed,
        "error_prompt": None,
        "detected_language": lang,
    }


def generate_assistant_dialogue(
    transcript: str = "",
    fields: Optional[list[ClaimField]] = None,
    missing_fields: Optional[list[str]] = None,
    detected_language: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate a natural, human-like voice assistant response in the speaker's detected/locked language.
    Supports Telugu (te-IN), Kannada (kn-IN), Hindi (hi-IN), Tamil (ta-IN), Marathi (mr-IN), and English (en-IN).
    Acknowledges already extracted fields and asks ONLY for missing fields.
    Never asks for details that were already provided.
    """
    fields = fields or []
    missing_fields = missing_fields if missing_fields is not None else []
    lang = detect_conversation_language(transcript, detected_language)

    fmap = {f.name: f.value for f in fields if f.value and f.confidence != FieldConfidence.MISSING}
    pol = fmap.get("policy_reference")
    veh = fmap.get("vehicle_type")
    loc = fmap.get("incident_location")
    date = fmap.get("incident_date")
    dam = fmap.get("damage_description")

    # Localize localized question for each field if language is known
    for f in fields:
        if f.confidence in (FieldConfidence.MISSING, FieldConfidence.LOW):
            by_lang = FIELD_QUESTIONS.get(f.name, {}).get("by_lang", {})
            if lang in by_lang:
                f.follow_up_question = by_lang[lang]

    # CASE A: All 5 fields are completely filled
    if not missing_fields:
        if lang == "te-IN":
            dialogue = (
                f"ధన్యవాదాలు! మీ క్లెయిమ్ కి సంబంధించిన అన్ని వివరాలు విజయవంతంగా నమోదయ్యాయి: "
                f"పాలసీ {pol or 'వెరిఫైడ్'}, వాహనం {veh or 'వాహనం'}, ప్రదేశం {loc or 'నమోదైంది'}, సమయం {date or 'నమోదైంది'}. "
                f"ఇప్పుడు స్టెప్ 2 కి వెళ్లి వాహన డ్యామేజ్ ఫోటోలు లేదా వీడియోలు అప్లోడ్ చేయండి."
            )
        elif lang == "kn-IN":
            dialogue = (
                f"ಧನ್ಯವಾದಗಳು! ನಿಮ್ಮ ಕ್ಲೈಮ್‌ನ ಎಲ್ಲಾ ವಿವರಗಳನ್ನು ಯಶಸ್ವಿಯಾಗಿ ದಾಖಲಿಸಲಾಗಿದೆ: "
                f"ಪಾಲಿಸಿ {pol or 'ದೃಢೀಕರಿಸಲಾಗಿದೆ'}, ವಾಹನ {veh or 'ವಾಹನ'}, ಸ್ಥಳ {loc or 'ದಾಖಲಾಗಿದೆ'}, ಸಮಯ {date or 'ದಾಖಲಾಗಿದೆ'}. "
                f"ದಯವಿಟ್ಟು ಈಗ ಹಂತ 2 ಕ್ಕೆ ಮುಂದುವರಿದು ವಾಹನದ ಹಾನಿಯ ಫೋಟೋಗಳನ್ನು ಅಪ್‌ಲೋಡ್ ಮಾಡಿ."
            )
        elif lang == "hi-IN":
            dialogue = (
                f"धन्यवाद! आपके क्लेम के सभी विवरण दर्ज हो चुके हैं: "
                f"पॉलिसी {pol or 'सत्यापित'}, गाड़ी {veh or 'वाहन'}, स्थान {loc or 'दर्ज'}, समय {date or 'दर्ज'}। "
                f"कृपया अब स्टेप 2 पर जाएं और वाहन डैमेज के फोटो या वीडियो अपलोड करें।"
            )
        elif lang == "ta-IN":
            dialogue = (
                f"நன்றி! உங்கள் கோரிக்கையின் அனைத்து விவரங்களும் பதிவு செய்யப்பட்டுள்ளன: "
                f"பாலிசி {pol or 'சரிபார்க்கப்பட்டது'}, வாகனம் {veh or 'வாகனம்'}, இடம் {loc or 'பதிவானது'}, நேரம் {date or 'பதிவானது'}. "
                f"இப்போது படி 2 க்குச் சென்று வாகன சேதப் புகைப்படங்களைப் பதிவேற்றவும்."
            )
        elif lang == "mr-IN":
            dialogue = (
                f"धन्यवाद! तुमच्या क्लेमचे सर्व तपशील नोंदवले गेले आहेत: "
                f"पॉलिसी {pol or 'सत्यापित'}, वाहन {veh or 'वाहन'}, ठिकाण {loc or 'नोंदवले'}, वेळ {date or 'नोंदवली'}. "
                f"कृपया आता स्टेप 2 वर जाऊन वाहनाच्या नुकसानीचे फोटो अपलोड करा."
            )
        else:
            dialogue = (
                f"Thank you! All 5 claim details have been recorded: "
                f"Policy {pol or 'verified'}, vehicle {veh or 'car'}, location {loc or 'verified'}, and time {date or 'recorded'}. "
                f"Please proceed to Step 2 to upload or live-capture your vehicle damage evidence."
            )
        return {
            "display_text": dialogue,
            "speech_text": dialogue,
            "language": lang,
        }

    # CASE B: One or more fields are missing -> acknowledge captured fields and ask ONLY missing
    next_missing = missing_fields[0]
    q_map = FIELD_QUESTIONS.get(next_missing, {}).get("by_lang", {})

    if lang == "te-IN":
        ack_parts = []
        if pol:
            ack_parts.append(f"పాలసీ నంబర్ {pol}")
        if veh:
            ack_parts.append(f"{veh}")
        if loc:
            ack_parts.append(f"{loc}")
        if date:
            ack_parts.append(f"సమయం {date}")
        if dam:
            ack_parts.append("డ్యామేజ్ వివరాలు")
        ack = f"మీ {', '.join(ack_parts)} గుర్తించబడ్డాయి." if ack_parts else "మీరు చెప్పిన సమాచారం నమోదైంది."
        q = q_map.get("te-IN", "దయచేసి మిగిలిన వివరాలు చెప్పండి.")
        full_dialogue = f"{ack} {q}"

    elif lang == "kn-IN":
        ack_parts = []
        if pol:
            ack_parts.append(f"ಪಾಲಿಸಿ {pol}")
        if veh:
            ack_parts.append(f"ವಾಹನ {veh}")
        if loc:
            ack_parts.append(f"ಸ್ಥಳ {loc}")
        if date:
            ack_parts.append(f"ಸಮಯ {date}")
        if dam:
            ack_parts.append("ಹಾನಿಯ ವಿವರಗಳು")
        ack = f"ನಿಮ್ಮ {', '.join(ack_parts)} ದಾಖಲಾಗಿದೆ." if ack_parts else "ನಿಮ್ಮ ಮಾಹಿತಿ ದಾಖಲಾಗಿದೆ."
        q = q_map.get("kn-IN", "ದಯವಿಟ್ಟು ಉಳಿದ ವಿವರಗಳನ್ನು ತಿಳಿಸಿ.")
        full_dialogue = f"{ack} {q}"

    elif lang == "hi-IN":
        ack_parts = []
        if pol:
            ack_parts.append(f"पॉलिसी {pol}")
        if veh:
            ack_parts.append(f"गाड़ी {veh}")
        if loc:
            ack_parts.append(f"स्थान {loc}")
        if date:
            ack_parts.append(f"समय {date}")
        if dam:
            ack_parts.append("डैमेज की जानकारी")
        ack = f"आपकी {', '.join(ack_parts)} की जानकारी दर्ज हो चुकी है।" if ack_parts else "आपकी जानकारी दर्ज कर ली गई है।"
        q = q_map.get("hi-IN", "कृपया बाकी जानकारी बताएं।")
        full_dialogue = f"{ack} {q}"

    elif lang == "ta-IN":
        ack_parts = []
        if pol:
            ack_parts.append(f"பாலிசி {pol}")
        if veh:
            ack_parts.append(f"வாகனம் {veh}")
        if loc:
            ack_parts.append(f"இடம் {loc}")
        if date:
            ack_parts.append(f"நேரம் {date}")
        if dam:
            ack_parts.append("சேத விவரங்கள்")
        ack = f"உங்கள் {', '.join(ack_parts)} பதிவு செய்யப்பட்டுள்ளது." if ack_parts else "உங்கள் தகவல் பதிவு செய்யப்பட்டுள்ளது."
        q = q_map.get("ta-IN", "தயவுசெய்து மீதமுள்ள விவரங்களைச் சொல்லுங்கள்.")
        full_dialogue = f"{ack} {q}"

    elif lang == "mr-IN":
        ack_parts = []
        if pol:
            ack_parts.append(f"पॉलिसी {pol}")
        if veh:
            ack_parts.append(f"वाहन {veh}")
        if loc:
            ack_parts.append(f"ठिकाण {loc}")
        if date:
            ack_parts.append(f"वेळ {date}")
        if dam:
            ack_parts.append("नुकसानीचा तपशील")
        ack = f"तुमचा {', '.join(ack_parts)} नोंदवला गेला आहे." if ack_parts else "तुमची माहिती नोंदवली गेली आहे."
        q = q_map.get("mr-IN", "कृपया उर्वरित माहिती सांगा.")
        full_dialogue = f"{ack} {q}"

    else:
        ack_parts = []
        if pol:
            ack_parts.append(f"policy {pol}")
        if veh:
            ack_parts.append(f"vehicle {veh}")
        if loc:
            ack_parts.append(f"location at {loc}")
        if date:
            ack_parts.append(f"time ({date})")
        if dam:
            ack_parts.append("damage details")
        ack = f"I have noted your {', '.join(ack_parts)}." if ack_parts else "I have received your initial claim intake."
        q = q_map.get("en-IN", "Please provide the missing details.")
        full_dialogue = f"{ack} {q}"

    return {
        "display_text": full_dialogue,
        "speech_text": full_dialogue,
        "language": lang,
    }
