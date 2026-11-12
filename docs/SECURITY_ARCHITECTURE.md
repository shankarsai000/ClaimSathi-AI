# ClaimSathi AI — Sprint 1 Security Architecture Document
## Security Hardening, Authentication & Claim-Level Data Isolation

**Author**: Senior Backend Security Engineer, PostgreSQL Architect & Full-Stack Engineer  
**Version**: 1.0.0 (Sprint 1 Production Release)  
**Status**: Complete & Verified (41 Tests Passing)  
**Target Environment**: FastAPI, PostgreSQL / Supabase, React 19, TypeScript  

---

## 1. Executive Summary & Security Posture

ClaimSathi AI handles sensitive personal data (PII), insurance policy numbers, accident descriptions, conversational voice transcripts, photographs, videos, and formal insurance claim dossiers.

In Sprint 1, the platform underwent comprehensive security hardening to enforce a **Zero-Trust Customer Data Isolation Model**:
1. **No Spoofed Identities**: Customer identity is strictly derived from cryptographically verified JSON Web Tokens (`sub` claim). All frontend-supplied `customer_id` fields in request bodies, query strings, and multipart forms are discarded.
2. **Mandatory Claim Ownership Verification**: Every claim operation (read, update, evidence upload, evidence download, report generation, PDF/JSON export, mock insurer submission) verifies that the authenticated customer owns the target claim before execution. Unauthorized cross-customer requests return **HTTP 403 Forbidden** and trigger a security audit alert.
3. **Database-Enforced Row-Level Security (RLS)**: 17 explicit PostgreSQL RLS policies with `FORCE ROW LEVEL SECURITY` guarantee that even if an application endpoint omits an authorization check, customer data remains completely invisible across tenant boundaries.
4. **Evidence Security**: Uploaded files undergo binary magic byte verification, strict extension allowlists, and server-side path traversal sanitization. Evidence downloads require authenticated token verification.
5. **Append-Only Security Audit Logging**: Sensitive events (logins, failed attempts, claim creation, access denials) are logged with request metadata, while zero credentials, hashes, or tokens are ever persisted to logs.

---

## 2. Threat Model & Trust Boundaries

```
[ Customer Browser / Mobile ]
            │
            ▼  (HTTPS / TLS 1.3)
┌──────────────────────────────────────────────────────────────────┐
│                   FastAPI Application Gateway                    │
│                                                                  │
│  [ Rate Limiter ]  ──>  [ JWT Auth Middleware (HS256) ]         │
│                                 │                                │
│                                 ▼                                │
│                 [ get_authorized_claim Dependency ]              │
│                       ├── Validates customer_id == token.sub     │
│                       └── Mismatches -> HTTP 403 & Audit Event   │
└──────────────────────────────────────────────────────────────────┘
            │                                    │
            ▼ (PostgreSQL Session)               ▼ (Local / S3 Storage)
┌──────────────────────────────┐       ┌───────────────────────────┐
│     PostgreSQL / Supabase    │       │  Private Evidence Storage │
│                              │       │                           │
│  FORCE ROW LEVEL SECURITY    │       │  - Binary magic byte check│
│  17 Active RLS Policies      │       │  - Traversal-safe paths   │
│  current_customer_id() check │       │  - Token-gated downloads  │
│  Append-Only Audit Logs      │       │  - Private object store   │
└──────────────────────────────┘       └───────────────────────────┘
```

### Assets Protected
- Policyholder PII (Names, Phone Numbers, Emails, Insurer Preferences).
- Insurance Policy References and Coverage Types.
- Incident statements and raw speech audio recordings.
- Crash scene photographs and guided video walk-around recordings.
- Evidence cryptographic hashes (SHA-256) and perceptual hashes (pHash).
- 9-Section Claim Dossiers, Canonical Schema JSONs, and official PDF documents.
- Security audit logs.

---

## 3. Authentication & Secrets Architecture

### 3.1 Secrets Management & Startup Validation
- Secret keys are managed exclusively via environment variables (`CLAIMSATHI_JWT_SECRET`).
- `Settings.validate_production_configuration()` executes during FastAPI `lifespan` startup.
- In production (`APP_ENV=production`):
  - Missing `CLAIMSATHI_JWT_SECRET` aborts startup immediately with `RuntimeError`.
  - Secrets shorter than 32 characters or matching insecure default placeholders are rejected.

### 3.2 JSON Web Token (JWT) Lifecycle
- **Algorithm**: Hardcoded and enforced to `HS256`. Token headers with `alg: "none"` or mismatched algorithms are rejected with HTTP 401.
- **Claims**:
  - `sub`: Authoritative customer identifier (`USR-100001`).
  - `email`: Customer registered email.
  - `name`: Customer full name.
  - `iat`: Issue timestamp (rejects tokens claiming future issuance beyond clock skew).
  - `exp`: Expiration timestamp (default 24 hours, strictly verified against UTC).
- **HMAC Verification**: Uses constant-time `hmac.compare_digest` to prevent timing attacks.

### 3.3 OTP Security Controls
- **Production Randomness**: 6-digit cryptographically secure integers generated via `secrets.randbelow(900_000) + 100_000`.
- **TTL**: 300 seconds (5 minutes) maximum validity window.
- **Attempt Limits**: Maximum 3 verification attempts per OTP before the record is invalidated.
- **Single-Use Consumption**: Once verified, `record["used"] = True`. Any replay of the same code is rejected.
- **Universal Code Restriction**: The testing bypass code (`123456`) is strictly blocked in production (`APP_ENV=production`).

### 3.4 Rate Limiting & Brute-Force Protection
- Login attempts are tracked in an in-memory sliding window cache.
- Exceeding 5 failed attempts within 15 minutes triggers an immediate **HTTP 429 Too Many Requests** response with a `Retry-After: 900` header.

---

## 4. Claim Ownership & Authorization Architecture

### 4.1 Zero-Trust Caller Identity
Every endpoint that creates or accesses claims ignores client-provided identity fields:
- `POST /api/claims/`: Derives `effective_customer_id = current_user["sub"]`.
- `GET /api/claims/`: Queries claims exclusively filtered by `WHERE customer_id = current_user["sub"]`.
- `GET /api/claims/stats`: Aggregates metrics only for claims owned by `current_user["sub"]`.
- `GET /api/auth/vault`: Ignores `?customer_id=...` and queries solely for `current_user["sub"]`.

### 4.2 Reusable Authorization Dependencies (`app/authorization.py`)

#### `get_authorized_claim(claim_id: str, current_user: Dict = Depends(get_current_user))`
1. Authenticates caller token via `get_current_user` (returns 401 if missing/invalid).
2. Retrieves claim record from database.
3. If claim does not exist -> returns **HTTP 404 Not Found**.
4. If `claim.customer_id != current_user["sub"]`:
   - Logs `ACCESS_DENIED_CROSS_CUSTOMER` to `audit_logs` table.
   - Returns **HTTP 403 Forbidden** with generic message: `"Access denied: You do not have permission to access or modify this claim."`
5. Returns verified `ClaimRecord` to route handler.

#### `get_authorized_claim_or_demo(claim_id: str, current_user: Optional[Dict] = Depends(get_optional_user))`
Provides dual-mode behavior:
- If caller provides valid token: strictly enforces `claim.customer_id == current_user["sub"]` (HTTP 403 on mismatch).
- If caller is unauthenticated:
  - In production (`APP_ENV=production`): returns **HTTP 401 Unauthorized**.
  - In development/test mode: allows access **only** if `claim.is_demo` or `claim_id.startswith("DEMO-")`.

### 4.3 Endpoint Security Matrix

| Endpoint | Method | Authentication | Ownership Verified? | Unauth Behavior | Cross-Customer Behavior |
|---|---|---|---|---|---|
| `/api/auth/register` | POST | Public | N/A | Creates account & consents | N/A |
| `/api/auth/login` | POST | Public | Validates credentials | 401 on bad password | Rate limited (429) |
| `/api/auth/logout` | POST | Optional | Clears session | 200 OK | N/A |
| `/api/auth/me` | GET | Mandatory | Verified against `sub` | 401 Unauthorized | N/A |
| `/api/auth/vault` | GET | Mandatory | Verified against `sub` | 401 Unauthorized | Query param ignored |
| `/api/claims/` | POST | Mandatory in Prod | Derived from `sub` | 401 in Prod / Demo in Dev | Cannot spoof owner |
| `/api/claims/` | GET | Mandatory in Prod | Scoped to `sub` | 401 in Prod / Demo in Dev | Sees only own claims |
| `/api/claims/stats` | GET | Mandatory in Prod | Scoped to `sub` | 401 in Prod / Demo in Dev | Sees only own stats |
| `/api/claims/{id}` | GET | Dependency | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/claims/{id}` | PUT | Dependency | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/claims/{id}/report` | POST/GET | Dependency | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/claims/{id}/report/pdf` | GET | Token / Header | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/claims/{id}/report/json` | GET | Token / Header | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/claims/{id}/report/localized` | GET | Token / Header | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/claims/{id}/submit-insurer` | POST | Dependency | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/evidence/capture-session` | POST | Mandatory | Verified against target claim | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/evidence/{id}/upload` | POST | Dependency | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/evidence/{id}` | GET | Dependency | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |
| `/api/evidence/{id}/file/{ev_id}` | GET | Token / Header | Verified by Dependency | 401 in Prod / Demo in Dev | **403 Forbidden** |

---

## 5. Evidence Security & Storage Architecture

### 5.1 Storage Isolation & File Upload Controls
- **Size Limits**: Enforced before processing:
  - Video files: maximum 50 MB (`MAX_VIDEO_SIZE_BYTES`).
  - Image files: maximum 20 MB (`MAX_IMAGE_SIZE_BYTES`).
  - Voice recordings: maximum 25 MB (`max_audio_upload_size_bytes`).
- **Allowed MIME & Extensions**:
  - Images: `image/jpeg` (.jpg, .jpeg), `image/png` (.png), `image/webp` (.webp).
  - Videos: `video/mp4` (.mp4), `video/webm` (.webm), `video/quicktime` (.mov), `video/x-msvideo` (.avi).
- **Two-Phase Integrity Verification**:
  1. Content-Type and file extension check.
  2. Binary Magic Byte signature inspection (validates true binary header: PNG `\x89PNG`, JPEG `\xff\xd8\xff`, MP4 `ftyp`, WebM `\x1a\x45\xdf\xa3`). Mismatched or fake extensions return **HTTP 400 Bad Request**.

### 5.2 Server-Side Filename Sanitization & Path Traversal Prevention
- Uploaded files are renamed using cryptographically random UUIDs:
  `{claim_id}_{asset_id}_{safe_label}.{ext}`
- Evidence retrieval verifies that the resolved path is strictly contained within the intended storage directory:
  ```python
  storage_dir = Path("storage/evidence").resolve()
  target_file = (storage_dir / filename).resolve()
  if not target_file.is_relative_to(storage_dir):
      raise HTTPException(status_code=400, detail="Invalid file path.")
  ```
- Any `../` or encoded `%2e%2e` traversal sequence is rejected.

### 5.3 Controlled, Authenticated Retrieval
- Evidence files and report PDFs are never exposed via unauthenticated public URLs.
- Downloads are served via authenticated streaming responses with security headers:
  - `X-Content-Type-Options: nosniff` (prevents MIME confusion attacks).
  - `Cache-Control: private, no-store, must-revalidate` (prevents intermediate proxy caching).
  - `Content-Disposition: inline` or `attachment; filename=...`.
- Direct browser media requests (e.g. `<img>`, `<video>`, PDF preview links) support an authenticated query parameter `?token=<jwt_token>`, strictly validated against the claim owner before serving bytes.

---

## 6. PostgreSQL & Supabase Row-Level Security (RLS)

### 6.1 Session Variable & JWT Mapping Function
A centralized PL/pgSQL helper function determines the authoritative caller:
```sql
CREATE OR REPLACE FUNCTION current_customer_id() RETURNS TEXT AS $$
BEGIN
    IF current_setting('app.bypass_rls', true) = 'true' THEN
        RETURN 'BYPASS';
    END IF;

    RETURN COALESCE(
        NULLIF(current_setting('app.current_customer_id', true), ''),
        NULLIF(current_setting('request.jwt.claim.sub', true), ''),
        (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')
    );
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;
```

### 6.2 17 Active RLS Policies Across 13 Tables
All 13 tables in the database have `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`:
1. `users`: `customer_id = current_customer_id()`
2. `user_consents`: `customer_id = current_customer_id()`
3. `conversations`: `customer_id = current_customer_id()`
4. `claims` (SELECT, INSERT, UPDATE, DELETE): `customer_id = current_customer_id()`
5. `claim_fields`: `claim_id IN (SELECT id FROM claims WHERE customer_id = current_customer_id())`
6. `evidence_assets`: `customer_id = current_customer_id() OR claim_id IN (SELECT id FROM claims WHERE customer_id = current_customer_id())`
7. `evidence_checks`: `claim_id IN (SELECT id FROM claims WHERE customer_id = current_customer_id()) OR asset_id IN (SELECT asset_id FROM evidence_assets WHERE customer_id = current_customer_id())`
8. `reports`: `claim_id IN (SELECT id FROM claims WHERE customer_id = current_customer_id())`
9. `claim_status_events`: `claim_id IN (SELECT id FROM claims WHERE customer_id = current_customer_id())`
10. `timeline_events`: `claim_id IN (SELECT id FROM claims WHERE customer_id = current_customer_id())`
11. `capture_sessions`: `customer_id = current_customer_id() OR (claim_id IS NOT NULL AND claim_id IN (SELECT id FROM claims WHERE customer_id = current_customer_id()))`
12. `insurer_submissions`: `claim_id IN (SELECT id FROM claims WHERE customer_id = current_customer_id())`
13. `audit_logs` (SELECT, INSERT): `user_id = current_customer_id()` (NO UPDATE, NO DELETE).

### 6.3 Append-Only Audit Log Guarantee
- `audit_logs` defines explicit policies for `SELECT` and `INSERT`.
- **Zero policies exist for `UPDATE` or `DELETE`**.
- Even an authenticated customer or service caller cannot modify or erase historical audit trail records.

---

## 7. Frontend Security & Token Handling

- **Storage**: Authentication tokens are stored in `localStorage` with reactive cross-tab synchronization via `claimsathi-auth-change`.
- **Automatic 401 Invalidation**: When any API call receives HTTP 401, `api.ts` clears stored credentials and dispatches `claimsathi-session-expired`, immediately redirecting the user to `/login`.
- **Direct Media URLs**: Download helper functions (`getEvidenceFileUrl`, `getReportPdfUrl`, `getReportJsonUrl`, `getReportLocalizedUrl`) automatically append `?token=<jwt_token>` for seamless media rendering without public exposure.
- **Production Sanitization**: Demo test cards and universal OTP auto-fills are gated by `import.meta.env.DEV` and are completely stripped in production builds.

---

## 8. Verification & Test Matrix

The complete test suite comprises **41 automated tests**, executed via `pytest`:

```
====================== 41 passed, 14 warnings in 53.81s =======================
```

### Baseline Functional Tests (25 Passed)
- `test_acceptance.py`: End-to-end Hinglish and Telugu voice claim intake workflows.
- `test_claims.py`: Health check, mock transcription, claim creation, validation, retrieval, and listing.
- `test_master_flow.py`: Registration, vault summary, conversation extraction, evidence duplicate screening (SHA-256 and pHash), SynthID/C2PA provenance rules, guided live capture, dossier generation, and mock insurer gateway.
- `test_voice.py`: Gnani Prisma STT (v2.5, v3.0), duration limits, unsupported formats, credit handling, Timbre TTS synthesis, and API key protection.

### Sprint 1 Security Tests (16 Passed)
- `test_auth_missing_token_returns_401`: Verifies unauthenticated protected requests return 401.
- `test_auth_invalid_token_returns_401`: Verifies malformed tokens return 401.
- `test_auth_expired_token_returns_401`: Verifies expired JWTs return 401 with appropriate detail.
- `test_auth_tampered_signature_returns_401`: Verifies payload tampering invalidates signature.
- `test_auth_valid_token_returns_200`: Verifies valid JWT resolves correct customer identity.
- `test_production_fails_startup_without_secure_secret`: Verifies startup fails on default secret in production.
- `test_production_fails_startup_with_short_secret`: Verifies secrets < 32 characters are rejected.
- `test_otp_universal_blocked_in_production`: Verifies fixed code 123456 is blocked in production.
- `test_otp_single_use_and_attempt_limit`: Verifies single-use guarantee and invalidation after use.
- `test_customer_claim_isolation_complete_matrix`: Verifies Customer B receives HTTP 403 on Customer A's claim across read, update, capture, upload, list, download, report, and insurer submission.
- `test_claims_list_isolated_per_customer`: Verifies zero claim overlap in customer dashboard lists.
- `test_vault_endpoint_ignores_spoofed_customer_id_query_parameter`: Verifies vault endpoint ignores query param.
- `test_evidence_rejects_disallowed_extension`: Verifies `.exe` and unsupported extensions return 400.
- `test_evidence_rejects_invalid_magic_bytes`: Verifies spoofed binary extensions return 400.
- `test_evidence_path_traversal_rejected`: Verifies directory traversal attempts are rejected.
- `test_audit_logs_record_events_and_leak_no_credentials`: Verifies audit records log logins, failures, and omit credentials.

---

## 9. Production Deployment Checklist & Rollback

### Production Deployment Checklist
1. [ ] Generate production JWT secret:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. [ ] Set environment variables in hosting environment:
   - `APP_ENV=production`
   - `CLAIMSATHI_JWT_SECRET=<generated_secret_64_hex>`
   - `DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<db>`
   - `GNANI_API_KEY_ID=<official_gnani_key>`
3. [ ] Run PostgreSQL RLS migration:
   ```bash
   python backend/migrations/run_migration.py
   ```
4. [ ] Build frontend production bundle:
   ```bash
   npm --prefix frontend run build
   ```
5. [ ] Launch backend service:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 4
   ```

### Rollback Procedure
If rollback to Phase 1 state is necessary:
1. Revert PostgreSQL RLS policies:
   ```bash
   python backend/migrations/rollback_sprint1_rls.py
   ```
2. Switch `APP_ENV=development` in environment configuration.
3. Restart backend service. Existing customer data and historical claims remain untouched.
