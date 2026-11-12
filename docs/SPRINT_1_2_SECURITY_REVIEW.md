# ClaimSathi AI — Sprint 1.2 Security Review & Threat Analysis
**Document Version:** 1.0.0  
**Target:** SQLite Database Architecture & Concurrency Foundation  
**Auditor:** Senior Application Security & Database Architect  
**Sprint Status:** Verified & Remediated

---

## 1. Executive Summary

During Sprint 1.2, ClaimSathi AI completed a comprehensive security review and architectural hardening of its embedded SQLite persistence layer. As established in the project charter, SQLite serves as the MVP database engine. Operating SQLite safely in an asynchronous FastAPI web application requires rigorous PRAGMA configuration, connection pooling discipline, strict authorization, transactional boundaries, and defensive file operations.

This security review identified five foundational architectural risks in the legacy database implementation, remediated each with minimal disruptive footprint, and verified all protections through 11 new automated adversarial regression tests in `backend/tests/test_security_sprint1_2.py`.

---

## 2. Vulnerability Findings & Remediations

### Finding 1: Unenforced Foreign Keys (CRITICAL — Silent Referential Integrity Breakage)
- **Vulnerability:** By default, SQLite connection handles do not enforce declared `FOREIGN KEY` constraints. Prior to Sprint 1.2, `PRAGMA foreign_keys = ON;` was never executed on connection open.
- **Impact:** An attacker or erroneous code could insert orphaned evidence records, forged claim fields, or fake consents referencing nonexistent users or claims. Deleting parent rows would leave orphaned records indefinitely.
- **Remediation:** Enforced `PRAGMA foreign_keys = ON;` on every single connection opened via `get_db_connection()` and `connect_db()`.
- **Verification:** Verified via `test_foreign_key_rejection_on_orphan_insert` and `test_foreign_key_rejection_on_orphan_consent`. Attempting to insert an orphan child record immediately raises `sqlite3.IntegrityError`.

---

### Finding 2: Missing WAL Mode & Busy Timeout (HIGH — Concurrency Denial-of-Service)
- **Vulnerability:** Connections operated in default rollback journal mode with a 0ms busy timeout.
- **Impact:** Any concurrent read during an active file write (e.g. while writing evidence records or uploading images) would immediately raise `OperationalError: database is locked`, causing HTTP 500 crashes and denial-of-service for legitimate policyholders.
- **Remediation:** Enforced `PRAGMA journal_mode = WAL;` (Write-Ahead Logging) and `PRAGMA busy_timeout = 5000;` on all connections. In WAL mode, readers never block writers, writers never block readers, and competing writers queue safely for up to 5 seconds.
- **Verification:** Verified via `test_sqlite_pragmas_configured`.

---

### Finding 3: Split Database File Paths (HIGH — State Divergence & Split-Brain)
- **Vulnerability:** `DB_PATH = "claimsathi.db"` was hardcoded as a relative path string.
- **Impact:** Depending on the execution directory of the Python process (`D:\ClaimSathi AI` vs `D:\ClaimSathi AI\backend`), the application created and operated on two separate SQLite database files. Customer accounts and claims created in one process were invisible to another.
- **Remediation:** Implemented `get_db_path()` which resolves the canonical absolute path relative to the codebase root:
  ```python
  BASE_DIR = Path(__file__).resolve().parent.parent.parent
  DEFAULT_DB_PATH = str(BASE_DIR / "claimsathi.db")
  ```
- **Verification:** Verified across all test suites; all operations target a single canonical database file.

---

### Finding 4: Absence of Performance Indexes (MEDIUM — Algorithmic Complexity / Table-Scan DoS)
- **Vulnerability:** Zero custom indexes existed on `claimsathi.db`. Cross-claim SHA-256 fingerprint screening, customer claim history lookups, and audit log queries performed $O(N)$ sequential table scans.
- **Impact:** As claims and evidence assets grew, database query latency would degrade linearly, enabling low-bandwidth algorithmic denial-of-service attacks.
- **Remediation:** Executed migration `002_add_foreign_keys_and_indexes.sql` creating 21 specialized B-tree indexes covering all foreign keys, status flags, and search hashes (`idx_evidence_checks_sha256`, `idx_claims_customer_id`, etc.). Query complexity dropped from $O(N)$ to $O(\log N)$.
- **Verification:** Verified via SQLite schema inspection; 21 custom indexes confirmed active.

---

### Finding 5: Incomplete Cascade Deletion & Audit Log Vulnerability (HIGH — Data Privacy & Compliance)
- **Vulnerability:** No secure `DELETE /api/claims/{claim_id}` endpoint existed. Deleting a claim required manual database intervention, creating risks of incomplete data removal (violating DPDP right to erasure) or improper deletion of compliance audit logs.
- **Impact:** If audit logs were deleted alongside claims, malicious actors could delete claims to erase forensic evidence of unauthorized access or fraud.
- **Remediation:**
  1. Implemented transactional `delete_claim_record(claim_id)` with explicit cascade cleanup of child fields, evidence assets, evidence checks, reports, and timeline events.
  2. Implemented strict customer-level ownership verification via `get_authorized_claim_or_demo` returning HTTP 403 Forbidden for unauthorized users.
  3. **Strict Audit Trail Immutability:** `audit_logs` are explicitly preserved across claim deletions, retaining forensic evidence of who created, updated, and deleted the claim.
- **Verification:** Verified via `test_cascade_claim_deletion_preserves_audit_logs` and `test_api_delete_claim_authorization_and_cross_customer_rejection`.

---

## 3. Threat Modeling & Security Controls Matrix

| Threat Category | Threat Scenario | Implemented Security Control | Status |
|---|---|---|---|
| **BOLA / IDOR** | Customer B attempts to delete or access Customer A's claim. | `get_authorized_claim_or_demo` dependency strictly validates `claim.customer_id == current_user['sub']`. Mismatches return HTTP 403. | **MITIGATED** |
| **Authentication Bypass** | Unauthenticated request attempts claim deletion in production. | Application checks `settings.app_env == "production"` and enforces mandatory Bearer token, returning HTTP 401. | **MITIGATED** |
| **Referential Integrity** | Attacker inserts orphaned record or modifies parent keys. | `PRAGMA foreign_keys = ON;` rejects invalid relationships with `sqlite3.IntegrityError`. | **MITIGATED** |
| **Concurrency Starvation** | Simultaneous uploads lock database during write transactions. | `PRAGMA journal_mode = WAL;` decouples readers from writers; `PRAGMA busy_timeout = 5000;` prevents instant timeouts. | **MITIGATED** |
| **Audit Trail Erasure** | Malicious insider deletes claim to remove evidence of tampering. | `delete_claim_record` cascades only to claim data; `audit_logs` are preserved with claim ID. | **MITIGATED** |
| **SQL Injection** | Attacker sends malicious SQL payloads in claim IDs. | Parameterized queries (`?` placeholders) used across all database calls. Verified via fuzzing tests. | **MITIGATED** |
| **Backup Corruption / Tampering** | Attacker corrupts backup file or triggers torn-page reads. | Live backups use atomic `sqlite3.backup`; restore utility validates `PRAGMA integrity_check;` before writing. | **MITIGATED** |

---

## 4. Test Suite Coverage & Verification Results

The complete Sprint 1.2 security suite was executed and verified:

```
backend/tests/test_security_sprint1_2.py::test_sqlite_pragmas_configured PASSED
backend/tests/test_security_sprint1_2.py::test_sqlite_row_factory_dual_access PASSED
backend/tests/test_security_sprint1_2.py::test_foreign_key_rejection_on_orphan_insert PASSED
backend/tests/test_security_sprint1_2.py::test_foreign_key_rejection_on_orphan_consent PASSED
backend/tests/test_security_sprint1_2.py::test_schema_migrations_applied_and_clean_fk_check PASSED
backend/tests/test_security_sprint1_2.py::test_migration_and_init_db_idempotency PASSED
backend/tests/test_security_sprint1_2.py::test_cascade_claim_deletion_preserves_audit_logs PASSED
backend/tests/test_security_sprint1_2.py::test_api_delete_claim_authorization_and_cross_customer_rejection PASSED
backend/tests/test_security_sprint1_2.py::test_sqlite_online_backup_and_verified_restore PASSED
backend/tests/test_security_sprint1_2.py::test_restore_rejects_corrupted_backup_file PASSED
backend/tests/test_security_sprint1_2.py::test_database_error_handling_no_internal_stack_leakage PASSED
```

**Total Backend Test Suite:** 65 passed, 0 failed in 85.02s.  
**Frontend Build Status:** Clean build in 1m 3s with 0 errors.
