"""
Stateful Human-Like Conversational Claim Assistant & Cognitive Reasoning Engine.
Combines:
- Layer 0: Silence / non-speech guard so silent recordings never fire scripts.
- Approach A: Google Gemini primary conversational reasoning & dynamic NLU brain.
- Approach B: Lightweight local Ollama offline LLM fallback.
- Local 4-Stage Cognitive & Emotional Engine: Sub-10ms deterministic reasoning
  fallback (Emotion/Safety Triage -> Causal Inference -> Drivability -> Plausibility).
- Gnani Timbre v3.0 Expressive Audio Tagger: Official inline `<...>` tags.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config import get_settings
from ..models import ClaimField, ConversationalReasoningTrace, FieldConfidence
from .speech import (
    extract_gnani_audio_tags,
    sanitize_gnani_audio_tags,
    strip_gnani_audio_tags,
)
from .transcription import (
    FIELD_QUESTIONS,
    _extract_universal_indian_registration,
    detect_conversation_language,
    extract_claim_fields,
    extract_group_a_motor_slots,
    extract_multimodal_slots,
    validate_and_normalize_field_answer,
)

logger = logging.getLogger("claimsathi.conversation")

FIELD_ORDER = [
    "policy_reference",
    "vehicle_type",
    "incident_location",
    "incident_date",
    "damage_description",
]

HIGH_IMPACT_CUES = [
    "truck", "lorry", "bus", "highway", "flyover", "fell", "fall", "gir gaya",
    "gir pada", "hurt", "injured", "injury", "hospital", "ambulance", "blood",
    "chot", "fracture", "head on", "head-on", "high speed", "fast", "airbag",
    "flipped", "overturned", "bura accident", "major accident", "bad accident",
    "crashed hard", "smashed", "బస్సు", "లారీ", "గాయం", "ಹೆದ್ದಾರಿ", "ಗಾಯ",
]

SAFETY_CONFIRMED_CUES = [
    "i am fine", "i'm fine", "i am okay", "i'm okay", "i am safe", "i'm safe",
    "no injury", "no injuries", "no one hurt", "nobody hurt", "unhurt", "all safe",
    "we are safe", "main theek", "hum theek", "sab theek", "surakshit",
    "kshemavaagiddini", "safe ga unnanu", "బాగున్నాను", "ಕ್ಷೇಮ",
]

FRUSTRATED_OR_CONFUSED_CUES = [
    "already told", "i just said", "how many times", "confused", "don't know",
    "do not know", "not sure", "pata nahi", "samajh nahi", "why are you asking",
]

_PURE_GREETING_RE = re.compile(
    r"^(?:hi+|hello+|hey+|hlo|namaste|namaskara|namaskar|namaskaram|nomoshkar|vanakkam|vanakam|salam|kem cho|sat sri akal|"
    r"good morning|good afternoon|good evening|good night|kaise ho|kya haal|"
    r"can you hear me|am i audible|are you there|anyone there|testing|test|mic test|mic check|"
    r"हलो|हेलो|हैलो|हाय|हॅलो|नमस्ते|नमस्कार|హలో|హాయ్|నమస్కారం|నమస్తే|ಹಲೋ|ಹಾಯ್|ನಮಸ್ಕಾರ|ನಮಸ್ತೆ|"
    r"ஹலோ|ஹாய்|வணக்கம்|ഹലോ|നമസ്കാരം|হ্যালো|নমস্কার|હેલો|નમસ્તે|ਹੈਲੋ|ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ|السلام علیکم)"
    r"(?:\s+(?:claimsathi|claim sathi|ji|जी|bro|sir|maam|madam|there|bhai))?[\s?!.,।]*$",
    re.IGNORECASE,
)

_IGNORED_LLM_FIELD_VALUES = frozenset({
    "", "null", "none", "unknown", "n/a", "na", "not mentioned", "not provided",
    "unspecified", "ka-17-ea-4590", "ts-09-ea-4590", "ka-01-mj-2026",
})

_WORD_RE = re.compile(r"[\w\u0600-\u06FF\u0900-\u0DFF]")


def _is_valid_api_key(val: Optional[str]) -> bool:
    """Return True only when an API key is populated and not a template placeholder."""
    if not val or not val.strip():
        return False
    low = val.strip().lower()
    if low.startswith("your_") or low.startswith("sk-your") or "api_key_here" in low or "placeholder" in low:
        return False
    return len(low) >= 8


def has_meaningful_words(text: Optional[str]) -> bool:
    """Check whether transcript/text contains at least one word or Indic character."""
    return bool(_WORD_RE.search((text or "").strip()))


def build_claim_fields_state(
    known_map: Dict[str, Optional[str]],
    resolved_lang: str = "en-IN",
) -> Tuple[List[ClaimField], List[str]]:
    """Build ClaimField objects and missing field keys from a field dictionary."""
    missing = [k for k in FIELD_ORDER if not known_map.get(k)]
    final_fields: List[ClaimField] = []
    for name in FIELD_ORDER:
        meta = FIELD_QUESTIONS[name]
        val = known_map.get(name)
        conf = FieldConfidence.HIGH if val else FieldConfidence.MISSING
        follow_up = (
            (meta.get("by_lang", {}).get(resolved_lang) or meta["question"])
            if not val
            else None
        )
        final_fields.append(
            ClaimField(
                name=name,
                label=meta["label"],
                value=val,
                confidence=conf,
                is_edited=False,
                follow_up_question=follow_up,
            )
        )
    return final_fields, missing


def _pick_variant(variants: List[str], history: List[Dict[str, str]]) -> str:
    """Choose a natural response phrasing not recently used in conversation history."""
    recent_texts = " ".join(
        (h.get("text") or "").lower()
        for h in history
        if h.get("sender") == "assistant"
    )
    for v in variants:
        snippet = v[:28].lower()
        if snippet not in recent_texts:
            return v
    return variants[len(history) % len(variants)]


def _is_conversational_question(text: str) -> bool:
    q_low = (text or "").strip().lower()
    if "?" in q_low:
        return True
    markers = [
        "why do you need", "what is", "what do you mean", "how long", "how much",
        "can i", "do i need", "explain", "meaning", "matlab kya", "kyu chahiye",
        "kya hai", "ಅಂದರೆ ಏನು", "ಯಾಕೆ ಬೇಕು", "అంటే ఏంటి", "ఎందుకు",
        "என்றால் என்ன", "ஏன்", "என்ன", "म्हणजे काय", "का पाहिजे", "काय आहे", "എന്താണ്",
    ]
    return any(m in q_low for m in markers)


def _is_pure_greeting_or_mic_check(text: str) -> bool:
    clean = (text or "").strip()
    if not clean:
        return False
    if _PURE_GREETING_RE.match(clean):
        return True
    low = clean.lower()
    mic_phrases = [
        "can you hear me", "am i audible", "are you there", "mic check", "mic test", "how are you",
        "meri aawaz aa rahi hai", "aawaz aa rahi", "kelistidya", "kelistideya",
        "vinipistunda", "vinapadutunda", "ketkiratha", "kekutha", "aawaz yete ka",
        "கேட்கிறதா", "ऐकू येतंय का", "వినిపిస్తుందా", "ಕೇಳಿಸುತ್ತಿದೆಯಾ", "आवाज आ रही है",
    ]
    return len(low.split()) <= 7 and any(p in low for p in mic_phrases)


_PRIOR_SAFETY_MARKERS = (
    "are you safe", "are you okay", "are you alright", "are you unhurt", "not hurt",
    "surakshit", "theek", "kshemavaagiddira", "safe ga", "safe-aa", "bathiramaaga",
    "surakshit aahat", "సురక్షిత", "సేఫ్", "ಕ್ಷೇಮ", "सुरक्षित", "பத்திரமாக",
)


def _has_prior_safety_empathy(history: List[Dict[str, str]]) -> bool:
    """Return True if the assistant has already checked on the user's personal safety earlier."""
    for h in history:
        if h.get("sender") == "assistant":
            txt = (h.get("text") or "").lower()
            if any(m in txt for m in _PRIOR_SAFETY_MARKERS):
                return True
    return False


def _analyze_cognitive_reasoning(
    current_text: str,
    history: List[Dict[str, str]],
    merged_fields: Dict[str, Optional[str]],
    newly_captured: Dict[str, str],
    missing_fields: List[str],
    is_first_turn: bool,
) -> ConversationalReasoningTrace:
    """
    Execute a 4-stage human-like cognitive & emotional reasoning pass:
    1. Emotional & personal safety triage
    2. Causal mechanics inference (how/why the accident occurred)
    3. Drivability & roadside risk assessment
    4. Physical plausibility & contradiction check
    """
    cur_low = (current_text or "").lower()
    all_user_text = " ".join(
        [(h.get("text") or "") for h in history if h.get("sender") == "user"] + [current_text]
    ).lower()

    # 1. Emotional & Safety Triage
    if any(c in cur_low for c in SAFETY_CONFIRMED_CUES):
        detected_emotion = "relieved_safe"
        empathy_cue = "Customer confirmed personal safety — expressing genuine relief & warmth"
        safety_check_status = "confirmed_safe"
        speech_rate = 0.98
        speech_pitch = 1.02
    elif any(c in cur_low for c in HIGH_IMPACT_CUES):
        detected_emotion = "distressed_high_impact"
        empathy_cue = "High-impact collision or injury risk — prioritizing human safety & calm reassurance"
        safety_check_status = "urgent_safety_inquiry"
        speech_rate = 0.93
        speech_pitch = 0.96
    elif any(c in cur_low for c in FRUSTRATED_OR_CONFUSED_CUES):
        detected_emotion = "frustrated_or_confused"
        empathy_cue = "Customer sounds stressed or uncertain — responding with patience & clear guidance"
        safety_check_status = "routine"
        speech_rate = 0.95
        speech_pitch = 0.98
    elif _is_pure_greeting_or_mic_check(current_text) and not newly_captured:
        detected_emotion = "warm_friendly"
        empathy_cue = "Friendly greeting or mic check — welcoming user naturally without assuming an accident"
        safety_check_status = "routine"
        speech_rate = 1.02
        speech_pitch = 1.03
    elif is_first_turn or "accident" in cur_low or "crashed" in cur_low or "hit" in cur_low:
        detected_emotion = "anxious_roadside"
        empathy_cue = "Roadside accident report — offering empathetic support & checking wellbeing"
        safety_check_status = "routine"
        speech_rate = 0.96
        speech_pitch = 0.99
    else:
        detected_emotion = "calm_informative"
        empathy_cue = "Attentive human listening — validating details & reasoning about claim completeness"
        safety_check_status = "routine"
        speech_rate = 1.0
        speech_pitch = 1.0

    # 2. Causal Inference (How / Why the accident happened)
    inferred_cause: Optional[str] = None
    rear_cues = ["from behind", "rear ended", "rear-ended", "hit from back", "back side hit", "piche se", "पीछे से", "వెనక నుండి", "ಹಿಂದಿನಿಂದ", "பின்னால்"]
    front_cues = ["head on", "head-on", "from front", "saamne se", "सामने से", "ముందు నుండి", "ಮುಂದಿನಿಂದ"]
    skid_cues = ["skid", "skidded", "slipped", "wet road", "rain", "gravel", "oil on road", "lost balance", "fisal", "फिसल", "స్కిడ్", "ಜಾರಿ"]
    parked_cues = ["parked", "standing", "parking", "khadi gaadi", "पार्क", "పార్కింగ్"]
    hazard_cues = ["pothole", "dog", "cattle", "cow", "animal", "divider", "pillar", "pole", "tree", "wall", "barricade", "गड्ढा"]
    collision_cues = ["hit by", "collided", "rammed", "auto", "car hit", "bike hit", "truck", "lorry", "bus", "signal", "turning", "takkar", "thok", "గుద్దింది", "ಡಿಕ್ಕಿ"]

    if any(c in all_user_text for c in rear_cues):
        inferred_cause = "Rear-end impact"
    elif any(c in all_user_text for c in skid_cues):
        inferred_cause = "Road skid / loss of traction"
    elif any(c in all_user_text for c in parked_cues):
        inferred_cause = "Struck while parked"
    elif any(c in all_user_text for c in hazard_cues):
        inferred_cause = "Road hazard / obstacle impact"
    elif any(c in all_user_text for c in front_cues):
        inferred_cause = "Frontal collision"
    elif any(c in all_user_text for c in collision_cues):
        inferred_cause = "Third-party vehicle collision"

    # 3. Drivability & Roadside Safety Reasoning
    damage_context = f"{all_user_text} {(merged_fields.get('damage_description') or '').lower()}"
    non_drivable_cues = [
        "axle", "radiator", "fork", "wheel bent", "wheel jammed", "engine",
        "chassis", "steering", "suspension", "can't ride", "cannot ride",
        "not drivable", "cannot drive", "towing", "oil leak", "coolant",
        "airbag", "handle bent", "front wheel",
    ]
    caution_cues = ["headlamp", "headlight", "windshield", "brake", "clutch", "tyre", "tire", "fender", "bumper"]
    minor_cues = ["scratch", "minor dent", "mirror", "indicator"]

    if any(c in damage_context for c in non_drivable_cues):
        drivability_assessment = "non_drivable_towing_recommended"
    elif any(c in damage_context for c in caution_cues):
        drivability_assessment = "caution_check_before_riding"
    elif any(c in damage_context for c in minor_cues):
        drivability_assessment = "likely_drivable"
    else:
        drivability_assessment = "unknown"

    # 4. Physical Plausibility & Contradiction Check
    front_part_cues = ["headlamp", "headlight", "front bumper", "bonnet", "front mudguard", "front fender", "front fork", "windshield", "radiator"]
    rear_part_cues = ["tail light", "taillight", "rear bumper", "dicky", "dickie", "boot", "back door", "tailgate"]

    has_rear_hit = any(c in all_user_text for c in rear_cues)
    has_front_hit = any(c in all_user_text for c in front_cues)
    has_front_damage = any(c in damage_context for c in front_part_cues)
    has_rear_damage = any(c in damage_context for c in rear_part_cues)

    plausibility_note = "Consistent narrative mechanics"
    causal_question_asked: Optional[str] = None

    if has_rear_hit and has_front_damage and not has_rear_damage:
        plausibility_note = "Rear impact reported with front-end damage — checking if vehicle was pushed forward into an obstacle"
        causal_question_asked = "Clarifying secondary forward impact after rear-end hit"
    elif has_front_hit and has_rear_damage and not has_front_damage:
        plausibility_note = "Frontal collision reported with rear-only damage — verifying impact direction for surveyor"
        causal_question_asked = "Clarifying impact mechanics between frontal hit and rear damage"
    elif drivability_assessment == "non_drivable_towing_recommended":
        plausibility_note = "Critical mechanical/structural damage detected — advising against riding/driving"
        causal_question_asked = "Advising roadside caution & checking if towing support is needed"
    elif merged_fields.get("damage_description") and not inferred_cause:
        plausibility_note = "Damaged parts identified; cause of loss (collision vs. skid vs. parked hit) can enrich surveyor dossier"
        causal_question_asked = "Asking how the impact occurred to establish cause of loss"

    # 5. Build Transparent Internal Thought Monologue
    captured_list = [f"{k}={v}" for k, v in newly_captured.items() if v]
    known_list = [k for k, v in merged_fields.items() if v]
    thought_parts: List[str] = []

    if detected_emotion == "warm_friendly":
        thought_parts.append("User greeted or checked audio without reporting an incident yet; responding warmly and inviting them to share whenever ready.")
    elif detected_emotion == "distressed_high_impact":
        thought_parts.append("The customer described a high-impact or potentially dangerous accident, so I must check on their personal safety first.")
    elif detected_emotion == "relieved_safe":
        thought_parts.append("The customer confirmed they are safe, so I should express genuine relief before continuing.")
    elif is_first_turn:
        thought_parts.append("This is the customer's initial accident report; I should respond with warmth and empathy.")

    if captured_list:
        thought_parts.append(f"Captured in this turn: {', '.join(captured_list)} (total known: {len(known_list)}/5 core fields).")
    if inferred_cause:
        thought_parts.append(f"Inferred cause of loss: {inferred_cause}.")
    if "Rear impact reported" in plausibility_note or "Frontal collision reported" in plausibility_note:
        thought_parts.append(f"Plausibility check: {plausibility_note}.")
    elif drivability_assessment == "non_drivable_towing_recommended":
        thought_parts.append("Damage suggests the vehicle may not be safe to drive/ride, so I should mention roadside safety/towing.")

    if detected_emotion != "warm_friendly":
        if missing_fields:
            thought_parts.append(f"Still needed: {', '.join(missing_fields)} — I will ask naturally without repeating any captured details.")
        else:
            thought_parts.append("All 5 core fields are complete; I can reassure the customer and guide them to Step 2 photo verification.")

    return ConversationalReasoningTrace(
        detected_emotion=detected_emotion,
        empathy_cue=empathy_cue,
        safety_check_status=safety_check_status,
        inferred_cause=inferred_cause,
        drivability_assessment=drivability_assessment,
        plausibility_note=plausibility_note,
        causal_question_asked=causal_question_asked,
        thought_process=" ".join(thought_parts),
        speech_rate=speech_rate,
        speech_pitch=speech_pitch,
        llm_provider="local-cognitive",
        detected_intent="greeting" if detected_emotion == "warm_friendly" else "claim_intake",
    )


def _format_greeting_reply(lang: str, history: List[Dict[str, str]]) -> str:
    """Warm, unscripted-feeling greeting when user simply says hello or checks microphone."""
    if lang.startswith("hi"):
        return _pick_variant([
            "Namaste! Haan, main aapko bilkul saaf sun sakta hoon. Aap kaise hain? Aaram se batayein, kya aap kisi gaadi ke claim ke liye baat kar rahe hain ya kuch poochna chahte hain?",
            "Hello ji! Aawaz bilkul clear aa rahi hai. Main ClaimSathi hoon — batayein main aaj aapki kis tarah madad kar sakta hoon?",
        ], history)
    if lang.startswith("kn"):
        return "Namaskara! Neevu maataaduvudu spashtavaagi kelisuttide. Naanu hege sahaya maadabahudu heli."
    if lang.startswith("te"):
        return "Namaskaram! Mee maata naaku clear ga vinipistondi. Cheppandi, nenu meeku ela sahayam cheyagalanu?"
    if lang.startswith("ta"):
        return "Vanakkam! Neenga pesuvathu thelivaaga kekkuthu. Sollunga, naan ungalukku eppadi udhava mudiyum?"
    if lang.startswith("mr"):
        return "Namaskar! Tumcha aawaz spashṭa yetoy. Tumhala claim sathi kashi madat karu shakto te sanga."
    return _pick_variant([
        "Hey there! Yes, I can hear you loud and clear. How can I help you today — would you like to walk me through what happened, or do you have a question first?",
        "Hello! I'm right here and listening clearly. Take your time — tell me what's going on or ask me anything.",
    ], history)


def _format_reasoning_insight(
    trace: ConversationalReasoningTrace,
    lang: str,
    missing: List[str],
    history: List[Dict[str, str]],
) -> str:
    """
    Generate an empathetic human reasoning reaction or causal follow-up when
    contradictions or critical drivability risks are spotted.
    """
    prior_assistant = " ".join(
        (h.get("text") or "").lower() for h in history if h.get("sender") == "assistant"
    )

    if "Rear impact reported" in trace.plausibility_note and "pushed" not in prior_assistant and "aage" not in prior_assistant:
        if lang.startswith("hi"):
            return "Ek choti si baat surveyor ke liye samajhna chahta hoon — kyunki takkar piche se lagi thi, kya uske jhatke se gaadi aage kisi cheez se takra gayi jisse aage ka hissa toot gaya?"
        if lang.startswith("kn"):
            return "Surveyor ge spashtavaagi tilisalu ondu prashne — hindininda dikki aadaga vaahana munde yavudadaru vastuvige taagi mundina bhaaga damage aayite?"
        if lang.startswith("te"):
            return "Surveyor ki clear ga undataniki oka chinna vishayam — venaka nundi guddinappudu vehicle mundu edaina tagili front damage ayyinda?"
        if lang.startswith("ta"):
            return "Surveyor ku thelivaaga puriya oru chinna kelvi — pinnaal irunthu idithathil vaganam munnaal ethilavathu mothi mun pakkam damage aanatha?"
        return "Just so I can explain the impact clearly to the surveyor — since you were hit from behind, did the force push your vehicle forward into something in front, causing the front damage?"

    if "Frontal collision reported" in trace.plausibility_note and "rear damage" not in prior_assistant:
        if lang.startswith("hi"):
            return "Surveyor ki report ke liye ek chota sa clarification — saamne ki takkar ke baad piche ke hisse mein nuksaan kaise aaya, kya piche se bhi kisi gaadi ne thoka?"
        return "Just to make sure the surveyor has the full story — since it was a frontal collision, did another vehicle also hit you from behind causing the rear damage?"

    if (
        trace.drivability_assessment == "non_drivable_towing_recommended"
        and "towing" not in prior_assistant
        and "safe to ride" not in prior_assistant
        and "chalana safe" not in prior_assistant
    ):
        if lang.startswith("hi"):
            return "Is damage ke saath gaadi chalana khatarnak ho sakta hai, isliye kripya isey wahin surakshit khada rakhein — hum claim mein towing support bhi note kar rahe hain."
        if lang.startswith("kn"):
            return "Ee damage jothe vaahana chalayisuvudu safe alla, dayavittu surakshitavaagi park maadi — naavu towing sahaya kooda note maadutteve."
        if lang.startswith("te"):
            return "Ee damage tho vehicle nadapadam safe kaadu, dayachesi safe ga park cheyandi — memu claim lo towing support kooda note chestamu."
        return "With that kind of damage, it might not be safe to ride or drive right now — please keep it parked safely, and I'll note that towing support may be needed."

    return ""


def _answer_clarifying_question(
    user_text: str,
    missing: List[str],
    lang: str,
    history: List[Dict[str, str]],
    trace: Optional[ConversationalReasoningTrace] = None,
) -> str:
    """Respond empathetically and thoughtfully to a user's question without losing any already-captured slots."""
    q_low = user_text.lower()
    next_field = missing[0] if missing else None

    if "photo" in q_low or "image" in q_low or "upload" in q_low:
        if lang.startswith("hi"):
            return "Bilkul — jaise hi yeh basic baat-cheet poori hogi, agle step mein hum aapke vehicle damage ki photo AI se verify karke turant repair estimate nikalenge. Abhi bas bachi hui choti si detail bata dein."
        if lang.startswith("kn"):
            return "Khandita — mundina step nalli nimma vaahana damage photo AI inda check maadi repair estimate kodutteve. Eega baki iro vivara heliri."
        return "Great question — right after this quick chat, you'll upload a photo of the damage in Step 2 so our AI can inspect the parts and calculate an instant repair estimate."

    if any(k in q_low for k in ["policy", "number", "registration", "bike no", "vehicle no"]) or next_field == "policy_reference":
        if lang.startswith("hi"):
            return "Main samajh sakta hoon — humein aapki gaadi ka registration number ya policy number sirf isliye chahiye taaki aapka claim sahi vehicle cover se link ho sake. Dono mein se jo bhi yaad ho bata dein."
        if lang.startswith("kn"):
            return "Claim nimmanna vaahana cover jothe link maadakke registration number athava policy number beku. Nimma hatra yavudide dayavittu heli."
        return "I completely understand why you're asking — we only need your vehicle registration or policy number to link this incident to the right insurance cover. Whichever one you have handy works fine."

    follow = _ask_missing_naturally(missing, lang, history, trace) if missing else ""
    if lang.startswith("hi"):
        return f"Bilkul, main aapki har baat samajh kar madad karne ke liye hoon. {follow}".strip()
    return f"Of course — I'm right here to walk you through every step. {follow}".strip()


def _format_natural_ack(
    newly_captured: Dict[str, str],
    updated_fields: Dict[str, str],
    lang: str,
    is_first_turn: bool,
    history: List[Dict[str, str]],
    trace: Optional[ConversationalReasoningTrace] = None,
    newly_captured_model: Optional[str] = None,
) -> str:
    """Acknowledge what the user shared with genuine human emotion, safety awareness, and causal reflection."""
    parts: List[str] = []
    pol = newly_captured.get("policy_reference")
    veh = newly_captured.get("vehicle_type")
    loc = newly_captured.get("incident_location")
    dt = newly_captured.get("incident_date")
    dam = newly_captured.get("damage_description")

    emotion = trace.detected_emotion if trace else "calm_informative"
    cause = trace.inferred_cause if trace else None
    veh_label = newly_captured_model or ("two-wheeler" if veh == "bike" else (veh or "vehicle"))

    if lang.startswith("hi"):
        veh_word = newly_captured_model or ("bike" if veh == "bike" else "car" if veh == "car" else "gaadi")
        if newly_captured_model and not veh and not pol:
            parts.append(f"aapki {newly_captured_model}")
        elif veh and pol:
            parts.append(f"aapki {veh_word} ({pol})")
        elif pol:
            parts.append(f"number {pol}")
        elif veh:
            parts.append(f"aapki {veh_word}")
        if loc:
            parts.append(f"{loc} ki location")
        if dt:
            parts.append(f"{dt} ka samay")
        if dam and not parts:
            parts.append("damage ki jaankari")

        if emotion == "distressed_high_impact":
            empathy = _pick_variant([
                "Baap re, yeh sun kar sach mein chinta hui — sabse pehle batayein, aap bilkul theek aur surakshit toh hain na?",
                "Oh no, itni badi takkar ke baare mein sunkar bahut bura laga — ummeed hai aapko ya kisi aur ko chot nahi aayi hogi?",
            ], history)
            if parts:
                return f"{empathy} Aap bilkul ghabraiye mat, maine {', '.join(parts)} note kar liya hai."
            return f"{empathy} Main poori tarah aapke saath hoon aur claim darj karne mein madad karunga."

        if emotion == "relieved_safe":
            relief = "Shukar hai ki aap bilkul surakshit hain — gaadi toh repair ho jayegi, aapki salamaati sabse zaroori hai."
            if parts:
                return f"{relief} Maine {', '.join(parts)} bhi note kar liya hai."
            return relief

        if is_first_turn:
            empathy = _pick_variant([
                "Accident ke baare mein sunkar sach mein bura laga — aap bilkul theek aur surakshit toh hain na? Chinta mat kijiye, main aaram se poora claim sambhal lunga.",
                "Aapke hadse ke baare mein sunkar dukh hua — sabse pehle, kya aap safe hain? Ghabraiye mat, hum milkar baaki details step by step complete kar lenge.",
            ], history)
            if parts:
                return f"{empathy} Maine {', '.join(parts)} note kar liya hai."
            return empathy
        if updated_fields:
            upd_desc = ", ".join(f"{v}" for v in updated_fields.values())
            return f"Bilkul theek, maine woh update karke {upd_desc} note kar liya hai."
        if parts:
            lead = _pick_variant(["Main samajh gaya,", "Shukriya batane ke liye,", "Theek hai, maine"], history)
            if lead.endswith("maine"):
                return f"{lead} {', '.join(parts)} note kar liya hai."
            return f"{lead} maine {', '.join(parts)} note kar liya hai."
        return "Maine aapki baat dhyan se note kar li hai."

    if lang.startswith("kn"):
        veh_word = newly_captured_model or ("bike" if veh == "bike" else "car" if veh == "car" else "vaahana")
        if newly_captured_model and not veh and not pol:
            parts.append(f"nimma {newly_captured_model}")
        elif veh and pol:
            parts.append(f"nimma {veh_word} ({pol})")
        elif pol:
            parts.append(f"number {pol}")
        elif veh:
            parts.append(f"nimma {veh_word}")
        if loc:
            parts.append(f"{loc} sthala")
        if dt:
            parts.append(f"{dt} samaya")
        if dam and not parts:
            parts.append("damage vivara")

        if emotion == "distressed_high_impact":
            empathy = "Ayyo, idu keli tumba ghabari aayitu — modalu heli, neevu kshemavaagiddira, yaarigu gayavaagillava?"
            if parts:
                return f"{empathy} Chinte maadabedi, naanu {', '.join(parts)} note maadidini."
            return f"{empathy} Naanu nimma jothe iddene."

        if is_first_turn:
            empathy = _pick_variant([
                "Apaghaata bagge keli tumba bejaar aayitu — modalu neevu kshemavaagiddira heli? Chinte maadabedi, naanu ellaa step by step nodikolluttene.",
                "Ee ghatane bagge keli dukha aayitu, neevu surakshitavaagiddira? Ghabari aagabedi, naavu aaraamavaagi munde hogona.",
            ], history)
            if parts:
                return f"{empathy} Naanu {', '.join(parts)} note maadidini."
            return empathy
        if parts:
            lead = _pick_variant(["Arthavaayitu,", "Dhanyavaadagalu,"], history)
            return f"{lead} {', '.join(parts)} daakhalisidini."
        return "Nimma maahiti note maadidini."

    if lang.startswith("te"):
        veh_word = newly_captured_model or ("bike" if veh == "bike" else "car" if veh == "car" else "vehicle")
        if newly_captured_model and not veh and not pol:
            parts.append(f"mee {newly_captured_model}")
        elif veh and pol:
            parts.append(f"mee {veh_word} ({pol})")
        elif pol:
            parts.append(f"number {pol}")
        elif veh:
            parts.append(f"mee {veh_word}")
        if loc:
            parts.append(f"{loc} area")
        if dt:
            parts.append(f"{dt}")
        if dam and not parts:
            parts.append("damage vivaralu")

        if emotion == "distressed_high_impact":
            empathy = "Ayyo, idi vintunte chala bhayamga undi — munduga meeru safe ga unnara, evariki debba tagalaledu kada?"
            if parts:
                return f"{empathy} Kangaru padakandi, nenu {', '.join(parts)} note chesanu."
            return f"{empathy} Nenu meeku sahayam chestanu."

        if is_first_turn:
            empathy = _pick_variant([
                "Accident gurinchi vini chala badha vesindi — munduga meeru safe ga unnara? Kangaru padakandi, nenu anni details mellaga teesukuni help chestanu.",
                "Ee incident gurinchi vini manasu baledu — meeru kshemanga unnaru kada? Em tension padakandi, manam step by step munduku veldam.",
            ], history)
            if parts:
                return f"{empathy} Nenu {', '.join(parts)} note chesanu."
            return empathy
        if parts:
            return f"Arthamaindi, {', '.join(parts)} note chesanu."
        return "Mee vivaralu note chesanu."

    if lang.startswith("ta"):
        if pol:
            parts.append(f"number {pol}")
        if loc:
            parts.append(f"{loc}")
        if dt:
            parts.append(f"{dt}")
        if emotion == "distressed_high_impact":
            if parts:
                return f"Ayyo, idhai ketka romba kavalaiyaaga irukku — muthalil neenga bathiramaaga irukkeengala? {', '.join(parts)} note pannitten."
            return "Ayyo, idhai ketka romba kavalaiyaaga irukku — muthalil neenga bathiramaaga irukkeengala?"
        if is_first_turn:
            empathy = _pick_variant([
                "Ungal vipathu pathi kettu romba varuthamaaga irukku — muthalil neenga bathiramaaga irukkeengala? Kavalappadatheenga, naan porumaiyaaga ellathaiyum paathukuren.",
                "Indha sambavam pathi kettu manasu kashtamaaga irukku — neenga safe-aa irukkeengala? Bayappadatheenga, meethi details-a step by step mudichidalam.",
            ], history)
            if parts:
                return f"{empathy} {', '.join(parts)} note pannitten."
            return empathy
        if parts:
            return f"Purinjathu, {', '.join(parts)} note pannitten."
        return "Ungal thagavalai note pannitten."

    if lang.startswith("mr"):
        veh_word = "bike" if veh == "bike" else "car" if veh == "car" else "vahan"
        if veh and pol:
            parts.append(f"tumchi {veh_word} ({pol})")
        elif pol:
            parts.append(f"number {pol}")
        elif veh:
            parts.append(f"tumchi {veh_word}")
        if loc:
            parts.append(f"{loc}")
        if dt:
            parts.append(f"{dt}")
        if dam and not parts:
            parts.append("nuksanachi mahiti")
        if is_first_turn:
            empathy = _pick_variant([
                "Tumchya apghatabaddal aikun khup vait vatle — pahilyanda tumhi surakshit aahat ka te sanga? Kalji karu naka, apan aramat pudhchi prakriya purna karu.",
                "Ya ghatnebaddal aikun dukh jhale — tumhi theek aahat na? Ghabaru naka, mi purna madat karin.",
            ], history)
            if parts:
                return f"{empathy} Mi {', '.join(parts)} nondavle aahe."
            return empathy
        if parts:
            return f"Samajle, mi {', '.join(parts)} nondavle aahe."
        return "Tumchi mahiti nondavli aahe."

    # Default natural Indian English
    if newly_captured_model and not veh and not pol:
        parts.append(f"your {newly_captured_model}")
    elif veh and pol:
        parts.append(f"your {veh_label} ({pol})")
    elif pol:
        parts.append(f"the registration/policy {pol}")
    elif veh:
        parts.append(f"your {veh_label}")
    if loc:
        parts.append(f"the location ({loc})")
    if dt:
        parts.append(f"the time ({dt})")
    if dam and not parts:
        parts.append("what happened to the vehicle")

    if emotion == "distressed_high_impact":
        empathy = _pick_variant([
            "Oh goodness, that sounds like a really scary impact — first of all, are you okay and in a safe spot right now?",
            "I'm so sorry you just went through such a jarring collision — before anything else, are you hurt or did anyone need medical attention?",
        ], history)
        if parts:
            return f"{empathy} Take a breath — I've already got {', '.join(parts)} noted down."
        return f"{empathy} Please don't stress about the paperwork; I'll walk you through this gently."

    if emotion == "relieved_safe":
        relief = "Thank goodness you're safe — a vehicle can always be repaired, your wellbeing is what matters most."
        if parts:
            return f"{relief} I've also noted {', '.join(parts)}."
        return relief

    if is_first_turn:
        empathy = _pick_variant([
            "I'm really sorry to hear that — first of all, are you safe and okay? Don't worry at all, take your time and we'll take care of this together.",
            "Oh no, I'm so sorry you just went through an accident — are you safe right now? Please don't stress, we'll handle everything calmly step by step.",
        ], history)
        if parts:
            return f"{empathy} I've got {', '.join(parts)} down."
        return empathy

    if updated_fields:
        upd = ", ".join(updated_fields.values())
        return f"No problem at all — I've updated that to {upd} for you."

    if parts:
        if cause and dam:
            lead = _pick_variant([
                f"I can see how a {cause.lower()} would cause that — I've noted",
                "That makes complete sense — I've recorded",
                "Got it, I can picture how that happened — noted",
            ], history)
        else:
            lead = _pick_variant([
                "Got it, I've noted",
                "Thanks for sharing that — I've added",
                "Understood, I've recorded",
            ], history)
        return f"{lead} {', '.join(parts)}."
    return "I hear you — thanks for explaining that."


def _ask_missing_naturally(
    missing: List[str],
    lang: str,
    history: List[Dict[str, str]],
    trace: Optional[ConversationalReasoningTrace] = None,
) -> str:
    """
    Ask concisely, empathetically, and with causal curiosity ('how/why' the damage happened)
    only for fields genuinely missing.
    """
    cause = trace.inferred_cause if trace else None

    if not missing:
        if lang.startswith("hi"):
            if not cause:
                return "Mere paas saari 5 zaroori details aa gayi hain! Agar aap chahein toh bata sakte hain ki yeh takkar kaise hui, ya seedhe Step 2 par jaakar damage ki photo upload kar dein."
            return _pick_variant([
                "Mere paas saari zaroori jaankari aa gayi hai. Ab aap Step 2 par jaakar damaged gaadi ki photo upload kar sakte hain taaki main turant estimate nikaal sakoon.",
                "Sabhi details bilkul saaf note ho gayi hain! Kripya ab Step 2 mein jaayein aur damage ki photo upload karein.",
            ], history)
        if lang.startswith("kn"):
            return "Ella mukhya maahiti sikkirodrinda eega Step 2 ge hogi damage photo upload maadi."
        if lang.startswith("te"):
            return "Anni mukhyamaina vivaralu vachayi. Ippudu Step 2 ki velli damage photo upload cheyandi."
        if lang.startswith("ta"):
            return "Ella mukkiya thagavalum kidaithuvittathu. Ippo Step 2 ku poi damage photo upload pannunga."
        if not cause:
            return "That covers all the core details we need! Feel free to mention how the impact happened if another vehicle or skid was involved, or head straight to Step 2 so our AI can inspect the damage photo."
        return _pick_variant([
            "You've given me a very clear picture of what happened! Whenever you're ready, move to Step 2 to upload or capture a photo of the damage for an instant repair estimate.",
            "Great, we have the full story and all details locked in. Head over to Step 2 whenever you're ready so our AI can verify the damage photo.",
        ], history)

    mset = set(missing)

    if mset == {"incident_location", "damage_description"}:
        if lang.startswith("hi"):
            return "Kya aap bata sakte hain ki yeh hadsa kis jagah par hua, aur takkar kaise lagi tatha gaadi mein kya nuksaan aaya?"
        if lang.startswith("kn"):
            return "Ee apaghaata yaava sthaladalli, hegayitu mattu vaahanakke yenu damage aagide endu helabahude?"
        if lang.startswith("te"):
            return "Ee accident ekkada, ela jarigindi mariyu vehicle ki em damage aindo cheppagalara?"
        return _pick_variant([
            "Could you tell me where this happened, how the impact occurred, and which parts were damaged?",
            "Where did the accident take place, and how did the vehicle get damaged?",
        ], history)

    if "incident_location" in mset and "incident_date" in mset and len(missing) >= 2 and missing[0] in ("incident_location", "incident_date"):
        if lang.startswith("hi"):
            return "Kya aap bata sakte hain ki yeh hadsa kis jagah aur kab hua tha?"
        if lang.startswith("kn"):
            return "Ee apaghaata yava sthaladalli mattu yaavaga nadeyitu endu helabahude?"
        if lang.startswith("te"):
            return "Ee accident ekkada mattu eppudu jarigindo cheppagalara?"
        return _pick_variant([
            "Could you tell me roughly where and when the accident happened?",
            "Where did this happen, and what date or time was it?",
        ], history)

    first_missing = missing[0]
    if lang.startswith("hi"):
        q_map = {
            "policy_reference": [
                "Claim ko aapki gaadi se jodne ke liye kripya apna vehicle number ya policy number bata dein?",
                "Aapki gaadi ka number ya insurance policy number kya hai?",
            ],
            "vehicle_type": [
                "Yeh kis tarah ki gaadi hai — two-wheeler (bike/scooter) ya four-wheeler (car)?",
                "Kya is hadse mein aapki bike/scooter thi ya car?",
            ],
            "incident_location": [
                "Yeh hadsa kis area, sadak ya shehar ke paas hua tha?",
                "Accident exact kis jagah ke paas hua?",
            ],
            "incident_date": [
                "Yeh accident kis tareekh ya kis waqt hua tha?",
                "Hadsa kab hua tha — din ya samay bata sakein?",
            ],
            "damage_description": [
                "Yeh takkar kaise lagi — kya kisi gaadi ne thoka ya skid hui — aur kis hisse mein nuksaan aaya hai?",
                "Kripya thoda batayein ki accident kaise hua aur gaadi ke kaunse parts damage hue hain?",
            ],
        }
        return _pick_variant(q_map.get(first_missing, ["Kripya bachi hui jaankari share karein."]), history)

    if lang.startswith("kn"):
        q_map = {
            "policy_reference": ["Nimma vaahana registration number athava policy number helabahude?"],
            "vehicle_type": ["Idu bike, scooter, athava car aa?"],
            "incident_location": ["Apaghaata yaava area athava ooralli nadeyitu?"],
            "incident_date": ["Ee apaghaata yaava dinanka athava samayakke nadeyitu?"],
            "damage_description": ["Apaghaata hege nadeyitu mattu vaahanada yaava bhaagadalli damage aagide?"],
        }
        return _pick_variant(q_map.get(first_missing, ["Dayavittu baki maahiti tilisi."]), history)

    if lang.startswith("te"):
        q_map = {
            "policy_reference": ["Mee vehicle registration number leda policy number cheppagalara?"],
            "vehicle_type": ["Idi bike, scooter, leda car aa?"],
            "incident_location": ["Accident ee area leda city lo jarigindi?"],
            "incident_date": ["Ee accident eppudu jarigindo date leda time cheptara?"],
            "damage_description": ["Accident ela jarigindi mariyu vehicle ki ekkada em damage aindo cheppagalara?"],
        }
        return _pick_variant(q_map.get(first_missing, ["Dayachesi migilina vivaralu cheppandi."]), history)

    if lang.startswith("ta"):
        q_map = {
            "policy_reference": ["Ungal vehicle registration number allathu policy number sollunga?"],
            "vehicle_type": ["Ithu bike, scooter, allathu car aa?"],
            "incident_location": ["Vipathu entha idathil allathu ooril nadanthathu?"],
            "incident_date": ["Vipathu eppo nadanthathu — thethi allathu neram sollunga?"],
            "damage_description": ["Vipathu eppadi nadanthathu matrum vaganathukku enna setham yerpattullathu?"],
        }
        return _pick_variant(q_map.get(first_missing, ["Meethi thagavalai sollunga."]), history)

    if lang.startswith("mr"):
        q_map = {
            "policy_reference": ["Tumchya vahanacha registration number kinva policy number sanga?"],
            "vehicle_type": ["Hi bike, scooter aahe ki car aahe?"],
            "incident_location": ["Apghat konatya thikani kinva shaharat jhala?"],
            "incident_date": ["Apghat kadhi jhala — tarikh kinva vel sanga?"],
            "damage_description": ["Apghat kasa jhala ani vahanache kay nuksan jhale?"],
        }
        return _pick_variant(q_map.get(first_missing, ["Krupaya urvarit mahiti sanga."]), history)

    q_map_en = {
        "policy_reference": [
            "So I can link this to your cover, could you share your vehicle registration or policy number?",
            "What is the registration number on your vehicle, or your policy number?",
        ],
        "vehicle_type": [
            "Was this a two-wheeler like a bike or scooter, or a car?",
            "Could you confirm what kind of vehicle you were driving or riding?",
        ],
        "incident_location": [
            "Which area, road, or city did the accident happen in?",
            "Where exactly did this take place?",
        ],
        "incident_date": [
            "When did the accident happen — roughly what date or time?",
            "Could you let me know the date or time of the incident?",
        ],
        "damage_description": [
            "How did the impact happen — did another vehicle hit you or did it skid — and which parts were damaged?",
            "Could you walk me through how the accident occurred and what parts of the vehicle took the damage?",
        ],
    }
    return _pick_variant(q_map_en.get(first_missing, ["Could you share the remaining detail?"]), history)


def _tune_prosody_speech_text(
    reply_text: str,
    trace: ConversationalReasoningTrace,
    is_complete: bool = False,
) -> str:
    """
    Create a Gnani Timbre v3.0 expressive audio-tagged script from plain `reply_text`
    using ONLY official Gnani angle-bracket tags (`<sigh>`, `<exhales>`, `<pauses>`, `<slow>`, `<excited>`).
    """
    base = strip_gnani_audio_tags(reply_text)
    if not base:
        return ""

    # Replace em-dash boundaries with Gnani Timbre <pauses> (first pause can slow down on empathy)
    dash_count = 0

    def _replace_dash(_m: re.Match) -> str:
        nonlocal dash_count
        dash_count += 1
        if dash_count == 1 and trace.detected_emotion in ("distressed_high_impact", "anxious_roadside", "frustrated_or_confused"):
            return " <pauses> <slow> "
        return " <pauses> "

    tagged = re.sub(r"\s*—\s*", _replace_dash, base)

    if "<pauses>" not in tagged and trace.detected_emotion in ("distressed_high_impact", "anxious_roadside", "relieved_safe", "frustrated_or_confused"):
        tagged = re.sub(r"([?.!।])\s+(?=\S)", r"\1 <pauses> ", tagged, count=1)

    if trace.detected_emotion == "distressed_high_impact":
        tagged = f"<sigh> {tagged}"
    elif trace.detected_emotion == "relieved_safe":
        tagged = f"<exhales> {tagged}"
    elif trace.detected_emotion in ("anxious_roadside", "frustrated_or_confused"):
        if "<slow>" not in tagged:
            tagged = f"<slow> {tagged}"
    elif trace.detected_emotion == "warm_friendly":
        tagged = f"<excited> {tagged}"
    elif is_complete:
        tagged = f"<excited> {tagged}"

    sanitized = sanitize_gnani_audio_tags(tagged)
    return sanitized if strip_gnani_audio_tags(sanitized) else base


_GENERIC_VEHICLE_WORDS = frozenset({
    "bandi", "బండి", "gaadi", "gadi", "गाड़ी", "गाडी", "ಗಾಡಿ", "vandi", "வண்டி",
    "vehicle", "motor vehicle", "ambiguous", "car or bike", "bike or car",
    "unclear", "two or four wheeler", "వాహనం", "ವಾಹನ", "வாகனம்", "वाहन",
})

_GENERIC_DAMAGE_PLACEHOLDERS = frozenset({
    "vehicle accident damage reported", "accident", "accident happened",
    "damage reported", "not specified", "unknown",
})


def _sanitize_llm_extracted_fields(raw_extracted: Any) -> Dict[str, str]:
    """Validate LLM-extracted field values and drop empty or hallucinated placeholders."""
    if not isinstance(raw_extracted, dict):
        return {}
    cleaned: Dict[str, str] = {}
    for key in FIELD_ORDER:
        val = raw_extracted.get(key)
        if not isinstance(val, str):
            continue
        s = val.strip()
        low = s.lower()
        if not s or low in _IGNORED_LLM_FIELD_VALUES:
            continue
        if key == "policy_reference":
            norm_plate = _extract_universal_indian_registration(s)
            s = norm_plate or s.upper()
        elif key == "vehicle_type":
            if low in _GENERIC_VEHICLE_WORDS or ("bike" in low and "car" in low):
                continue
            bike_markers = (
                "bike", "motorcycle", "scooter", "two", "2w", "scooty", "activa",
                "బైక్", "బైకు", "స్కూటర్", "ಬೈಕ್", "ಬೈಕು", "ಸ್ಕೂಟರ್",
                "बाइक", "बाईक", "स्कूटर", "स्कूटी", "दुचाकी",
                "பைக்", "ஸ்கூட்டர்", "ബൈക്ക്", "বাইক", "બાઇક", "ਬਾਈਕ",
            )
            car_markers = (
                "car", "sedan", "suv", "hatchback", "four", "4w",
                "కార్", "కారు", "ಕಾರ್", "ಕಾರು", "कार", "चारचाकी",
                "கார்", "കാർ", "কার", "કાર", "ਕਾਰ",
            )
            if any(w in low or w in s for w in bike_markers):
                s = "bike"
            elif any(w in low or w in s for w in car_markers):
                s = "car"
            elif "truck" in low or "lorry" in low:
                s = "truck"
            elif "auto" in low or "rickshaw" in low:
                s = "auto_rickshaw"
            elif "bus" in low:
                s = "bus"
            else:
                continue
        elif key == "damage_description":
            if low in _GENERIC_DAMAGE_PLACEHOLDERS:
                continue
        cleaned[key] = s
    return cleaned


def _looks_like_json_or_code(text: Optional[str]) -> bool:
    """Reject leaked JSON objects, truncated LLM JSON buffers, or schema keys from spoken/displayed text."""
    t = (text or "").strip()
    if not t:
        return True
    if t.startswith("{") or t.startswith("[") or t.startswith("```"):
        return True
    schema_markers = ('"extracted_fields"', '"thought_process"', '"reply_text"', '"speech_text"', '"intent":', '"insurance_sector"')
    return any(m in t for m in schema_markers)


def _parse_llm_json_response(raw_out: str) -> Optional[Dict[str, Any]]:
    """Parse structured JSON returned by Gemini or Ollama, tolerating markdown code fences."""
    if not raw_out:
        return None
    text = raw_out.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


COMPACT_FINETUNED_SYSTEM_PROMPT = (
    "You are ClaimSathi AI, an empathetic Indian Motor Insurance (Two-Wheeler & Four-Wheeler) claims voice companion. "
    "Respond strictly in JSON with intent, insurance_sector ('motor'|'general'), detected_emotion, safety_check_status, "
    "thought_process, extracted_fields, reply_text (clean spoken text), "
    "and speech_text (with official Gnani Timbre v3.0 tags: <sigh>, <exhales>, <pauses>, <slow>, <excited>)."
)


def _build_llm_prompts(
    user_message: str,
    prev_known: Dict[str, Optional[str]],
    deterministic_extracted: Dict[str, str],
    lang: str,
    history: List[Dict[str, str]],
    known_make_model: Optional[str] = None,
) -> Tuple[str, List[Dict[str, str]], str]:
    """Build both the zero-shot reasoning prompt and the compact fine-tuned prompt + conversation turns."""
    captured_so_far = {**{k: v for k, v in prev_known.items() if v}, **deterministic_extracted}
    if known_make_model:
        captured_so_far["vehicle_make_model"] = known_make_model
    still_needed = [k for k in FIELD_ORDER if not captured_so_far.get(k)]
    safety_already_checked = bool(any(prev_known.values()) or _has_prior_safety_empathy(history))

    compact_prompt = (
        f"{COMPACT_FINETUNED_SYSTEM_PROMPT}\n"
        f"Language preference: {lang}\n"
        f"already_captured: {json.dumps(captured_so_far, ensure_ascii=False)}\n"
        f"still_missing: {json.dumps(still_needed)}"
    )

    system_prompt = (
        "You are ClaimSathi AI, a warm, genuinely caring, and accurate Indian motor insurance intake companion.\n"
        "Strict rules for input extraction & response:\n"
        "1. Understand literally what the user just said in ANY Indian language (Hindi, Kannada, Telugu, Tamil, Marathi, Malayalam, Bengali, Gujarati, Punjabi, Urdu), English, or mixed Romanized speech (Hinglish, Kanglish, Tenglish, Tanglish). NEVER invent or guess unmentioned fields. Leave unmentioned fields as null.\n"
        "2. Normalize every extracted slot strictly to clean English for the insurer:\n"
        "   - policy_reference: convert spoken letters/digits in any Indian script into uppercase alphanumeric (e.g. 'కేఏ త్రీ ఫోర్ ఈ వన్ నేన్' -> 'KA-34-E-19', 'டி என் ஜீரோ ஒன் ஏ பி நைன் எய்ட் செவன் சிக்ஸ்' -> 'TN-01-AB-9876', 'KA 01 MJ 4412' -> 'KA-01-MJ-4412').\n"
        "   - vehicle_type: extract ONLY 'bike' (two-wheeler/scooter), 'car' (four-wheeler), 'auto_rickshaw', 'truck', or 'bus'. Generic regional words ('bandi', 'బండి', 'gaadi', 'gadi', 'vandi', 'వண்டி', 'గాడి', 'ಗಾಡಿ', 'गाड़ी', 'वाहन', 'వాహనం', 'வாகனம்') NEVER imply car or bike — if ambiguous or uncertain between bike and car, set vehicle_type to null and ask politely in `reply_text` whether it is a bike or a car.\n"
        "   - vehicle_make_model: extract clean English make/model name if mentioned in ANY language (e.g. 'Pulsar 220' / 'పల్సర్ 220' / 'पल्सर 220' -> 'Bajaj Pulsar 220F', 'Swift' -> 'Maruti Suzuki Swift'). When the user tells you their vehicle model (e.g. 'My bike is Pulsar 220' or 'My bike model is Pulsar 220'), capture `vehicle_make_model` AND set `vehicle_type` ('bike' or 'car'), acknowledge the model naturally, NEVER confuse model numbers like 220/350/125/MT-15 with policy/registration numbers or dates, and smoothly ask ONLY for the next genuinely missing field in `still_missing`.\n"
        "   - incident_location: clean English place/city name (e.g. 'ధవళగిరిలో' -> 'Dhavalagiri', 'சென்னையில்' -> 'Chennai').\n"
        "   - incident_date: clean English date/time ('నిన్న' / 'कल' / 'நேற்று' -> 'Yesterday').\n"
        "   - damage_description: concise English summary ONLY when actual damage or damaged parts were described; if the user only said 'accident happened' without naming damage, leave damage_description as null and ask what was damaged.\n"
        "3. Memory rule: First extract any newly mentioned values into `extracted_fields`. NEVER ask in `reply_text` for anything in `already_captured` OR anything you just extracted into `extracted_fields`. Only ask for fields that remain null after extraction — if all 5 fields are now captured, confirm warmly and invite them to proceed to Step 2.\n"
        f"4. Human warmth, safety-first empathy & language lock: Match the user's exact spoken language & script style ('{lang}' — e.g. reply in Telugu for Telugu, Tamil for Tamil, Kannada for Kannada, Hindi for Hindi, Marathi for Marathi, Hinglish/Kanglish/Tenglish/Tanglish when spoken in mixed style). NEVER switch unexpectedly to English when the user spoke an Indian language.\n"
        f"   Speak like a real, compassionate human assistant (never robotic, never scripted):\n"
        f"   - If `safety_already_checked` is False ({json.dumps(safety_already_checked)}) AND the user is reporting an accident or damage: BEFORE discussing claim fields, lead naturally in your own words with sincere concern (express sympathy, ask if they are safe and unhurt, and reassure them calmly not to worry — you'll take care of everything with them step by step). Then briefly acknowledge any details they already gave and gently ask for the next missing detail(s) in `still_missing`.\n"
        "   - If the user confirms they are safe: express warm relief first, confirm new details, and smoothly ask what's still missing.\n"
        "   - On later follow-up turns (`safety_already_checked` is True): maintain a warm, supportive tone without repeating 'Are you safe?'; confirm the new detail and move smoothly to the next missing detail (or warmly invite them to Step 2 when complete).\n"
        "   Keep `reply_text` conversational and natural (2-3 concise sentences on first accident turn, 1-2 on follow-ups), with zero markdown, zero JSON keys, and zero internal thoughts.\n"
        "   NEVER read aloud or ask the user by voice for long form IDs like residential pincode, driving license number, issuing RTO, or bank IFSC code — collect only natural incident facts and leave form IDs for the structured form.\n"
        "5. Expressive Voice Prosody for Gnani Timbre v3.0: Keep `reply_text` 100% plain text (zero `<...>` tags). In `speech_text`, weave official Gnani Timbre v3.0 voice tags naturally so the spoken voice sounds genuinely caring: use `<sigh>` or `<slow>` at the start of an accident/empathy turn, `<exhales>` when relieved the user is safe, `<excited>` on warm greetings or completion, and `<pauses>` between the safety check/reassurance and the follow-up question. Set `speech_rate` around 0.94-0.96 on accident/empathy turns and 1.0 on routine turns.\n"
        f"Safety check already asked in prior turns: {json.dumps(safety_already_checked)}\n"
        f"Already captured details: {json.dumps(captured_so_far, ensure_ascii=False)}\n"
        f"Still missing core claim fields: {json.dumps(still_needed)}\n"
        "Respond strictly as compact valid JSON with `extracted_fields` and `reply_text` FIRST:\n"
        "{\n"
        '  "extracted_fields": {"policy_reference": null, "vehicle_type": null, "vehicle_make_model": null, "incident_location": null, "incident_date": null, "damage_description": null},\n'
        '  "motor_slots": {"loss_type": null, "incident_time": null, "driver_was_owner": null, "driver_name": null, "driver_relationship": null, "vehicle_usage_type": null, "pillion_rider_present": null, "occupants_count": null, "injury_or_third_party_flag": null, "police_fir_lodged_flag": null, "inspection_location": null},\n'
        '  "reply_text": "clean short spoken acknowledgement + missing field question only",\n'
        '  "speech_text": "same reply with optional Gnani tags",\n'
        '  "intent": "greeting|claim_intake|question|correction|casual_chat|unclear",\n'
        '  "insurance_sector": "motor|general",\n'
        '  "detected_emotion": "warm_friendly|calm_informative|anxious_roadside|distressed_high_impact|relieved_safe",\n'
        '  "empathy_cue": "short internal note",\n'
        '  "safety_check_status": "routine|urgent_safety_inquiry|confirmed_safe|medical_attention_noted",\n'
        '  "inferred_cause": null,\n'
        '  "drivability_assessment": "unknown|likely_drivable|caution_check_before_riding|non_drivable_towing_recommended",\n'
        '  "plausibility_note": "short internal note",\n'
        '  "thought_process": "short internal backend-only note",\n'
        '  "speech_rate": 1.0,\n'
        '  "speech_pitch": 1.0\n'
        "}"
    )

    turns: List[Dict[str, str]] = []
    for h in history[-8:]:
        txt = (h.get("text") or "").strip()
        if txt:
            turns.append({"sender": "assistant" if h.get("sender") == "assistant" else "user", "text": txt})
    turns.append({"sender": "user", "text": user_message})
    return system_prompt, turns, compact_prompt


async def _call_gemini_reasoning(
    system_prompt: str,
    turns: List[Dict[str, str]],
) -> Optional[Tuple[Dict[str, Any], str]]:
    """Approach A: Call Google Gemini API with structured JSON reasoning and automatic model fallback."""
    settings = get_settings()
    if not _is_valid_api_key(settings.gemini_api_key):
        return None

    primary = (settings.gemini_model or "gemini-flash-lite-latest").strip()
    candidate_models = list(dict.fromkeys([
        primary,
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]))

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.gemini_api_key.strip(),
    }
    contents = [
        {
            "role": "model" if t["sender"] == "assistant" else "user",
            "parts": [{"text": t["text"]}],
        }
        for t in turns
    ]
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.45,
            "maxOutputTokens": 900,
            "responseMimeType": "application/json",
        },
    }

    async with httpx.AsyncClient(timeout=settings.gemini_timeout_seconds) as client:
        for model_name in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code in (404, 429, 503):
                    logger.warning("Gemini model '%s' returned HTTP %s; trying next fallback model.", model_name, resp.status_code)
                    continue
                if resp.status_code != 200:
                    logger.warning("Gemini API returned HTTP %s; falling back to secondary brain.", resp.status_code)
                    return None
                candidates = resp.json().get("candidates") or []
                if not candidates:
                    continue
                parts = candidates[0].get("content", {}).get("parts") or []
                raw_text = "".join(
                    p.get("text", "")
                    for p in parts
                    if isinstance(p, dict) and not p.get("thought")
                ).strip()
                parsed = _parse_llm_json_response(raw_text)
                if parsed and parsed.get("reply_text") and not _looks_like_json_or_code(str(parsed["reply_text"])):
                    return parsed, f"gemini:{model_name}"
            except Exception as exc:
                logger.warning("Gemini call for '%s' failed (%s); trying fallback.", model_name, exc.__class__.__name__)
                continue
    return None


async def _call_ollama_reasoning(
    system_prompt: str,
    turns: List[Dict[str, str]],
    compact_prompt: Optional[str] = None,
) -> Optional[Tuple[Dict[str, Any], str]]:
    """Approach B: Call lightweight local Ollama server (supports fine-tuned ClaimSathi multi-sector model)."""
    settings = get_settings()
    if not settings.ollama_enabled or not settings.ollama_api_url:
        return None

    model_name = (settings.ollama_model or "qwen2.5:1.5b").strip()
    is_finetuned = "claimsathi" in model_name.lower()
    active_sys_prompt = (compact_prompt or system_prompt) if is_finetuned else system_prompt

    messages = [{"role": "system", "content": active_sys_prompt}] + [
        {"role": "assistant" if t["sender"] == "assistant" else "user", "content": t["text"]}
        for t in turns
    ]
    payload = {
        "model": model_name,
        "stream": False,
        "format": "json",
        "options": {"num_predict": 240 if is_finetuned else 320, "temperature": 0.45 if is_finetuned else 0.55},
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
            resp = await client.post(settings.ollama_api_url.strip(), json=payload)
        if resp.status_code != 200:
            logger.debug("Ollama returned HTTP %s; using local cognitive fallback.", resp.status_code)
            return None
        raw_out = (resp.json().get("message", {}).get("content") or "").strip()
        parsed = _parse_llm_json_response(raw_out)
        if parsed and parsed.get("reply_text"):
            return parsed, f"ollama:{model_name}"
    except Exception as exc:
        logger.debug("Ollama reasoning skipped (%s); using local cognitive fallback.", exc.__class__.__name__)
    return None


async def _call_generic_llm_reasoning(
    system_prompt: str,
    turns: List[Dict[str, str]],
) -> Optional[Tuple[Dict[str, Any], str]]:
    """Primary / custom OpenAI-compatible or Groq endpoint configured via LLM_API_URL & LLM_API_KEY."""
    settings = get_settings()
    if not settings.llm_api_url or not settings.llm_api_url.strip():
        return None

    url = settings.llm_api_url.strip()
    is_local_ollama = "/api/chat" in url and ("localhost" in url or "127.0.0.1" in url)
    if not is_local_ollama and not _is_valid_api_key(settings.llm_api_key):
        return None

    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key and settings.llm_api_key.strip():
        headers["Authorization"] = f"Bearer {settings.llm_api_key.strip()}"

    messages = [{"role": "system", "content": system_prompt}] + [
        {"role": "assistant" if t["sender"] == "assistant" else "user", "content": t["text"]}
        for t in turns
    ]
    model_name = (settings.llm_model or "qwen/qwen3.8-27b").strip()
    provider_tag = f"groq:{model_name}" if "groq.com" in url.lower() else f"custom-llm:{model_name}"

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            if "/api/chat" in url:
                resp = await client.post(
                    url,
                    headers=headers,
                    json={"model": model_name, "stream": False, "format": "json", "messages": messages},
                )
                raw_out = (resp.json().get("message", {}).get("content") or "").strip() if resp.status_code == 200 else ""
            else:
                body: Dict[str, Any] = {
                    "model": model_name,
                    "temperature": 0.45,
                    "max_tokens": 900,
                    "response_format": {"type": "json_object"},
                    "messages": messages,
                }
                resp = await client.post(url, headers=headers, json=body)
                if resp.status_code != 200:
                    logger.warning("Groq/Custom LLM returned HTTP %s; falling back to Gemini.", resp.status_code)
                    return None
                choices = resp.json().get("choices") or []
                raw_out = (choices[0].get("message", {}).get("content") or "").strip() if choices else ""

        parsed = _parse_llm_json_response(raw_out)
        if parsed and parsed.get("reply_text") and not _looks_like_json_or_code(str(parsed["reply_text"])):
            return parsed, provider_tag
        logger.warning("Groq/Custom LLM returned incomplete or non-JSON reply; triggering fallback.")
    except Exception as exc:
        logger.warning("Groq/Custom LLM call failed (%s); falling back to Gemini.", exc.__class__.__name__)
    return None


async def _run_reasoning_llm(
    user_message: str,
    prev_known: Dict[str, Optional[str]],
    deterministic_extracted: Dict[str, str],
    lang: str,
    history: List[Dict[str, str]],
    known_make_model: Optional[str] = None,
) -> Optional[Tuple[Dict[str, Any], str]]:
    """
    Execute Language-Smart LLM Cascade:
    - South Indian / Dravidian languages (kn-IN, te-IN, ta-IN, ml-IN): Gemini first -> Groq -> Ollama
    - English, Hindi, Hinglish & Auto-Detect: Groq first (>2x faster) -> Gemini -> Ollama
    """
    system_prompt, turns, compact_prompt = _build_llm_prompts(
        user_message=user_message,
        prev_known=prev_known,
        deterministic_extracted=deterministic_extracted,
        lang=lang,
        history=history,
        known_make_model=known_make_model,
    )
    prefer_gemini_first = (lang or "").strip() in {
        "kn-IN", "kn-Latn", "te-IN", "te-Latn", "ta-IN", "ta-Latn",
        "ml-IN", "ml-Latn", "mr-IN", "mr-Latn", "bn-IN", "gu-IN", "pa-IN", "ur-IN",
    }

    if prefer_gemini_first:
        res = await _call_gemini_reasoning(system_prompt, turns)
        if res:
            return res
        res = await _call_generic_llm_reasoning(system_prompt, turns)
        if res:
            return res
    else:
        res = await _call_generic_llm_reasoning(system_prompt, turns)
        if res:
            return res
        res = await _call_gemini_reasoning(system_prompt, turns)
        if res:
            return res

    return await _call_ollama_reasoning(system_prompt, turns, compact_prompt=compact_prompt)


def _sanitize_motor_slots_dict(
    raw_slots: Any,
    resolved_vehicle_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate Group A motor slots from LLM or previous turn and enforce 2W vs 4W scoping."""
    if not isinstance(raw_slots, dict):
        return {}
    allowed_loss = {"own_damage_accident", "theft", "fire_natural_calamity", "third_party"}
    allowed_rel = {"owner", "paid_driver", "relative_or_friend"}
    allowed_usage = {"private_social_domestic", "commercial_hire_reward"}
    out: Dict[str, Any] = {}
    for k in (
        "claimed_registration", "loss_type", "incident_time", "driver_was_owner",
        "driver_name", "driver_relationship", "vehicle_usage_type",
        "pillion_rider_present", "occupants_count", "injury_or_third_party_flag",
        "police_fir_lodged_flag", "inspection_location",
    ):
        v = raw_slots.get(k)
        if v is None:
            continue
        if isinstance(v, str) and (not v.strip() or v.strip().lower() in _IGNORED_LLM_FIELD_VALUES):
            continue
        if k == "loss_type" and v not in allowed_loss:
            continue
        if k == "driver_relationship" and v not in allowed_rel:
            continue
        if k == "vehicle_usage_type" and v not in allowed_usage:
            continue
        if k == "occupants_count":
            try:
                v = int(v)
            except Exception:
                continue
        if k in ("driver_was_owner", "pillion_rider_present", "injury_or_third_party_flag", "police_fir_lodged_flag"):
            if isinstance(v, str):
                v = v.strip().lower() in ("true", "yes", "1")
            else:
                v = bool(v)
        out[k] = v.strip() if isinstance(v, str) else v

    if resolved_vehicle_type == "two_wheeler":
        out.pop("occupants_count", None)
    elif resolved_vehicle_type == "four_wheeler":
        out.pop("pillion_rider_present", None)
    return out


async def process_conversational_turn(
    message: str,
    language: Optional[str] = "indic-auto",
    known_fields: Optional[Dict[str, Optional[str]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    expected_field: Optional[str] = None,
    known_motor_slots: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Stateful cognitive & emotional conversational processor:
    0. Guards against silence / non-speech input so empty recordings never trigger scripts.
    1. Preserves all previously known fields (`known_fields`).
    2. Extracts newly mentioned fields deterministically + fuses LLM-understood slots.
    3. Prioritizes real LLM reasoning (Approach A Gemini -> Approach B Ollama),
       falling back cleanly to the 4-stage local cognitive & emotional engine.
    4. Returns clean `reply_text`, Gnani Timbre v3.0 tagged `assistant_speech_text`,
       and rich `reasoning_trace`.
    """
    raw_text = (message or "").strip()
    history = history or []
    prev_known: Dict[str, Optional[str]] = {
        k: (known_fields.get(k) or None) if known_fields else None
        for k in FIELD_ORDER
    }

    # Layer 0: Silence / noise-only guard
    if not has_meaningful_words(raw_text):
        final_fields, missing = build_claim_fields_state(prev_known, language or "en-IN")
        return {
            "transcript": raw_text,
            "detected_language": language if (language and language != "indic-auto") else "en-IN",
            "assistant_language": language if (language and language != "indic-auto") else "en-IN",
            "reply_text": "",
            "assistant_dialogue": "",
            "assistant_speech_text": "",
            "fields": final_fields,
            "missing_fields": missing,
            "known_fields": prev_known,
            "newly_captured": {},
            "claimed_vehicle_type": None,
            "vehicle_make_model": None,
            "vehicle_registration": prev_known.get("policy_reference"),
            "damage_keywords": [],
            "incident_description": prev_known.get("damage_description"),
            "is_complete": len(missing) == 0,
            "no_speech_detected": True,
            "reasoning_trace": ConversationalReasoningTrace(
                detected_emotion="calm_informative",
                empathy_cue="Waiting for audible speech",
                thought_process="No spoken words were detected in the audio or text input.",
                llm_provider="layer0-silence-gate",
                detected_intent="silence_or_noise",
            ),
        }

    is_first_turn = not any(prev_known.values()) and not _has_prior_safety_empathy(history)
    resolved_lang = detect_conversation_language(raw_text, language)
    prev_make_model = None
    if isinstance(known_motor_slots, dict) and known_motor_slots.get("vehicle_make_model"):
        prev_make_model = str(known_motor_slots["vehicle_make_model"]).strip() or None
    elif isinstance(known_fields, dict) and known_fields.get("vehicle_make_model"):
        prev_make_model = str(known_fields["vehicle_make_model"]).strip() or None

    # Check pure greeting / mic check before any spurious slot match can override it
    routed_fallback: Dict[str, str] = {}
    det_make_model: Optional[str] = None
    if _is_pure_greeting_or_mic_check(raw_text):
        turn_extracted = {}
        slots = {"claimed_vehicle_type": None, "vehicle_make_model": None, "vehicle_registration": None, "damage_keywords": [], "incident_description": None, "detected_language": resolved_lang}
        pure_greeting = True
        asked_question = False
    else:
        extracted_fields, _ = extract_claim_fields(raw_text)
        slots = extract_multimodal_slots(raw_text, language_hint=resolved_lang)
        det_make_model = slots.get("vehicle_make_model")

        # 1. Deterministic NLU extraction from this turn
        turn_extracted = {}
        for f in extracted_fields:
            if f.confidence != FieldConfidence.MISSING and f.value:
                turn_extracted[f.name] = f.value

        if "policy_reference" not in turn_extracted and slots.get("vehicle_registration"):
            turn_extracted["policy_reference"] = slots["vehicle_registration"]
        if "vehicle_type" not in turn_extracted and slots.get("claimed_vehicle_type"):
            turn_extracted["vehicle_type"] = "bike" if slots["claimed_vehicle_type"] == "two_wheeler" else "car"
        if "vehicle_type" not in turn_extracted and det_make_model:
            from ..evidence.cost_estimator import infer_vehicle_type_from_make_model
            inferred_vt = infer_vehicle_type_from_make_model(det_make_model)
            if inferred_vt:
                turn_extracted["vehicle_type"] = inferred_vt

        # Compute missing before short-answer routing
        tentative_merged = dict(prev_known)
        for k, v in turn_extracted.items():
            if v:
                tentative_merged[k] = v
        tentative_missing = [k for k in FIELD_ORDER if not tentative_merged.get(k)]

        asked_question = _is_conversational_question(raw_text)
        pure_greeting = False

        # Route standalone field answers only when NOT a pure greeting, question, or pure model-declaration turn
        if not asked_question and not turn_extracted and not det_make_model and tentative_missing:
            target = expected_field if (expected_field and not prev_known.get(expected_field)) else tentative_missing[0]
            val_res = validate_and_normalize_field_answer(target, raw_text, language=resolved_lang)
            if val_res.get("routed_fields"):
                for rk, rv in val_res["routed_fields"].items():
                    if rv:
                        routed_fallback[rk] = rv
            if val_res.get("is_valid_for_target") and val_res.get("english_value"):
                routed_fallback[target] = val_res["english_value"]

    # 2. Try Real Conversational LLM Brain (Approach A: Gemini -> Approach B: Ollama)
    llm_result = await _run_reasoning_llm(
        user_message=raw_text,
        prev_known=prev_known,
        deterministic_extracted=turn_extracted,
        lang=resolved_lang,
        history=history,
        known_make_model=det_make_model or prev_make_model,
    )

    llm_make_model: Optional[str] = None
    if llm_result:
        llm_payload, llm_provider_name = llm_result
        llm_intent = str(llm_payload.get("intent") or "").strip().lower()
        llm_extracted = _sanitize_llm_extracted_fields(llm_payload.get("extracted_fields"))
        raw_llm_mm = (
            (llm_payload.get("extracted_fields") or {}).get("vehicle_make_model")
            if isinstance(llm_payload.get("extracted_fields"), dict)
            else None
        ) or llm_payload.get("vehicle_make_model")
        if isinstance(raw_llm_mm, str) and raw_llm_mm.strip() and raw_llm_mm.strip().lower() not in _IGNORED_LLM_FIELD_VALUES:
            from ..evidence.cost_estimator import extract_vehicle_make_model, resolve_make_model_tier
            llm_mm_cand = extract_vehicle_make_model(raw_llm_mm.strip()) or resolve_make_model_tier(raw_llm_mm.strip()).get("vehicle_make_model")
            if llm_mm_cand and llm_mm_cand != "Standard Category Baseline":
                llm_make_model = llm_mm_cand
        # Fuse LLM-extracted slots cleanly (let explicit LLM correction update ambiguous vehicle/location if deterministic differed)
        for lk, lv in llm_extracted.items():
            if not lv:
                continue
            if lk not in turn_extracted:
                turn_extracted[lk] = lv
            elif lk == "policy_reference" and "-" in lv and "-" not in (turn_extracted.get(lk) or ""):
                turn_extracted[lk] = lv
        # Drop speculative standalone routing if LLM recognized greeting/chat/question/unclear with no claim fields
        if llm_intent not in ("greeting", "question", "casual_chat", "unclear") or llm_extracted:
            for rk, rv in routed_fallback.items():
                if rk not in turn_extracted and rv:
                    turn_extracted[rk] = rv
    else:
        llm_payload = None
        llm_provider_name = "local-cognitive"
        for rk, rv in routed_fallback.items():
            if rk not in turn_extracted and rv:
                turn_extracted[rk] = rv

    resolved_make_model = det_make_model or llm_make_model or prev_make_model
    newly_captured_model = (
        resolved_make_model
        if (det_make_model or llm_make_model) and resolved_make_model and resolved_make_model != prev_make_model
        else None
    )
    if resolved_make_model and not turn_extracted.get("vehicle_type") and not prev_known.get("vehicle_type"):
        from ..evidence.cost_estimator import infer_vehicle_type_from_make_model
        inferred_vt = infer_vehicle_type_from_make_model(resolved_make_model)
        if inferred_vt:
            turn_extracted["vehicle_type"] = inferred_vt

    # 3. Merge into final state: NEVER lose previous fields; track what was new vs updated
    merged: Dict[str, Optional[str]] = dict(prev_known)
    newly_captured: Dict[str, str] = {}
    updated_existing: Dict[str, str] = {}

    for k, val in turn_extracted.items():
        if not val:
            continue
        old_val = prev_known.get(k)
        if not old_val:
            newly_captured[k] = val
            merged[k] = val
        elif old_val != val:
            updated_existing[k] = val
            merged[k] = val

    final_fields, missing = build_claim_fields_state(merged, resolved_lang)
    is_complete = len(missing) == 0

    # 4. Build cognitive trace & compose clean reply + Gnani Timbre v3.0 tagged speech script
    baseline_trace = _analyze_cognitive_reasoning(
        current_text=raw_text,
        history=history,
        merged_fields=merged,
        newly_captured=newly_captured,
        missing_fields=missing,
        is_first_turn=is_first_turn,
    )

    if llm_payload and not _looks_like_json_or_code(str(llm_payload.get("reply_text") or "")):
        raw_reply = re.sub(r"[*_#`]", "", str(llm_payload.get("reply_text") or "").strip())
        reply_text = strip_gnani_audio_tags(raw_reply)

        resolved_emotion = str(llm_payload.get("detected_emotion") or baseline_trace.detected_emotion)
        if resolved_emotion == "calm_informative" and baseline_trace.detected_emotion in ("anxious_roadside", "distressed_high_impact", "relieved_safe"):
            resolved_emotion = baseline_trace.detected_emotion

        raw_rate = float(llm_payload.get("speech_rate") or 0.0)
        if raw_rate == 0.0 or (raw_rate == 1.0 and resolved_emotion in ("distressed_high_impact", "anxious_roadside", "frustrated_or_confused")):
            raw_rate = baseline_trace.speech_rate
        raw_pitch = float(llm_payload.get("speech_pitch") or 0.0)
        if raw_pitch == 0.0 or (raw_pitch == 1.0 and resolved_emotion in ("distressed_high_impact", "anxious_roadside", "frustrated_or_confused")):
            raw_pitch = baseline_trace.speech_pitch

        reasoning_trace = ConversationalReasoningTrace(
            detected_emotion=resolved_emotion,
            empathy_cue=str(llm_payload.get("empathy_cue") or baseline_trace.empathy_cue),
            safety_check_status=str(llm_payload.get("safety_check_status") or baseline_trace.safety_check_status),
            inferred_cause=llm_payload.get("inferred_cause") or baseline_trace.inferred_cause,
            drivability_assessment=str(llm_payload.get("drivability_assessment") or baseline_trace.drivability_assessment),
            plausibility_note=str(llm_payload.get("plausibility_note") or baseline_trace.plausibility_note),
            causal_question_asked=baseline_trace.causal_question_asked,
            thought_process=str(llm_payload.get("thought_process") or baseline_trace.thought_process),
            speech_rate=max(0.85, min(1.15, raw_rate)),
            speech_pitch=max(0.90, min(1.10, raw_pitch)),
            llm_provider=llm_provider_name,
            detected_intent=str(llm_payload.get("intent") or baseline_trace.detected_intent),
            insurance_sector=str(llm_payload.get("insurance_sector") or "motor"),
            applied_gnani_tags=[],
        )

        raw_speech = re.sub(r"[*_#`]", "", str(llm_payload.get("speech_text") or raw_reply).strip())
        if _looks_like_json_or_code(raw_speech):
            raw_speech = raw_reply
        speech_text = sanitize_gnani_audio_tags(raw_speech)
        if not strip_gnani_audio_tags(speech_text):
            speech_text = reply_text
        if not extract_gnani_audio_tags(speech_text):
            speech_text = _tune_prosody_speech_text(reply_text, reasoning_trace, is_complete=is_complete)
        reasoning_trace.applied_gnani_tags = extract_gnani_audio_tags(speech_text)
    else:
        reasoning_trace = baseline_trace
        if pure_greeting:
            reply_text = _format_greeting_reply(resolved_lang, history)
        elif asked_question and not newly_captured and not updated_existing:
            reply_text = _answer_clarifying_question(raw_text, missing, resolved_lang, history, reasoning_trace)
        else:
            ack_part = _format_natural_ack(
                newly_captured=newly_captured,
                updated_fields=updated_existing,
                lang=resolved_lang,
                is_first_turn=is_first_turn,
                history=history,
                trace=reasoning_trace,
                newly_captured_model=newly_captured_model,
            )
            insight_part = _format_reasoning_insight(
                trace=reasoning_trace,
                lang=resolved_lang,
                missing=missing,
                history=history,
            )
            ask_part = _ask_missing_naturally(missing, resolved_lang, history, reasoning_trace)
            pieces = [p for p in (ack_part, insight_part, ask_part) if p]
            reply_text = " ".join(pieces).strip()

        reply_text = strip_gnani_audio_tags(reply_text)
        speech_text = _tune_prosody_speech_text(reply_text, reasoning_trace, is_complete=is_complete)
        reasoning_trace.applied_gnani_tags = extract_gnani_audio_tags(speech_text)

    if merged.get("vehicle_type"):
        vt_low = merged["vehicle_type"].lower()
        resolved_vtype = "two_wheeler" if vt_low in ("bike", "motorcycle", "scooter") else "four_wheeler"
    else:
        resolved_vtype = slots.get("claimed_vehicle_type")

    merged_motor_slots: Dict[str, Any] = {}
    if isinstance(known_motor_slots, dict):
        merged_motor_slots.update(_sanitize_motor_slots_dict(known_motor_slots, resolved_vtype))
    if not _is_pure_greeting_or_mic_check(raw_text):
        det_motor = extract_group_a_motor_slots(raw_text, resolved_vehicle_type=resolved_vtype)
        merged_motor_slots.update(_sanitize_motor_slots_dict(det_motor, resolved_vtype))
        if llm_payload and isinstance(llm_payload.get("motor_slots"), dict):
            llm_motor = _sanitize_motor_slots_dict(llm_payload.get("motor_slots"), resolved_vtype)
            for mk, mv in llm_motor.items():
                if mk not in merged_motor_slots:
                    merged_motor_slots[mk] = mv

    reg_val = (
        merged_motor_slots.get("claimed_registration")
        or slots.get("vehicle_registration")
        or merged.get("policy_reference")
    )
    if reg_val and not merged_motor_slots.get("claimed_registration"):
        norm_p = _extract_universal_indian_registration(str(reg_val))
        if norm_p:
            merged_motor_slots["claimed_registration"] = norm_p

    if resolved_make_model and not merged_motor_slots.get("vehicle_make_model"):
        merged_motor_slots["vehicle_make_model"] = resolved_make_model

    if resolved_vtype == "two_wheeler":
        merged_motor_slots.pop("occupants_count", None)
    elif resolved_vtype == "four_wheeler":
        merged_motor_slots.pop("pillion_rider_present", None)

    return {
        "transcript": raw_text,
        "detected_language": slots.get("detected_language") or resolved_lang,
        "assistant_language": resolved_lang,
        "reply_text": reply_text,
        "assistant_dialogue": reply_text,
        "assistant_speech_text": speech_text,
        "fields": final_fields,
        "missing_fields": missing,
        "known_fields": merged,
        "newly_captured": newly_captured,
        "claimed_vehicle_type": resolved_vtype,
        "vehicle_make_model": resolved_make_model,
        "vehicle_registration": merged.get("policy_reference") or slots.get("vehicle_registration"),
        "claimed_registration": merged_motor_slots.get("claimed_registration"),
        "motor_slots": merged_motor_slots,
        "damage_keywords": slots.get("damage_keywords", []),
        "incident_description": merged.get("damage_description"),
        "is_complete": is_complete,
        "no_speech_detected": False,
        "reasoning_trace": reasoning_trace,
    }
