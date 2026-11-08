# 🎬 ClaimSathi AI — 2.5-Minute Demo Video Script & UI Choreography
**Target Duration:** 2 minutes 30 seconds – 2 minutes 50 seconds  
**Live App URL to Record:** `http://localhost:5173/login`

---

## 🛠️ Pre-Recording Setup (30 Seconds Before You Hit Record)
1. Open Chrome/Edge to **`http://localhost:5173/login`** (if already logged in, click **Sign Out** in the top right so you start on the Login screen).
2. Keep your folder **`d:\ClaimSathi AI\test_evidence_samples\real_car_accidents\`** ready in File Explorer so you can quickly pick photos during Step 2.
3. Make sure your system audio + microphone are enabled in your screen recorder (OBS / Loom / Windows `Win + G`).

---

## Scene 1: Problem Hook, Login & Multilingual App UI (0:00 – 0:30)

| 🖥️ What to Show / Click on the UI | 🎙️ What to Say (Voiceover Script) |
| :--- | :--- |
| **1.** Start on **`http://localhost:5173/login`**. Hover over the 4 Demo Test Account cards (*Rahul Sharma*, *Sai Shankar Reddy*, *Ananya Lakshmi Iyer*, *Vikramaditya Deshmukh*).<br>**2.** Click **Rahul Sharma** (or **Sai Shankar Reddy**) to auto-fill credentials, then click **Sign In to Customer Claims Vault**.<br>**3.** On the **Customer Claims Vault (`/dashboard`)**, click the **Language Selector (`🌐 English`)** in the top navbar and switch to **`ಕನ್ನಡ`** or **`తెలుగు`**, then open **Settings & Profile** for 2 seconds and switch back to **`English`**. | *"Hi everyone! Today we are presenting **ClaimSathi AI**—a voice-first, multilingual motor insurance claim preparation and evidence-screening platform built for India, powered by **Gnani AI Speech APIs**.*<br><br>*Over 75% of Indian policyholders prefer speaking in their regional language, yet filing an insurance claim after a road accident still requires complex English forms. We start at our **Customer Claims Vault**, backed by **Supabase Cloud PostgreSQL**. Policyholders can switch the entire app UI into **Kannada, Telugu, Hindi, Tamil, or English** with one click so they can read comfortably in their own language."* |

---

## Scene 2: Gnani Prisma v3.0 Voice Intake, Auto-Language Lock & Smart Routing (0:30 – 1:25)

| 🖥️ What to Show / Click on the UI | 🎙️ What to Say (Voiceover Script) |
| :--- | :--- |
| **1.** Click **New Claim Wizard (`/new-claim`)**.<br>**2.** Point to the **Voice Language dropdown** set to **`✨ Auto-Detect (All Indian Languages)`** and the **`GNANI AI [LIVE]`** badge.<br>**3.** Click **🎙️ Speak Your Claim** and speak in **Telugu** or **Kannada** *(or click the **"Telugu Voice Scenario (Missing Date Follow-up)"** button)*:<br>   - **If speaking Telugu on Mic:** *"నా పాలసీ నంబర్ ఎం ఓ టీ 2024 టీ ఎస్ 98765. హైదరాబాద్ మాదాపూర్ లో నా కారుకి యాక్సిడెంట్ అయింది. ముందు బంపర్ మరియు హెడ్ లైట్ పగిలిపోయింది."*<br>   - **If speaking Kannada on Mic:** *"ನನ್ನ ಕಾರು ಬೆಂಗಳೂರು ಎಂ ಜಿ ರೋಡ್ ನಲ್ಲಿ ಅಪಘಾತವಾಗಿದೆ, ಮುಂದಿನ ಬಂಪರ್ ಮತ್ತು ಹೆಡ್ ಲೈಟ್ ಜಖಂಗೊಂಡಿದೆ."*<br>**4.** Point to the right-hand panel (**Extracted Claim Fields**): show how all captured fields are automatically normalized into **clean English** (`MOT-2024-TS-98765`, `Car`, `Madhapur, Hyderabad`, `Front bumper, headlight damaged`) while the AI asks a follow-up for the missing **Incident Date** in your spoken language via **Gnani Timbre v2.5 TTS**.<br>**5.** *(Optional Wild-Case Demo)* Type or speak a question or out-of-order answer, or answer the follow-up (`"నిన్న సాయంత్రం"` / `"ನಿನ್ನೆ ಸಂಜೆ"` / `"Yesterday evening"`) to reach **`5 of 5 Captured`**. | *"In Step 1, our **Gnani Prisma v3.0** Speech-to-Text engine runs in **Auto-Detect** mode. Even if the customer doesn't select a language, the system detects the language of their very first spoken sentence—here in Telugu/Kannada—and locks the entire conversation and **Gnani Timbre v2.5 Text-to-Speech** voice responses into that language.*<br><br>*Notice the right panel: while the conversation happens in Telugu or Kannada, every extracted claim field—Policy or Vehicle Number, Vehicle Type, Location, Date, and Damage Description—is **automatically normalized into 100% clean English** because insurance underwriters require English records.*<br><br>*Our strict field validator also rejects irrelevant questions and smartly routes out-of-order answers to the right field. Now that all 5 core fields are captured, let's proceed to Step 2."* |

---

## Scene 3: 5-Stage Evidence Integrity & AI Provenance Screening (1:25 – 2:05)

| 🖥️ What to Show / Click on the UI | 🎙️ What to Say (Voiceover Script) |
| :--- | :--- |
| **1.** Click **Continue to Step 2: Upload & Screen Evidence**.<br>**2.** Click **Upload Photos / Videos** and select from `d:\ClaimSathi AI\test_evidence_samples\real_car_accidents\`:<br>   - First upload **`car_accident_01_original.jpg`** -> point to the `SHA-256`, `64-bit pHash`, and `Unique` badge.<br>   - Next upload **`car_accident_01_TEST6_resized_whatsapp_duplicate.jpg`** -> point to the **Amber Duplicate Warning (`Resized / Recompressed Near-Duplicate via 64-bit DCT pHash`)**.<br>   - Next upload **`car_accident_01_TEST7A_c2pa_ai_edited.jpg`** -> point to the **Red C2PA AI-Generated / Edited Warning**.<br>**3.** Click **Start Guided Live Camera Capture** briefly to show the server-issued session token (`CAP-...`) and camera checklist. | *"In Step 2, ClaimSathi AI runs a **5-Stage Evidence Integrity and AI-Provenance Engine**.*<br><br>*First, we upload a real car accident photo—it computes a **SHA-256 cryptographic hash** and a **64-bit DCT Perceptual Hash (pHash)**.*<br><br>*Second, when we upload a resized, WhatsApp-compressed copy of that photo, our **64-bit pHash** catches the near-duplicate even though the file bytes changed!*<br><br>*Third, when we upload an AI-manipulated photo, our **C2PA Content Credentials and Google SynthID** scanner flags the synthetic provenance marker. We also support **Server-Tokenized Guided Live Camera Capture** for tamper-resistant inspection."* |

---

## Scene 4: 9-Section Dossier, Multi-Language Report, Honest Limitations & Insurer Gateway (2:05 – 2:45)

| 🖥️ What to Show / Click on the UI | 🎙️ What to Say (Voiceover Script) |
| :--- | :--- |
| **1.** Click **Proceed to Step 3: Review & Generate Dossier**, check the **Customer Confirmation checkbox**, and click **Confirm & Generate 9-Section Claim Dossier**.<br>**2.** On the **Claim Dossier page (`/claims/CS-2026-...`)**, scroll briefly through the **9-Section Official Dossier**.<br>**3.** At the top right, change **Report Language** to **`ಕನ್ನಡ (Kannada)`** or **`తెలుగు (Telugu)`** and click **Print / Download in Preferred Language** (opens the localized report in a new tab), then show the **Official English PDF (For Insurer)** button.<br>**4.** Click the **Simulated Insurer Gateway** tab (or button) and click **Submit to Insurer Gateway** to show the 6-step pipeline and simulated insurer reference (`CLM-SIM-...`). | *"Finally, in Step 3, ClaimSathi AI compiles a complete **9-Section Motor Insurance Claim Dossier**.*<br><br>*We provide an **Official English PDF** and **Layer-1 Canonical JSON** for the insurance company, while allowing the policyholder to **download and print the full 9-section report in their preferred language—Kannada, Telugu, Hindi, Tamil, or English**.*<br><br>*Before we close, we want to highlight two honest engineering limitations of our MVP:*<br>*First, **Deepfake Detection is Advisory**: while we detect C2PA, SynthID, and pHash duplicates, unwatermarked or metadata-stripped deepfakes cannot be 100% ruled out by software alone, so unverified uploads are honestly labeled **Inconclusive — Manual Surveyor Review Recommended**.*<br>*Second, **Simulated Insurer Tie-Up**: since we do not have live commercial insurance company tie-ups yet, our **Layer-2 Mock Insurer Gateway** simulates carrier submission clearly labeled as Demo Only.*<br><br>*Thank you for watching ClaimSathi AI!"* |
