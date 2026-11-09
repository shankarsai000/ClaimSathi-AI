# ClaimSathi AI — 1-Page Solution Pitch
**The Great Indian Internship Challenge — Project Submission**  
**Repository:** [https://github.com/shankarsai000/ClaimSathi-AI](https://github.com/shankarsai000/ClaimSathi-AI)

---

## 1. The Problem: Why Motor Insurance Claims Fail in India
Over **75% of Indian policyholders** prefer speaking in their native language or code-mixed dialects (Kannada, Telugu, Hindi, Tamil, Hinglish/Tenglish/Kanglish), yet motor insurance First Notice of Loss (FNOL) forms require complex English inputs right after a stressful road accident. Meanwhile, Indian motor insurers face rising fraud from recycled WhatsApp accident photos and AI-edited damage images.

---

## 2. Our Solution: ClaimSathi AI Powered by Gnani.ai Speech APIs
**ClaimSathi AI** is an **IRDAI-aligned, Voice-First Multilingual Motor Insurance Claim Preparation & Evidence Screening Platform** powered natively by **Gnani AI's Vachana Speech Platform**:

### 🎙️ Exactly How Gnani AI APIs Are Used in ClaimSathi AI:
1. **Gnani Prisma v3.0 Speech-to-Text (STT) (`https://api.vachana.ai/stt/v3`):**
   - **How it works:** Ingests live 16-bit 16kHz PCM WAV audio streams directly from the claimant's browser microphone.
   - **Auto-Language Identification (`indic-auto`):** Prisma v3.0 analyzes the acoustic stream and automatically identifies the spoken Indian language (Kannada, Telugu, Hindi, Tamil, Marathi, Bengali, Gujarati, Malayalam, Punjabi, Urdu, or English).
   - **Transcription & Normalization:** Employs Prisma v3.0 `transcribe` mode with Inverse Text Normalization (ITN) to accurately capture vehicle registrations, dates, and accident descriptions across regional scripts and code-mixed speech.
2. **Gnani Timbre v2.5 Text-to-Speech (TTS) (`https://api.vachana.ai/api/v1/tts/inference`):**
   - **How it works:** Synthesizes clear, low-latency 24kHz WAV audio responses for interactive conversational follow-ups.
   - **Sticky Dialect Lock:** When an incident field is missing (e.g. incident date or damage detail), the backend invokes Timbre TTS in the claimant's detected native language (`te-IN`, `kn-IN`, `hi-IN`, `ta-IN`) using verified regional neural voices (e.g. `Nalini`), giving users an empathetic, natural conversational experience.

---

## 3. Core Technical Innovations
1. **Strict Per-Field Type Validation, Smart Routing & 100% English Insurer Normalization:**
   - Converts spoken Indic vehicle/policy numbers (`"ಕೆ ಎ ಥರ್ಟೀ ಫೋರ್ ಟು ಟ್ವೆಂಟಿ ತ್ರೀ"` -> `KA-34-2-23`), transliterates Indic locations (`"पुणे"` -> `Pune`), translates damage into standardized English, rejects irrelevant questions, and routes out-of-order answers to the correct field.
2. **5-Stage Evidence Provenance & Duplicate Screening + Live Camera Capture:**
   - Screens binary magic bytes, **C2PA Content Credentials**, **Google SynthID** markers, **SHA-256 exact duplicates**, and **64-bit DCT Perceptual Hash (pHash)** (Hamming distance $\le 10$ for WhatsApp/resized duplicates), paired with **Server-Tokenized Live WebRTC Camera Capture**.
3. **Two-Layer Insurer Interoperability & Multilingual Dossier:**
   - Exports **Layer 1 Canonical Claim Schema JSON**, **Binary PDF**, and **Localized Reports** (`kn`, `te`, `hi`, `ta`, `en`), plus a **Layer 2 Mock Insurer Gateway**.

---

## 4. Transparent MVP Limitations & Honest Engineering Scope
We explicitly disclose two real-world limitations of this MVP so there is zero overclaiming:

1. **Deepfake & AI-Image Detection Is Advisory (Not 100% Proof of Authenticity):**
   - Our screening checks for **C2PA Content Credentials**, **SynthID watermarks**, and **SHA-256 / 64-bit pHash duplicates**. However, if a sophisticated deepfake or AI-edited image has had its metadata stripped or comes from an unwatermarked open-source model, software screening alone **cannot guarantee 100% deepfake detection**. Unverified photos are marked **`Inconclusive (Manual Surveyor Review Recommended)`**.
2. **No Real Commercial Insurance Company Tie-Up Yet (Simulated Gateway Only):**
   - ClaimSathi AI does **not** have live production API integrations with real insurance companies yet. Submissions run through a **Simulated Layer-2 Insurer Adapter Gateway** tagged with `DEMO ONLY — Not a Real Insurer Submission`.

---

## 5. Tech Stack
- **Voice AI:** Gnani Vachana (`Prisma v3.0 STT` & `Timbre v2.5 TTS`) | **Backend:** FastAPI, Pydantic v2, Pillow (pHash), Pytest (`25/25 passing`) | **Frontend:** React 18, TypeScript, Tailwind CSS | **Database:** Supabase Cloud PostgreSQL + Storage + SQLite.
