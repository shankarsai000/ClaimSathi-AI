# ClaimSathi AI — Sprint 1 Security Audit Report
**Date:** November 12, 2026  
**Auditor:** Senior Backend Security Engineer & PostgreSQL Architect  
**Target Repository:** `https://github.com/shankarsai000/ClaimSathi-AI`  
**Scope:** Authentication, Authorization, Claim-Level Data Isolation, Evidence Security, Database & Storage Architecture

---

## 1. Executive Summary

ClaimSathi AI is an IRDAI-aligned motor insurance claim intake and documentation platform handling sensitive Indian policyholder Personally Identifiable Information (PII), vehicle records, insurance policy references, damage photographs/videos, and formal insurance dossiers.

A thorough baseline security audit was conducted against the complete backend codebase, API routes, database layer, storage mechanisms, frontend state management, and existing test suite.

### Key Audit Findings:
1. **Critical Authentication Bypass & Default Demo User Fallback:** Any unauthenticated request or request with an invalid/expired token was silently converted to customer `USR-100001` (`Rahul Sharma`) across protected endpoints via `get_optional_current_user_id()`.
2. **Broken Object Level Authorization (BOLA / IDOR):** No endpoint verified that the authenticated customer actually owned the target `claim_id`. Any user could view, update, generate reports, download PDFs/JSONs, list evidence, or submit claims belonging to any other customer.
3. **Unauthenticated Public Evidence Retrieval:** The endpoint `GET /api/evidence/{claim_id}/file/{evidence_id}` lacked any authentication, allowing anyone on the internet with a URL to view or download policyholder accident photos and inspection videos.
4. **Hardcoded Secrets & Universal Backdoor:** `CLAIMSATHI_JWT_SECRET` had a hardcoded default string in code. Universal OTP `123456` was accepted in all modes without rate-limiting, expiration, or single-use invalidation.
5. **Database Disconnect & Zero RLS Policies:** While 13 tables were provisioned in Supabase PostgreSQL with `ROW LEVEL SECURITY` enabled, 0 RLS policies were defined, and the application backend actually executed purely against a local SQLite file (`claimsathi.db`). Furthermore, Supabase database credentials were hardcoded in `backend/migrate_supabase.py` and committed to git history.

---

## 2. Current Architecture & Component Inventory

```mermaid
flowchart TD
    Client["React 18 + Vite Frontend (Port 5173)"]
    API["FastAPI Backend (Port 8080)"]
    AuthModule["auth.py (JWT + PBKDF2)"]
    DB_SQLite["Local aiosqlite (claimsathi.db)"]
    DB_PG["Supabase Cloud PostgreSQL (Port 5432)"]
    StorageLocal["Local Storage (storage/evidence)"]
    Gnani["Gnani Vachana APIs (Prisma STT + Timbre TTS)"]

    Client -->|Bearer JWT via fetch()| API
    API --> AuthModule
    API --> DB_SQLite
    API -.->|Configured in .env but dormant| DB_PG
    API --> StorageLocal
    API --> Gnani
```

### Component Details:
- **FastAPI Backend (`backend/app/main.py`):** Runs asynchronously on port 8080. Includes routers for `/api/health`, `/api/auth`, `/api/claims`, `/api/voice`, and `/api/evidence`.
- **Authentication (`backend/app/auth.py`):** Custom HMAC-SHA256 JWT implementation and PBKDF2-HMAC-SHA256 password hashing.
- **Database (`backend/app/database.py`):** Implements 12 SQLite tables via `aiosqlite`.
- **Evidence Storage (`backend/app/evidence_engine.py`):** Stores uploaded and captured media at `storage/evidence/{claim_id}/{evidence_id}_{safe_fname}`.
- **Frontend (`frontend/src/`):** React 18 with TypeScript. Stores JWT token and user profile in `localStorage`. Uses custom event `claimsathi-auth-change` for session synchronization.

---

## 3. Authentication & Data Ownership Flow Analysis

### Current Authentication Flow (Vulnerabilities Highlighted):
1. **Login (`POST /api/auth/login`):** User submits identifier (Email, Phone, or Customer ID) and Password or OTP.
   - *Vulnerability:* If `demo_quick_login=True` is passed, password/OTP check is completely bypassed.
   - *Vulnerability:* OTP verification accepts `123456` universally for any account.
   - *Vulnerability:* No rate limiting on login attempts, enabling credential stuffing.
2. **Token Issuance:** Backend signs a JWT with `customer_id` in `sub`.
   - *Vulnerability:* Default secret `"claimsathi-mvp-secret-key-2026-secure"` used if environment variable is missing. Algorithm header is not validated on decode.
3. **Protected Route Access:** Routes call `Depends(get_optional_current_user_id)`.
   - *Critical Vulnerability:* If no `Authorization` header is passed, or if the token is invalid/expired, `get_optional_current_user_id` catches the exception and returns `"USR-100001"`.

### Data Ownership Flow (Vulnerabilities Highlighted):
1. **Claim Listing (`GET /api/claims/`):**
   - Takes `customer_id` as an optional query parameter.
   - If omitted, returns **ALL claims in the database across all customers**.
   - If provided, returns claims for whatever `customer_id` was supplied, without verifying the caller's identity.
2. **Claim Details (`GET /api/claims/{claim_id}`):**
   - Fetches claim record by `claim_id`.
   - Never compares `claim.customer_id` to authenticated user. Returns claim, timeline, evidence, reports, and insurer submissions to any caller.
3. **Claim Modification (`PUT /api/claims/{claim_id}`):**
   - Allows arbitrary caller to modify another customer's claim details and confirmation status.
4. **Reports & Exports (`GET /api/claims/{claim_id}/report/*`):**
   - PDF, localized HTML, and canonical JSON can be downloaded by any user for any claim.
5. **Evidence Upload & Serving (`/api/evidence/*`):**
   - Upload accepts any `claim_id` without ownership check.
   - File serving `GET /api/evidence/{claim_id}/file/{evidence_id}` has no authentication at all.

---

## 4. Sensitive Data Inventory

| Category | Sensitive Fields | Regulatory / Privacy Impact |
| :--- | :--- | :--- |
| **Customer PII** | Full name, email address, mobile phone number, customer ID, declared insurer | DPDP Act 2023 & IRDAI Confidentiality |
| **Authentication Data** | Password hashes, verification OTPs, JWT access tokens | Critical Security / Account Takeover |
| **Vehicle & Policy Data** | Policy number, vehicle registration number, chassis/VIN, vehicle type, make/model | Motor Vehicles Act & Insurance Data Privacy |
| **Incident Information** | Accident location, incident date & time, detailed statement, voice transcripts, injury status | Sensitive Incident Data |
| **Evidence Media** | Vehicle damage photos, scene photos, odometer photos, inspection videos, EXIF GPS metadata | Digital Evidence / Chain of Custody |
| **Cryptographic Provenance** | SHA-256 hashes, 64-bit DCT pHash, C2PA JUMBF boxes, SynthID digital watermark signals | Non-repudiation & Anti-fraud Integrity |
| **Legal Claim Dossiers** | 9-Section formal claim packages, insurer submission records, carrier acknowledgment references | Formal Legal Insurance Submission |

---

## 5. API Endpoint Security Matrix (Pre-Remediation Baseline)

| Endpoint | Method | Current Auth Status | Ownership Enforced? | Severity / Risk |
| :--- | :--- | :--- | :--- | :--- |
| `/api/health` | GET | None | N/A (Public) | Low (Info disclosure) |
| `/api/auth/register` | POST | None | N/A (Registration) | Low (Needs rate-limit) |
| `/api/auth/request-otp` | POST | None | N/A | High (Universal OTP, no rate-limit) |
| `/api/auth/login` | POST | None | N/A | High (Demo bypass, universal OTP) |
| `/api/auth/me` | GET | `get_optional_current_user_id` | No (Defaults to USR-100001) | High (PII Leakage) |
| `/api/auth/vault` | GET | `get_optional_current_user_id` | No (Trusts `?customer_id=`) | Critical (Complete Vault IDOR) |
| `/api/claims/` | POST | Header Optional / Body trusted | No (`request.customer_id` trusted) | Critical (Spoofed claim creation) |
| `/api/claims/` | GET | None | No (Returns ALL claims if no query) | Critical (Mass Data Exposure) |
| `/api/claims/stats` | GET | None | No (Returns stats + recent claims) | High (Cross-customer data leak) |
| `/api/claims/{id}` | GET | `get_optional_current_user_id` | No (Returns any claim) | Critical (Claim BOLA / IDOR) |
| `/api/claims/{id}` | PUT | `get_optional_current_user_id` | No (Updates any claim) | Critical (Unauthorized Modification) |
| `/api/claims/{id}/report` | POST | `get_optional_current_user_id` | No | High (Unauthorized report trigger) |
| `/api/claims/{id}/report` | GET | `get_optional_current_user_id` | No | Critical (Unauthorized Dossier view) |
| `/api/claims/{id}/report/pdf`| GET | `get_optional_current_user_id` | No | Critical (Unauthorized PDF download) |
| `/api/claims/{id}/report/localized`| GET | `get_optional_current_user_id` | No | Critical (Unauthorized Report download)|
| `/api/claims/{id}/report/json`| GET | `get_optional_current_user_id` | No | Critical (Unauthorized JSON export) |
| `/api/claims/{id}/submit-insurer`| POST | `get_optional_current_user_id` | No | High (Unauthorized carrier submission)|
| `/api/evidence/capture-session`| POST | `get_optional_current_user_id` | No (Does not verify claim owner) | Medium (Session spoofing) |
| `/api/evidence/{id}/upload`| POST | `get_optional_current_user_id` | No | Critical (Unauthorized Evidence upload)|
| `/api/evidence/{id}` | GET | `get_optional_current_user_id` | No | Critical (Evidence list BOLA) |
| `/api/evidence/{id}/file/{ev_id}`| GET | **None (Completely unauthenticated)**| No | **Critical (Public Media Download)** |
| `/api/voice/transcribe` | POST | None | N/A (Speech proxy) | Low (Rate limiting advised) |
| `/api/voice/speak` | POST | None | N/A (Speech proxy) | Low (Rate limiting advised) |

---

## 6. Vulnerability Findings & Risk Classification

### CRITICAL SEVERITY

#### [CRIT-01] Broken Object-Level Authorization (BOLA/IDOR) Across All Claim & Vault Operations
- **Location:** `backend/app/routes/claims.py`, `backend/app/routes/auth.py`, `backend/app/routes/evidence.py`
- **Description:** Endpoints retrieving claims, reports, evidence, or customer vaults either do not inspect authorization or rely on `customer_id` query parameters and URL path parameters without checking ownership against the verified JWT subject.
- **Impact:** Any authenticated or unauthenticated attacker can view, download, update, or submit any other customer's insurance claims, dossiers, damage images, and personal details.
- **Remediation:** Implement a centralized `verify_claim_ownership(claim_id, authenticated_customer_id)` dependency that looks up the claim, validates ownership, and raises HTTP 404 (to avoid leaking existence) or HTTP 403. Derive customer identity exclusively from verified JWT credentials.

#### [CRIT-02] Silent Authentication Fallback to Demo User (`USR-100001`)
- **Location:** `backend/app/auth.py:108-120`
- **Description:** `get_optional_current_user_id()` catches any authentication failure (missing header, malformed token, expired token, forged signature) and silently returns `"USR-100001"`.
- **Impact:** An attacker sending garbage authentication headers or no header at all is granted access to Rahul Sharma's customer profile and claims.
- **Remediation:** Remove silent demo fallback. Replace with strict dependency `get_current_authenticated_user` that validates tokens and raises HTTP 401 on missing, invalid, or expired tokens. Isolate demo behavior strictly to explicit development/demo flags.

#### [CRIT-03] Unauthenticated Public Evidence Media Access
- **Location:** `backend/app/routes/evidence.py:106-126`
- **Description:** `GET /api/evidence/{claim_id}/file/{evidence_id}` takes no authentication parameters and serves files directly from disk.
- **Impact:** Direct URL access to sensitive photographs of damaged vehicles, odometer readings, and inspection videos.
- **Remediation:** Require authentication and verify that the requesting user owns the parent claim associated with `evidence_id`.

#### [CRIT-04] Mass Data Leakage via Unfiltered Claim Listing
- **Location:** `backend/app/routes/claims.py:176-184`
- **Description:** `GET /api/claims/` with no query parameters returns every claim record in the database.
- **Impact:** Complete enumeration of all policyholders, policy numbers, locations, and damage details.
- **Remediation:** Require authentication and strictly scope query results to `customer_id == authenticated_user.customer_id`.

---

### HIGH SEVERITY

#### [HIGH-01] Hardcoded JWT Secret & Weak Cryptographic Defaults
- **Location:** `backend/app/auth.py:15`
- **Description:** Fallback secret `"claimsathi-mvp-secret-key-2026-secure"` is embedded in source code. No enforcement of minimum entropy or production secret presence during startup.
- **Impact:** Attackers can forge valid JWTs for any customer ID (`sub`) if `CLAIMSATHI_JWT_SECRET` is not set.
- **Remediation:** Enforce `CLAIMSATHI_JWT_SECRET` validation on startup in production (`APP_ENV=production`), requiring $\ge 32$ characters with high entropy. Fail startup if absent or insecure.

#### [HIGH-02] Universal OTP Backdoor (`123456`) & Missing OTP Security Controls
- **Location:** `backend/app/auth.py:91-105`, `backend/app/routes/auth.py:65-75`
- **Description:** OTP code `123456` is unconditionally accepted for any identifier in `verify_otp()`. `generate_otp()` only returns `123456`. OTPs have no expiration, no attempt limits, and are not invalidated upon use.
- **Impact:** Anyone can log into any customer account using OTP `123456` without knowing the password.
- **Remediation:** Restrict universal OTP bypass strictly to development/test mode. In production, generate cryptographically random 6-digit OTPs using `secrets`, enforce a 5-minute time-to-live (TTL), limit failed attempts to 3, and consume the OTP immediately upon successful verification.

#### [HIGH-03] Supabase Database Credentials Committed to Git History
- **Location:** `backend/migrate_supabase.py:4` (Commit `a01a1a8`)
- **Description:** Hardcoded PostgreSQL URI containing database user `postgres.btflaabvtrjlfrmqrslg` and plaintext password was committed to the git repository.
- **Impact:** Anyone with read access to the git repository has direct superuser network access to the Supabase PostgreSQL database.
- **Remediation:** Immediate credential rotation in the Supabase dashboard. Strip hardcoded URI from `migrate_supabase.py` and read exclusively from `DATABASE_URL` in `.env`.

---

### MEDIUM SEVERITY

#### [MED-01] Missing Row-Level Security (RLS) Policies on PostgreSQL
- **Location:** Supabase Cloud Database (`aws-0-ap-southeast-1.pooler.supabase.com`)
- **Description:** RLS is enabled (`rowsecurity=True`) on all 13 tables, but 0 RLS policies exist. Backend accesses the database as table owner/superuser, bypassing RLS.
- **Impact:** Defense-in-depth is absent at the database layer. An application-level SQL vulnerability would grant unrestricted cross-customer access.
- **Remediation:** Define explicit PostgreSQL RLS policies mapping customer identity to rows.

#### [MED-02] Missing Authentication Rate Limiting
- **Location:** `backend/app/routes/auth.py`
- **Description:** `/api/auth/login` and `/api/auth/request-otp` have no rate limiting or IP-based throttling.
- **Impact:** Susceptible to automated credential stuffing, brute-force password guessing, and SMS/OTP flooding.
- **Remediation:** Implement an in-memory/sliding-window rate limiter for authentication endpoints.

#### [MED-03] Potential Path Traversal & File Spoofing Risks in Evidence Storage
- **Location:** `backend/app/evidence_engine.py:478-482`
- **Description:** Filename sanitization uses regex `re.sub(r"[^A-Za-z0-9_.\-]", "_", filename)`, but preserves user-controlled extensions. `Path(storage_path)` in download endpoint could be manipulated if storage path format is modified.
- **Impact:** Potential path manipulation or arbitrary file overwrite if directories are improperly bounded.
- **Remediation:** Ensure all storage paths are strictly generated server-side using secure UUIDs, validate paths resolve strictly within `STORAGE_ROOT`, and serve downloads using controlled streaming.

---

### LOW SEVERITY

#### [LOW-01] Frontend LocalStorage Token Storage
- **Location:** `frontend/src/api.ts:27`
- **Description:** JWT access token is stored in browser `localStorage`.
- **Impact:** Vulnerable to exfiltration if an XSS vulnerability exists.
- **Remediation:** Implement strict input sanitization, CSP headers, and structured session cleanup.

#### [LOW-02] Deprecated Datetime Methods
- **Location:** `backend/app/database.py`, `backend/app/dossier_engine.py`, `backend/app/routes/claims.py`
- **Description:** Widespread use of `datetime.utcnow()` generating Python 3.12+ deprecation warnings.
- **Impact:** Technical debt and potential timezone ambiguity.
- **Remediation:** Standardize on timezone-aware UTC timestamps (`datetime.now(timezone.utc)`).

---

## 7. Recommended Sprint 1 Remediation Plan

1. **Authentication Architecture:**
   - Centralize token and credential configuration in `backend/app/auth.py` and `backend/app/config.py`.
   - Remove hardcoded secrets; mandate `CLAIMSATHI_JWT_SECRET` in production with startup validation.
   - Implement `get_current_user` dependency that strictly returns HTTP 401 on missing, invalid, or expired tokens.
   - Implement secure OTP generation (cryptographic random, 5-minute TTL, single-use, max 3 attempts) with universal test OTP isolated strictly to `APP_ENV != "production"`.
   - Add login rate limiting and structured audit logging.
2. **Mandatory Customer Identity & Ownership Enforcement:**
   - Create reusable authorization dependency `get_customer_claim(claim_id, current_user)` that retrieves the claim and verifies `claim.customer_id == current_user["customer_id"]`.
   - Enforce on all endpoints: claim creation, listing, detail, updates, report generation, PDF/JSON/HTML downloads, evidence upload/listing/download, and insurer submission.
   - Scope `GET /api/claims/` strictly to the authenticated user's claims.
   - In `POST /api/claims/`, ignore any client-supplied `customer_id` and bind strictly to `current_user["customer_id"]`.
3. **Evidence Security:**
   - Require authentication on `GET /api/evidence/{claim_id}/file/{evidence_id}` and verify claim ownership.
   - Support authenticated query tokens for direct browser media embedding (`<img src="...?token=...">`).
   - Restrict path traversal and enforce storage root boundaries.
4. **Database & Row-Level Security:**
   - Create explicit PostgreSQL RLS policies for all 13 tables in Supabase.
   - Provide a safe migration script and documentation.
5. **Frontend Hardening:**
   - Automatic 401 interceptor in `api.ts` to clear expired sessions and redirect to login.
   - Pass authorization tokens on all API requests and downloads.
6. **Comprehensive Automated Security Tests:**
   - Implement exhaustive unit and adversarial test suites covering authentication, cross-customer isolation, evidence access, and database isolation.

