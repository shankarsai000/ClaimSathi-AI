"""
ClaimSathi AI — Multi-Sector, Multi-Language Conversational Insurance Dataset Generator.

Generates ShareGPT / ChatML instruction fine-tuning datasets (`train.jsonl` & `val.jsonl`)
for QLoRA fine-tuning of a compact open-source LLM (`Qwen/Qwen2.5-1.5B-Instruct` or
`Llama-3.2-1B-Instruct`) on Google Colab (T4 GPU) or Adaptation Labs.

Supported Insurance Sectors (Long-Term Multi-Sector Architecture):
  1. motor    — Two-Wheeler (Bike/Scooter) & Four-Wheeler (Car/SUV/Commercial) FNOL
  2. health   — Hospitalization, Emergency Cashless & Medical Reimbursement Claims
  3. property — Home, Shop, Fire, Flood & Natural Calamity Property Damage Claims
  4. crop     — Agricultural / PMFBY Weather, Hailstorm, Flood & Pest Crop Loss Claims
  5. travel   — Flight Delay, Lost Baggage & Overseas Medical Emergency Claims

Key Behavioral Pillars Baked Into Weights:
  - Zero premature accident scripts on greetings/mic-checks ("Hello", "हलो।", "ನಮಸ್ಕಾರ", "నమస్కారం", "வணக்கம்")
  - Human safety & emotional triage first on high-impact crashes or medical emergencies
  - Causal & physical plausibility reasoning (e.g. rear-end impact vs. front damage; non-drivable towing advice)
  - Strict multi-turn memory (never re-asking fields already present in `already_captured`)
  - Official Gnani Timbre v3.0 inline emotion/pacing tags (<sigh>, <exhales>, <pauses>, <slow>, <excited>)
  - Code-mixed & native Indic fluency (English, Hindi, Hinglish, Kannada, Kanglish, Telugu, Tenglish, Tamil, Tanglish)
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

COMPACT_SYSTEM_PROMPT = (
    "You are ClaimSathi AI, an empathetic, thinking human insurance claims companion for India "
    "across Motor, Health, Property, Crop, and Travel insurance. "
    "Understand what the user actually said (never assume an accident on a greeting), prioritize human safety, "
    "reason about cause and plausibility, never re-ask already_captured fields, and respond in valid JSON with keys: "
    "intent, insurance_sector, detected_emotion, safety_check_status, inferred_cause, drivability_assessment, "
    "plausibility_note, thought_process, extracted_fields, reply_text, speech_text, speech_rate, speech_pitch."
)

_TAG_RE = re.compile(r"<[^<>]{1,32}>")


def strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


def make_example(
    user_text: str,
    already_captured: Dict[str, Any],
    still_missing: List[str],
    lang: str,
    output_dict: Dict[str, Any],
    history: List[Tuple[str, str]] | None = None,
) -> Dict[str, Any]:
    """Create a ChatML multi-turn conversation record ready for Unsloth / HuggingFace SFTTrainer."""
    if "reply_text" not in output_dict and "speech_text" in output_dict:
        output_dict["reply_text"] = strip_tags(output_dict["speech_text"])

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": (
                f"{COMPACT_SYSTEM_PROMPT}\n"
                f"Language preference: {lang}\n"
                f"already_captured: {json.dumps(already_captured, ensure_ascii=False)}\n"
                f"still_missing: {json.dumps(still_missing)}"
            ),
        }
    ]
    for u_turn, a_turn in (history or []):
        messages.append({"role": "user", "content": u_turn})
        messages.append({"role": "assistant", "content": a_turn})

    messages.append({"role": "user", "content": user_text})
    messages.append({"role": "assistant", "content": json.dumps(output_dict, ensure_ascii=False)})
    return {"messages": messages, "sector": output_dict.get("insurance_sector", "motor"), "language": lang}


def build_greeting_examples() -> List[Dict[str, Any]]:
    """Greetings and mic checks across Indian scripts & code-mixed speech — NEVER fill damage_description."""
    empty_fields = {
        "policy_reference": None,
        "vehicle_type": None,
        "incident_location": None,
        "incident_date": None,
        "damage_description": None,
    }
    all_missing = list(empty_fields.keys())

    samples = [
        ("Hello, can you hear me?", "en-IN", "<excited> Hello there! Yes, I can hear you loud and clear. <pauses> How can I help you with your insurance claim today?"),
        ("Hi ClaimSathi, are you there?", "en-IN", "<excited> Hi! I'm right here and listening. <pauses> Tell me how I can help you today — whether it's a motor, health, property, or travel claim."),
        ("हलो।", "hi-IN", "<excited> नमस्ते! मैं क्लेमसाथी हूँ, आपका बीमा सहायक। <pauses> बताइए, आज मैं आपकी किस प्रकार सहायता कर सकता हूँ?"),
        ("नमस्ते जी, मेरी आवाज़ आ रही है?", "hi-IN", "<excited> नमस्ते! जी हाँ, आपकी आवाज़ बिल्कुल साफ़ आ रही है। <pauses> आराम से बताइए, क्या बात है?"),
        ("Hello bhai, meri aawaz sunai de rahi hai?", "hi-IN", "<excited> Haan ji, aapki aawaz bilkul clear aa rahi hai! <pauses> Batayein, aaj main aapki kya madad kar sakta hoon?"),
        ("ನಮಸ್ಕಾರ, ನನ್ನ ಧ್ವನಿ ಕೇಳಿಸುತ್ತಿದೆಯೇ?", "kn-IN", "<excited> ನಮಸ್ಕಾರ! ಹೌದು, ನಿಮ್ಮ ಧ್ವನಿ ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸುತ್ತಿದೆ. <pauses> ನಾನು ನಿಮಗೆ ಹೇಗೆ సహಾಯ ಮಾಡಬಹುದು ಹೇಳಿ?"),
        ("Hello, nanna voice kelistidya?", "kn-IN", "<excited> Namaskara! Haan, nimma voice clear aagi kelistide. <pauses> Yenu sahaya beku heli?"),
        ("హలో, నా మాట వినిపిస్తుందా?", "te-IN", "<excited> నమస్కారం! అవును, మీ మాట నాకు స్పష్టంగా వినిపిస్తోంది. <pauses> చెప్పండి, నేను మీకు ఎలా సహాయం చేయగలను?"),
        ("Namaskaram andi, vinipistunda?", "te-IN", "<excited> Namaskaram! Clear ga vinipistondi. <pauses> Cheppandi, ee roju meeku ela help cheyali?"),
        ("வணக்கம், நான் பேசுவது கேட்கிறதா?", "ta-IN", "<excited> வணக்கம்! நீங்கள் பேசுவது தெளிவாகக் கேட்கிறது. <pauses> சொல்லுங்கள், நான் உங்களுக்கு எப்படி உதவ முடியும்?"),
        ("Testing mic 1 2 3", "en-IN", "<excited> Your microphone is working great! <pauses> Whenever you're ready, let me know what kind of claim or question you have."),
        ("Good morning!", "en-IN", "<excited> Good morning! Hope you're having a safe day. <pauses> How can I assist you with your insurance today?"),
    ]

    out: List[Dict[str, Any]] = []
    for text, lang, speech in samples:
        out.append(
            make_example(
                user_text=text,
                already_captured={},
                still_missing=all_missing,
                lang=lang,
                output_dict={
                    "intent": "greeting",
                    "insurance_sector": "general",
                    "detected_emotion": "warm_friendly",
                    "empathy_cue": "Responding warmly to user greeting without assuming an accident",
                    "safety_check_status": "routine",
                    "inferred_cause": None,
                    "drivability_assessment": "unknown",
                    "plausibility_note": "Greeting or audio check only — no claim details provided yet",
                    "thought_process": "The customer is only greeting me or checking their microphone. I must leave all claim fields null and welcome them warmly.",
                    "extracted_fields": dict(empty_fields),
                    "reply_text": strip_tags(speech),
                    "speech_text": speech,
                    "speech_rate": 1.02,
                    "speech_pitch": 1.03,
                },
            )
        )
    return out


def build_motor_insurance_examples(rng: random.Random) -> List[Dict[str, Any]]:
    """Generate rich multi-turn Motor Insurance (2W Bike & 4W Car) examples across languages and emotional states."""
    plates = [
        "KL-07-AB-1234", "KA-01-MJ-4412", "KA-05-NB-7821", "MH-12-DE-1433",
        "TS-09-UB-5510", "AP-39-CK-8820", "TN-07-BW-2041", "DL-03-CA-9012",
        "GJ-01-KR-3345", "WB-02-AL-6711", "RJ-14-QC-4099", "UP-16-BM-7123",
    ]
    cities = [
        ("Indiranagar, Bengaluru", "Indiranagar"),
        ("Koramangala Signal, Bengaluru", "Koramangala"),
        ("MG Road, Kochi", "Kochi"),
        ("Andheri East, Mumbai", "Andheri East"),
        ("Gachibowli Flyover, Hyderabad", "Gachibowli"),
        ("Madhapur, Hyderabad", "Madhapur"),
        ("Anna Nagar, Chennai", "Anna Nagar"),
        ("Hinjewadi Phase 2, Pune", "Hinjewadi"),
        ("Jayanagar 4th Block, Bengaluru", "Jayanagar"),
        ("Whitefield Main Road, Bengaluru", "Whitefield"),
        ("Connaught Place, Delhi", "Connaught Place"),
        ("Banjara Hills, Hyderabad", "Banjara Hills"),
    ]
    dates = [
        ("18th November", "on 18th November"),
        ("Yesterday Evening", "yesterday evening"),
        ("Today Morning", "today morning"),
        ("15th October", "on 15th October"),
        ("Yesterday Night", "last night"),
        ("Two Days Ago", "two days ago"),
    ]

    bike_damages_critical = [
        ("front fork bent and headlamp shattered", "Front fork bent and headlight shattered.", "non_drivable_towing_recommended"),
        ("front wheel jammed and handle bent", "Front wheel jammed and handlebar bent.", "non_drivable_towing_recommended"),
        ("engine oil leaking and fairing broken", "Engine oil leak and fairing broken.", "non_drivable_towing_recommended"),
    ]
    bike_damages_moderate = [
        ("headlamp broke and front mudguard cracked", "Headlight broken and front mudguard cracked.", "caution_check_before_riding"),
        ("fuel tank dented and right mirror broken", "Fuel tank dented and side mirror broken.", "likely_drivable"),
        ("side fairing scratched and indicator broken", "Side fairing scratched and indicator broken.", "likely_drivable"),
    ]
    car_damages_critical = [
        ("radiator leaking and front bumper crushed", "Radiator leaking and front bumper crushed.", "non_drivable_towing_recommended"),
        ("front axle broken and airbag deployed", "Front axle broken and airbag deployed.", "non_drivable_towing_recommended"),
    ]
    car_damages_moderate = [
        ("rear bumper dented and tail light cracked", "Rear bumper dented and taillight cracked.", "likely_drivable"),
        ("left door dented and side mirror broken", "Left door dented and side mirror broken.", "likely_drivable"),
        ("windshield cracked and bonnet dented", "Windshield cracked and bonnet dented.", "caution_check_before_riding"),
    ]

    out: List[Dict[str, Any]] = []

    # Pattern A: High-Impact / Scary Crash (Turn 1 -> Safety Check + Towing Advice)
    for _ in range(180):
        plate = rng.choice(plates)
        spoken_plate = plate.replace("-", " ")
        loc_full, loc_short = rng.choice(cities)
        dt_norm, dt_spoken = rng.choice(dates)
        is_bike = rng.random() < 0.6
        vtype = "bike" if is_bike else "car"
        raw_dmg, norm_dmg, driv = rng.choice(bike_damages_critical if is_bike else car_damages_critical)
        lang = rng.choice(["en-IN", "hi-IN", "kn-IN", "te-IN", "ta-IN"])

        if lang == "en-IN":
            user_msg = f"A speeding truck hit my {vtype} {spoken_plate} near {loc_short} {dt_spoken}, {raw_dmg}"
            speech = (
                f"<sigh> Oh goodness, getting hit by a truck near {loc_short} sounds terrifying <pauses> <slow> "
                f"first of all, are you completely safe and unhurt right now? "
                f"I have noted your {vtype} ({plate}), {dt_norm}, and the damage. "
                f"Please do not try to {'ride' if is_bike else 'drive'} it in this condition — we can arrange towing support and move to Step 2 for your damage photo whenever you're ready."
            )
        elif lang == "hi-IN":
            user_msg = f"Tez truck ne meri {vtype} {spoken_plate} ko {loc_short} ke paas {dt_spoken} thok diya, {raw_dmg}"
            speech = (
                f"<sigh> Baap re, {loc_short} ke paas truck se takkar sunkar bahut chinta hui <pauses> <slow> "
                f"sabse pehle batayein, aap bilkul surakshit toh hain na, kisi ko chot toh nahi aayi? "
                f"Maine aapki {vtype} ({plate}), {dt_norm} aur damage note kar liya hai. "
                f"Kripya is haalat mein gaadi bilkul na chalayein — hum towing note kar rahe hain, aur aap Step 2 mein photo upload kar sakte hain."
            )
        elif lang == "kn-IN":
            user_msg = f"{loc_short} hattira truck nanna {vtype} {spoken_plate} ge {dt_spoken} dikki Hodeyitu, {raw_dmg}"
            speech = (
                f"<sigh> Ayyo, {loc_short} hattira truck dikki keli tumba ghabari aayitu <pauses> <slow> "
                f"modalu heli, neevu kshemavaagiddira, yaarigu gayavaagillava? "
                f"Naanu nimma {vtype} ({plate}), {dt_norm} mattu damage vivara note maadidini. "
                f"Dayavittu ee ಸ್ಥಿತಿಯಲ್ಲಿ vaahana chalayisabedi, towing sahaya note maadutteve."
            )
        elif lang == "te-IN":
            user_msg = f"{loc_short} daggara {dt_spoken} oka lారీ naa {vtype} {spoken_plate} ni guddindi, {raw_dmg}"
            speech = (
                f"<sigh> Ayyo, {loc_short} daggara lorry accident vintunte chala bhayamga undi <pauses> <slow> "
                f"munduga meeru safe ga unnara, evariki debba tagalaledu kada? "
                f"Mee {vtype} ({plate}), {dt_norm} mariyu damage vivaralu note chesanu. "
                f"Dayachesi vehicle nadapakandi, towing arrange chesi Step 2 lo photo upload cheyandi."
            )
        else:
            user_msg = f"{loc_short} arugil {dt_spoken} oru lorry en {vtype} {spoken_plate} mel idithathu, {raw_dmg}"
            speech = (
                f"<sigh> Ayyo, {loc_short} arugil lorry mothiyathu ketka romba kavalaiyaaga irukku <pauses> <slow> "
                f"muthalil neenga bathiramaaga irukkeengala? "
                f"Ungal {vtype} ({plate}), {dt_norm} matrum damage vivaram note pannitten. "
                f"Vaganathai otta வேண்டாம், towing support note pannikiren."
            )

        out.append(
            make_example(
                user_text=user_msg,
                already_captured={},
                still_missing=FIELD_KEYS_ALL,
                lang=lang,
                output_dict={
                    "intent": "claim_intake",
                    "insurance_sector": "motor",
                    "detected_emotion": "distressed_high_impact",
                    "empathy_cue": "High-impact truck collision — checking personal safety first & warning against riding/driving",
                    "safety_check_status": "urgent_safety_inquiry",
                    "inferred_cause": "Third-party vehicle collision",
                    "drivability_assessment": driv,
                    "plausibility_note": "Critical mechanical/structural damage consistent with heavy collision — advising towing",
                    "thought_process": f"The user suffered a severe truck impact on their {vtype} ({plate}) with critical damage ({norm_dmg}). I must prioritize checking if they are unhurt and warn them not to drive/ride.",
                    "extracted_fields": {
                        "policy_reference": plate,
                        "vehicle_type": vtype,
                        "incident_location": loc_short,
                        "incident_date": dt_norm,
                        "damage_description": norm_dmg,
                    },
                    "reply_text": strip_tags(speech),
                    "speech_text": speech,
                    "speech_rate": 0.93,
                    "speech_pitch": 0.96,
                },
            )
        )

    # Pattern B: Multi-Turn Stateful Memory (Turn 1 gives Plate + Bike + Date; Turn 2 gives Location + Damage — NEVER re-ask Plate!)
    for _ in range(200):
        plate = rng.choice(plates)
        spoken_plate = plate.replace("-", " ")
        loc_full, loc_short = rng.choice(cities)
        dt_norm, dt_spoken = rng.choice(dates)
        is_bike = rng.random() < 0.65
        vtype = "bike" if is_bike else "car"
        raw_dmg, norm_dmg, driv = rng.choice(bike_damages_moderate if is_bike else car_damages_moderate)
        lang = rng.choice(["en-IN", "hi-IN", "kn-IN", "te-IN"])

        if lang == "en-IN":
            t1_user = f"An accident happened {dt_spoken}, my {vtype} number is {spoken_plate}"
            t1_speech = (
                f"<slow> I'm really sorry to hear about the accident <pauses> I hope you're doing okay. "
                f"I've noted your {vtype} registration {plate} and the time ({dt_norm}). "
                f"Could you tell me where this happened, how the impact occurred, and which parts were damaged?"
            )
        elif lang == "hi-IN":
            t1_user = f"Mera accident {dt_spoken} hua, meri {vtype} ka number {spoken_plate} hai"
            t1_speech = (
                f"<slow> Accident ke baare mein sunkar dukh hua <pauses> ummeed hai aap bilkul theek hain. "
                f"Maine aapki {vtype} ({plate}) aur {dt_norm} note kar liya hai. "
                f"Kya aap bata sakte hain ki yeh hadsa kis jagah par hua aur gaadi mein kya nuksaan aaya hai?"
            )
        elif lang == "kn-IN":
            t1_user = f"Nanna {vtype} {spoken_plate} {dt_spoken} accident aayitu"
            t1_speech = (
                f"<slow> Apaghaata bagge keli bejaar aayitu <pauses> neevu kshemavaagiddira endu bhavisuttene. "
                f"Nimma {vtype} ({plate}) mattu {dt_norm} note maadidini. "
                f"Ee ghatane yaava area nalli nadeyitu mattu vaahanakke yenu damage aagide heli?"
            )
        else:
            t1_user = f"Naa {vtype} {spoken_plate} ki {dt_spoken} accident ayyindi"
            t1_speech = (
                f"<slow> Accident gurinchi vini badha vesindi <pauses> meeru safe ga unnaru ani aashistunnanu. "
                f"Mee {vtype} ({plate}) mariyu {dt_norm} note chesanu. "
                f"Ee accident ekkada jarigindi mariyu vehicle ki em damage aindo cheppagalara?"
            )

        out.append(
            make_example(
                user_text=t1_user,
                already_captured={},
                still_missing=FIELD_KEYS_ALL,
                lang=lang,
                output_dict={
                    "intent": "claim_intake",
                    "insurance_sector": "motor",
                    "detected_emotion": "anxious_roadside",
                    "empathy_cue": "Warm empathy on initial report — acknowledging plate & date without re-asking",
                    "safety_check_status": "routine",
                    "inferred_cause": None,
                    "drivability_assessment": "unknown",
                    "plausibility_note": "Initial vehicle and date captured; awaiting location and damage details",
                    "thought_process": f"Captured {vtype} registration {plate} and date {dt_norm}. I must never ask for the registration number again; I will only ask for incident_location and damage_description.",
                    "extracted_fields": {
                        "policy_reference": plate,
                        "vehicle_type": vtype,
                        "incident_location": None,
                        "incident_date": dt_norm,
                        "damage_description": None,
                    },
                    "reply_text": strip_tags(t1_speech),
                    "speech_text": t1_speech,
                    "speech_rate": 0.96,
                    "speech_pitch": 0.99,
                },
            )
        )

        # Turn 2 of the same conversation (already_captured has policy_reference, vehicle_type, incident_date)
        t2_known = {
            "policy_reference": plate,
            "vehicle_type": vtype,
            "incident_date": dt_norm,
        }
        t2_missing = ["incident_location", "damage_description"]
        if lang == "en-IN":
            t2_user = f"I am safe, it skidded near {loc_short} because of rain and {raw_dmg}"
            t2_speech = (
                f"<exhales> Thank goodness you're safe! <pauses> Wet roads near {loc_short} can be really slippery. "
                f"I've recorded the location ({loc_short}) and the damage ({norm_dmg}). "
                f"<excited> All five details for your {vtype} {plate} are now complete — head over to Step 2 whenever you're ready to upload the damage photo!"
            )
        elif lang == "hi-IN":
            t2_user = f"Main bilkul theek hoon, {loc_short} ke paas baarish mein skid ho gayi aur {raw_dmg}"
            t2_speech = (
                f"<exhales> Shukar hai ki aap bilkul surakshit hain! <pauses> Maine {loc_short} ki location aur damage ({norm_dmg}) note kar liya hai. "
                f"<excited> Aapki {vtype} {plate} ki saari 5 details poori ho gayi hain — ab aap Step 2 mein damage photo upload kar sakte hain."
            )
        elif lang == "kn-IN":
            t2_user = f"Naanu safe iddini, {loc_short} hattira skid aagi {raw_dmg}"
            t2_speech = (
                f"<exhales> Neevu kshemavaagirodu keli samadhaana aayitu! <pauses> {loc_short} sthala mattu damage vivara daakhalisidini. "
                f"<excited> Nimma {vtype} {plate} na ella 5 vivaragalu poornavaagive — eega Step 2 nalli damage photo upload maadi."
            )
        else:
            t2_user = f"Nenu safe ga unnanu, {loc_short} daggara skid ayyi {raw_dmg}"
            t2_speech = (
                f"<exhales> Meeru safe ga unnaru ani vini santosham! <pauses> {loc_short} location mariyu damage note chesanu. "
                f"<excited> Mee {vtype} {plate} yokka 5 vivaralu complete ayyayi — ippudu Step 2 lo damage photo upload cheyandi."
            )

        out.append(
            make_example(
                user_text=t2_user,
                already_captured=t2_known,
                still_missing=t2_missing,
                lang=lang,
                history=[(t1_user, strip_tags(t1_speech))],
                output_dict={
                    "intent": "claim_intake",
                    "insurance_sector": "motor",
                    "detected_emotion": "relieved_safe",
                    "empathy_cue": "Customer confirmed personal safety — expressing relief & completing intake",
                    "safety_check_status": "confirmed_safe",
                    "inferred_cause": "Road skid / loss of traction",
                    "drivability_assessment": driv,
                    "plausibility_note": "Consistent wet-road skid mechanics matching reported damage",
                    "thought_process": f"Customer confirmed they are safe and provided the remaining location ({loc_short}) and damage ({norm_dmg}). All 5 core fields are now complete.",
                    "extracted_fields": {
                        "policy_reference": None,
                        "vehicle_type": None,
                        "incident_location": loc_short,
                        "incident_date": None,
                        "damage_description": norm_dmg,
                    },
                    "reply_text": strip_tags(t2_speech),
                    "speech_text": t2_speech,
                    "speech_rate": 0.99,
                    "speech_pitch": 1.02,
                },
            )
        )

    # Pattern C: Physical Plausibility / Contradiction Reasoning (Rear-end hit + Front-only damage)
    for _ in range(120):
        plate = rng.choice(plates)
        loc_full, loc_short = rng.choice(cities)
        dt_norm, _ = rng.choice(dates)
        vtype = rng.choice(["bike", "car"])
        front_dmg = "Front headlamp and front mudguard broken." if vtype == "bike" else "Front headlight and bonnet dented."
        lang = rng.choice(["en-IN", "hi-IN"])

        known = {"policy_reference": plate, "vehicle_type": vtype, "incident_date": dt_norm}
        if lang == "en-IN":
            u_msg = f"Another vehicle hit me from behind at {loc_short} traffic signal, and my front headlamp broke"
            speech = (
                f"<slow> Got it, I've noted the location ({loc_short}) and the front headlamp damage. <pauses> "
                f"Just so I can explain the mechanics clearly to the surveyor — since you were hit from behind at the signal, "
                f"did the impact push your {vtype} forward into a vehicle or barrier in front?"
            )
        else:
            u_msg = f"{loc_short} signal par piche se ek gaadi ne thoka aur meri aage ki headlight toot gayi"
            speech = (
                f"<slow> Samajh gaya, maine {loc_short} ki location aur front headlight damage note kar liya hai. <pauses> "
                f"Surveyor ko poori baat saaf samajh aaye isliye ek chota sa sawal — jab takkar piche se lagi, "
                f"kya jhatke se aapki {vtype} aage kisi gaadi ya divider se ja takrayi jisse aage ka hissa toota?"
            )

        out.append(
            make_example(
                user_text=u_msg,
                already_captured=known,
                still_missing=["incident_location", "damage_description"],
                lang=lang,
                output_dict={
                    "intent": "claim_intake",
                    "insurance_sector": "motor",
                    "detected_emotion": "calm_informative",
                    "empathy_cue": "Active listening with gentle physical plausibility inquiry",
                    "safety_check_status": "routine",
                    "inferred_cause": "Rear-end impact",
                    "drivability_assessment": "caution_check_before_riding",
                    "plausibility_note": "Rear impact reported with front-end damage — checking if vehicle was pushed forward into an obstacle",
                    "thought_process": "The customer reported being hit from behind, yet only front damage occurred. I should gently ask if they were pushed forward into a secondary collision so the surveyor doesn't flag a contradiction.",
                    "extracted_fields": {
                        "policy_reference": None,
                        "vehicle_type": None,
                        "incident_location": loc_short,
                        "incident_date": None,
                        "damage_description": front_dmg,
                    },
                    "reply_text": strip_tags(speech),
                    "speech_text": speech,
                    "speech_rate": 0.96,
                    "speech_pitch": 0.99,
                },
            )
        )

    return out


FIELD_KEYS_ALL = [
    "policy_reference",
    "vehicle_type",
    "incident_location",
    "incident_date",
    "damage_description",
]


def build_multi_sector_insurance_examples(rng: random.Random) -> List[Dict[str, Any]]:
    """
    Build multi-sector examples for ClaimSathi's long-term vision across:
      - Health Insurance (Hospitalization, Cashless, Surgery/Emergency)
      - Property / Home & Shop Insurance (Flood, Fire, Short-Circuit, Storm)
      - Crop / Agricultural PMFBY Insurance (Hailstorm, Unseasonal Rain, Pest)
      - Travel Insurance (Lost Baggage, Flight Delay, Medical Abroad)
    Maps sector-specific entities cleanly into the universal 5 core claim slots so the platform
    schema works across every insurance line while tagging `insurance_sector`.
    """
    out: List[Dict[str, Any]] = []

    # 1. Health Insurance (Hospitalization & Emergency Claims)
    hospitals = ["Apollo Hospital, Bengaluru", "Yashoda Hospital, Hyderabad", "Fortis Hospital, Mumbai", "Manipal Hospital, Mangaluru", "CMC Vellore"]
    diagnoses = [
        ("acute appendicitis surgery", "Emergency appendicitis surgery hospitalization"),
        ("dengue fever high platelet drop admission", "In-patient hospitalization for severe dengue fever"),
        ("wrist fracture after slip at home", "Orthopedic hospitalization for wrist fracture"),
        ("cardiac chest pain ICU observation", "Emergency ICU admission for acute chest pain"),
    ]
    health_policies = ["HLT-2026-88412", "STAR-MEDI-99201", "CARE-HLT-44109", "HDFC-ERGO-77210"]

    for _ in range(95):
        pol = rng.choice(health_policies)
        hosp = rng.choice(hospitals)
        raw_diag, norm_diag = rng.choice(diagnoses)
        dt = rng.choice(["Yesterday Night", "Today Morning", "18th November", "Two Days Ago"])
        lang = rng.choice(["en-IN", "hi-IN"])

        if lang == "en-IN":
            u_txt = f"My father was admitted to {hosp} {dt.lower()} for {raw_diag}, our health policy number is {pol}"
            speech = (
                f"<sigh> I'm so sorry your father had to be rushed to {hosp} <pauses> <slow> I really hope he is stable and recovering well under the doctors' care. "
                f"I've logged your health policy {pol}, the hospital ({hosp}), admission time ({dt}), and diagnosis ({norm_diag}). "
                f"Please upload the hospital admission slip or doctor's note in the next step so we can fast-track your cashless/reimbursement claim."
            )
        else:
            u_txt = f"Mere papa ko {dt.lower()} {hosp} mein {raw_diag} ke liye admit kiya gaya hai, health policy {pol} hai"
            speech = (
                f"<sigh> Papa ke hospital mein admit hone ki khabar sunkar chinta hui <pauses> <slow> ummeed hai ab unki tabiyat behtar hai. "
                f"Maine aapki health policy {pol}, {hosp}, {dt} aur diagnosis ({norm_diag}) note kar liya hai. "
                f"Kripya agle step mein hospital admission slip ya doctor prescription upload karein."
            )

        out.append(
            make_example(
                user_text=u_txt,
                already_captured={},
                still_missing=FIELD_KEYS_ALL,
                lang=lang,
                output_dict={
                    "intent": "claim_intake",
                    "insurance_sector": "health",
                    "detected_emotion": "distressed_high_impact",
                    "empathy_cue": "Family medical hospitalization — expressing heartfelt concern for patient recovery",
                    "safety_check_status": "medical_attention_noted",
                    "inferred_cause": "Medical emergency hospitalization",
                    "drivability_assessment": "unknown",
                    "plausibility_note": "Consistent inpatient hospitalization record with hospital, policy, and diagnosis",
                    "thought_process": "This is a Health Insurance hospitalization claim. I should express warm concern for the patient's health and map the health policy, hospital location, admission date, and medical condition.",
                    "extracted_fields": {
                        "policy_reference": pol,
                        "vehicle_type": "Health Plan (In-Patient)",
                        "incident_location": hosp,
                        "incident_date": dt,
                        "damage_description": norm_diag,
                    },
                    "reply_text": strip_tags(speech),
                    "speech_text": speech,
                    "speech_rate": 0.94,
                    "speech_pitch": 0.97,
                },
            )
        )

    # 2. Property / Home & Shop Insurance
    prop_events = [
        ("heavy rain water entered our ground floor shop and damaged electronics inventory", "Flood water inundation damaging shop inventory", "Waterlogging / flash flood"),
        ("electrical short circuit in kitchen caused smoke and cabinet fire damage", "Kitchen electrical short-circuit fire and smoke damage", "Electrical short-circuit fire"),
        ("cyclone wind blew off the warehouse tin roof and damaged stored goods", "Cyclone wind roof collapse and stock damage", "Severe storm / cyclone"),
    ]
    prop_policies = ["PROP-HOME-55120", "SHOP-SURAKSHA-33910", "FIRE-IND-77812"]
    prop_locs = ["Velachery, Chennai", "Kothrud, Pune", "Salt Lake, Kolkata", "Peenya Industrial Area, Bengaluru"]

    for _ in range(85):
        pol = rng.choice(prop_policies)
        loc = rng.choice(prop_locs)
        raw_ev, norm_ev, cause = rng.choice(prop_events)
        dt = rng.choice(["Yesterday Night", "Today Morning", "17th November"])
        u_txt = f"Under property policy {pol}, at our premises in {loc} {dt.lower()}, {raw_ev}"
        speech = (
            f"<sigh> Dealing with property damage like that in {loc} is really stressful <pauses> <slow> "
            f"first, please make sure the main power supply is switched off and everyone at the premises is safe. "
            f"I have recorded property policy {pol}, location ({loc}), date ({dt}), and the loss details ({norm_ev}). "
            f"Whenever it is safe, proceed to upload photos of the affected premises for surveyor assessment."
        )
        out.append(
            make_example(
                user_text=u_txt,
                already_captured={},
                still_missing=FIELD_KEYS_ALL,
                lang="en-IN",
                output_dict={
                    "intent": "claim_intake",
                    "insurance_sector": "property",
                    "detected_emotion": "anxious_roadside",
                    "empathy_cue": "Property flood/fire damage — prioritizing electrical/premises safety first",
                    "safety_check_status": "urgent_safety_inquiry",
                    "inferred_cause": cause,
                    "drivability_assessment": "unknown",
                    "plausibility_note": "Consistent property damage report with hazard safety guidance",
                    "thought_process": "This is a Property Insurance claim. I should advise premises safety (power/fire hazard) and capture policy, address, date, and property damage.",
                    "extracted_fields": {
                        "policy_reference": pol,
                        "vehicle_type": "Commercial / Residential Property",
                        "incident_location": loc,
                        "incident_date": dt,
                        "damage_description": norm_ev,
                    },
                    "reply_text": strip_tags(speech),
                    "speech_text": speech,
                    "speech_rate": 0.95,
                    "speech_pitch": 0.98,
                },
            )
        )

    # 3. Crop / Agricultural Insurance (PMFBY)
    crop_cases = [
        ("unseasonal hailstorm flattened 4 acres of standing wheat crop", "Hailstorm lodging and flattening of 4-acre wheat crop", "Unseasonal hailstorm"),
        ("heavy flood water submerged our paddy field for 3 days", "Inundation damage to standing paddy crop", "Flood inundation"),
        ("severe bollworm pest attack damaged our cotton crop", "Pest infestation damage across standing cotton crop", "Pest attack"),
    ]
    crop_policies = ["PMFBY-2026-KA-4419", "PMFBY-MH-88301", "KISAN-CROP-66201"]
    crop_locs = ["Mandya District, Karnataka", "Nashik, Maharashtra", "Guntur, Andhra Pradesh", "Karnal, Haryana"]

    for _ in range(85):
        pol = rng.choice(crop_policies)
        loc = rng.choice(crop_locs)
        raw_c, norm_c, cause = rng.choice(crop_cases)
        dt = rng.choice(["Yesterday", "16th November", "Two Days Ago"])
        u_txt = f"My crop insurance ID is {pol} in {loc}, {dt.lower()} {raw_c}"
        speech = (
            f"<sigh> I am truly sorry to hear about the loss to your harvest in {loc} <pauses> <slow> I know how much hard work goes into every season. "
            f"I have registered your PMFBY crop policy {pol}, location ({loc}), date ({dt}), and crop damage ({norm_c}) within the 72-hour intimation window. "
            f"Please upload field photos in the next step so we can schedule the agricultural loss inspection."
        )
        out.append(
            make_example(
                user_text=u_txt,
                already_captured={},
                still_missing=FIELD_KEYS_ALL,
                lang="en-IN",
                output_dict={
                    "intent": "claim_intake",
                    "insurance_sector": "crop",
                    "detected_emotion": "anxious_roadside",
                    "empathy_cue": "Empathy for farmer's harvest loss & timely 72-hour PMFBY intimation reassurance",
                    "safety_check_status": "routine",
                    "inferred_cause": cause,
                    "drivability_assessment": "unknown",
                    "plausibility_note": "Valid agricultural weather/pest peril under PMFBY guidelines",
                    "thought_process": "This is an Agricultural / Crop Insurance claim. I should empathetically acknowledge the farmer's crop loss and record the PMFBY ID, district, date, and crop damage.",
                    "extracted_fields": {
                        "policy_reference": pol,
                        "vehicle_type": "Agricultural Standing Crop (PMFBY)",
                        "incident_location": loc,
                        "incident_date": dt,
                        "damage_description": norm_c,
                    },
                    "reply_text": strip_tags(speech),
                    "speech_text": speech,
                    "speech_rate": 0.95,
                    "speech_pitch": 0.98,
                },
            )
        )

    # 4. Travel Insurance (Baggage Loss / Flight Disruption)
    travel_cases = [
        ("my checked-in suitcase was lost by the airline and PIR report was filed", "Checked-in baggage lost in transit (Airline PIR filed)", "Airline baggage mishandling"),
        ("our connecting international flight was delayed by 14 hours due to severe weather", "14-hour international flight delay disruption", "Severe weather flight delay"),
    ]
    travel_policies = ["TRV-INTL-90211", "TATA-TRV-44180", "ICICI-TRV-31092"]
    travel_locs = ["Terminal 2, Mumbai Airport", "Kempegowda International Airport, Bengaluru", "Dubai International Airport", "IGI Airport, Delhi"]

    for _ in range(75):
        pol = rng.choice(travel_policies)
        loc = rng.choice(travel_locs)
        raw_t, norm_t, cause = rng.choice(travel_cases)
        dt = rng.choice(["Today Morning", "Yesterday Evening", "19th November"])
        u_txt = f"Travel policy {pol}, at {loc} {dt.lower()}, {raw_t}"
        speech = (
            f"<slow> Travelling disruptions at {loc} can be exhausting <pauses> I'll help you get this sorted quickly. "
            f"I've recorded your travel policy {pol}, airport location ({loc}), date ({dt}), and incident ({norm_t}). "
            f"Please keep your boarding pass and airline PIR/delay certificate ready to upload in Step 2."
        )
        out.append(
            make_example(
                user_text=u_txt,
                already_captured={},
                still_missing=FIELD_KEYS_ALL,
                lang="en-IN",
                output_dict={
                    "intent": "claim_intake",
                    "insurance_sector": "travel",
                    "detected_emotion": "calm_informative",
                    "empathy_cue": "Reassuring traveler after transit disruption & guiding on PIR/boarding pass proof",
                    "safety_check_status": "routine",
                    "inferred_cause": cause,
                    "drivability_assessment": "unknown",
                    "plausibility_note": "Standard travel insurance peril requiring airline confirmation document",
                    "thought_process": "This is a Travel Insurance claim. I should record the travel policy, airport location, date, and baggage/flight incident while guiding them on required documents.",
                    "extracted_fields": {
                        "policy_reference": pol,
                        "vehicle_type": "Travel & Transit Policy",
                        "incident_location": loc,
                        "incident_date": dt,
                        "damage_description": norm_t,
                    },
                    "reply_text": strip_tags(speech),
                    "speech_text": speech,
                    "speech_rate": 0.98,
                    "speech_pitch": 1.0,
                },
            )
        )

    return out


def generate_datasets(seed: int = 2026) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Focused Motor-Only (2W Bike & 4W Car) + General Greeting dataset across core Indian languages.
    Avoids multi-sector dilution so QLoRA fine-tuning achieves high accuracy on real motor claims.
    """
    rng = random.Random(seed)
    greetings = build_greeting_examples() * 8  # Oversample greetings so greetings never trigger accident scripts
    motor = build_motor_insurance_examples(rng)

    all_records = greetings + motor
    rng.shuffle(all_records)

    split_idx = int(len(all_records) * 0.90)
    return all_records[:split_idx], all_records[split_idx:]


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    train_records, val_records = generate_datasets()
    train_path = out_dir / "claimsathi_multidomain_train.jsonl"
    val_path = out_dir / "claimsathi_multidomain_val.jsonl"

    with train_path.open("w", encoding="utf-8") as f:
        for row in train_records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with val_path.open("w", encoding="utf-8") as f:
        for row in val_records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    sector_counts: Dict[str, int] = {}
    for r in train_records + val_records:
        sec = r.get("sector", "unknown")
        sector_counts[sec] = sector_counts.get(sec, 0) + 1

    print(f"Generated {len(train_records)} train and {len(val_records)} val examples.")
    print(f"Sector distribution: {sector_counts}")
    print(f"Train file: {train_path}")
    print(f"Val file:   {val_path}")


if __name__ == "__main__":
    main()
