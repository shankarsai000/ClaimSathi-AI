# ClaimSathi AI — 1-Page Solution Pitch
**The Great Indian Internship Challenge — Project Submission**  
**Repository:** [https://github.com/shankarsai000/ClaimSathi-AI](https://github.com/shankarsai000/ClaimSathi-AI)

---

## 1. The Problem: Why Motor Insurance Claims Fail in India
Over **75% of Indian policyholders** prefer speaking in their native language or code-mixed dialects (Kannada, Telugu, Hindi, Tamil, Hinglish/Tenglish/Kanglish), yet motor insurance First Notice of Loss (FNOL) forms require complex English inputs right after a stressful road accident. Meanwhile, Indian motor insurers lose **₹15,000+ Crore annually** to fraudulent claims—amplified today by generative AI image editing (C2PA/SynthID deepfakes) and recycled WhatsApp accident photos.

---

## 2. Our Solution: ClaimSathi AI
**ClaimSathi AI** is an **IRDAI-aligned, Voice-First Multilingual Motor Insurance Claim Preparation & Cryptographic Evidence Screening Platform** powered by **Gnani AI Speech APIs (`Prisma v3.0 STT` + `Timbre v2.5 TTS`)**.

A stressed policyholder simply speaks naturally in **Kannada, Telugu, Hindi, Tamil, or English**. ClaimSathi AI listens, locks onto their language, asks smart voice follow-ups for any missing details, translates and normalizes all 5 core insurer fields into **100% clean English for the insurance company**, screens uploaded/live-camera accident photos through a **5-Stage Fraud & AI-Provenance Engine**, and generates a **9-Section Official Claim Dossier** downloadable in both **Official English PDF** (for the insurer) and the **Customer's Preferred Indian Language** (`ಕನ್ನಡ`, `తెలుగు`, `हिन्दी`, `தமிழ்`, `English`).

---

## 3. Core Technical Innovations
1. **Gnani Prisma v3.0 STT + Timbre v2.5 TTS with Sticky First-Turn Language Lock:**
   - Default `indic-auto` mode detects the user's language on their very first spoken sentence and locks the entire voice/text conversation, UI prompts, and Timbre TTS audio responses into that language.
2. **Strict Per-Field Type Validation, Smart Routing & 100% English Insurer Normalization:**
   - Phonetic Indic parser converts spoken vehicle/policy numbers (e.g., `"ಕೆ ಎ ಥರ್ಟೀ ಫೋರ್ ಟು ಟ್ವೆಂಟಿ ತ್ರೀ"` -> `KA-34-2-23`, `"టి ఎస్ సున్నా తొమ్మిది ఇ ఎ తొమ్మిది తొమ్మిది ఒకటి రెండు"` -> `TS-09-EA-9912`), transliterates Indic locations (`"पुणे"` -> `Pune`), translates damage descriptions into standardized English, rejects irrelevant questions, and automatically routes out-of-order answers to the right field.
3. **5-Stage Cryptographic Evidence & AI-Provenance Engine:**
   - **Stage 1:** Binary Magic-Byte Verification (`JPEG`, `PNG`, `MP4`, `WEBM`).
   - **Stage 2 & 3:** **C2PA Content Credentials** (`c2pa` JUMBF boxes) & **Google SynthID** screening to flag AI-generated/edited damage.
   - **Stage 4 & 5:** **SHA-256 Exact Hash** + **64-bit DCT Perceptual Hash (pHash)** with Hamming-distance threshold ($\le 10$) to catch resized or WhatsApp-recompressed duplicate photos across claims, paired with **Server-Tokenized Live WebRTC Camera Capture**.
4. **Two-Layer Insurer Interoperability & Multilingual Dossier:**
   - Produces **Layer 1 Canonical Claim Schema JSON**, **Binary PDF**, **Localized HTML/Print Report** (`kn`, `te`, `hi`, `ta`, `en`), and submits via a **Layer 2 Mock Insurer Gateway** (`DEMO_INSURER_A`, `BHARAT_GENERAL_MOCK`).

---

## 4. Architecture & Tech Stack
- **Voice AI:** Gnani Vachana Platform — **Prisma v3.0 STT** (`https://api.vachana.ai/stt/v3`) & **Timbre v2.5 TTS** (`https://api.vachana.ai/api/v1/tts/inference`).
- **Backend:** Python, FastAPI, Pydantic v2, HTTPX, Pillow (64-bit DCT pHash), 25-test Pytest suite (`100% passing`).
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, 16-bit PCM WAV Web Audio Recorder, Full 5-Language App UI (`i18n.tsx`).
- **Database & Storage:** Supabase Cloud PostgreSQL (`12-table schema`) + Supabase Storage (`claimsathi-evidence` bucket) + Local SQLite Vault.
