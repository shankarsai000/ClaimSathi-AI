# ClaimSathi AI — Sprint 1.1 Independent Security Review & Vulnerability Audit

**Auditor**: Independent Principal Security Architect & Database Engineer  
**Date**: November 12, 2026  
**Repository**: `https://github.com/shankarsai000/ClaimSathi-AI`  
**Branch**: `security/sprint-1-1-independent-remediation`  
**Base Commit**: `ef2574ae297b30a5a21ac1c695489ffc52a86bed`  
**Status**: Comprehensive Baseline Established — Remediation Underway  

---

## 1. Executive Summary

This independent security review was conducted following Sprint 1. While Sprint 1 introduced important application-layer ownership checks in `app/authorization.py` and authored initial PostgreSQL Row-Level Security (RLS) policies, a critical independent evaluation revealed serious vulnerabilities and architectural discrepancies that must be remediated:

1. **CRITICAL: RLS Bypass Backdoor in PostgreSQL Migration**: The SQL function `current_customer_id()` in `001_sprint1_security_rls.sql` trusted a user-settable session GUC (`app.bypass_rls`). Any unprivileged role or client could issue `SET app.bypass_rls = 'true'` to completely disable RLS across all 13 tables.
2. **HIGH: Blanket Privilege Grants**: `GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;` granted excessive DDL/DML privileges to untrusted and unauthenticated roles.
3. **HIGH: Runtime Database Architecture Mismatch**: The runtime application (`app/database.py`, `app/main.py`) operates exclusively on local SQLite (`aiosqlite` on `claimsathi.db`). The PostgreSQL RLS policies in `backend/migrations/` are not executed in the runtime path, meaning SQLite does not enforce database-level RLS.
4. **HIGH: Capture-Session Replay & Cross-Customer Reuse**: Guided live camera capture sessions lacked user-ownership validation on upload. Unbound capture sessions (`claim_id = NULL`) could be claimed by arbitrary customers, and sessions could be replayed indefinitely without status invalidation.
5. **MEDIUM: Unbounded Memory Consumption on Uploads**: The file upload endpoint executed `await file.read()` before checking file size limits, enabling memory exhaustion denial-of-service (DoS) via oversized payloads.
6. **MEDIUM: Long-Lived JWT Tokens in Query Strings**: Direct media and PDF preview links exposed full bearer JWTs in URL query strings (`?token=...`), risking credential leakage through browser history, HTTP access logs, and referrer headers.
7. **MEDIUM: Multi-Worker & OTP Delivery State**: Rate limiting and OTP stores are held in process-local Python dictionaries (`_LOGIN_ATTEMPTS`, `_ACTIVE_OTPS`), which diverge when multiple Uvicorn workers run. Furthermore, the UI claimed "OTP sent" without a configured SMS/email provider.

---

## 2. Baseline Test Execution Results

Prior to making any source code modifications on the `security/sprint-1-1-independent-remediation` branch, the full backend and frontend test suites were executed to establish a reproducible baseline:

### Backend Baseline (`python -m pytest backend/tests -v`)
- **Total Tests Collected**: 41
- **Passed**: 41
- **Failed**: 0
- **Warnings**: 14 (deprecation warnings for `datetime.utcnow()`)
- **Execution Time**: 57.03s

```
====================== 41 passed, 14 warnings in 57.03s =======================
```

### Frontend Baseline (`npm --prefix frontend run build`)
- **TypeScript Check**: `tsc -b` passed with 0 errors.
- **Vite Production Bundler**: `vite build` completed in 8.62s.
- **Output Bundle**:
  - `dist/index.html`: 0.54 kB
  - `dist/assets/index-3LEt1ufD.css`: 32.94 kB
  - `dist/assets/index-B4tUtjFD.js`: 312.79 kB

---

## 3. Vulnerability Findings & Reproduction Matrix

### Vulnerability 1: PostgreSQL RLS Bypass via GUC Parameter (`app.bypass_rls`)
- **Severity**: **Critical** (CVSS: 9.8)
- **Location**: `backend/migrations/001_sprint1_security_rls.sql` (Lines 40–55)
- **Reproduction**:
  ```sql
  SET ROLE authenticated;
  SET app.current_customer_id = 'USR-100001';
  -- Normal view: returns 1 row
  SELECT COUNT(*) FROM claims; -- Returns 1
  -- Exploit: Set bypass flag in ordinary session
  SET app.bypass_rls = 'true';
  SELECT COUNT(*) FROM claims; -- Returns ALL claims across all customers!
  ```
- **Root Cause**: `current_customer_id()` checks `current_setting('app.bypass_rls', true) = 'true'`, and all 17 policies accept `current_customer_id() = 'BYPASS'`. In PostgreSQL, any connected session can set custom GUC variables (`SET custom.var = '...'`).
- **Remediation**:
  1. Remove `app.bypass_rls` entirely from `current_customer_id()`.
  2. Remove `current_customer_id() = 'BYPASS'` from all table policies.
  3. Enforce that only authorized superusers or internal migration roles can bypass RLS via database role privileges, not via user-controllable session variables.

---

### Vulnerability 2: Blanket Table Privileges to `anon` and `authenticated`
- **Severity**: **High** (CVSS: 8.5)
- **Location**: `backend/migrations/001_sprint1_security_rls.sql` (Lines 325–330)
- **Root Cause**:
  ```sql
  GRANT USAGE ON SCHEMA public TO anon, authenticated;
  GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
  GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
  GRANT ALL ON ALL ROUTINES IN SCHEMA public TO anon, authenticated;
  ```
  This gives `anon` (unauthenticated web users) and `authenticated` full table privileges, including `DELETE`, `TRUNCATE`, and schema inspection.
- **Remediation**:
  1. Revoke `ALL` privileges from `anon` and `authenticated`.
  2. Explicitly grant minimal privileges:
     - `anon`: No direct table access, or strictly limited to registration insertion if applicable.
     - `authenticated`: `SELECT`, `INSERT`, `UPDATE` only on tables required; `SELECT`, `INSERT` on `audit_logs` (strictly no `UPDATE` or `DELETE`).
     - No role gets `TRUNCATE` or `DROP`.

---

### Vulnerability 3: Actual Database Architecture Discrepancy (SQLite vs PostgreSQL)
- **Severity**: **High** (Architectural Risk / Audit Integrity)
- **Location**: `backend/app/database.py`, `backend/app/main.py`, `backend/app/config.py`
- **Root Cause**:
  - `backend/app/database.py` defines `DB_PATH = "claimsathi.db"` and performs all database calls using `aiosqlite`.
  - While PostgreSQL migrations exist in `backend/migrations/`, the FastAPI service never opens a PostgreSQL connection pool at runtime.
  - As a result, PostgreSQL RLS **does not protect runtime data today** because runtime data resides in SQLite.
- **Remediation**:
  1. Accurately document in security reports that RLS is a database-level capability prepared for PostgreSQL deployment, but current development runtime relies on application-level authorization in FastAPI.
  2. Maintain SQLite compatibility for lightweight local testing.
  3. Provide an explicit, controlled PostgreSQL database adapter architecture that binds `app.current_customer_id` inside transactional PostgreSQL sessions when `DATABASE_URL` is PostgreSQL.

---

### Vulnerability 4: Capture-Session Replay, Ownership & Claim Mismatch
- **Severity**: **High** (CVSS: 7.8)
- **Location**: `backend/app/routes/evidence.py` (`start_live_capture_session` and `upload_and_screen_evidence`)
- **Reproduction**:
  - Customer A creates an unbound capture session (`POST /api/evidence/capture-session` with `claim_id = null`).
  - Customer B obtains Customer A's session ID (`CAP-2026-XXXXXX`) and passes it in `POST /api/evidence/{claim_b_id}/upload`.
  - Because `session.get("claim_id")` is `None`, the check `session.get("claim_id") and session["claim_id"] != claim_id` evaluates to `False`, permitting Customer B to associate Customer A's capture session with Claim B!
  - Furthermore, sessions were never marked `used` or `expired`, allowing infinite uploads under the same session ID.
- **Remediation**:
  1. Require authentication to start any capture session.
  2. Bind every capture session to the caller's verified `customer_id`.
  3. Validate that `session["customer_id"] == current_user["sub"]`.
  4. If a session is bound to a `claim_id`, enforce exact claim match; if unbound, bind it permanently on first upload and prevent cross-customer reuse.
  5. Check `session["status"] == "active"`. Once completed or expired (default 15 minutes TTL), reject further uploads.

---

### Vulnerability 5: Unbounded In-Memory File Reads
- **Severity**: **Medium** (CVSS: 6.5)
- **Location**: `backend/app/routes/evidence.py` (Line 111)
- **Root Cause**:
  ```python
  raw_bytes = await file.read()
  file_size = len(raw_bytes)
  if file_size > MAX_VIDEO_SIZE_BYTES:
      raise HTTPException(status_code=413, ...)
  ```
  `file.read()` buffers the entire incoming payload into memory before verifying its length against the 50 MB limit.
- **Remediation**:
  Implement bounded chunked streaming reads:
  ```python
  chunk_size = 1024 * 1024  # 1 MB
  total_read = 0
  buffer = io.BytesIO()
  while True:
      chunk = await file.read(chunk_size)
      if not chunk:
          break
      total_read += len(chunk)
      if total_read > max_allowed_bytes:
          raise HTTPException(status_code=413, detail=f"File exceeds maximum allowed limit.")
      buffer.write(chunk)
  ```

---

### Vulnerability 6: Token Exposure in URL Query Parameters
- **Severity**: **Medium** (CVSS: 5.3)
- **Location**: `frontend/src/api.ts` and `backend/app/routes/evidence.py`, `backend/app/routes/claims.py`
- **Root Cause**: Passing `?token=<jwt_token>` exposes bearer credentials in URL strings. URLs appear in browser navigation history, server access logs, reverse proxy logs, and `Referer` headers.
- **Remediation**:
  1. Frontend: Implement authenticated `fetch` with `Authorization: Bearer <token>` for media assets and report downloads, converting responses to local `Blob` URLs (`URL.createObjectURL(blob)`).
  2. Backend: Keep query parameter fallback strictly for scenarios where browser media tags cannot supply headers, but enforce short-lived expiration and strict claim ownership.

---

### Vulnerability 7: Process-Local State & Simulated OTP Delivery
- **Severity**: **Low / Informational**
- **Location**: `backend/app/auth.py`, `backend/app/routes/auth.py`
- **Root Cause**:
  - `_ACTIVE_OTPS` and `_LOGIN_ATTEMPTS` are process-local Python dictionaries. In a multi-worker production environment (e.g., 4 Uvicorn workers), worker A does not know about OTPs or rate limits stored in worker B.
  - The API returns `"message": "OTP sent successfully to ..."` even though no SMS or email gateway is integrated in this prototype.
- **Remediation**:
  1. Clearly report the honest engineering limitation in `docs/` and API responses when SMS delivery is simulated.
  2. Implement an abstracted storage interface for rate limiting and OTPs, documenting Redis/PostgreSQL as the multi-worker backing store for production.

---

## 4. Phase 1 Sign-Off & Action Plan for Phase 2

All 7 vulnerabilities have been confirmed and root causes isolated. The remediation plan will be implemented on the `security/sprint-1-1-independent-remediation` branch without breaking existing ClaimSathi AI product functionality or the 25 baseline functional tests.

