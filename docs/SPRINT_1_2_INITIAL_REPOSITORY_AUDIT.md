# ClaimSathi AI — Sprint 1.2 Initial Repository & Baseline Security Audit
**Document ID:** `docs/SPRINT_1_2_INITIAL_REPOSITORY_AUDIT.md`  
**Date:** November 12, 2026  
**Auditor / Architect:** Senior Backend Architect, Application Security Engineer & QA Lead  
**Branch:** `security/sprint-1-2-sqlite-foundation`  
**Base Commit Verified:** `9224d05` (with doc formatting commit `2511460`)  
**Repository:** [https://github.com/shankarsai000/ClaimSathi-AI](https://github.com/shankarsai000/ClaimSathi-AI)  
**Baseline Test Execution:** 54 Passed, 0 Failed (76.68s)  
**Baseline Frontend Build:** 0 TypeScript Errors, Production Build Successful (11.05s)

---

## 1. Executive Summary & Objective

In Sprint 1.2, ClaimSathi AI establishes a hardened, verified, maintainable **SQLite application database foundation** for the current MVP, backed by application-level customer data isolation, explicit foreign-key constraints, Write-Ahead Logging (WAL) concurrency, versioned schema management, and automated backup/restore facilities.

This document records the exact state of the repository prior to introducing architectural enhancements, verifies Sprint 1.1 commits, analyzes current database and authorization implementations, and outlines the planned structural improvements.

---

## 2. Git & Working Tree Baseline

- **Current Working Branch:** `security/sprint-1-2-sqlite-foundation` (branched from `security/sprint-1-1-independent-remediation` at commit `9224d05`).
- **Base Commit Verification:** Commit `9224d05` (`feat(security): Sprint 1.1 independent security audit, remediation, and adversarial verification`) is verified present and forms the parent of this branch.
- **Working Tree Status:** Clean; all tracked files match HEAD.
- **Sprint 1.1 Branch State:** The Sprint 1.1 branch remains a dedicated security branch and has **not** been merged into `main`.
- **Diff Against `main`:**
  - 16 files modified/created (+1,701 lines / -184 lines).
  - Additions include zero-bypass PostgreSQL RLS migration (`backend/migrations/001_sprint1_security_rls.sql`), bounded upload streaming, ephemeral media access tickets, password complexity policy, honest OTP channel disclosure, 13 adversarial regression tests (`test_security_sprint1_1.py`), and Sprint 1.1 audit/remediation reports.

---

## 3. Codebase & Architectural Inventory

### 3.1 Directory Structure
```text
D:\ClaimSathi AI\
├── backend/
│   ├── app/
│   │   ├── providers/          # Gnani Prisma STT & Timbre TTS adapters
│   │   ├── routes/             # auth.py, claims.py, evidence.py, health.py, voice.py
│   │   ├── audio_utils.py      # Audio duration inspection & header extraction
│   │   ├── auth.py             # JWT token issuance, verification, OTP store, media tickets
│   │   ├── authorization.py    # Claim ownership dependencies (get_authorized_claim)
│   │   ├── config.py           # Pydantic Settings & production secret validation
│   │   ├── database.py         # 12-table SQLite persistence & seed records
│   │   ├── dossier_engine.py   # 9-section PDF & Canonical JSON generator
│   │   ├── evidence_engine.py  # 4-check Evidence Integrity Engine (SHA-256, pHash, C2PA, SynthID)
│   │   ├── main.py             # FastAPI entrypoint, CORS, lifespan startup/shutdown
│   │   └── models.py           # Pydantic domain models & request/response schemas
│   ├── migrations/             # PostgreSQL RLS migration, runner, rollback scripts
│   ├── tests/                  # 6 test modules (54 automated tests)
│   ├── .env / .env.example     # Configuration environment files
│   └── requirements.txt        # Backend dependencies
├── docs/                       # Security architecture, audit reports, checklists
├── frontend/                   # React 19 + TypeScript + Vite SPA
├── storage/evidence/           # Preserved original evidence media files
└── claimsathi.db               # SQLite database file
```

### 3.2 Installed Dependencies & Capabilities
- **FastAPI / Uvicorn:** `0.115.0` / `0.30.6`
- **Database Driver:** `aiosqlite 0.20.0`
- **Database Tooling Available:** `SQLAlchemy 2.0.51` & `Alembic 1.18.5` (installed in Python 3.14.2 environment)
- **Cryptography & Security:** PBKDF2-HMAC-SHA256 password hashing, HMAC-SHA256 JWT & media tickets
- **Imaging & Evidence:** `Pillow 11.1.0`

---

## 4. Current SQLite Implementation Findings & Weaknesses

Inspection of [`backend/app/database.py`](file:///d:/ClaimSathi%20AI/backend/app/database.py) and route handlers revealed the following structural issues:

### A. Missing Connection-Level Foreign Key Enforcement
SQLite disables foreign key enforcement by default on every new database connection.
In `backend/app/database.py`, connections are opened using:
```python
async with aiosqlite.connect(DB_PATH) as db:
    ...
```
`PRAGMA foreign_keys = ON;` is never executed. Consequently, `FOREIGN KEY (claim_id) REFERENCES claims(id)` constraints defined in table definitions are completely ignored by the SQLite engine at runtime, allowing orphan records.

### B. Missing Concurrency Controls (WAL Mode & Busy Timeout)
- The database connection does not set `PRAGMA journal_mode = WAL;`. By default, SQLite operates in rollback journal mode, where read operations block write operations and vice-versa.
- The connection does not set `PRAGMA busy_timeout = 5000;`. In concurrent workloads (e.g. simultaneous evidence uploads or background tasks), SQLite immediately raises `sqlite3.OperationalError: database is locked` instead of waiting for pending locks to release.

### C. Relative Path Resolution Splitting Database Files
`DB_PATH = "claimsathi.db"` is a relative string. When the backend or tests are executed from `D:\ClaimSathi AI\`, a database file is created at `D:\ClaimSathi AI\claimsathi.db`. When executed from `D:\ClaimSathi AI\backend\`, a separate database file is created at `D:\ClaimSathi AI\backend\claimsathi.db`.
The database file path must be derived from validated configuration (`settings.database_url` or a canonical absolute data path).

### D. Ad-Hoc Connections Scattered Across Route Files
`backend/app/routes/evidence.py` directly executes `async with aiosqlite.connect(DB_PATH) as db:` in two locations instead of delegating data operations through a unified database/repository layer.

### E. Manual Schema DDL & Non-Versioned Migrations
Table creation and migrations currently run procedurally in `init_db()` via raw `CREATE TABLE IF NOT EXISTS` and PRAGMA table inspection with `ALTER TABLE ADD COLUMN` loops. A structured schema migration and version tracking mechanism is required.

### F. Customer Data Isolation Depends 100% on Application-Level Enforcement
Because SQLite has no native Row-Level Security (RLS), the PostgreSQL RLS script (`001_sprint1_security_rls.sql`) does not protect runtime SQLite data. All customer isolation is strictly enforced via FastAPI dependencies (`get_authorized_claim`, `get_authorized_claim_or_demo`).

---

## 5. Baseline Test & Build Verification

### 5.1 Backend Test Suite (54 Passed, 0 Failed in 76.68s)
```text
backend/tests/test_acceptance.py (2 tests) .................... PASSED
backend/tests/test_claims.py (7 tests) ........................ PASSED
backend/tests/test_master_flow.py (5 tests) ................... PASSED
backend/tests/test_security_sprint1.py (13 tests) ............. PASSED
backend/tests/test_security_sprint1_1.py (13 tests) ........... PASSED
backend/tests/test_voice.py (14 tests) ........................ PASSED
====================== 54 passed, 18 warnings in 76.68s =======================
```

### 5.2 Frontend Build (0 TypeScript Errors in 11.05s)
```text
> claimsathi-frontend@0.1.0 build
> tsc -b && vite build

vite v5.4.21 building for production...
✓ 1586 modules transformed.
dist/index.html                   0.54 kB │ gzip:  0.37 kB
dist/assets/index-3LEt1ufD.css   32.94 kB │ gzip:  6.12 kB
dist/assets/index-BEIqvsqO.js   313.58 kB │ gzip: 93.36 kB
✓ built in 11.05s
```

---

## 6. Action Plan for Sprint 1.2

1. **Centralize SQLite Connection Management:** Implement a connection factory that enforces `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`, `PRAGMA busy_timeout = 5000;`, and resolves canonical database paths.
2. **Canonical Schema & Relational Integrity:** Enforce foreign-key relationships, unique constraints, and check constraints across all 12 core tables.
3. **Structured Repository / Service Boundaries:** Encapsulate database operations and prevent raw queries in route handlers.
4. **Automated SQLite Backup & Restore Utilities:** Script safe online SQLite backups using the SQLite online backup API or VACUUM INTO.
5. **Adversarial Regression Test Suite (`test_security_sprint1_2.py`):** Validate foreign-key enforcement, WAL concurrency, ownership scoping, media tickets, and error sanitization.
6. **Documentation Deliverables:** Create `SQLITE_DATABASE_ARCHITECTURE.md`, `SQLITE_SCHEMA_REFERENCE.md`, `SPRINT_1_2_SECURITY_REVIEW.md`, `SPRINT_1_2_REMEDIATION_REPORT.md`, and `SPRINT_1_2_DEPLOYMENT_CHECKLIST.md`.
