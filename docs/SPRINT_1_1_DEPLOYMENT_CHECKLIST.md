# ClaimSathi AI — Sprint 1.1 Production Deployment & Verification Checklist
**Document ID:** `docs/SPRINT_1_1_DEPLOYMENT_CHECKLIST.md`  
**Date:** November 12, 2026  
**Target Environment:** Staging & Production  
**Audience:** Platform Engineers, Security Operations & DevOps

---

## 1. Pre-Deployment Configuration Audit

Before deploying Sprint 1.1 changes to production, verify that all mandatory environment variables are set and meet security specifications:

- [ ] `APP_ENV=production` (Enforces strong JWT secret validation, blocks universal OTP `123456`, enables strict password complexity).
- [ ] `CLAIMSATHI_JWT_SECRET` is set to a cryptographically random secret of at least 32 characters (e.g. `openssl rand -hex 32`).
- [ ] Application fails fast on startup if `CLAIMSATHI_JWT_SECRET` is default, empty, or shorter than 32 characters.
- [ ] `CLAIMSATHI_DATABASE_URL` or `DATABASE_URL` connects to the secured PostgreSQL instance via SSL (`sslmode=require`).
- [ ] `CORS_ORIGINS` explicitly lists approved production domains (no wildcard `*` with credentials).
- [ ] `GNANI_API_KEY` and `GNANI_TOKEN` are populated with valid production credentials.
- [ ] Telephony SMS carrier credentials (if enabled) are configured, or development simulated mode is acknowledged.

---

## 2. Database Migration & RLS Deployment

Execute the zero-bypass Row-Level Security migration against PostgreSQL:

- [ ] Take a full database snapshot / backup before migration:
  ```bash
  pg_dump -Fc -v -d "$DATABASE_URL" -f "claimsathi_pre_sprint1_1_backup.dump"
  ```
- [ ] Execute `001_sprint1_security_rls.sql` migration:
  ```bash
  python backend/migrations/run_migration.py
  ```
- [ ] Verify that all 17 policies in schema `public` are active.
- [ ] Verify blanket grants are revoked:
  ```sql
  -- Confirm anon and authenticated do NOT have blanket permissions
  SELECT grantee, table_name, privilege_type 
  FROM information_schema.role_table_grants 
  WHERE grantee IN ('anon', 'authenticated') AND table_schema = 'public';
  ```
- [ ] Run adversarial bypass verification:
  ```bash
  python -m pytest backend/tests/test_security_sprint1_1.py -k test_postgresql_rls_zero_bypass_when_database_url_configured
  ```
- [ ] Verify audit log immutability:
  ```sql
  -- Under authenticated role, UPDATE and DELETE must fail or affect 0 rows
  SET ROLE authenticated;
  SET app.current_customer_id = 'USR-100001';
  UPDATE audit_logs SET details = 'tampered' WHERE user_id = 'USR-100001'; -- Expect 0 rows
  DELETE FROM audit_logs WHERE user_id = 'USR-100001'; -- Expect 0 rows
  RESET ROLE;
  ```

---

## 3. Storage & Evidence Security

- [ ] Ensure `storage/evidence/` filesystem directory has permissions restricted to the backend process owner (`chmod 700 storage/evidence`).
- [ ] Confirm reverse proxy (Nginx / Cloudflare) sets `client_max_body_size 55M` to match the application's 50 MB streaming read limit.
- [ ] Confirm reverse proxy forwards standard security headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Cache-Control: private, no-cache, no-store, must-revalidate`

---

## 4. Frontend Production Build & Asset Delivery

- [ ] Run TypeScript type-checking and production Vite build:
  ```bash
  npm --prefix frontend run build
  ```
- [ ] Verify `dist/` directory generated with hash-versioned assets.
- [ ] Confirm no JWT tokens are embedded in build artifacts or environment files.
- [ ] Confirm that `api.createMediaTicket()` and authenticated blob download utilities are utilized.

---

## 5. Automated Verification & Smoke Testing

- [ ] Run full regression suite:
  ```bash
  python -m pytest backend/tests -v
  ```
  *Requirement: All 54 tests must pass.*
- [ ] Health check endpoint verification:
  ```bash
  curl -fsS https://<domain>/api/health
  # Expected: {"status": "ok", "app": "ClaimSathi AI", "sprint_1_hardened": true}
  ```
- [ ] Test cross-customer IDOR rejection on production endpoint:
  ```bash
  curl -i -H "Authorization: Bearer <Customer_B_Token>" https://<domain>/api/claims/CS-2026-000124
  # Expected: HTTP 403 Forbidden
  ```
- [ ] Verify ephemeral media ticket issuance:
  ```bash
  curl -i -X POST -H "Authorization: Bearer <Customer_A_Token>" https://<domain>/api/claims/CS-2026-000124/media-ticket
  # Expected: HTTP 200 {"ticket": "...", "expires_in": 60, "claim_id": "CS-2026-000124"}
  ```

---

## 6. Rollback & Emergency Recovery Plan

If an unexpected production defect occurs:

1. **Database Rollback:**
   Execute `backend/migrations/rollback_sprint1_rls.py` to disable RLS and drop helper functions:
   ```bash
   python backend/migrations/rollback_sprint1_rls.py
   ```
2. **Snapshot Restoration:**
   If schema corruption occurs, restore from the pre-deployment snapshot:
   ```bash
   pg_restore --clean --if-exists -d "$DATABASE_URL" "claimsathi_pre_sprint1_1_backup.dump"
   ```
3. **Application Rollback:**
   Revert deployment artifact to the previous verified release tag.

