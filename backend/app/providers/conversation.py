"""
Stateful Human-Like Conversational Claim Assistant Engine.
Maintains multi-turn memory (`known_fields` + `history`) so already-provided
details (such as bike/car registration number, date, or location) are NEVER
re-asked, supports optional configured LLM endpoints, and dynamically composes
natural, non-repetitive Indic/code-mixed/English replies.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from ..config import get_settings
from ..models import ClaimField, FieldConfidence
from .transcription import (
    FIELD_QUESTIONS,
    _extract_universal_indian_registration,
    detect_conversation_language,
    extract_claim_fields,
    extract_multimodal_slots,
    parse_indic_phonetic_policy,
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
    ]
    return any(m in q_low for m in markers)


def _answer_clarifying_question(
    user_text: str,
    missing: List[str],
    lang: str,
    history: List[Dict[str, str]],
) -> str:
    """Respond empathetically to a user's question without losing any already-captured slots."""
    q_low = user_text.lower()
    next_field = missing[0] if missing else None

    if "photo" in q_low or "image" in q_low or "upload" in q_low:
        if lang.startswith("hi"):
            return "Agle step mein hum aapke vehicle damage ki photo verify karke turant repair estimate nikalenge. Abhi bas incident ki bachi hui details share kar dein."
        if lang.startswith("kn"):
            return "Mundina step nalli nimma vaahana damage photo check maadi repair estimate kodutteve. Eega baki iro vivara heliri."
        return "In the next step, you'll upload a photo of the damage for instant AI screening and a repair estimate. Once we finish these quick details, we can move right ahead."

    if any(k in q_low for k in ["policy", "number", "registration", "bike no", "vehicle no"]) or next_field == "policy_reference":
        if lang.startswith("hi"):
            return "Humein aapki gaadi ka registration number ya policy number chahiye taaki aapka claim sahi vehicle se link ho sake. Aapke paas jo bhi ho bata dein."
        if lang.startswith("kn"):
            return "Claim nimmanna vaahana jothe link maadakke registration number athava policy number beku. Nimma hatra yavudide dayavittu heli."
        return "We use your vehicle registration or policy number simply to link this claim to the right cover. Whichever one you have handy works fine."

    follow = _ask_missing_naturally(missing, lang, history) if missing else ""
    if lang.startswith("hi"):
        return f"Bilkul, main aapki madad ke liye hoon. {follow}".strip()
    return f"Of course — happy to clarify. {follow}".strip()


def _format_natural_ack(newly_captured: Dict[str, str], updated_fields: Dict[str, str], lang: str, is_first_turn: bool, history: List[Dict[str, str]]) -> str:
    """Acknowledge only what was newly captured or corrected in this turn, warmly and briefly."""
    parts: List[str] = []
    pol = newly_captured.get("policy_reference")
    veh = newly_captured.get("vehicle_type")
    loc = newly_captured.get("incident_location")
    dt = newly_captured.get("incident_date")
    dam = newly_captured.get("damage_description")

    veh_label = "two-wheeler" if veh == "bike" else (veh or "vehicle")
    if lang.startswith("hi"):
        veh_word = "bike" if veh == "bike" else "car" if veh == "car" else "gaadi"
        if veh and pol:
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

        if is_first_turn:
            empathy = _pick_variant([
                "Sun kar bura laga — ummeed hai aap surakshit hain.",
                "Aapke accident ke baare mein sunkar dukh hua, ummeed hai sab theek hai.",
            ], history)
            if parts:
                return f"{empathy} Maine {', '.join(parts)} note kar liya hai."
            return f"{empathy} Main aapka claim darj karne mein madad karunga."
        if updated_fields:
            upd_desc = ", ".join(f"{v}" for v in updated_fields.values())
            return f"Theek hai, maine update karke {upd_desc} note kar liya hai."
        if parts:
            lead = _pick_variant(["Samajh gaya,", "Theek hai,", "Dhanyavaad,"], history)
            return f"{lead} maine {', '.join(parts)} note kar liya hai."
        return "Maine aapki baat note kar li hai."

    if lang.startswith("kn"):
        veh_word = "bike" if veh == "bike" else "car" if veh == "car" else "vaahana"
        if veh and pol:
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

        if is_first_turn:
            empathy = _pick_variant([
                "Apaghaata bagge keli bejaar aayitu — neevu kshemavaagiddira endu bhavisuttene.",
                "Ee ghatane bagge keli dukha aayitu, neevu surakshitavaagiddira?",
            ], history)
            if parts:
                return f"{empathy} Naanu {', '.join(parts)} note maadidini."
            return f"{empathy} Naanu nimma claim file maadakke sahaya maaduttene."
        if parts:
            lead = _pick_variant(["Sari,", "Dhanyavaadagalu,"], history)
            return f"{lead} {', '.join(parts)} daakhalisidini."
        return "Nimma maahiti note maadidini."

    if lang.startswith("te"):
        veh_word = "bike" if veh == "bike" else "car" if veh == "car" else "vehicle"
        if veh and pol:
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

        if is_first_turn:
            empathy = "Accident gurinchi vini badha vesindi — meeru safe ga unnaru ani aashistunnanu."
            if parts:
                return f"{empathy} Nenu {', '.join(parts)} note chesanu."
            return f"{empathy} Mee claim register cheyadaniki nenu help chestanu."
        if parts:
            return f"Sare, {', '.join(parts)} note chesanu."
        return "Mee vivaralu note chesanu."

    if lang.startswith("ta"):
        if pol:
            parts.append(f"number {pol}")
        if loc:
            parts.append(f"{loc}")
        if dt:
            parts.append(f"{dt}")
        if is_first_turn:
            if parts:
                return f"Ungal vipathu pathi kettu varuthamaaga irukkirathu. {', '.join(parts)} note pannitten."
            return "Ungal vipathu pathi kettu varuthamaaga irukkirathu. Claim file panna naan help panren."
        if parts:
            return f"Sari, {', '.join(parts)} note pannitten."
        return "Ungal thagavalai note pannitten."

    # Default natural Indian English
    if veh and pol:
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

    if is_first_turn:
        empathy = _pick_variant([
            "I'm really sorry to hear about the accident — I hope you're okay.",
            "Sorry to hear you went through that — glad you reached out.",
        ], history)
        if parts:
            return f"{empathy} I've got {', '.join(parts)} down."
        return f"{empathy} I'll help you get this claim filed smoothly."

    if updated_fields:
        upd = ", ".join(updated_fields.values())
        return f"Updated that to {upd} for you."
    if parts:
        lead = _pick_variant(["Got it — noted", "Thanks, I've added", "Okay, I've noted"], history)
        return f"{lead} {', '.join(parts)}."
    return "Got it, thanks for sharing that."


def _ask_missing_naturally(missing: List[str], lang: str, history: List[Dict[str, str]]) -> str:
    """Ask concisely and naturally only for fields genuinely missing — combining related ones cleanly."""
    if not missing:
        if lang.startswith("hi"):
            return _pick_variant([
                "Mere paas saari zaroori jaankari aa gayi hai. Ab aap Step 2 par jaakar damaged gaadi ki photo upload kar sakte hain.",
                "Sabhi details complete hain! Kripya ab Step 2 mein jaayein aur damage ki saaf photo upload karein.",
            ], history)
        if lang.startswith("kn"):
            return "Ella mukhya maahiti sikkirodrinda eega Step 2 ge hogi damage photo upload maadi."
        if lang.startswith("te"):
            return "Anni mukhyamaina vivaralu vachayi. Ippudu Step 2 ki velli damage photo upload cheyandi."
        if lang.startswith("ta"):
            return "Ella mukkiya thagavalum kidaithuvittathu. Ippo Step 2 ku poi damage photo upload pannunga."
        return _pick_variant([
            "That covers all the incident details we need! Whenever you're ready, move to Step 2 to upload or capture a photo of the damage.",
            "Great, we have all the initial details now. Head over to Step 2 whenever you're ready so our AI can inspect the damage photo.",
        ], history)

    mset = set(missing)

    # Combine Location + Date smoothly when both are missing
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
                "Kripya apni gaadi ka registration number ya policy number bata dein?",
                "Aapki gaadi ka number ya insurance policy number kya hai?",
            ],
            "vehicle_type": [
                "Yeh kis tarah ki gaadi hai — bike, scooter, car ya koi aur?",
                "Kya yeh two-wheeler (bike/scooter) hai ya car?",
            ],
            "incident_location": [
                "Yeh hadsa kis area ya shehar mein hua tha?",
                "Accident exact kis jagah ke paas hua?",
            ],
            "incident_date": [
                "Yeh accident kis tareekh ya kis waqt hua tha?",
                "Hadsa kab hua tha — din ya samay bata sakein?",
            ],
            "damage_description": [
                "Gaadi mein kis hisse ko kya nuksaan hua hai?",
                "Kripya thoda batayein ki gaadi mein kya damage aaya hai?",
            ],
        }
        return _pick_variant(q_map.get(first_missing, ["Kripya bachi hui jaankari share karein."]), history)

    if lang.startswith("kn"):
        q_map = {
            "policy_reference": ["Nimma vaahana registration number athava policy number helabahude?"],
            "vehicle_type": ["Idu bike, scooter, athava car aa?"],
            "incident_location": ["Apaghaata yaava area athava ooralli nadeyitu?"],
            "incident_date": ["Ee apaghaata yaava dinanka athava samayakke nadeyitu?"],
            "damage_description": ["Vaahanakke yaava bhaagadalli yenu damage aagide?"],
        }
        return _pick_variant(q_map.get(first_missing, ["Dayavittu baki maahiti tilisi."]), history)

    if lang.startswith("te"):
        q_map = {
            "policy_reference": ["Mee vehicle registration number leda policy number cheppagalara?"],
            "vehicle_type": ["Idi bike, scooter, leda car aa?"],
            "incident_location": ["Accident ee area leda city lo jarigindi?"],
            "incident_date": ["Ee accident eppudu jarigindo date leda time cheptara?"],
            "damage_description": ["Vehicle ki ekkada em damage aindo cheppagalara?"],
        }
        return _pick_variant(q_map.get(first_missing, ["Dayachesi migilina vivaralu cheppandi."]), history)

    if lang.startswith("ta"):
        q_map = {
            "policy_reference": ["Ungal vehicle registration number allathu policy number sollunga?"],
            "vehicle_type": ["Ithu bike, scooter, allathu car aa?"],
            "incident_location": ["Vipathu entha idathil allathu ooril nadanthathu?"],
            "incident_date": ["Vipathu eppo nadanthathu — thethi allathu neram sollunga?"],
            "damage_description": ["Vaganathukku enna setham yerpattullathu?"],
        }
        return _pick_variant(q_map.get(first_missing, ["Meethi thagavalai sollunga."]), history)

    q_map_en = {
        "policy_reference": [
            "Could you share your vehicle registration number or policy number?",
            "What is the registration number on your vehicle, or your policy number?",
        ],
        "vehicle_type": [
            "Was this a bike, scooter, car, or another vehicle?",
            "Could you confirm what kind of vehicle was involved?",
        ],
        "incident_location": [
            "Which area or city did the accident happen in?",
            "Where exactly did this take place?",
        ],
        "incident_date": [
            "When did the accident happen — roughly what date or time?",
            "Could you let me know the date or time of the incident?",
        ],
        "damage_description": [
            "What parts of the vehicle were damaged?",
            "Could you briefly describe the damage to the vehicle?",
        ],
    }
    return _pick_variant(q_map_en.get(first_missing, ["Could you share the remaining detail?"]), history)


async def _try_configured_llm_reply(
    user_message: str,
    known: Dict[str, Optional[str]],
    missing: List[str],
    lang: str,
    history: List[Dict[str, str]],
) -> Optional[str]:
    """
    If an explicit fast LLM endpoint (`LLM_API_URL`) is configured in `.env`,
    generate a genuine conversational reply constrained strictly to facts already captured.
    Never blocks user UX on slow/unconfigured runtimes.
    """
    settings = get_settings()
    if not settings.llm_api_url or not settings.llm_api_url.strip():
        return None

    url = settings.llm_api_url.strip()
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key and settings.llm_api_key.strip():
        headers["Authorization"] = f"Bearer {settings.llm_api_key.strip()}"

    sys_prompt = (
        "You are ClaimSathi AI, a warm, empathetic human-sounding motor insurance claims officer in India. "
        f"Reply naturally in language '{lang}' in 1-2 short sentences (under 35 words, plain spoken text with NO markdown, NO asterisks, NO bullet lists). "
        f"Already recorded details (NEVER ask for these again): { {k: v for k, v in known.items() if v} }. "
        f"Still missing details: {missing}. "
        "If missing is empty, invite the customer to proceed to Step 2 to upload or capture damage photos. "
        "Otherwise acknowledge briefly and ask naturally for the missing info."
    )
    msgs = [{"role": "system", "content": sys_prompt}]
    for h in history[-4:]:
        role = "assistant" if h.get("sender") == "assistant" else "user"
        if h.get("text"):
            msgs.append({"role": role, "content": h["text"]})
    msgs.append({"role": "user", "content": user_message})

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            if "/api/chat" in url:
                payload = {
                    "model": settings.llm_model or "mistral:latest",
                    "stream": False,
                    "options": {"num_predict": 90, "temperature": 0.4},
                    "messages": msgs,
                }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    txt = (resp.json().get("message", {}).get("content") or "").strip()
                    return re.sub(r"[*_#`]", "", txt) if txt else None
            else:
                payload = {
                    "model": settings.llm_model or "gpt-4o-mini",
                    "temperature": 0.4,
                    "max_tokens": 90,
                    "messages": msgs,
                }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    choices = resp.json().get("choices") or []
                    if choices:
                        txt = (choices[0].get("message", {}).get("content") or "").strip()
                        return re.sub(r"[*_#`]", "", txt) if txt else None
    except Exception as exc:
        logger.debug("Optional LLM reply skipped (%s); using contextual dialogue composer.", exc)
    return None


async def process_conversational_turn(
    message: str,
    language: Optional[str] = "indic-auto",
    known_fields: Optional[Dict[str, Optional[str]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    expected_field: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stateful conversational processor:
    1. Preserves all previously known fields (`known_fields`).
    2. Extracts all newly mentioned fields from `message` (even multiple at once or corrections).
    3. Routes short contextual answers cleanly to missing fields.
    4. Returns updated ClaimFields, missing_fields, slots, and a natural human reply.
    """
    raw_text = (message or "").strip()
    history = history or []
    prev_known: Dict[str, Optional[str]] = {
        k: (known_fields.get(k) or None) if known_fields else None
        for k in FIELD_ORDER
    }
    is_first_turn = not any(prev_known.values()) and len([h for h in history if h.get("sender") == "user"]) == 0

    resolved_lang = detect_conversation_language(raw_text, language)
    extracted_fields, _ = extract_claim_fields(raw_text)
    slots = extract_multimodal_slots(raw_text, language_hint=resolved_lang)

    # Extract everything directly spotted in this turn
    turn_extracted: Dict[str, str] = {}
    for f in extracted_fields:
        if f.confidence != FieldConfidence.MISSING and f.value:
            turn_extracted[f.name] = f.value

    if "policy_reference" not in turn_extracted and slots.get("vehicle_registration"):
        turn_extracted["policy_reference"] = slots["vehicle_registration"]
    if "vehicle_type" not in turn_extracted and slots.get("claimed_vehicle_type"):
        turn_extracted["vehicle_type"] = "bike" if slots["claimed_vehicle_type"] == "two_wheeler" else "car"

    # Compute currently missing before applying standalone follow-up context
    tentative_merged = dict(prev_known)
    for k, v in turn_extracted.items():
        if v:
            tentative_merged[k] = v
    tentative_missing = [k for k in FIELD_ORDER if not tentative_merged.get(k)]

    # If the user gave a short standalone answer (e.g. "Indiranagar", "18th November", "MH12DE1433")
    # and did NOT trigger a question, interpret it against expected_field / first missing field!
    asked_question = _is_conversational_question(raw_text)
    if not asked_question and not turn_extracted and tentative_missing:
        target = expected_field if (expected_field and not prev_known.get(expected_field)) else tentative_missing[0]
        val_res = validate_and_normalize_field_answer(target, raw_text, language=resolved_lang)
        if val_res.get("routed_fields"):
            for rk, rv in val_res["routed_fields"].items():
                if rv:
                    turn_extracted[rk] = rv
        if val_res.get("is_valid_for_target") and val_res.get("english_value"):
            turn_extracted[target] = val_res["english_value"]

    # Merge into final state: NEVER lose previous fields; track what was new vs updated
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

    missing = [k for k in FIELD_ORDER if not merged.get(k)]

    # Build ClaimField objects reflecting full state
    final_fields: List[ClaimField] = []
    for name in FIELD_ORDER:
        meta = FIELD_QUESTIONS[name]
        val = merged.get(name)
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

    # Compose natural human reply (LLM if explicitly configured & fast; else contextual composer)
    if asked_question and not newly_captured and not updated_existing:
        reply_text = _answer_clarifying_question(raw_text, missing, resolved_lang, history)
    else:
        llm_reply = await _try_configured_llm_reply(
            user_message=raw_text,
            known=merged,
            missing=missing,
            lang=resolved_lang,
            history=history,
        )
        if llm_reply:
            reply_text = llm_reply
        else:
            ack_part = _format_natural_ack(
                newly_captured=newly_captured,
                updated_fields=updated_existing,
                lang=resolved_lang,
                is_first_turn=is_first_turn,
                history=history,
            )
            ask_part = _ask_missing_naturally(missing, resolved_lang, history)
            reply_text = f"{ack_part} {ask_part}".strip()

    resolved_vtype = slots.get("claimed_vehicle_type")
    if not resolved_vtype and merged.get("vehicle_type"):
        vt_low = merged["vehicle_type"].lower()
        resolved_vtype = "two_wheeler" if vt_low in ("bike", "motorcycle", "scooter") else "four_wheeler"

    return {
        "transcript": raw_text,
        "detected_language": slots.get("detected_language") or resolved_lang,
        "assistant_language": resolved_lang,
        "reply_text": reply_text,
        "assistant_dialogue": reply_text,
        "assistant_speech_text": reply_text,
        "fields": final_fields,
        "missing_fields": missing,
        "known_fields": merged,
        "newly_captured": newly_captured,
        "claimed_vehicle_type": resolved_vtype,
        "vehicle_registration": merged.get("policy_reference") or slots.get("vehicle_registration"),
        "damage_keywords": slots.get("damage_keywords", []),
        "incident_description": merged.get("damage_description") or raw_text,
        "is_complete": len(missing) == 0,
    }
