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


async def transcribe_via_groq_whisper(
    audio_bytes: bytes,
    filename: str = "recording.wav",
    content_type: str = "audio/wav",
    language_code: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Automatic STT failover using Groq Whisper (`whisper-large-v3-turbo`) when
    a valid Groq key (`gsk_...`) is configured in `LLM_API_KEY` and Gnani Prisma STT
    returns 402/429/5xx or times out.
    """
    settings = get_settings()
    key = (settings.llm_api_key or "").strip()
    if not key.startswith("gsk_"):
        return None

    groq_stt_url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {key}"}
    data: Dict[str, str] = {"model": "whisper-large-v3-turbo", "response_format": "verbose_json"}
    if language_code and language_code not in ("indic-auto", "auto"):
        iso_lang = language_code.split("-")[0].lower()
        if iso_lang in ("en", "hi", "kn", "te", "ta", "mr", "bn", "gu", "ml", "pa", "ur"):
            data["language"] = iso_lang

    files = {"file": (filename or "recording.wav", audio_bytes, content_type or "audio/wav")}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(groq_stt_url, headers=headers, data=data, files=files)
        if resp.status_code != 200:
            logger.warning("Groq Whisper fallback returned HTTP %s.", resp.status_code)
            return None
        res_json = resp.json()
        transcript = (res_json.get("text") or "").strip()
        return {
            "transcript": transcript,
            "model": "groq:whisper-large-v3-turbo",
            "detected_language": language_code or "indic-auto",
            "is_mock": False,
            "request_metadata": {
                "mode": "groq-whisper-fallback",
                "audio_filename": filename,
                "bytes_received": len(audio_bytes),
                "duration_seconds": res_json.get("duration"),
            },
        }
    except Exception as exc:
        logger.warning("Groq Whisper fallback failed (%s).", exc.__class__.__name__)
        return None


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


# ── Word-boundary & Multilingual Matching Helpers ───────────────────────────────
def _contains_term(text_lower: str, raw_text: str, term: str) -> bool:
    """
    Match `term` safely against text:
    - ASCII terms match with word boundaries so 'car' never hits 'scared',
      'dio' never hits 'audio', 'auto' never hits 'automatically', and 'kal' never hits 'Kalyan'.
    - Indic Unicode terms use substring matching to support natural agglutinative suffixes.
    """
    if not term:
        return False
    if term.isascii():
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text_lower))
    return term in raw_text or term.lower() in text_lower


# ── Multilingual Field Questions (Per-Language + Clean Natural Phrasing) ─────────
FIELD_QUESTIONS = {
    "policy_reference": {
        "label": "Policy / Vehicle Number",
        "question": "Could you share your vehicle registration number or insurance policy number?",
        "by_lang": {
            "te-IN": "మీ వాహన రిజిస్ట్రేషన్ నంబర్ లేదా పాలసీ నంబర్ చెప్పండి.",
            "kn-IN": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ವಾಹನದ ನೋಂದಣಿ ಸಂಖ್ಯೆ ಅಥವಾ ಪಾಲಿಸಿ ನಂಬರ್ ತಿಳಿಸಿ.",
            "hi-IN": "कृपया अपनी गाड़ी का नंबर या पॉलिसी नंबर बताएं।",
            "ta-IN": "தயவுசெய்து உங்கள் வாகனப் பதிவு எண் அல்லது பாலிசி எண்ணைச் சொல்லுங்கள்.",
            "mr-IN": "कृपया तुमच्या वाहनाचा नोंदणी क्रमांक किंवा पॉलिसी नंबर सांगा.",
            "en-IN": "Could you share your vehicle registration number or policy number?",
        },
    },
    "incident_location": {
        "label": "Incident Location",
        "question": "Where did the accident happen?",
        "by_lang": {
            "te-IN": "యాక్సిడెంట్ ఏ ప్రాంతంలో లేదా నగరంలో జరిగింది?",
            "kn-IN": "ಅಪಘಾತ ಯಾವ ಸ್ಥಳದಲ್ಲಿ ಅಥವಾ ನಗರದಲ್ಲಿ ನಡೆಯಿತು?",
            "hi-IN": "हादसा किस जगह या शहर में हुआ था?",
            "ta-IN": "விபத்து எந்த இடத்தில் அல்லது நகரத்தில் நடந்தது?",
            "mr-IN": "अपघात कोणत्या ठिकाणी किंवा शहरात झाला?",
            "en-IN": "Where did the accident take place? Please share the area or city.",
        },
    },
    "incident_date": {
        "label": "Incident Date",
        "question": "When did the accident happen?",
        "by_lang": {
            "te-IN": "యాక్సిడెంట్ ఏ రోజు లేదా ఏ సమయానికి జరిగింది? తేదీ లేదా సమయం చెప్పండి.",
            "kn-IN": "ಅಪಘಾತ ಯಾವ ದಿನ ಅಥವಾ ಯಾವ ಸಮಯಕ್ಕೆ ನಡೆಯಿತು? ದಿನಾಂಕ ಅಥವಾ ಸಮಯ ಹೇಳಿ.",
            "hi-IN": "हादसा कब हुआ था? कृपया तारीख या समय बताएं।",
            "ta-IN": "விபத்து எப்போது நடந்தது? தேதி அல்லது நேரத்தைச் சொல்லுங்கள்.",
            "mr-IN": "अपघात कधी झाला? कृपया तारीख किंवा वेळ सांगा.",
            "en-IN": "When did this accident happen? Please mention the date or time.",
        },
    },
    "vehicle_type": {
        "label": "Vehicle Type",
        "question": "What type of vehicle was involved (car, bike, scooter, auto)?",
        "by_lang": {
            "te-IN": "మీ వాహనం రకం ఏంటి - కార్, బైక్ లేదా ఇతర వాహనమా?",
            "kn-IN": "ನಿಮ್ಮ ವಾಹನದ ಪ್ರಕಾರ ಯಾವುದು - ಕಾರ್, ಬೈಕ್ ಅಥವಾ ಇತರ ವಾಹನವೇ?",
            "hi-IN": "आपकी गाड़ी का प्रकार क्या है - कार, बाइक या कोई अन्य वाहन?",
            "ta-IN": "உங்கள் வாகனத்தின் வகை என்ன - கார், பைக் அல்லது மற்றதா?",
            "mr-IN": "तुमच्या वाहनाचा प्रकार कोणता आहे - कार, बाईक की इतर?",
            "en-IN": "What type of vehicle was involved (car, bike, scooter, auto, or truck)?",
        },
    },
    "damage_description": {
        "label": "Damage Description",
        "question": "What damage happened to your vehicle?",
        "by_lang": {
            "te-IN": "వాహనానికి ఎలాంటి నష్టం లేదా డ్యామేజ్ జరిగింది?",
            "kn-IN": "ವಾಹನಕ್ಕೆ ಯಾವ ರೀತಿಯ ಹಾನಿ ಅಥವಾ ಡ್ಯಾಮೇಜ್ ಆಗಿದೆ?",
            "hi-IN": "गाड़ी में क्या नुकसान हुआ है? कृपया बताएं।",
            "ta-IN": "வாகனத்திற்கு என்ன சேதம் ஏற்பட்டுள்ளது?",
            "mr-IN": "वाहनाचे काय नुकसान झाले आहे? कृपया सांगा.",
            "en-IN": "Please describe what parts of your vehicle were damaged.",
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
        "కొచ్చి": "Kochi", "കൊച്ചി": "Kochi", "कोच्चि": "Kochi", "नोएडा": "Noida", "नोएडा में": "Noida",
        "पुणे": "Pune", "पुण्यात": "Pune", "मुंबईत": "Mumbai", "ठाणे": "Thane", "नागपूर": "Nagpur",
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
        # Offset within Indic block (all share standard ISCII Unicode block offsets)
        offset = None
        if 0x0C00 <= code <= 0x0C7F:
            offset = code - 0x0C00
        elif 0x0C80 <= code <= 0x0CFF:
            offset = code - 0x0C80
        elif 0x0900 <= code <= 0x097F:
            offset = code - 0x0900
        elif 0x0B80 <= code <= 0x0BFF:
            offset = code - 0x0B80
        elif 0x0D00 <= code <= 0x0D7F:
            offset = code - 0x0D00
        elif 0x0980 <= code <= 0x09FF:
            offset = code - 0x0980
        elif 0x0A80 <= code <= 0x0AFF:
            offset = code - 0x0A80
        elif 0x0A00 <= code <= 0x0A7F:
            offset = code - 0x0A00

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
        (["fuel tank", "tank", "ట్యాంక్", "ಟ್ಯಾಂಕ್", "टैंक", "टाकी"], "Fuel tank"),
        (["radiator", "engine", "ఇంజిన్", "రేడియేటర్", "ಎಂಜಿನ್", "इंजन", "रेडिएटर"], "Engine / Radiator"),
        (["ஹெட்லைட்", "ഹെഡ്ലൈറ്റ്", "হেডলাইট", "હેડલાઇટ", "हेडलाईट"], "Headlight"),
        (["பம்பர்", "ബമ്പർ", "বাম্পার", "બમ્પર"], "Bumper"),
    ]

    for triggers, eng_label in part_mappings:
        if any(_contains_term(t_low, text, tr) for tr in triggers):
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
        (["crushed", "full ga damage", "ఫుల్ గా డ్యామేజ్", "బాగా డ్యామేజ్", "ಪೂರ್ತಿ ಡ್ಯಾಮೇಜ್", "बहुत नुकसान", "बुरी तरह", "खूप नुकसान"], "severely damaged"),
        (["broken", "tut gaya", "tut gayi", "toot gaya", "toot gayi", "तुटले", "फुटले", "పగిలిపోయింది", "పగిలింది", "ఇరిగిపోయింది", "విరిగింది", "ಒಡೆದಿದೆ", "ಮುರಿದಿದೆ", "टूट गया", "टूट गई", "உடைந்தது", "പൊട്ടി", "ভাঙা", "તૂટી", "ਟੁੱਟ"], "broken / cracked"),
        (["dent", "dented", "pichak", "సొట్ట", "డెంట్", "ಡೆಂಟ್", "पिचक गया", "डेंट"], "dented"),
        (["scratch", "scratched", "గీత", "గీతలు", "స్క్రాచ్", "ಸ್ಕ್ರಾಚ್", "खरोंच"], "scratched"),
        (["side hit", "side lo hit", "సైడ్ లో హిట్", "సైడ్ నుంచి", "ಸೈಡ್ ಇಂದ", "साइड से टक्कर"], "impacted from the side"),
        (["rear hit", "వెనుక నుంచి", "ಹಿಂದಿನಿಂದ", "पीछे से टक्कर"], "impacted from the rear"),
    ]
    for triggers, eng_act in severity_mappings:
        if any(_contains_term(t_low, text, tr) for tr in triggers):
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
        marathi_markers = ["माझ्या", "माझी", "माझा", "झाला", "झाली", "गाडीचा", "पुण्यात", "कोथरूड", "आहे", "अपघात", "संध्याकाळी", "सकाळी", "दुपारी", "बाईक"]
        if any(m in text for m in marathi_markers) or hint.startswith("mr"):
            return "mr-IN"
        return "hi-IN"

    # 2. If caller explicitly specified a concrete language (not 'indic-auto'), honor it
    if hint and hint.lower() != "indic-auto":
        for prefix in ("te", "kn", "hi", "ta", "mr", "ml", "bn", "gu", "pa", "ur", "en"):
            if hint.lower().startswith(prefix):
                return f"{prefix}-IN"

    # 3. Romanized Indic (Tenglish / Kanglish / Hinglish / Tanglish / Marathi / Malayalam) Detection when in indic-auto mode
    words = set(re.findall(r"[a-z]+", text_lower))
    tenglish_markers = {"chudandi", "naa", "ayyindi", "aindi", "nenu", "deggara", "daggara", "chesindi", "ninna", "eeroju", "vachi", "gantala", "sayantram"}
    kanglish_markers = {"nanna", "aayitu", "ayitu", "alli", "hattira", "ninne", "ivattu", "maadide", "sanje"}
    hinglish_markers = {"mera", "meri", "apni", "hua", "gaya", "tha", "kal", "aaj", "mein", "paas", "dekhiye", "haan", "shaam", "subah", "tut"}
    tanglish_markers = {"ennoda", "vandi", "aagiduchu", "aachu", "netru", "pakkathula", "indru"}
    marathi_latn_markers = {"majha", "majhi", "jhala", "zala", "apghat", "madhe"}
    malayalam_latn_markers = {"ente", "innale", "innu", "evide", "aayi"}

    if len(words & tenglish_markers) >= 1:
        return "te-IN"
    if len(words & kanglish_markers) >= 1:
        return "kn-IN"
    if len(words & tanglish_markers) >= 1:
        return "ta-IN"
    if len(words & marathi_latn_markers) >= 1:
        return "mr-IN"
    if len(words & malayalam_latn_markers) >= 1:
        return "ml-IN"
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
    question_markers = [
        "?", "ಅಂದರೆ ಏನು", "ಏನು", "అంటే ఏంటి", "ఏంటి", "मतलब क्या", "क्या है",
        "என்றால் என்ன", "என்ன", "म्हणजे काय", "काय आहे", "what is", "meaning",
    ]
    if any(qm in text.lower() for qm in question_markers):
        return None

    policy_kws = [
        "పాలసీ", "పాలిసీ", "పాలసి", "पॉलिसी", "पालिसी", "ಪಾಲಿಸಿ", "பாலிசி", "policy",
        "బండి నంబర్", "బండి నెంబర్", "బైక్ నంబర్", "బైక్ నెంబర్", "బైకు నంబర్", "బైకు నెంబర్",
        "కారు నంబర్", "కారు నెంబర్", "వెహికల్ నంబర్", "వెహికల్ నెంబర్", "గాడి నంబర్",
        "ಗಾಡಿ ನಂಬರ್", "ವಾಹನ ಸಂಖ್ಯೆ", "ಗಾಡಿ ಸಂಖ್ಯೆ", "ಬೈಕ್ ನಂಬರ್", "ಕಾರ್ ನಂಬರ್", "ವಾಹನದ ನಂಬರ್", "ನಂಬರ್ ಪ್ಲೇಟ್",
        "गाड़ी नंबर", "वाहन नंबर", "बाइक नंबर", "कार नंबर", "नम्बर", "गाडी नंबर", "बाईक नंबर", "वाहन क्रमांक", "क्रमांक", "नंबर प्लेट",
        "பைக் நம்பர்", "கார் நம்பர்", "வண்டி நம்பர்", "வாகன எண்", "வாகன நம்பர்", "நம்பர்",
        "vehicle number", "vehicle no", "registration number", "registration no", "reg no",
        "bike number", "bike no", "car number", "car no", "scooter number", "scooter no",
        "gaadi number", "gaadi no", "number plate", "plate number",
    ]
    has_policy_kw = any(k in text.lower() for k in policy_kws)
    if require_keyword and not has_policy_kw:
        return None

    if has_policy_kw:
        m = re.search(
            r"(?:పాలసీ|పాలిసీ|పాలసి|पॉलिसी|पालिसी|ಪಾಲಿಸಿ|பாலிசி|policy|వెహికల్|గాడి|బండి|బైక్|బైకు|కారు|ಗಾಡಿ|ವಾಹನ|ವಾಹನದ|ಬೈಕ್|ಕಾರ್|गाड़ी|गाडी|वाहन|बाइक|बाईक|कार|பைக்|கார்|வண்டி|வாகன|vehicle|bike|car|scooter|registration|reg|number\s*plate|plate)\s+(?:నంబర్|నెంబర్|నెం|नंबर|नम्बर|क्रमांक|ನಂಬರ್|ಸಂಖ್ಯೆ|நம்பர்|எண்|number|no\.?|reference|plate)\s*(?:is|hai|అనేది)?\s*[:\-\.]?\s*([^\.\n।]+)",
            text,
            re.IGNORECASE,
        )
        if not m or not m.group(1).strip():
            m = re.search(
                r"(?:పాలసీ|పాలిసీ|పాలసి|पॉलिसी|पालिसी|ಪಾಲಿಸಿ|பாலிசி|policy)\s*(?:is|hai)?\s*[:\-\.]?\s*([^\.\n।]+)",
                text,
                re.IGNORECASE,
            )
        seg = m.group(1).strip() if m else text.strip()
    else:
        seg = text.strip()

    # Stop at common narrative words that follow the policy/vehicle number in a single sentence
    stop_words = [
        "నేను", "మా", "నా", "మరియు", "హైదరాబాద్", "హైదరాబాదు", "మధురాపూర్", "మాదాపూర్", "నిన్న", "ఈరోజు",
        "డ్రైవ్", "యాక్సిడెంట్", "కారు", "కార్", "బైక్", "బండి", "ఆటో", "లెఫ్ట్", "రైట్", "బంపర్", "డోర్", "హెడ్",
        "nenu", "hyderabad", "madhapur", "main", "when", "while", "yesterday", "today", "front", "left", "right",
        "kal", "aaj", "shaam", "subah", "raat", "mein", "accident", "hua", "huva", "ayyindi", "aindi",
        "aayitu", "aachu", "aagiduchu", "jhala", "zala", "ninna", "ninne", "eeroju", "ivattu", "netru", "indru",
        "bike", "car", "gaadi", "bandi", "vandi", "bumper", "headlight", "damage",
        "ಮತ್ತು", "ನಾನು", "ನಿನ್ನೆ", "ದಾವಣಗೆರೆ", "ಬೆಂಗಳೂರು", "ನನ್ನ", "ಅಪಘಾತ", "ಬೈಕ್", "ಕಾರ್", "ಹೆಡ್", "ಬಂಪರ್", "ಆಯಿತು",
        "मैं", "मेरी", "मेरा", "माझी", "माझा", "कल", "काल", "और", "आणि", "एक्सीडेंट", "हादसा", "अपघात", "बाइक", "बाईक", "कार", "गाड़ी", "हेडलाइट", "बंपर",
        "மற்றும்", "நான்", "நேற்று", "இன்று", "விபத்து", "பைக்", "கார்", "வண்டி", "ஹெட்லைட்", "பம்பர்",
    ]
    for sw in stop_words:
        idx = seg.lower().find(f" {sw.lower()}")
        if idx > 3:
            seg = seg[:idx].strip()

    # Expand spoken 'double X' / 'triple X' digit groups BEFORE tokenization (e.g. 'double four' -> '4 4')
    word_digits = {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    }
    for w, d in word_digits.items():
        seg = re.sub(rf"\bdouble\s+{w}\b", f" {d} {d} ", seg, flags=re.IGNORECASE)
        seg = re.sub(rf"\btriple\s+{w}\b", f" {d} {d} {d} ", seg, flags=re.IGNORECASE)

    # Multi-word number & prefix substitutions (Telugu, Kannada, Hindi, Marathi, Tamil, English)
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
        # Common prefixes & state abbreviations (Telugu, Kannada, Hindi/Marathi, Tamil)
        ("ఎంఓటీ", "MOT"), ("ఎంఓటి", "MOT"), ("ఎమ్ఓటీ", "MOT"), ("ఎమ్ఒటి", "MOT"), ("ఎం ఓ టీ", "MOT"), ("ఎం ఓ టి", "MOT"), ("एमओटी", "MOT"), ("ಎಂಒಟಿ", "MOT"), ("ಎಂ ಓ ಟಿ", "MOT"), ("எம்ஓடி", "MOT"), ("எம் ஓ டி", "MOT"),
        ("సిఎస్", "CS"), ("సీఎస్", "CS"), ("సి ఎస్", "CS"), ("సీ ఎస్", "CS"), ("ಸಿಎಸ್", "CS"), ("ಸಿ ಎಸ್", "CS"),
        ("టీఎస్", "TS"), ("టిఎస్", "TS"), ("టీ ఎస్", "TS"), ("టి ఎస్", "TS"), ("टीएस", "TS"), ("टी एस", "TS"), ("ಟಿಎಸ್", "TS"), ("ಟಿ ಎಸ್", "TS"),
        ("ఎంహెచ్", "MH"), ("ఎం హెచ్", "MH"), ("एमएच", "MH"), ("एम एच", "MH"), ("ಎಂಹೆಚ್", "MH"), ("ಎಂ ಎಚ್", "MH"),
        ("డిఎల్", "DL"), ("డి ఎల్", "DL"), ("डीएल", "DL"), ("डी एल", "DL"), ("ಡಿಎಲ್", "DL"),
        ("ఎపి", "AP"), ("ఏపీ", "AP"), ("ఏ పి", "AP"), ("एपी", "AP"), ("ए पी", "AP"), ("ಎಪಿ", "AP"), ("ಎ ಪಿ", "AP"), ("ஏபி", "AP"),
        ("కెఎ", "KA"), ("కేఏ", "KA"), ("కె ఎ", "KA"), ("కే ఏ", "KA"), ("केए", "KA"), ("के ए", "KA"), ("ಕೆಎ", "KA"), ("ಕೆ ಎ", "KA"), ("கேஏ", "KA"), ("கே ஏ", "KA"),
        ("టిఎన్", "TN"), ("టీఎన్", "TN"), ("టి ఎన్", "TN"), ("टीएन", "TN"), ("टी एन", "TN"), ("ಟಿಎನ್", "TN"), ("ಟಿ ಎನ್", "TN"), ("டிஎன்", "TN"), ("டி என்", "TN"),
        ("केएल", "KL"), ("के एल", "KL"), ("கேஎல்", "KL"), ("கே எல்", "KL"),
        ("जीजे", "GJ"), ("जी जे", "GJ"), ("आरजे", "RJ"), ("आर जे", "RJ"), ("यूपी", "UP"), ("यू पी", "UP"), ("डब्ल्यूबी", "WB"), ("डब्ल्यू बी", "WB"),
        ("పిఒఎల్", "POL"), ("పివోఎల్", "POL"), ("పీవోఎల్", "POL"), ("पीओएल", "POL"), ("ಪಿಒಎಲ್", "POL"),
        ("బికె", "BK"), ("బీకే", "BK"), ("ಬಿಕೆ", "BK"),
        # Individual single digits (Telugu, Kannada, Hindi/Marathi, Tamil, English words)
        ("నైన్", "9"), ("నేన్", "9"), ("ఎయిట్", "8"), ("సెవెన్", "7"), ("సిక్స్", "6"), ("ఫైవ్", "5"),
        ("ఫోర్", "4"), ("త్రీ", "3"), ("టూ", "2"), ("టు", "2"), ("వన్", "1"), ("జీరో", "0"),
        ("తొమ్మిది", "9"), ("ఎనిమిది", "8"), ("ఏడు", "7"), ("ఆరు", "6"), ("ఐదు", "5"),
        ("నాలుగు", "4"), ("మూడు", "3"), ("రెండు", "2"), ("ఒకటి", "1"), ("సున్నా", "0"),
        ("ನೈನ್", "9"), ("ನೇನ್", "9"), ("ಏಯ್ಟ್", "8"), ("ಎಂಟು", "8"), ("ಸೆವೆನ್", "7"), ("ಏಳು", "7"), ("ಸಿಕ್ಸ್", "6"), ("ಆರು", "6"),
        ("ಫೈವ್", "5"), ("ಐದು", "5"), ("ಫೋರ್", "4"), ("ನಾಲ್ಕು", "4"), ("ತ್ರೀ", "3"), ("ಮೂರು", "3"),
        ("ಟು", "2"), ("ಟೂ", "2"), ("ಎರಡು", "2"), ("ವನ್", "1"), ("ಒಂದು", "1"), ("ಜೀರೋ", "0"), ("ಸೊನ್ನೆ", "0"),
        ("ಥರ್ಟೀ", "30"), ("ಥರ್ಟಿ", "30"), ("ಟ್ವೆಂಟಿ", "20"), ("ಫೋರ್ಟಿ", "40"), ("ಫಿಫ್ಟಿ", "50"),
        ("नाईन", "9"), ("नाइन", "9"), ("एइट", "8"), ("एट", "8"), ("सेवन", "7"), ("सिक्स", "6"), ("फाइव", "5"),
        ("फोर", "4"), ("थ्री", "3"), ("टू", "2"), ("वन", "1"), ("जीरो", "0"),
        ("नौ", "9"), ("नऊ", "9"), ("आठ", "8"), ("सात", "7"), ("छह", "6"), ("सहा", "6"), ("पांच", "5"), ("पाच", "5"),
        ("चार", "4"), ("तीन", "3"), ("दो", "2"), ("दोन", "2"), ("एक", "1"), ("शून्य", "0"),
        ("நைன்", "9"), ("ஒன்பது", "9"), ("எய்ட்", "8"), ("எட்டு", "8"), ("செவன்", "7"), ("ஏழு", "7"),
        ("சிக்ஸ்", "6"), ("ஆறு", "6"), ("ஃபைவ்", "5"), ("ஐந்து", "5"), ("ஃபோர்", "4"), ("நான்கு", "4"),
        ("த்ரீ", "3"), ("மூன்று", "3"), ("டூ", "2"), ("இரண்டு", "2"), ("ஒன்", "1"), ("ஒன்று", "1"), ("ஜீரோ", "0"), ("பூஜ்ஜியம்", "0"),
        ("nine", "9"), ("eight", "8"), ("seven", "7"), ("six", "6"), ("five", "5"),
        ("four", "4"), ("three", "3"), ("two", "2"), ("one", "1"), ("zero", "0"),
    ]

    # Tamil 'ஏ பி' is 'AP' only when spoken at the start (state code); after RTO digits it is series 'A B'
    seg = re.sub(r"^ஏ\s+பி\b", " AP ", seg)

    for k, v in subs:
        seg = re.sub(re.escape(k), f" {v} ", seg, flags=re.IGNORECASE)

    # Single phonetic English alphabet letters in Telugu / Kannada / Hindi / Tamil
    letter_map = {
        # Telugu
        "ఎం": "M", "ఎమ్": "M", "ఓ": "O", "ఒ": "O", "టీ": "T", "టి": "T", "ఎస్": "S",
        "పి": "P", "పీ": "P", "ఎల్": "L", "బి": "B", "బీ": "B", "కె": "K", "కే": "K",
        "డి": "D", "డీ": "D", "ఆర్": "R", "ఎన్": "N", "హెచ్": "H", "ఎ": "A", "ఏ": "A",
        "సి": "C", "సీ": "C", "ఇ": "E", "ఈ": "E", "వి": "V", "జెడ్": "Z",
        "జి": "G", "జీ": "G", "జె": "J", "జే": "J", "యు": "U", "యూ": "U", "డబ్ల్యూ": "W", "ఎక్స్": "X", "వై": "Y",
        # Kannada
        "ಎಂ": "M", "ಎಮ್": "M", "ಓ": "O", "ಒ": "O", "ಟಿ": "T", "ಟೀ": "T", "ಎಸ್": "S",
        "ಪಿ": "P", "ಪೀ": "P", "ಎಲ್": "L", "ಬಿ": "B", "ಬೀ": "B", "ಕೆ": "K", "ಕೇ": "K",
        "ಡಿ": "D", "ಡೀ": "D", "ಆರ್": "R", "ಎನ್": "N", "ಹೆಚ್": "H", "ಎ": "A", "ಏ": "A",
        "ಸಿ": "C", "ಸೀ": "C", "ಇ": "E", "ಈ": "E", "ವಿ": "V", "ಜೆಡ್": "Z",
        "ಜಿ": "G", "ಜೀ": "G", "ಜೆ": "J", "ಜೇ": "J", "ಯು": "U", "ಡಬ್ಲ್ಯು": "W", "ಎಕ್ಸ್": "X", "ವೈ": "Y",
        # Hindi / Marathi
        "एम": "M", "ओ": "O", "टी": "T", "एस": "S", "पी": "P", "एल": "L", "के": "K", "ए": "A",
        "बी": "B", "सी": "C", "डी": "D", "ई": "E", "आर": "R", "एन": "N", "एच": "H",
        "एफ": "F", "जी": "G", "आई": "I", "जे": "J", "क्यू": "Q", "यू": "U", "वी": "V", "डब्ल्यू": "W", "एक्स": "X", "वाई": "Y", "जेड": "Z",
        # Tamil
        "ஏ": "A", "பி": "B", "சி": "C", "டி": "D", "இ": "E", "எஃப்": "F", "ஜி": "G", "எச்": "H",
        "ஐ": "I", "ஜே": "J", "கே": "K", "எல்": "L", "எம்": "M", "என்": "N", "ஓ": "O",
        "ஆர்": "R", "எஸ்": "S", "யு": "U", "யூ": "U", "வி": "V", "டபிள்யு": "W", "எக்ஸ்": "X", "ஒய்": "Y", "இசட்": "Z",
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
        elif t.isdigit() and len(digit_buf) == 1 and len(t) == 2:
            # Combine spoken '2' + '23' ('two twenty three') into '223' without merging preceding RTO code ('34')
            digit_buf += t
            flush_buffers()
        else:
            flush_buffers()
            # Stop collecting if a non-plate multi-letter narrative word follows an already-complete numeric plate prefix
            if (
                grouped
                and len(grouped) >= 2
                and any(any(c.isdigit() for c in g) for g in grouped)
                and t.isalpha()
                and len(t) >= 4
                and t not in {"POLICY", "NUMBER"}
            ):
                break
            grouped.append(t)
    flush_buffers()

    if grouped and len(grouped) >= 2 and any(any(c.isdigit() for c in g) for g in grouped):
        # Never mistake vehicle make/model names or English prose for a registration/policy code
        _non_plate_alpha = {
            "BIKE", "CAR", "SCOOTER", "SCOOTY", "MODEL", "NAME", "HONDA", "BAJAJ", "HERO", "TVS",
            "YAMAHA", "SUZUKI", "MARUTI", "HYUNDAI", "TATA", "MAHINDRA", "KIA", "TOYOTA",
            "PULSAR", "PULSER", "IMPULSER", "ACTIVA", "SPLENDOR", "APACHE", "SWIFT", "CRETA",
            "NEXON", "THAR", "INNOVA", "FORTUNER", "CLASSIC", "BULLET", "DUKE", "RAIDER", "NTORQ",
        }
        has_valid_prefix = grouped[0] in INDIAN_STATE_CODES or grouped[0] in {"MOT", "POL", "CS", "BK", "INS", "VEH"}
        has_long_prose = any(g.isalpha() and (len(g) > 3 or g in _non_plate_alpha) for g in grouped)
        if not has_valid_prefix and has_long_prose:
            return None
        if any(g in _non_plate_alpha for g in grouped) and not has_valid_prefix:
            return None

        # Trim trailing narrative tokens after a valid registration plate only when grouped starts with a state code
        if grouped[0] in INDIAN_STATE_CODES and not any(g in {"MOT", "POL", "CS", "BK"} for g in grouped):
            joined_grouped = " ".join(grouped)
            m_plate = re.match(
                r"^([A-Za-z]{2})\s+(\d{1,2})(?:\s+([A-Za-z]{1,3}))?\s+(\d{3,4})\b",
                joined_grouped,
            )
            if m_plate:
                parts = [m_plate.group(1).upper(), m_plate.group(2).zfill(2)]
                if m_plate.group(3):
                    parts.append(m_plate.group(3).upper())
                parts.append(m_plate.group(4))
                return "-".join(parts)
        return "-".join(grouped)
    if len(grouped) == 1 and len(grouped[0]) >= 5 and any(c.isdigit() for c in grouped[0]):
        return grouped[0]

    return None


INDIAN_STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ",
    "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
    "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
    "UP", "WB",
}


def _extract_universal_indian_registration(text: str) -> Optional[str]:
    """
    Extract any Indian vehicle registration number across all states/UTs
    (with spaces, hyphens, dots, or compact form: e.g. 'KA 17 EA 4021', 'KL07AB1234', 'KA 05 1234').
    """
    pattern = re.compile(
        r"\b([A-Za-z]{2})[\s\-\.]?(\d{1,2})[\s\-\.]?([A-Za-z]{0,3})[\s\-\.]?(\d{3,4})\b"
    )
    for m in pattern.finditer(text or ""):
        st = m.group(1).upper()
        rto = m.group(2)
        series = m.group(3).upper()
        num = m.group(4)
        # Accept if valid Indian state code OR contains series letters (e.g., DL-3C-AS-1111)
        if st in INDIAN_STATE_CODES or (series and st not in {"AM", "PM", "ON", "AT", "IN", "TO", "BY", "NO", "OF"}):
            parts = [st, rto.zfill(2)]
            if series:
                parts.append(series)
            parts.append(num)
            return "-".join(parts)
    return None


def extract_claim_fields(transcript: str) -> Tuple[list[ClaimField], list[str]]:
    """
    Intelligently extract structured claim fields from English, Hinglish, Telugu (Tenglish),
    Kannada (Kanglish), Tamil, Marathi, and other Indic language transcripts.
    ALL extracted field values are normalized into clean English for insurer submission.
    """
    from ..evidence.cost_estimator import extract_vehicle_make_model, infer_vehicle_type_from_make_model

    text = transcript or ""
    text_lower = text.lower()
    detected_model = extract_vehicle_make_model(text)

    fields_dict: Dict[str, Tuple[Optional[str], FieldConfidence]] = {}

    # ── 1. Policy / Vehicle Reference (Always Uppercase English Alphanumeric) ──
    policy_pattern_re = re.compile(
        r"\b((?=[A-Za-z0-9\-]*\d)(?=[A-Za-z0-9\-]*[A-Za-z])[A-Za-z0-9]{2,5}(?:-[A-Za-z0-9]{1,6}){1,4})\b"
    )
    policy_match_val: Optional[str] = None
    _model_compact = re.sub(r"[^A-Z0-9]", "", (detected_model or "").upper())
    for pm in policy_pattern_re.finditer(text):
        cand = pm.group(1).strip().upper()
        cand_compact = re.sub(r"[^A-Z0-9]", "", cand)
        # Never confuse hyphenated vehicle models like MT-15, NS-200, XUV-700, FZ-S with a policy/plate number
        if _model_compact and cand_compact in _model_compact and not cand.startswith(("POL-", "MOT-", "CS-", "INS-", "VEH-")):
            if cand[:2] not in INDIAN_STATE_CODES or len(cand_compact) <= 6:
                continue
        if cand in {"MT-15", "NS-200", "RS-200", "XUV-700", "XUV-3XO", "FZ-S", "S-PRESSO"}:
            continue
        policy_match_val = cand
        break

    universal_plate = _extract_universal_indian_registration(text)
    if policy_match_val:
        fields_dict["policy_reference"] = (
            policy_match_val,
            FieldConfidence.HIGH,
        )
    elif universal_plate:
        fields_dict["policy_reference"] = (
            universal_plate,
            FieldConfidence.HIGH,
        )
    else:
        indic_policy = parse_indic_phonetic_policy(text, require_keyword=True)
        if not indic_policy:
            state_regex = "|".join(sorted(INDIAN_STATE_CODES | {"MOT", "POL", "CS"}))
            if re.search(
                rf"(?:\b(?:{state_regex})\b|ఎంఓటీ|ఎం ఓ టీ|ಕೆ ಎ|కె ఎ|కేఏ|కే ఏ|టీ ఎస్|టీఎస్|ఏపీ|ఎపి|"
                rf"ಕೆಎ|ಟಿಎನ್|ಟಿ ಎನ್|ಎಂಎಚ್|ಎಂ ಎಚ್|ಎಪಿ|"
                rf"டிஎன்|டி என்|கேஏ|கே ஏ|கேஎல்|கே எல்|எம்ஓடி|எம் ஓ டி|"
                rf"केए|के ए|एमएच|एम एच|डीएल|डी एल|टीएस|टी एस|एपी|यूपी|जीजे|आरजे|एमओटी)",
                text,
                re.IGNORECASE,
            ):
                indic_policy = parse_indic_phonetic_policy(text, require_keyword=False)
        if indic_policy:
            fields_dict["policy_reference"] = (indic_policy, FieldConfidence.HIGH)
        else:
            policy_explicit = re.search(
                r"(?:policy(?:\s*(?:number|no\.?|id|ref(?:erence)?))?|"
                r"(?:bike|car|scooter|vehicle|registration|reg|gaadi)\s+"
                r"(?:number|no\.?|reference|plate|నంబర్|నెంబర్|नंबर|नम्बर|ನಂಬರ್|நம்பர்|எண்))\s*(?:is|hai)?\s*[:\-]?\s*([A-Za-z0-9\-]{4,})",
                text,
                re.IGNORECASE,
            )
            if policy_explicit and any(c.isdigit() for c in policy_explicit.group(1)):
                fields_dict["policy_reference"] = (
                    policy_explicit.group(1).strip().upper(),
                    FieldConfidence.HIGH,
                )
            elif any(k in text_lower for k in ["policy", "bike number", "car number", "vehicle number", "registration", "పాలసీ", "పాలిసీ", "पॉलिसी", "ಪಾಲಿಸಿ", "பாலிசி"]):
                num_fallback = re.search(r"\b(\d{4,10})\b", text)
                if num_fallback:
                    fields_dict["policy_reference"] = (f"VEH-{num_fallback.group(1)}" if "policy" not in text_lower else f"POL-{num_fallback.group(1)}", FieldConfidence.HIGH)
                else:
                    fields_dict["policy_reference"] = (None, FieldConfidence.LOW)
            else:
                fields_dict["policy_reference"] = (None, FieldConfidence.MISSING)

    # ── 2. Vehicle Type (Accurate, un-guessed: 'bike', 'car', 'truck', 'auto_rickshaw', 'bus') ──
    # Generic regional words like Telugu 'బండి', Hindi 'gaadi', Tamil 'வண்டி' are NEVER hardcoded to 'car'.
    # If both explicit bike and explicit car words appear, resolve by possessive ownership ('my bike' vs 'car hit my bike'),
    # or leave MISSING so the assistant clarifies ("Is it a car or a bike?") when genuinely ambiguous.
    explicit_bike_kws = [
        "bike", "bikes", "motorcycle", "motorcycles", "motorbike", "scooter", "scooters", "scooty",
        "activa", "dio", "jupiter", "pulsar", "splendor", "apache", "bullet", "enfield",
        "two wheeler", "two-wheeler", "two_wheeler", "2 wheeler", "2w",
        "బైక్", "బైకు", "మోటార్ సైకిల్", "స్కూటర్", "స్కూటీ", "యాక్టివా",
        "बाइक", "बाईक", "स्कूटर", "स्कूटी", "मोटरसाइकिल", "दुचाकी",
        "ಬೈಕ್", "ಬೈಕು", "ಸ್ಕೂಟರ್", "பைக்", "பைக்கை", "ஸ்கூட்டர்", "இருசக்கர",
        "ബൈക്ക്", "സ്കൂട്ടർ", "বাইক", "স্কুটার", "બાઇક", "સ્કૂટર", "ਬਾਈਕ", "ਸਕੂਟਰ",
    ]
    explicit_car_kws = [
        "car", "cars", "motor car", "sedan", "suv", "hatchback", "swift", "baleno", "creta", "nexon", "innova",
        "four wheeler", "four-wheeler", "four_wheeler", "4 wheeler", "4w",
        "కార్", "కారు", "మోటార్ కారు", "कार", "चारचाकी", "ಕಾರು", "ಕಾರ್", "கார்", "காரை", "நான்கு சக்கர",
        "കാർ", "কার", "કાર", "ਕਾਰ",
    ]

    possessive_explicit = re.findall(
        r"(?:meri|apni|mera|apna|my|riding|on my|on a|naa|na|maa|nanna|en|ennoda|majhi|majha|ente|"
        r"माझ्या|माझी|माझा|मेरी|मेरा|अपनी|మా|నా|ನನ್ನ|என்|என்னுடைய|എന്റെ|আমার|મારી|મારું|ਮੇਰੀ|ਮੇਰਾ)\s+"
        r"(bikes?|motorcycle|scooters?|scooty|activa|dio|jupiter|pulsar|splendor|apache|bullet|enfield|two\s*wheeler|two_wheeler|"
        r"cars?|kaar|kar|sedan|suv|hatchback|swift|baleno|creta|nexon|innova|four\s*wheeler|four_wheeler|"
        r"truck|lorry|auto|rickshaw|"
        r"కార్|కారు|బైక్|బైకు|స్కూటర్|స్కూటీ|యాక్టివా|ఆటో|లారీ|"
        r"ಕಾರು|ಕಾರ್|ಬೈಕ್|ಬೈಕು|ಸ್ಕೂಟರ್|ಆಟೋ|"
        r"कार|बाइक|बाईक|स्कूटर|स्कूटी|दुचाकी|चारचाकी|ऑटो|ट्रक|"
        r"கார்|பைக்|ஆட்டோ|ബൈക്ക്|കാർ|বাইক|কার|બાઇક|કાર|ਬਾਈਕ|ਕਾਰ)",
        text_lower,
    )
    poss_is_bike = any(any(_contains_term(p, p, b) for b in explicit_bike_kws) for p in possessive_explicit)
    poss_is_car = any(any(_contains_term(p, p, c) for c in explicit_car_kws) for p in possessive_explicit)

    has_bike = any(_contains_term(text_lower, text, k) for k in explicit_bike_kws)
    has_car = any(_contains_term(text_lower, text, k) for k in explicit_car_kws)

    if poss_is_bike and not poss_is_car:
        fields_dict["vehicle_type"] = ("bike", FieldConfidence.HIGH)
    elif poss_is_car and not poss_is_bike:
        fields_dict["vehicle_type"] = ("car", FieldConfidence.HIGH)
    elif poss_is_bike and poss_is_car:
        # User claimed both 'my bike' and 'my car' — ambiguous, let AI clarify instead of guessing
        fields_dict["vehicle_type"] = (None, FieldConfidence.MISSING)
    elif has_bike and not has_car:
        fields_dict["vehicle_type"] = ("bike", FieldConfidence.HIGH)
    elif has_car and not has_bike:
        fields_dict["vehicle_type"] = ("car", FieldConfidence.HIGH)
    elif has_bike and has_car:
        # Both car and bike mentioned without possessive disambiguation -> ambiguous, let AI ask
        fields_dict["vehicle_type"] = (None, FieldConfidence.MISSING)
    elif any(_contains_term(text_lower, text, k) for k in ["truck", "lorry", "లారీ", "ట్రక్", "ట్రక్కు", "ट्रक", "ಲಾರಿ", "லாரி"]):
        fields_dict["vehicle_type"] = ("truck", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in ["auto", "rickshaw", "auto-rickshaw", "ఆటో", "ఆటో రిక్షా", "రిక్షా", "ऑटो", "ಆಟೋ", "ஆட்டோ"]):
        fields_dict["vehicle_type"] = ("auto_rickshaw", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in ["bus", "బస్సు", "बस", "ಬಸ್", "பேருந்து"]):
        fields_dict["vehicle_type"] = ("bus", FieldConfidence.HIGH)
    else:
        inferred_vt = infer_vehicle_type_from_make_model(detected_model)
        if inferred_vt:
            fields_dict["vehicle_type"] = (inferred_vt, FieldConfidence.HIGH)
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
        ("noida", "", "Noida"),
        ("नोएडा", "", "Noida"),
        ("kochi", "", "Kochi"),
        ("కొచ్చి", "", "Kochi"),
        ("കൊച്ചി", "", "Kochi"),
        ("कोच्चि", "", "Kochi"),
        ("పుణె", "", "Pune"),
        ("पुण्यात", "", "Pune"),
        ("पुणे", "", "Pune"),
        ("சென்னை", "", "Chennai"),
    ]

    matched_loc = None
    for city_term, area_term, resolved_name in known_locations:
        has_city = _contains_term(text_lower, text, city_term)
        has_area = _contains_term(text_lower, text, area_term) if area_term else True
        if has_city and has_area:
            matched_loc = resolved_name
            break

    if matched_loc:
        fields_dict["incident_location"] = (matched_loc, FieldConfidence.HIGH)
    else:
        loc_re = re.search(
            r"(?:in|at|near|on|లో|దగ్గర|వద్ద|ನಲ್ಲಿ|ಹತ್ತಿರ|ಅಲ್ಲಿ|में|के पास|मध्ये|जवळ|येथे|இல்|அருகில்|பக்கத்தில்|യിൽ|അടുത്ത്)?\s*"
            r"([\w\s\u0900-\u0DFF]{3,35}?)\s+"
            r"(?:mein|me(?=\s+(?:hua|hui|tha|thi|ek|accid|had|gadi|gaadi|car|bike))|madhe|road pe|ke paas|lo|deggara|daggara|దగ్గర|వద్ద|లో|రోడ్డుపై|ನಲ್ಲಿ|ಹತ್ತಿರ|ಅಲ್ಲಿ|में|के पास|मध्ये|जवळ|येथे|இல்|அருகில்|பக்கத்தில்|യിൽ|അടുത്ത്)\b",
            text,
            re.IGNORECASE,
        )
        attached_loc_re = re.search(
            r"(?:^|\s)([\u0900-\u0DFF]{3,28}?)(?:లో|దగ్గర|వద్ద|ನಲ್ಲಿ|ಯಲ್ಲಿ|मध्ये|जवळ|யில்|இல்|യിൽ|ൽ)(?=\s|[.,!?।]|$)",
            text,
        )
        eng_prep_loc = re.search(
            r"\b(?:near|outside|opposite|around|towards|at|in)\s+"
            r"([A-Za-z][A-Za-z0-9\s\-]{2,40}?)"
            r"(?=\s*(?:,|;|\.|yesterday|today|tomorrow|last\b|this\b|on\s+\d|around\s+\d|at\s+\d|and\s+(?:my|the|a|an|broke|damaged|hit)|when|while|$))",
            text,
            re.IGNORECASE,
        )
        non_places = {
            "side", "front", "back", "car", "bike", "scooter", "evening", "morning",
            "afternoon", "night", "accident", "damage", "repair", "time", "date",
            "today", "yesterday", "tomorrow", "today morning", "today evening",
            "yesterday morning", "yesterday evening", "last night", "this morning",
            "the evening", "the morning", "the afternoon", "india", "road",
            "can you hear", "you hear", "help", "tell", "hello", "please",
            "సైడ్", "మధ్య", "కారు", "కార్", "బైక్", "బండి", "అందు", "ఇందు", "రోడ్డు", "ఇంట్", "యాక్సిడెంట్",
            "गाड़ी", "बंपर", "साइड", "अपघात", "विपత్తు", "ಅಪಘಾತ", "ಅದರ", "ಇದರ", "വണ്ടി", "അപകട",
        }
        months_set = {
            "january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december",
            "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        }
        chosen_loc = None
        if loc_re:
            candidate = loc_re.group(1).strip()
            for prefix in ["నేను ", "మేము ", "నిన్న ", "ఈరోజు ", "nenu ", "main ", "i was ", "ನಾನು ", "ನಿನ್ನೆ ", "कल ", "काल "]:
                if candidate.lower().startswith(prefix.lower()):
                    candidate = candidate[len(prefix):].strip()
            if len(candidate) > 2 and candidate.lower() not in non_places and candidate.lower() not in months_set:
                chosen_loc = transliterate_indic_to_english(candidate)
        if not chosen_loc and attached_loc_re:
            stem = attached_loc_re.group(1).strip()
            if len(stem) >= 3 and stem.lower() not in non_places and not any(np in stem for np in non_places):
                chosen_loc = transliterate_indic_to_english(stem)
        non_place_tokens = {
            "accident", "crash", "collision", "damage", "damaged", "repair", "got", "had",
            "was", "were", "some", "pain", "shock", "trouble", "morning", "evening",
            "afternoon", "night", "english", "hindi", "telugu", "kannada", "tamil",
            "marathi", "malayalam", "details", "claim",
        }
        if not chosen_loc and eng_prep_loc:
            cand = re.sub(r"^(?:the|a|an)\s+", "", eng_prep_loc.group(1).strip(), flags=re.IGNORECASE)
            cand_words = set(re.findall(r"[a-z]+", cand.lower()))
            if (
                len(cand) > 2
                and cand.lower() not in non_places
                and cand.lower() not in months_set
                and not (cand_words & non_place_tokens)
                and not re.match(r"^\d+", cand)
            ):
                chosen_loc = cand.title()
        fields_dict["incident_location"] = (
            (chosen_loc, FieldConfidence.HIGH) if chosen_loc else (None, FieldConfidence.MISSING)
        )

    # ── 4. Incident Date & Time (Always English) ──
    month_pattern = (
        r"(?:january|february|march|april|may|june|july|august|september|october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    )
    month_date_re = re.search(
        rf"\b(?:(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({month_pattern})(?:\s*,?\s*(\d{{4}}))?|({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{{4}}))?)\b",
        text,
        re.IGNORECASE,
    )
    rel_days_ago_re = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|an|a)\s+(day|days|hour|hours|minute|minutes|week|weeks)\s+ago\b",
        text_lower,
    )
    weekday_re = re.search(
        r"\b(?:last\s+|this\s+|on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        text_lower,
    )
    date_re = re.search(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b", text)
    time_re = re.search(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.|గంటలకు|గంటలకి|బజే|baje|o'clock))\b",
        text,
        re.IGNORECASE,
    )

    if any(_contains_term(text_lower, text, k) for k in [
        "ninna evening", "ninna sayantram", "నిన్న సాయంత్రం", "నిన్న సాయంత్రము", "నిన్న సాయంకాలం", "నిన్న ఈవినింగ్",
        "kal shaam", "कल शाम", "ನಿನ್ನೆ ಸಂಜೆ", "ninne sanje", "நேற்று மாலை", "काल संध्याकाळी", "कल संध्याकाळी",
        "ഇന്നലെ വൈകുന്നേരം", "yesterday evening",
    ]):
        fields_dict["incident_date"] = ("Yesterday Evening", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in [
        "ninna afternoon", "నిన్న మధ్యాహ్నం", "నిన్న మధ్యాహ్నము", "kal dopahar", "कल दोपहर", "काल दुपारी",
        "ನಿನ್ನೆ ಮಧ್ಯಾಹ್ನ", "நேற்று மதியம்", "yesterday afternoon",
    ]):
        fields_dict["incident_date"] = ("Yesterday Afternoon", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in [
        "ninna morning", "నిన్న ఉదయం", "నిన్న పొద్దున్న", "kal subah", "कल सुबह", "काल सकाळी",
        "ನಿನ್ನೆ ಬೆಳಿಗ್ಗೆ", "நேற்று காலை", "yesterday morning",
    ]):
        fields_dict["incident_date"] = ("Yesterday Morning", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in [
        "ninna night", "నిన్న రాత్రి", "kal raat", "कल रात", "काल रात्री", "ನಿನ್ನೆ ರಾತ್ರಿ", "நேற்று இரவு",
        "yesterday night", "last night",
    ]):
        fields_dict["incident_date"] = ("Yesterday Night", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in ["day before yesterday", "parso", "परसों", "परवा", "monna", "మొన్న", "ಮೊನ್ನೆ"]):
        fields_dict["incident_date"] = ("Day Before Yesterday", FieldConfidence.HIGH)
    elif month_date_re:
        extracted_m_date = month_date_re.group(0).strip()
        if time_re:
            t_clean = re.sub(r"(?:గంటలకు|గంటలకి|బజే|baje)", "PM", time_re.group(1))
            fields_dict["incident_date"] = (f"{extracted_m_date} {t_clean}", FieldConfidence.HIGH)
        else:
            fields_dict["incident_date"] = (extracted_m_date, FieldConfidence.HIGH)
    elif rel_days_ago_re:
        fields_dict["incident_date"] = (rel_days_ago_re.group(0).strip().capitalize(), FieldConfidence.HIGH)
    elif date_re and time_re:
        t_clean = re.sub(r"(?:గంటలకు|గంటలకి|బజే|baje)", "PM", time_re.group(1))
        fields_dict["incident_date"] = (f"{date_re.group(1)} {t_clean}", FieldConfidence.HIGH)
    elif date_re:
        fields_dict["incident_date"] = (date_re.group(1), FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in ["kal", "कल", "yesterday", "ninna", "నిన్న", "ನಿನ್ನೆ", "ninne", "நேற்று", "netru", "काल", "ഇന്നലെ", "innale"]):
        if time_re:
            t_clean = re.sub(r"(?:గంటలకు|గంటలకి|బజే|baje)", "PM", time_re.group(1))
            fields_dict["incident_date"] = (f"Yesterday {t_clean}", FieldConfidence.HIGH)
        else:
            fields_dict["incident_date"] = ("Yesterday", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in [
        "aaj subah", "आज सुबह", "today morning", "this morning", "ee roju udayam", "ఈ రోజు ఉదయం", "ఈరోజు ఉదయం", "ఈరోజు పొద్దున్న",
        "ಇವತ್ತು ಬೆಳಿಗ್ಗೆ", "ಇಂದು ಬೆಳಿಗ್ಗೆ", "இன்று காலை", "आज सकाळी",
    ]):
        fields_dict["incident_date"] = ("Today Morning", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in [
        "aaj shaam", "आज शाम", "आज संध्याकाळी", "today evening", "this evening", "ఈ రోజు సాయంత్రం", "ఈరోజు సాయంత్రం", "ಇವತ್ತು ಸಂಜೆ", "இன்று மாலை",
    ]):
        fields_dict["incident_date"] = ("Today Evening", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in ["this afternoon", "आज दोपहर", "इன்று மதியம்", "ಇವತ್ತು ಮಧ್ಯಾಹ್ನ", "tonight", "aaj raat", "आज रात", "இன்று இரவு"]):
        fields_dict["incident_date"] = ("Today", FieldConfidence.HIGH)
    elif any(_contains_term(text_lower, text, k) for k in ["aaj", "आज", "today", "ee roju", "eeraju", "eeroju", "ఈ రోజు", "ఈరోజు", "ఇవాళ", "ಇವತ್ತು", "ಇಂದು", "ivattu", "இன்று", "indru", "ഇന്ന്", "innu", "just now"]):
        if time_re:
            t_clean = re.sub(r"(?:గంటలకు|గంటలకి|బజే|baje)", "PM", time_re.group(1))
            fields_dict["incident_date"] = (f"Today {t_clean}", FieldConfidence.HIGH)
        else:
            fields_dict["incident_date"] = ("Today", FieldConfidence.HIGH)
    elif weekday_re:
        fields_dict["incident_date"] = (weekday_re.group(0).strip().title(), FieldConfidence.HIGH)
    else:
        indic_time_to_eng = [
            ("ఆదివారం", "Sunday"), ("సోమవారం", "Monday"), ("మంగళవారం", "Tuesday"),
            ("బుధవారం", "Wednesday"), ("గురువారం", "Thursday"), ("శుక్రవారం", "Friday"), ("శనివారం", "Saturday"),
            ("సాయంత్రం", "Evening"), ("సాయంకాలం", "Evening"), ("ಸಂಜೆ", "Evening"), ("மாலை", "Evening"),
            ("ఉదయం", "Morning"), ("పొద్దున్న", "Morning"), ("ಬೆಳಿಗ್ಗೆ", "Morning"), ("காலை", "Morning"),
            ("మధ్యాహ్నం", "Afternoon"), ("ರಾತ್ರಿ", "Night"), ("రాత్రి", "Night"), ("இரவு", "Night"),
            ("ఐదున్నర", "5:30 PM"), ("ఆరున్నర", "6:30 PM"),
        ]
        eng_parts = [eng for ind, eng in indic_time_to_eng if ind in text]
        resolved_time = " ".join(dict.fromkeys(eng_parts)).strip()
        if resolved_time:
            fields_dict["incident_date"] = (resolved_time, FieldConfidence.HIGH)
        elif time_re:
            t_clean = re.sub(r"(?:గంటలకు|గంటలకి|బజే|baje)", "PM", time_re.group(1))
            fields_dict["incident_date"] = (t_clean, FieldConfidence.HIGH)
        else:
            fields_dict["incident_date"] = (None, FieldConfidence.MISSING)

    # ── 5. Damage Description (Always Translated/Normalized to English for Insurer) ──
    damage_indicators = [
        # English / Hinglish
        "damage", "damaged", "tut gaya", "tut gayi", "toot gaya", "toot gayi", "pichak gaya", "crushed", "broken", "broke",
        "hit", "leak", "dent", "dented", "fender", "door", "bonnet", "bumper", "headlight", "headlamp",
        "mudguard", "radiator", "scratch", "scratched", "windshield", "glass", "shatter", "shattered",
        "mirror", "indicator", "fork", "wheel", "rim", "tank", "fairing", "exhaust", "silencer",
        "clutch", "brake", "lever", "chassis", "frame", "panel", "boot", "dickie", "dicky", "roof",
        "tailgate", "skid", "skidded", "slipped", "fell", "crashed", "collided", "rammed", "smashed", "cracked",
        # Telugu
        "డ్యామేజ్", "డామేజ్", "లెఫ్ట్ డోర్", "రైట్ డోర్", "డోర్", "బంపర్", "మడ్ గార్డ్", "మడ్‌గార్డ్",
        "హెడ్‌లైట్", "హెడ్ లైట్", "బోనెట్", "హిట్", "గుద్దింది", "గుద్దేశాడు", "పగిలిపోయింది", "పగిలింది",
        "ఇరిగిపోయింది", "విరిగింది", "సొట్ట", "గీత", "అద్దం", "బాగా డ్యామేజ్",
        # Kannada
        "ಡ್ಯಾಮೇಜ್", "ಹಾನಿ", "ಮಡ್‌ಗಾರ್ಡ್", "ಹೆಡ್‌ಲೈಟ್", "ಬಂಪರ್", "ಡೋರ್", "ಒಡೆದಿದೆ", "ಜಖಂ", "ಮುರಿದಿದೆ",
        # Hindi / Marathi
        "डैमेज", "नुकसान", "टूट गया", "टूट गई", "तुटले", "फुटले", "पिचक गया", "डेंट", "टक्कर", "दरवाजा", "बंपर", "हेडलाइट", "हेडलाईट", "मडगार्ड",
        # Tamil / Malayalam / Bengali / Gujarati / Punjabi
        "சேதம்", "டேமேஜ்", "பம்பர்", "ஹெட்லைட்", "கதவு", "உடைந்தது", "கண்ணாடி",
        "ഹെഡ്ലൈറ്റ്", "ബമ്പർ", "പൊട്ടി", "ভাঙা", "হেডলাইট", "બમ્પર", "હેડલાઇટ", "ਟੁੱਟ",
    ]
    found_damages = [ind for ind in damage_indicators if _contains_term(text_lower, text, ind)]
    if found_damages:
        eng_damage = translate_damage_to_english(text)
        fields_dict["damage_description"] = (eng_damage, FieldConfidence.HIGH)
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
    from ..evidence.cost_estimator import extract_vehicle_make_model

    text = (raw_answer or "").strip()
    lang = detect_conversation_language(text, language)
    detected_model = extract_vehicle_make_model(text)

    # 1. Check if the user asked a question instead of providing a field value (e.g. "ಸಿ ಎಂ ಎಂ ಅಂದರೆ ಏನು?")
    question_markers = [
        "?", "ಅಂದರೆ ಏನು", "ಏನು", "అంటే ఏంటి", "ఏంటి", "मतलब क्या", "क्या है",
        "என்றால் என்ன", "என்ன", "म्हणजे काय", "काय आहे", "what is", "meaning",
    ]
    is_question = any(qm in text.lower() for qm in question_markers)

    # Run full extraction + relaxed phonetic policy/vehicle extraction on the answer
    extracted_fields, _ = extract_claim_fields(text)
    routed: Dict[str, str] = {
        f.name: f.value
        for f in extracted_fields
        if f.confidence != FieldConfidence.MISSING and f.value
    }

    # Also check relaxed universal registration & phonetic policy/vehicle extraction
    # (Skip relaxed phonetic guess on pure make/model utterances like "My bike model is Pulsar 220")
    if "policy_reference" not in routed and not is_question:
        candidate_pol = _extract_universal_indian_registration(text)
        if not candidate_pol and (not detected_model or any(k in text.lower() for k in ("number", "policy", "plate", "reg"))):
            candidate_pol = parse_indic_phonetic_policy(text, require_keyword=False)
        if candidate_pol and any(c.isdigit() for c in candidate_pol):
            routed["policy_reference"] = candidate_pol

    # If user asked a question, explain the current field in their language and do NOT fill the field
    if is_question:
        help_prompts = {
            "policy_reference": {
                "kn-IN": "ಇದು ನಿಮ್ಮ ವಾಹನದ ನೋಂದಣಿ ಸಂಖ್ಯೆ ಅಥವಾ ಇನ್ಶೂರೆನ್ಸ್ ಪಾಲಿಸಿ ಸಂಖ್ಯೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ವಾಹನ ಅಥವಾ ಪಾಲಿಸಿ ಸಂಖ್ಯೆಯನ್ನು ಹೇಳಿ.",
                "te-IN": "ఇది మీ వాహన రిజిస్ట్రేషన్ నంబర్ లేదా ఇన్సూరెన్స్ పాలసీ నంబర్. దయచేసి మీ వాహనం లేదా పాలసీ నంబర్ చెప్పండి.",
                "hi-IN": "यह आपकी गाड़ी का रजिस्ट्रेशन नंबर या बीमा पॉलिसी नंबर है। कृपया अपना नंबर बताएं।",
                "ta-IN": "இது உங்கள் வாகனப் பதிவு எண் அல்லது இன்சூரன்ஸ் பாலிசி எண். தயவுசெய்து உங்கள் எண்ணைச் சொல்லுங்கள்.",
                "mr-IN": "हा तुमच्या वाहनाचा नोंदणी क्रमांक किंवा विमा पॉलिसी क्रमांक आहे. कृपया तुमचा नंबर सांगा.",
                "en-IN": "This is your Vehicle Registration Number or Insurance Policy Number. Could you share whichever you have handy?",
            },
        }
        q_Prompt = (
            help_prompts.get(target_field, {}).get(lang)
            or FIELD_QUESTIONS.get(target_field, {}).get("by_lang", {}).get(lang)
            or "Could you please share that detail?"
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
        if not pol_val:
            # Never turn a vehicle model declaration ("My bike is Pulsar 220" / "MT-15") into a policy_reference
            has_model_phrase = bool(detected_model) or any(
                k in text.lower() for k in ("model", "pulsar", "pulser", "impulser", "splendor", "activa", "apache", "swift", "creta", "nexon", "thar")
            )
            if not has_model_phrase:
                compact = re.sub(r"[^A-Za-z0-9\-]", "", text).upper()
                if len(compact) >= 4 and sum(c.isdigit() for c in compact) >= 2 and not re.search(r"(?:MYBIKE|MYCAR|MODEL)", compact):
                    pol_val = compact
                    routed["policy_reference"] = pol_val
        if pol_val:
            return {
                "is_valid_for_target": True,
                "english_value": pol_val,
                "routed_fields": routed,
                "vehicle_make_model": detected_model,
                "error_prompt": None,
                "detected_language": lang,
            }
        # Reject non-alphanumeric / non-number / model-only text for policy_reference
        err_map = {
            "kn-IN": "ದಯವಿಟ್ಟು ಮಾನ್ಯವಾದ ವಾಹನ ನೋಂದಣಿ ಸಂಖ್ಯೆ ಅಥವಾ ಪಾಲಿಸಿ ಸಂಖ್ಯೆಯನ್ನು ತಿಳಿಸಿ.",
            "te-IN": "దయచేసి సరైన వాహన నంబర్ లేదా పాలసీ నంబర్ చెప్పండి.",
            "hi-IN": "कृपया अपनी गाड़ी का रजिस्ट्रेशन नंबर या पॉलिसी नंबर बताएं।",
            "ta-IN": "தயவுசெய்து சரியான வாகனப் பதிவு எண் அல்லது பாலிசி எண்ணைச் சொல்லுங்கள்.",
            "mr-IN": "कृपया तुमच्या वाहनाचा वैध नोंदणी क्रमांक किंवा पॉलिसी नंबर सांगा.",
            "en-IN": "I didn't quite catch the number — could you share your vehicle registration or policy number?",
        }
        return {
            "is_valid_for_target": False,
            "english_value": None,
            "routed_fields": routed,
            "vehicle_make_model": detected_model,
            "error_prompt": err_map.get(lang, err_map["en-IN"]),
            "detected_language": lang,
        }

    if target_field == "incident_location":
        # If the user spoke a policy/vehicle number instead of a location,
        # route it to policy_reference and ask naturally for incident_location.
        if "policy_reference" in routed and "incident_location" not in routed:
            pol_captured = routed["policy_reference"]
            reroute_msg = {
                "kn-IN": f"ನಿಮ್ಮ ಸಂಖ್ಯೆ {pol_captured} ದಾಖಲಾಗಿದೆ. ಈಗ ದಯವಿಟ್ಟು ಅಪಘಾತ ಎಲ್ಲಿ ನಡೆಯಿತು ಎಂದು ಹೇಳಿ.",
                "te-IN": f"మీ నంబర్ {pol_captured} నమోదైంది. ఇప్పుడు యాక్సిడెంట్ ఎక్కడ జరిగిందో చెప్పండి.",
                "hi-IN": f"आपका नंबर {pol_captured} नोट कर लिया है। अब कृपया बताएं कि हादसा किस जगह हुआ था?",
                "ta-IN": f"உங்கள் எண் {pol_captured} பதிவு செய்யப்பட்டது. இப்போது விபத்து எங்கே நடந்தது என்று சொல்லுங்கள்.",
                "mr-IN": f"तुमचा नंबर {pol_captured} नोंदवला आहे. आता अपघात नेमका कुठे झाला ते सांगा.",
                "en-IN": f"Got it, I've noted {pol_captured}. Where did the accident take place?",
            }
            return {
                "is_valid_for_target": False,
                "english_value": None,
                "routed_fields": routed,
                "error_prompt": reroute_msg.get(lang, reroute_msg["en-IN"]),
                "detected_language": lang,
            }

        loc_val = routed.get("incident_location")
        if not loc_val and not detected_model:
            non_loc_tokens = {
                "accident", "happened", "hua", "ayyindi", "aayitu", "aagiduchu", "jhala", "zala",
                "gaadi", "bandi", "vandi", "bike", "car", "damage", "broken", "confused", "model",
                "don't", "dont", "know", "pata", "nahi", "yes", "no", "okay", "ok", "hello", "hi",
                "యాక్సిడెంట్", "एक्सीडेंट", "ಅಪಘಾತ", "விபத்து", "अपघात",
            }
            words_in_ans = re.findall(r"[^\s,.;!?]+", text.lower())
            has_non_loc = any(w in non_loc_tokens for w in words_in_ans)
            if 1 <= len(words_in_ans) <= 4 and not has_non_loc:
                eng_candidate = transliterate_indic_to_english(text)
                if eng_candidate and not eng_candidate.isdigit() and len(eng_candidate) >= 3:
                    loc_val = eng_candidate
                    routed["incident_location"] = loc_val

        if loc_val:
            return {
                "is_valid_for_target": True,
                "english_value": loc_val,
                "routed_fields": routed,
                "vehicle_make_model": detected_model,
                "error_prompt": None,
                "detected_language": lang,
            }

        err_loc = {
            "kn-IN": "ಅಪಘಾತ ನಡೆದ ಸ್ಥಳ ಅಥವಾ ನಗರವನ್ನು ತಿಳಿಸಬಹುದೇ?",
            "te-IN": "యాక్సిడెంట్ జరిగిన ప్రాంతం లేదా నగరం పేరు చెప్పగలరా?",
            "hi-IN": "कृपया हादसे की जगह या शहर का नाम बताएं।",
            "ta-IN": "விபத்து நடந்த இடம் அல்லது நகரத்தின் பெயரைச் சொல்லுங்கள்.",
            "mr-IN": "कृपया अपघात झालेल्या ठिकाणाचे किंवा शहराचे नाव सांगा.",
            "en-IN": "Could you share the area or city where the accident occurred?",
        }
        return {
            "is_valid_for_target": False,
            "english_value": None,
            "routed_fields": routed,
            "vehicle_make_model": detected_model,
            "error_prompt": err_loc.get(lang, err_loc["en-IN"]),
            "detected_language": lang,
        }

    if target_field == "incident_date":
        date_val = routed.get("incident_date")
        if not date_val:
            # Accept natural temporal replies containing a date digit or time/day keyword,
            # but NEVER misread model CC numbers ("Pulsar 220", "Classic 350") as a date!
            temporal_kws = [
                "morning", "evening", "afternoon", "night", "noon", "week", "month", "day", "ago", "last", "this",
                "shaam", "subah", "raat", "dopahar", "kal", "parso", "aaj", "am", "pm", "baje",
                "ninna", "ninne", "ivattu", "sanje", "beligge", "raatri", "monne", "monna", "eeroju", "udayam", "sayantram",
                "netru", "indru", "kaalai", "maalai", "iravu", "innale", "innu", "sakali", "sandhyakali",
            ]
            has_date_sep = bool(re.search(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b", text))
            has_temporal_kw = any(_contains_term(text.lower(), text, k) for k in temporal_kws)
            if len(text) >= 3 and (has_temporal_kw or has_date_sep or (any(c.isdigit() for c in text) and not detected_model)):
                date_val = transliterate_indic_to_english(text) if any(ord(c) > 127 for c in text) else text.strip()
                routed["incident_date"] = date_val
        if date_val:
            return {
                "is_valid_for_target": True,
                "english_value": date_val,
                "routed_fields": routed,
                "vehicle_make_model": detected_model,
                "error_prompt": None,
                "detected_language": lang,
            }
        err_date = {
            "kn-IN": "ದಯವಿಟ್ಟು ಅಪಘಾತ ನಡೆದ ದಿನಾಂಕ ಅಥವಾ ಸಮಯವನ್ನು ಹೇಳಿ (ಉದಾ: ನಿನ್ನೆ ಸಂಜೆ, ಇಂದು ಬೆಳಿಗ್ಗೆ).",
            "te-IN": "దయచేసి యాక్సిడెంట్ జరిగిన తేదీ లేదా సమయం చెప్పండి (ఉదా: నిన్న సాయంత్రం, ఈరోజు ఉదయం).",
            "hi-IN": "कृपया हादसे की तारीख या समय बताएं (जैसे: कल शाम, आज सुबह)।",
            "ta-IN": "விபத்து நடந்த தேதி அல்லது நேரத்தைச் சொல்லுங்கள் (எ.கா: நேற்று மாலை, இன்று காலை).",
            "mr-IN": "कृपया अपघात झाल्याची तारीख किंवा वेळ सांगा (उदा. काल संध्याकाळी, आज सकाळी).",
            "en-IN": "Please state when the accident happened (e.g. Yesterday Evening, Today Morning, or a date/time).",
        }
        return {
            "is_valid_for_target": False,
            "english_value": None,
            "routed_fields": routed,
            "vehicle_make_model": detected_model,
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
            "ta-IN": "உங்கள் வாகனத்தின் வகையைச் சொல்லுங்கள் - கார், பைக், ஆட்டோ அல்லது டிரக்?",
            "mr-IN": "कृपया तुमच्या वाहनाचा प्रकार सांगा - कार, बाईक, रिक्षा की ट्रक?",
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


def extract_multimodal_slots(text: str, language_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract key multi-slot information from conversational or code-mixed utterances:
    - claimed_vehicle_type ('two_wheeler' vs 'four_wheeler')
    - vehicle_registration (normalized uppercase e.g. KA-17-AB-1234)
    - damage_keywords (list of detected damage tokens)
    - incident_description (text summary)
    - detected_language (code-mixed or Indic language tag)
    """
    raw_text = (text or "").strip()
    text_lower = raw_text.lower()

    # 1. Vehicle Registration Number (Universal Indian Format Normalization)
    vehicle_registration = _extract_universal_indian_registration(raw_text)

    # 2. Claimed Vehicle Type (Two-Wheeler vs Four-Wheeler, word-boundary safe)
    two_wheeler_markers = [
        "bike", "bikes", "motorcycle", "motorbike", "scooter", "scooters", "scooty", "activa", "dio", "jupiter",
        "pulsar", "splendor", "apache", "bullet", "2w", "two wheeler", "two-wheeler", "two_wheeler",
        "ಬೈಕ್", "ಬೈಕು", "ಸ್ಕೂಟರ್", "बाइक", "बाईक", "स्कूटी", "स्कूटर", "दुचाकी",
        "பைக்", "பைக்கை", "ஸ்கூட்டர்", "இருசக்கர", "బైక్", "బైకు", "స్కూటర్", "స్కూటీ",
        "ബൈക്ക്", "സ്കൂട്ടർ", "বাইক", "স্কুটার", "બાઇક", "સ્કૂટર", "ਬਾਈਕ", "ਸਕੂਟਰ",
    ]
    four_wheeler_markers = [
        "car", "cars", "sedan", "suv", "hatchback", "swift", "baleno", "creta", "nexon",
        "innova", "four wheeler", "four-wheeler", "four_wheeler", "4w",
        "कार", "चारचाकी", "ಕಾರ್", "ಕಾರು", "கார்", "காரை", "நான்கு சக்கர", "కారు", "కార్",
        "കാർ", "কার", "કાર", "ਕਾਰ",
    ]
    claimed_vehicle_type = None
    has_2w = any(_contains_term(text_lower, raw_text, marker) for marker in two_wheeler_markers)
    has_4w = any(_contains_term(text_lower, raw_text, marker) for marker in four_wheeler_markers)
    if has_2w and not has_4w:
        claimed_vehicle_type = "two_wheeler"
    elif has_4w and not has_2w:
        claimed_vehicle_type = "four_wheeler"

    # 3. Damage Keywords
    candidate_damages = [
        "headlamp", "headlight", "fairing", "mudguard", "bumper", "windshield",
        "glass", "dent", "scratch", "crack", "shatter", "door", "hood", "bonnet",
        "fender", "mirror", "side mirror", "tire", "lamp", "indicator", "broken",
        "break", "toot", "tuta", "tooti", "damage", "scratches", "dents",
        "cracks", "haani",
    ]
    damage_keywords = [d for d in candidate_damages if _contains_term(text_lower, raw_text, d)]

    # 4. Detected Language (with Code-Mixed Latn variants & all supported Indic scripts)
    detected_lang = "en-IN"
    if any(0x0C80 <= ord(c) <= 0x0CFF for c in raw_text):
        detected_lang = "kn-IN"
    elif any(0x0C00 <= ord(c) <= 0x0C7F for c in raw_text):
        detected_lang = "te-IN"
    elif any(0x0B80 <= ord(c) <= 0x0BFF for c in raw_text):
        detected_lang = "ta-IN"
    elif any(0x0D00 <= ord(c) <= 0x0D7F for c in raw_text):
        detected_lang = "ml-IN"
    elif any(0x0980 <= ord(c) <= 0x09FF for c in raw_text):
        detected_lang = "bn-IN"
    elif any(0x0A80 <= ord(c) <= 0x0AFF for c in raw_text):
        detected_lang = "gu-IN"
    elif any(0x0A00 <= ord(c) <= 0x0A7F for c in raw_text):
        detected_lang = "pa-IN"
    elif any(0x0600 <= ord(c) <= 0x06FF for c in raw_text):
        detected_lang = "ur-IN"
    elif any(0x0900 <= ord(c) <= 0x097F for c in raw_text):
        marathi_markers = ["माझ्या", "माझी", "माझा", "झाला", "झाली", "गाडीचा", "पुण्यात", "कोथरूड", "आहे", "अपघात", "संध्याकाळी", "सकाळी", "दुपारी", "बाईक"]
        if any(m in raw_text for m in marathi_markers) or (language_hint or "").lower().startswith("mr"):
            detected_lang = "mr-IN"
        else:
            detected_lang = "hi-IN"
    else:
        # Romanized code-mixed checks
        tokens = set(re.findall(r"[a-z]+", text_lower))
        kanglish_markers = {"nanna", "aagide", "aayitu", "mattu", "illi", "alli", "hattira", "ninne", "ivattu", "maadide", "beku"}
        tanglish_markers = {"ennoda", "vandi", "aagiduchu", "aachu", "netru", "pakkathula", "indru", "thayavu"}
        tenglish_markers = {"naa", "chudandi", "ayyindi", "aindi", "chesindi", "ninna", "eeroju", "vachi", "dayachesi"}
        marathi_latn_markers = {"majha", "majhi", "jhala", "zala", "apghat", "madhe"}
        malayalam_latn_markers = {"ente", "innale", "innu", "evide", "aayi"}
        hinglish_markers = {"mera", "meri", "mere", "hua", "gaya", "gayi", "tha", "thi", "hai", "ho gaya", "tut", "toot", "kripya", "dekho"}

        if len(tokens & kanglish_markers) >= 1:
            detected_lang = "kn-Latn"
        elif len(tokens & tanglish_markers) >= 1:
            detected_lang = "ta-Latn"
        elif len(tokens & tenglish_markers) >= 1:
            detected_lang = "te-Latn"
        elif len(tokens & marathi_latn_markers) >= 1:
            detected_lang = "mr-Latn"
        elif len(tokens & malayalam_latn_markers) >= 1:
            detected_lang = "ml-Latn"
        elif len(tokens & hinglish_markers) >= 1:
            detected_lang = "hi-Latn"
        elif language_hint and language_hint.lower() != "indic-auto":
            detected_lang = language_hint

    from ..evidence.cost_estimator import extract_vehicle_make_model
    vehicle_make_model = extract_vehicle_make_model(raw_text)
    motor_slots = extract_group_a_motor_slots(raw_text, resolved_vehicle_type=claimed_vehicle_type)
    if vehicle_registration and not motor_slots.get("claimed_registration"):
        motor_slots["claimed_registration"] = vehicle_registration
    if vehicle_make_model:
        motor_slots["vehicle_make_model"] = vehicle_make_model

    return {
        "claimed_vehicle_type": claimed_vehicle_type,
        "vehicle_make_model": vehicle_make_model,
        "vehicle_registration": vehicle_registration,
        "claimed_registration": vehicle_registration,
        "motor_slots": motor_slots,
        "damage_keywords": damage_keywords,
        "incident_description": raw_text,
        "detected_language": detected_lang,
    }


_OCCUPANT_WORD_TO_INT = {
    "one": 1, "single": 1, "alone": 1, "solo": 1,
    "two": 2, "couple": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8,
}


def extract_group_a_motor_slots(
    text: str,
    resolved_vehicle_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract Group A conversational Indian Motor Claim slots deterministically
    when mentioned naturally in speech/text, without guessing or asking for long form IDs.
    """
    raw = (text or "").strip()
    low = raw.lower()
    slots: Dict[str, Any] = {}

    reg = _extract_universal_indian_registration(raw)
    if reg:
        slots["claimed_registration"] = reg

    # 1. loss_type
    theft_cues = ("stolen", "theft", "robbed", "chori", "चोरी", "దొంగతనం", "ಕಳ್ಳತನ", "திருட்டு")
    fire_cues = (
        "caught fire", "on fire", "burnt", "short circuit", "flood", "waterlogged",
        "submerged", "cyclone", "tree fell", "aag lag", "आग", "बाढ़", "మంట", "వరద",
    )
    tp_only_cues = ("third party", "third-party", "hit a pedestrian", "damaged third party")
    own_dmg_cues = (
        "accident", "crash", "crashed", "hit", "collided", "skid", "slipped",
        "dent", "scratch", "broken", "damaged", "bumper", "headlight", "mirror",
        "ప్రమాదం", "ಅಪಘಾತ", "हादसा", "टक्कर",
    )
    if any(_contains_term(low, raw, c) for c in theft_cues):
        slots["loss_type"] = "theft"
    elif any(_contains_term(low, raw, c) for c in fire_cues):
        slots["loss_type"] = "fire_natural_calamity"
    elif any(c in low for c in tp_only_cues) and not any(_contains_term(low, raw, c) for c in own_dmg_cues):
        slots["loss_type"] = "third_party"
    elif any(_contains_term(low, raw, c) for c in own_dmg_cues):
        slots["loss_type"] = "own_damage_accident"

    # 2. incident_time
    time_match = re.search(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}\s*(?:baje|gantalu|gante|mani|o'clock))\b",
        raw,
        re.IGNORECASE,
    )
    if time_match:
        slots["incident_time"] = time_match.group(1).strip()
    else:
        tod_map = [
            ("early morning", "Early Morning"), ("morning", "Morning"), ("afternoon", "Afternoon"),
            ("evening", "Evening"), ("midnight", "Midnight"), ("night", "Night"),
            ("subah", "Morning"), ("dopahar", "Afternoon"), ("shaam", "Evening"), ("raat", "Night"),
            ("सुबह", "Morning"), ("दोपहर", "Afternoon"), ("शाम", "Evening"), ("रात", "Night"),
            ("ఉదయం", "Morning"), ("సాయంత్రం", "Evening"), ("రాత్రి", "Night"),
            ("ಬೆಳಿಗ್ಗೆ", "Morning"), ("ಸಂಜೆ", "Evening"), ("ರಾತ್ರಿ", "Night"),
        ]
        for cue, eng_tod in tod_map:
            if _contains_term(low, raw, cue):
                slots["incident_time"] = eng_tod
                break

    # 3. driver_was_owner, driver_name, driver_relationship
    paid_drv = re.search(
        r"(?:my|our|the)?\s*(?:paid\s+driver|chauffeur|driver)(?:\s+([A-Z][a-z]{1,20}))?\s+(?:was\s+)?(?:driving|riding|at\s+the\s+wheel)",
        raw,
        re.IGNORECASE,
    )
    rel_friend = re.search(
        r"(?:my\s+(?:friend|brother|sister|cousin|father|dad|mother|mom|son|daughter|wife|husband|uncle|relative))(?:\s+([A-Z][a-z]{1,20}))?\s+(?:was\s+)?(?:driving|riding)",
        raw,
        re.IGNORECASE,
    )
    hinglish_other = re.search(
        r"(?:mera\s+(?:dost|bhai|driver))(?:\s+([A-Za-z]{2,20}))?\s+(?:chala|drive)",
        raw,
        re.IGNORECASE,
    )
    if paid_drv:
        slots["driver_was_owner"] = False
        slots["driver_relationship"] = "paid_driver"
        if paid_drv.group(1):
            slots["driver_name"] = paid_drv.group(1).strip().title()
    elif rel_friend:
        slots["driver_was_owner"] = False
        slots["driver_relationship"] = "relative_or_friend"
        if rel_friend.group(1):
            slots["driver_name"] = rel_friend.group(1).strip().title()
    elif hinglish_other:
        slots["driver_was_owner"] = False
        slots["driver_relationship"] = "paid_driver" if "driver" in low else "relative_or_friend"
        if hinglish_other.group(1):
            slots["driver_name"] = hinglish_other.group(1).strip().title()
    elif any(
        p in low
        for p in (
            "i was driving", "i was riding", "i drove", "myself driving",
            "main chala raha", "main khud", "nene naduputunnanu", "naane odistidde",
        )
    ):
        slots["driver_was_owner"] = True
        slots["driver_relationship"] = "owner"

    # 4. vehicle_usage_type
    if any(c in low for c in ("commercial", "yellow board", "taxi", "cab", "ola", "uber", "rapido", "delivery", "hire")):
        slots["vehicle_usage_type"] = "commercial_hire_reward"
    elif any(c in low for c in ("personal use", "private vehicle", "private car", "personal bike", "office commute", "family trip", "white board")):
        slots["vehicle_usage_type"] = "private_social_domestic"

    # 5. 2W-only pillion_rider_present OR 4W-only occupants_count
    vtype_eff = resolved_vehicle_type
    if not vtype_eff:
        if any(_contains_term(low, raw, m) for m in ("bike", "scooter", "motorcycle", "scooty", "2w", "two wheeler", "బైక్", "ಬೈಕ್", "बाइक")):
            vtype_eff = "two_wheeler"
        elif any(_contains_term(low, raw, m) for m in ("car", "suv", "sedan", "hatchback", "4w", "four wheeler", "కారు", "ಕಾರ್", "कार")):
            vtype_eff = "four_wheeler"

    if vtype_eff == "two_wheeler":
        if any(p in low for p in ("no pillion", "without pillion", "riding alone", "alone on bike", "solo ride", "only me on bike")):
            slots["pillion_rider_present"] = False
        elif any(p in low for p in ("pillion", "riding double", "sitting behind", "friend behind", "wife behind", "with my friend on bike", "two of us")):
            slots["pillion_rider_present"] = True
    elif vtype_eff == "four_wheeler":
        occ_match = re.search(
            r"\b(\d+|one|two|three|four|five|six|seven|eight)\s+(?:people|persons|occupants|passengers|members|friends|log|jana)\b",
            low,
        )
        if occ_match:
            tok = occ_match.group(1)
            val = int(tok) if tok.isdigit() else _OCCUPANT_WORD_TO_INT.get(tok)
            if val is not None:
                slots["occupants_count"] = val
        elif any(p in low for p in ("driving alone", "alone in the car", "only me in car")):
            slots["occupants_count"] = 1

    # 6. injury_or_third_party_flag
    no_inj_cues = ("no injury", "no injuries", "nobody hurt", "no one hurt", "unhurt", "all safe", "no third party")
    pos_inj_cues = ("injured", "injury", "hospital", "fracture", "bleeding", "pedestrian", "third party", "third-party")
    if any(p in low for p in pos_inj_cues):
        slots["injury_or_third_party_flag"] = True
    elif any(p in low for p in no_inj_cues):
        slots["injury_or_third_party_flag"] = False

    # 7. police_fir_lodged_flag
    no_fir_cues = ("no fir", "fir not filed", "not filed fir", "didn't file fir", "did not file fir", "no police report", "no police complaint")
    yes_fir_cues = ("fir filed", "fir lodged", "lodged fir", "lodged an fir", "filed fir", "filed a police complaint", "police report filed", "gd entry")
    if any(p in low for p in no_fir_cues):
        slots["police_fir_lodged_flag"] = False
    elif any(p in low for p in yes_fir_cues):
        slots["police_fir_lodged_flag"] = True

    # 8. inspection_location
    insp_match = re.search(
        r"(?:parked\s+at|kept\s+at|taken\s+to|inspect(?:ion)?\s+(?:at|near)|at)\s+([A-Za-z0-9][A-Za-z0-9\s,&-]{2,48}?(?:service\s*cent(?:er|re)|workshop|garage|motors|showroom))",
        raw,
        re.IGNORECASE,
    )
    if insp_match:
        slots["inspection_location"] = re.sub(r"\s+", " ", insp_match.group(1)).strip(" ,.")

    return slots


def generate_code_mixed_slot_reply(
    slots: Dict[str, Any],
    language_hint: Optional[str] = None,
) -> str:
    """
    Generate a concise (1-2 sentences, <35 words), empathetic roadside voice reply
    matching the speaker's language or code-mix (Hinglish, Kanglish, Tanglish, Teluglish, English).
    Zero markdown or JSON symbols.
    """
    lang_norm = (language_hint or slots.get("detected_language") or "en-IN").lower()
    vtype = slots.get("claimed_vehicle_type")
    reg = slots.get("vehicle_registration") or ""
    dmgs = slots.get("damage_keywords") or []
    dmg_phrase = " aur ".join(dmgs[:2]) if "hi" in lang_norm or "hinglish" in lang_norm else ", ".join(dmgs[:2])

    if "kn" in lang_norm or "kanglish" in lang_norm:
        v_word = "bike" if vtype == "two_wheeler" else "car" if vtype == "four_wheeler" else "vehicle"
        reg_part = f" {reg}" if reg else ""
        return f"Nimma {v_word}{reg_part} damage vivara note maadiddene. Dayavittu ega damage photo upload maadi."
    if "ta" in lang_norm or "tanglish" in lang_norm:
        v_word = "bike" if vtype == "two_wheeler" else "car" if vtype == "four_wheeler" else "vehicle"
        reg_part = f" {reg}" if reg else ""
        return f"Unga {v_word}{reg_part} damage vivaram note pannitten. Ippo damaged photo upload pannunga."
    if "te" in lang_norm or "teluglish" in lang_norm or "tenglish" in lang_norm:
        v_word = "bike" if vtype == "two_wheeler" else "car" if vtype == "four_wheeler" else "vehicle"
        reg_part = f" {reg}" if reg else ""
        return f"Mee {v_word}{reg_part} damage vivaralu note chesanu. Ippudu damage photo upload cheyandi."
    if "hi" in lang_norm or "hinglish" in lang_norm:
        v_word = "bike" if vtype == "two_wheeler" else "car" if vtype == "four_wheeler" else "gaadi"
        reg_part = f" {reg}" if reg else ""
        dmg_note = f" ke {dmg_phrase}" if dmg_phrase else ""
        return f"Maine aapki {v_word}{reg_part}{dmg_note} ka damage note kar liya hai. Ab kripya photo upload karein."

    v_word = "bike" if vtype == "two_wheeler" else "car" if vtype == "four_wheeler" else "vehicle"
    reg_part = f" {reg}" if reg else ""
    dmg_note = f" ({dmg_phrase})" if dmg_phrase else ""
    return f"Got it, I have noted the damage for your {v_word}{reg_part}{dmg_note}. Please upload a clear photo now."


def _format_damage_names_for_speech(damages: Optional[list]) -> str:
    """Convert damage items (dicts or strings) into a concise spoken phrase."""
    if not damages:
        return ""
    names = []
    for item in damages:
        if isinstance(item, str):
            raw = item
        elif isinstance(item, dict):
            raw = item.get("damage_type") or item.get("class_name") or ""
        else:
            raw = ""
        clean = str(raw).replace("_", " ").strip()
        if clean and clean not in names:
            names.append(clean)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{names[0]} and {names[1]}"


def generate_evidence_narration(
    decision: str,
    claimed_vehicle_type: str = "four_wheeler",
    detected_vehicle_category: Optional[str] = None,
    vehicle_category_mismatch: bool = False,
    total_estimated_inr: float = 0.0,
    damages: Optional[list] = None,
    language: Optional[str] = "hi-IN",
    reasons: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Generate spoken Indic / code-mixed explanation for multimodal evidence verdict.
    Concise (1-3 sentences, <40 words, no markdown or symbols) for clean TTS playback.
    Handles PASS (approved estimate), REVIEW (provisional queue or missing vehicle),
    and REJECT (category mismatch, person/selfie capture, or file error).
    """
    amt = int(round(float(total_estimated_inr or 0)))
    lang_code = (language or "hi-IN").strip()
    norm = lang_code.lower()
    dmg_phrase = _format_damage_names_for_speech(damages)
    reason_list = [str(r) for r in (reasons or [])]
    is_person_selfie = any("NON_VEHICLE_PERSON_SELFIE" in r for r in reason_list)
    is_no_vehicle_reject = any("NO_VEHICLE_DETECTED_REJECTED" in r or "NON_VEHICLE_OBJECT_DETECTED" in r for r in reason_list)
    no_vehicle_detected = any("NO_VEHICLE_OR_DAMAGE" in r for r in reason_list)

    if "kn" in norm or "kanglish" in norm:
        target_lang = "kn-IN"
        if decision == "REJECT":
            if is_person_selfie:
                spoken = "Photo reject aagide. Camera nalli vehicle badalu vyakti kanisuttiddare. Dayavittu damaged bike athava car photo upload maadi."
            elif is_no_vehicle_reject:
                spoken = "Photo reject aagide. Ee chitra nalli yavude bike athava car kanisuttilla. Dayavittu damaged vehicle photo upload maadi."
            elif vehicle_category_mismatch:
                if claimed_vehicle_type == "two_wheeler":
                    spoken = "Photo reject aagide. Neevu bike claim maadiddiri aadare car photo upload aagide. Dayavittu bike photo upload maadi."
                else:
                    spoken = "Photo reject aagide. Neevu car claim maadiddiri aadare bike photo upload aagide. Dayavittu car photo upload maadi."
            else:
                spoken = "File integrity dooshadinda photo reject aagide. Dayavittu innondu spashtavada photo upload maadi."
        elif decision == "PASS":
            dmg_text = f" ({dmg_phrase})" if dmg_phrase else ""
            spoken = f"Evidence verify aagide. AI damage{dmg_text} detect maadi {amt} rupayi repair estimate approve maadide."
        elif no_vehicle_detected or amt == 0:
            spoken = "Frame nalli vehicle athava damage spashtavagi kanisuttilla. Dayavittu damaged vehicle na spashtavada photo upload maadi."
        else:
            spoken = f"Evidence preliminary review queue ge hogide. Sumaru {amt} rupayi provisional estimate ide, surveyor verify maaduttare."

    elif "ta" in norm or "tanglish" in norm:
        target_lang = "ta-IN"
        if decision == "REJECT":
            if is_person_selfie:
                spoken = "Photo reject aagiduchu. Vaganathukku badilaaga manithar mugam therigirathu. Thayavu seidhu damaged vaganathin photo upload pannunga."
            elif is_no_vehicle_reject:
                spoken = "Photo reject aagiduchu. Indha photovil endha bike allathu car-um theriyavillai. Thayavu seidhu damaged vaganathin photo upload pannunga."
            elif vehicle_category_mismatch:
                if claimed_vehicle_type == "two_wheeler":
                    spoken = "Photo reject aagiduchu. Neenga bike claim panneenga aana car photo upload aachu. Thayavu seidhu bike photo upload pannunga."
                else:
                    spoken = "Photo reject aagiduchu. Neenga car claim panneenga aana bike photo upload aachu. Thayavu seidhu car photo upload pannunga."
            else:
                spoken = "File integrity kolarinaal photo reject aagiduchu. Thayavu seidhu vera thelivaana photo upload pannunga."
        elif decision == "PASS":
            dmg_text = f" ({dmg_phrase})" if dmg_phrase else ""
            spoken = f"Evidence verify aagiduchu. AI damage{dmg_text} kandupidithu {amt} roobai repair estimate approve panniyullathu."
        elif no_vehicle_detected or amt == 0:
            spoken = "Photovil vaganam alladhu damage thelivaaga theriyavillai. Thayavu seidhu vaganathin thelivaana photo upload pannunga."
        else:
            spoken = f"Evidence preliminary review queue ku anuppappattullathu. Sumaar {amt} roobai provisional estimate kidaithullathu, surveyor verify seivaar."

    elif "te" in norm or "teluglish" in norm or "tenglish" in norm:
        target_lang = "te-IN"
        if decision == "REJECT":
            if is_person_selfie:
                spoken = "Photo reject ayyindi. Camera lo vehicle badulu person kanipistunnaru. Dayachesi mee damaged vehicle photo upload cheyandi."
            elif is_no_vehicle_reject:
                spoken = "Photo reject ayyindi. Ee photo lo bike leda car kanipinchadam ledu. Dayachesi mee damaged vehicle clear photo upload cheyandi."
            elif vehicle_category_mismatch:
                if claimed_vehicle_type == "two_wheeler":
                    spoken = "Photo reject ayyindi. Meeru bike claim chesaru kani car photo upload aindi. Dayachesi bike photo upload cheyandi."
                else:
                    spoken = "Photo reject ayyindi. Meeru car claim chesaru kani bike photo upload aindi. Dayachesi car photo upload cheyandi."
            else:
                spoken = "File integrity samasya valla photo reject ayyindi. Dayachesi maro spastamaina photo upload cheyandi."
        elif decision == "PASS":
            dmg_text = f" ({dmg_phrase})" if dmg_phrase else ""
            spoken = f"Evidence verify ayyindi. AI damage{dmg_text} gurtinchi {amt} roopayala repair estimate approve chesindi."
        elif no_vehicle_detected or amt == 0:
            spoken = "Ee photo lo vehicle leda damage spastanga kanipinchadam ledu. Dayachesi mee vehicle clear photo upload cheyandi."
        else:
            spoken = f"Evidence preliminary review queue ki pampabadindi. Sumaru {amt} roopayala provisional estimate vachindi, surveyor verify chestaru."

    elif "hi" in norm or "hinglish" in norm:
        target_lang = "hi-IN"
        if decision == "REJECT":
            if is_person_selfie:
                spoken = "Photo reject ho gaya hai. Camera mein gaadi ki jagah aapka chehra ya selfie aaya hai. Kripya damaged gaadi ki saaf photo upload karein."
            elif is_no_vehicle_reject:
                spoken = "Photo reject ho gaya hai kyunki is photo mein koi bike ya car nahi dikh rahi hai. Kripya damaged gaadi ki saaf photo upload karein."
            elif vehicle_category_mismatch:
                if claimed_vehicle_type == "two_wheeler":
                    spoken = "Photo reject ho gaya hai. Aapne bike claim kiya hai par photo car ka upload hua hai. Kripya apni bike ki photo upload karein."
                else:
                    spoken = "Photo reject ho gaya hai. Aapne car claim kiya hai par photo bike ka upload hua hai. Kripya apni car ki photo upload karein."
            else:
                spoken = "Photo reject ho gaya hai file integrity failure ke kaaran. Kripya doosri saaf photo upload karein."
        elif decision == "PASS":
            dmg_text = f" ({dmg_phrase.replace(' and ', ' aur ')})" if dmg_phrase else ""
            spoken = f"Evidence verify ho gaya hai. AI ne damage{dmg_text} detect karke {amt} rupaye ka repair estimate approve kiya hai."
        elif no_vehicle_detected or amt == 0:
            spoken = "Is photo mein koi gaadi ya clear damage nahi dikh raha hai. Kripya apni damaged gaadi ki saaf photo upload karein."
        else:
            spoken = f"Evidence preliminary review queue mein bhej diya gaya hai. Lagbhag {amt} rupaye ka provisional estimate mila hai, surveyor jald verify karenge."

    else:
        target_lang = "en-IN"
        if decision == "REJECT":
            if is_person_selfie:
                spoken = "Photo rejected because a person or selfie was detected instead of a vehicle. Please capture or upload a clear photo of your damaged vehicle."
            elif is_no_vehicle_reject:
                spoken = "Photo rejected because no bike, car, or motor vehicle was detected in this image. Please capture or upload a clear photo of your damaged vehicle."
            elif vehicle_category_mismatch:
                if claimed_vehicle_type == "two_wheeler":
                    spoken = "Photo rejected due to vehicle mismatch. You claimed a bike accident but uploaded a car photo. Please upload a bike photo."
                else:
                    spoken = "Photo rejected due to vehicle mismatch. You claimed a car accident but uploaded a bike photo. Please upload a car photo."
            else:
                spoken = "Photo rejected due to file integrity issue. Please upload a clear original photo."
        elif decision == "PASS":
            dmg_text = f" {dmg_phrase}" if dmg_phrase else " the damage"
            spoken = f"Evidence verified successfully. AI detected{dmg_text} and approved an initial repair estimate of {amt} rupees."
        elif no_vehicle_detected or amt == 0:
            spoken = "No vehicle or clear damage was detected in this image. Please capture or upload a clear photo of your damaged vehicle."
        else:
            spoken = f"Evidence flagged for human review. Provisional estimate is {amt} rupees. A claims officer will verify shortly."

    return {
        "spoken_narration": spoken,
        "narration_text": spoken,
        "language": target_lang,
        "decision": decision,
        "total_estimated_inr": float(amt),
    }
