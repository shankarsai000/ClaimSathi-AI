# ClaimSathi AI – Voice-First Insurance Claim Intake

> **Voice-first motor insurance claim-intake application designed for Indian users who speak naturally in Hinglish and code-mixed Indian languages.**
> Powered by **Gnani AI Speech APIs** (Gnani Prisma for Speech-to-Text and Gnani Timbre for Text-to-Speech).

---

## Architecture Overview (Phase 2)

- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS.
  - Direct 16-bit PCM WAV microphone recorder (Web Audio API, 16kHz mono).
  - Audio file upload support (`.wav`, `.mp3`, `.ogg`, `.flac`, `.aac`, `.m4a`).
  - 30-second live countdown timer and volume visualization.
  - Real-time TTS audio playback using HTML5 Audio.
  - Clear provider indicators (`GNANI AI [LIVE]` vs `DEMO / SIMULATED`).
  - Recoverable error handling with immediate fallback to Demo Mode without reload.
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, HTTPX.
  - **Prisma STT**: Configurable for Prisma v2.5 (`gnani-prisma-v2.5` / `prisma-v2.5`) and Prisma v3.0 (`prisma-v3.0`).
  - **Timbre TTS**: Timbre v2.5 with verified voice (`Nalini` for `hi-IN`).
  - 30-second maximum duration validation and format inspection.
  - Safe error handling: 401 unauthorized, 402 insufficient credits, 429 rate limits, 502 upstream errors.
  - No secret API key leakage in logs or responses.
- **Storage**: Async SQLite (`aiosqlite`) storing claims and activity timeline.
- **Safety**: All submitted tickets are local demo tickets (`DEMO-XXXXXXXX`). No real insurance claim is filed.

---

## 1. Secure Configuration

Configuration is loaded **exclusively on the FastAPI backend** from environment variables. Secrets are never exposed to the browser.

Create your backend `.env` from `.env.example`:

```bash
cd backend
copy .env.example .env    # Windows
# cp .env.example .env    # macOS / Linux
```

### Environment Variables (`backend/.env`):

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `GNANI_API_KEY_ID` | Your Gnani Vachana API Key | `vach_...` |
| `GNANI_STT_MODEL` | Speech-to-Text model | `prisma-v2.5` or `prisma-v3.0` |
| `GNANI_STT_LANGUAGE_CODE` | Default language code for STT | `hi-IN` |
| `GNANI_TTS_MODEL` | Text-to-Speech model | `timbre-v2.5` |
| `GNANI_TTS_LANGUAGE` | Default language for TTS | `hi-IN` |
| `GNANI_TTS_VOICE` | Verified voice name | `Nalini` |

> `.env` is gitignored. Never commit credentials to version control.

---

## 2. Quick Start & Startup Commands

### Step 1: Backend Server (Port 8000)

```powershell
cd "d:\ClaimSathi AI\backend"
.\venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

- API Base URL: `http://localhost:8000`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`

### Step 2: Frontend Dev Server (Port 5173)

```powershell
cd "d:\ClaimSathi AI\frontend"
npm run dev
```

- Web UI: `http://localhost:5173`
- Vite automatically proxies `/api` calls to `http://localhost:8000`.

---

## 3. Running Automated Tests

All automated unit and integration tests use **mocked HTTP responses** so that running tests **never consumes Gnani API credits**.

```powershell
cd "d:\ClaimSathi AI\backend"
.\venv\Scripts\activate
pytest -v
```

### Test Suite Coverage:
- `test_health_check`: Health check and configuration status.
- `test_create_claim_success`: Local claim ticket creation with `DEMO-` prefix.
- `test_create_claim_validation_error`: Input validation on required claim fields.
- `test_get_claim_not_found`: 404 handling on missing ticket IDs.
- `test_list_claims`: Listing tickets from SQLite.
- `test_create_and_retrieve_claim`: Full CRUD flow with activity timeline.
- `test_transcribe_prisma_v25_mocked`: Prisma v2.5 multipart request format and response parsing.
- `test_transcribe_prisma_v30_mocked`: Prisma v3.0 model and writing mode handling.
- `test_transcribe_enforces_30s_duration_limit`: Rejection of recordings exceeding 30.0 seconds.
- `test_transcribe_rejects_unsupported_format`: Guidance on unsupported formats like WebM.
- `test_transcribe_handles_401_unauthorized`: Clear actionable error on invalid credentials.
- `test_transcribe_handles_402_insufficient_credits`: Clean error handling for exhausted credits.
- `test_transcribe_demo_mode_returns_mock_without_external_call`: Explicit demo mode isolation.
- `test_speak_timbre_tts_mocked`: Timbre TTS request format (`audio_config`, `Nalini`, WAV output).
- `test_speak_failure_does_not_return_mock`: Verifies live TTS failure never silently returns mock audio.
- `test_speak_demo_mode_returns_wav`: Playable WAV tone for demo mode.
- `test_api_key_not_leaked_in_responses`: Guarantees secrets are never leaked in headers or JSON details.

---

## 4. API Endpoints

### Voice Endpoints (Phase 2)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/voice/transcribe` | Upload audio file (`audio_file`) for Gnani Prisma ASR (max 30s) |
| `POST` | `/api/voice/speak` | Synthesize speech (`text`, `language`, `voice`) via Gnani Timbre TTS |

### Claim & Health Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Health check and Gnani configuration status |
| `POST` | `/api/claims/` | Create a local demo claim ticket |
| `GET` | `/api/claims/` | List all demo claims |
| `GET` | `/api/claims/{id}` | Get ticket detail and activity timeline |
| `GET` | `/api/claims/stats` | Dashboard metrics |

---

## 5. Manual Verification Steps (Live Gnani APIs)

Follow these steps to manually test live speech recognition and synthesis when valid credentials are configured:

### Testing Speech Synthesis (Gnani Timbre TTS):
1. Start backend (`uvicorn app.main:app --port 8000`) and frontend (`npm run dev`).
2. Open `http://localhost:5173/claims/new`.
3. Switch toggle to **"Live Gnani AI"**.
4. In the missing information question or after transcription, click **"Listen (Timbre TTS)"**.
5. Verify you hear clear spoken Hindi audio generated in real-time by Gnani Timbre using the `Nalini` voice.

### Testing Speech-to-Text (Gnani Prisma ASR):
1. On `http://localhost:5173/claims/new`, ensure mode is set to **"Live Gnani AI"**.
2. Click **"Start Recording (Max 30s)"** and speak naturally in Hinglish:
   > *"Mera kal Andheri East Mumbai mein accident ho gaya tha car ka, left door tut gaya hai. Policy number MOT-2024-MH-78432."*
3. Click **"Finish & Transcribe"** before the 30-second timer expires.
4. Verify the exact Hindi / Hinglish transcript appears with `GNANI AI [LIVE]` badge, showing model `prisma-v2.5` or `prisma-v3.0` and latency.
5. Verify the extracted fields (Policy, Location, Date, Vehicle, Damage) are auto-populated in the review card.
6. Confirm and create the ticket, then view the activity timeline on the details page.

### Testing Error Recovery:
1. Temporarily change `GNANI_API_KEY_ID=invalid_key` in `.env`.
2. Attempt a recording in Live mode.
3. Observe the clear error banner: *"Authentication failed with Gnani Speech API"*.
4. Click **"Switch to Demo Mode"** to immediately recover and continue the workflow without page reload.
