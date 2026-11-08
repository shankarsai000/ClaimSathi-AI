# ClaimSathi AI — 1-Page Solution Pitch
**The Great Indian Internship Challenge — Project Submission**  
**Repository:** [https://github.com/shankarsai000/ClaimSathi-AI](https://github.com/shankarsai000/ClaimSathi-AI)

---

## 1. The Problem: Why Motor Insurance Claims Fail in India
Over **75% of Indian policyholders** prefer speaking in their native language or code-mixed dialects (Kannada, Telugu, Hindi, Tamil, Hinglish/Tenglish/Kanglish), yet motor insurance First Notice of Loss (FNOL) forms require complex English inputs right after a stressful road accident. Meanwhile, Indian motor insurers face rising fraud from recycled WhatsApp accident photos and AI-edited damage images.

---

## 2. Our Solution: ClaimSathi AI
**ClaimSathi AI** is an **IRDAI-aligned, Voice-First Multilingual Motor Insurance Claim Preparation & Evidence Screening Platform** powered by **Gnani AI Speech APIs (`Prisma v3.0 STT` + `Timbre v2.5 TTS`)**.

A policyholder speaks naturally in **Kannada, Telugu, Hindi, Tamil, or English**. ClaimSathi AI detects and locks onto their language, asks voice follow-ups for missing details, normalizes all 5 core insurer fields into **100% clean English for the insurance company**, screens accident photos through a **5-Stage Provenance & Duplicate Engine**, and generates a **9-Section Claim Dossier** downloadable in both **Official English PDF** (for insurers) and the **Customer's Preferred Language** (`ಕನ್ನಡ`, `తెలుగు`, `हिन्दी`, `தமிழ்`, `English`).

---

## 3. Core Technical Innovations
1. **Gnani Prisma v3.0 STT + Timbre v2.5 TTS with Sticky First-Turn Language Lock:**
   - Default `indic-auto` mode detects the user's language on the first turn and locks the entire conversation and Timbre TTS responses into that language.
2. **Strict Per-Field Type Validation, Smart Routing & 100% English Insurer Normalization:**
   - Converts spoken Indic vehicle/policy numbers (`"ಕೆ ಎ ಥರ್ಟೀ ಫೋರ್ ಟು ಟ್ವೆಂಟಿ ತ್ರೀ"` -> `KA-34-2-23`), transliterates Indic locations (`"पुणे"` -> `Pune`), translates damage into standardized English, rejects irrelevant questions, and routes out-of-order answers to the correct field.
3. **5-Stage Evidence Provenance & Duplicate Screening + Live Camera Capture:**
   - Screens binary magic bytes, **C2PA Content Credentials**, **Google SynthID** markers, **SHA-256 exact duplicates**, and **64-bit DCT Perceptual Hash (pHash)** (Hamming distance $\le 10$ for WhatsApp/resized duplicates), paired with **Server-Tokenized Live WebRTC Camera Capture**.
4. **Two-Layer Insurer Interoperability & Multilingual Dossier:**
   - Exports **Layer 1 Canonical Claim Schema JSON**, **Binary PDF**, and **Localized Reports** (`kn`, `te`, `hi`, `ta`, `en`), plus a **Layer 2 Mock Insurer Gateway**.

---

## 4. Transparent MVP Limitations & Honest Engineering Scope
We explicitly disclose two real-world limitations of this MVP so there is zero overclaiming:

1. **Deepfake & AI-Image Detection Is Advisory (Not 100% Proof of Authenticity):**
   - Our screening checks for **C2PA Content Credentials**, **SynthID watermarks**, and **SHA-256 / 64-bit pHash duplicates**. However, if a sophisticated deepfake or AI-edited image has had its metadata stripped or comes from an unwatermarked open-source model, software screening alone **cannot guarantee 100% deepfake detection**. Conversely, standard phone photos without C2PA metadata are marked **`Inconclusive (Manual Surveyor Review Recommended)`**—never falsely certified as "100% authentic." We mitigate this risk via **Guided Live Camera Capture** with server-issued session tokens, but final physical/surveyor verification remains essential.
2. **No Real Commercial Insurance Company Tie-Up Yet (Simulated Gateway Only):**
   - ClaimSathi AI does **not** have live production API integrations or commercial tie-ups with real insurance companies yet. All insurer submissions (`DEMO_INSURER_A`, `BHARAT_GENERAL_MOCK`) run through a **Simulated Layer-2 Insurer Adapter Gateway** and carry a prominent **`DEMO ONLY — Not a Real Insurer Submission`** disclaimer.

---

## 5. Tech Stack
- **Voice AI:** Gnani Vachana (`Prisma v3.0 STT` & `Timbre v2.5 TTS`) | **Backend:** FastAPI, Pydantic v2, Pillow (pHash), Pytest (`25/25 passing`) | **Frontend:** React 18, TypeScript, Tailwind CSS | **Database:** Supabase Cloud PostgreSQL + Storage + SQLite.
