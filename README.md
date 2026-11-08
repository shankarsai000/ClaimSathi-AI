# ClaimSathi AI — Conversational Motor Insurance Claims Platform

> **IRDAI-Aligned, Multilingual Voice-First Motor Insurance Claim Preparation Platform for India.**  
> Powered by **Gnani AI Speech APIs** (Prisma STT + Timbre TTS), **Multi-Stage Cryptographic Evidence Screening** (C2PA, SynthID, SHA-256, 64-bit DCT pHash), **Supabase PostgreSQL & Storage**, and **Dynamic Multi-Language Dossier Generation**.

---

## 🌟 Executive Summary & Capabilities

ClaimSathi AI implements the full **7-Phase / 9-Step Specification** (`_ClaimSathi AI product flow.pdf`):

1. **Customer Account & Claims Vault**:
   - Secure customer authentication via **Email, Phone Number, or Customer ID** with **Password or 6-digit OTP**.
   - Cloud-native **Supabase PostgreSQL** + fallback local SQLite storage with IRDAI-compliant user consents.
2. **Multilingual Conversational AI Intake**:
   - **Auto-Detect (`indic-auto`) Mode**: Detects Telugu, Kannada, Hindi, Tamil, and English in the very first turn and locks on to the customer's language.
   - **100% English Insurer Normalization**: Spoken Kannada/Telugu damage, location, and vehicle numbers are phonetically parsed and translated into clean English for insurance underwriters.
   - **Strict Per-Field Type Validation & Out-of-Order Routing**: Rejects conversational questions (e.g. `"ಸಿ ಎಂ ಎಂ ಅಂದರೆ ಏನು?"`) and automatically re-routes misplaced answers (e.g. policy number given for location) to the correct field.
3. **5-Stage Evidence Integrity & AI Provenance Screening**:
   - **Stage 1: File Format & Magic Bytes** (JPEG, PNG, HEIC, MP4, MOV).
   - **Stage 2: C2PA Content Credentials** (Detects Adobe Firefly, DALL-E, synthetic edits).
   - **Stage 3: Google SynthID Digital Watermark** (Detects Imagen-generated synthetic damage).
   - **Stage 4: SHA-256 Exact Duplicate Screening**.
   - **Stage 5: 64-Bit DCT Perceptual Hashing (pHash)** (Flags WhatsApp-compressed, resized, or re-saved duplicate fraud across claims).
   - **Guided Live Camera Capture** for tamper-proof odometer, VIN plate, and 360° accident angles.
4. **9-Section Insurer Dossier & Localized Downloads**:
   - Compiles a complete 9-section insurance dossier with cryptographic evidence hashes.
   - Exports **Official English PDF** (for underwriters) and **Canonical JSON**.
   - **Multi-Language Download / Print**: Customers can read and print their dossier in **English, ಕನ್ನಡ, తెలుగు, हिन्दी, or தமிழ்**.
5. **Global App Language Switcher & Settings Modal**:
   - Real-time UI language switcher across all headers, menus, and forms.
   - Customer Profile & Policy details modal.

---

## 👥 Seeded Test Customer Accounts

The following accounts are pre-seeded in the database (`users`, `user_consents`, `claims`) and available via **One-Click Auto-Fill** on the login screen:

| Customer Name | Email / Identifier | Password | City / Vehicle | Seeded Claim ID |
| :--- | :--- | :--- | :--- | :--- |
| **Rahul Sharma** | `rahul.sharma@claimsathi.in` | `Rahul@2026` | Bengaluru (Car / Bike) | `CS-2026-000085` |
| **Sai Shankar Reddy** | `saishankar.reddy@claimsathi.in` | `Shankar@2026` | Hyderabad (Car) | `CS-2026-000092` |
| **Ananya Lakshmi Iyer** | `ananya.iyer@claimsathi.in` | `Ananya@2026` | Chennai (Two-Wheeler) | `CS-2026-000104` |
| **Vikramaditya Deshmukh** | `vikram.deshmukh@claimsathi.in` | `Vikram@2026` | Pune (Car / SUV) | `CS-2026-000118` |

> *Full details and policy numbers are available in [`USER_ACCOUNTS.md`](./USER_ACCOUNTS.md).*

---

## 📸 Real Accident Evidence Sample Sets

A complete test suite of real accident photographs and synthetic edge cases is included in [`test_evidence_samples/`](./test_evidence_samples/):

- **Real Car Accidents**: Front bumper crashes, side impact dents, rear tailgate collisions.
- **Real Bike Accidents**: Handlebar & tank dent, exhaust scrape, front fork impacts.
- **Cryptographic Fraud Edge Cases**:
  - `synthetic_c2pa_ai_generated.jpg` (Triggers C2PA synthetic warning)
  - `synthid_watermarked_accident.jpg` (Triggers SynthID synthetic alert)
  - `exact_duplicate_test.jpg` (Triggers SHA-256 duplicate alert)
  - `whatsapp_duplicate_test.jpg` (Triggers 64-bit DCT pHash duplicate alert)

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.11+**
- **Node.js 18+** & npm

### 2. Backend Server (FastAPI on Port 8080)
```powershell
cd "d:\ClaimSathi AI\backend"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```
- API Docs: `http://127.0.0.1:8080/docs`
- Health Endpoint: `http://127.0.0.1:8080/api/health`

### 3. Frontend Dev Server (Vite on Port 5173)
```powershell
cd "d:\ClaimSathi AI\frontend"
npm run dev
```
- Web Application: `http://localhost:5173`

---

## 🧪 Automated Test Suite (100% Passing)

Run the full automated test suite covering all 7 phases, voice intake, edge-case validation, evidence hashing, and insurer gateway:

```powershell
cd "d:\ClaimSathi AI\backend"
python -m pytest -v
```

Expected output:
```text
====================== 25 passed in 13.64s =======================
```

---

## 🛡️ Architecture & Security Integrity
- **Zero API Key Leakage**: Gnani Vachana credentials and Supabase database connection strings are kept strictly in backend `.env`.
- **Sandbox Safe**: All submitted claims generate verifiable mock insurer acknowledgments (`ACK-BajajAllianz-...`) with no accidental live carrier submissions.
