# ClaimSathi AI — SQLite Database Architecture & Concurrency Guide
**Document Version:** 1.0.0  
**Sprint Baseline:** Sprint 1.2 (SQLite Security Validation & Database Foundation)  
**Target Environment:** Python 3.10+ / FastAPI / SQLite 3.37+ / `aiosqlite` 0.20+

---

## 1. Executive Summary & Design Decision

ClaimSathi AI uses **SQLite** as its authoritative relational database engine for the MVP and core deployment. SQLite provides an embedded, self-contained, zero-configuration, ACID-compliant database that eliminates network latency and external dependency overhead while providing strong relational integrity.

To ensure production robustness, security, and multi-user safety, the SQLite persistence layer implements:
1. **Mandatory Foreign Key Enforcement** on every connection (`PRAGMA foreign_keys = ON;`).
2. **Write-Ahead Logging (WAL)** mode (`PRAGMA journal_mode = WAL;`) allowing concurrent readers alongside active writers without blocking.
3. **Busy Timeout Concurrency Bounding** (`PRAGMA busy_timeout = 5000;`) to prevent `database is locked` operational failures under load.
4. **Canonical Absolute Path Resolution** eliminating database split bugs between execution contexts.
5. **Versioned SQL Schema Migrations** with cryptographic SHA-256 verification and automatic idempotent startup application.
6. **Live Online Backup & Restoration** via Python's native `sqlite3.backup` API without locking application readers.
7. **Comprehensive Indexing Strategy** with 21 custom performance indexes eliminating full-table scans.

---

## 2. Canonical Database Path Resolution

### The Split-Path Vulnerability in Legacy Implementations
Previously, `DB_PATH = "claimsathi.db"` was declared as a relative path string. Depending on whether tests or processes were executed from the repository root `D:\ClaimSathi AI` or the sub-directory `D:\ClaimSathi AI\backend`, SQLite created two disparate database files:
- `D:\ClaimSathi AI\claimsathi.db`
- `D:\ClaimSathi AI\backend\claimsathi.db`

This resulted in silent data fragmentation, missed fixtures, and potential split-brain states where claims created in one session were invisible in another.

### Standardized Canonical Path Implementation
In `backend/app/database.py`, path resolution is standardized relative to the codebase root with environment override capability:

```python
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = str(BASE_DIR / "claimsathi.db")

def get_db_path() -> str:
    """Returns canonical SQLite database path from env or defaults to repository root claimsathi.db."""
    return os.environ.get("CLAIMSATHI_DB_PATH", DEFAULT_DB_PATH)

DB_PATH = get_db_path()
```

Every database operation, test runner, backup utility, and migration manager resolves against `get_db_path()`.

---

## 3. Connection Management & PRAGMA Lifecycle

SQLite connections in embedded applications default to permissive configurations that are unsuitable for secure, multi-tenant web applications:
- Foreign keys are **disabled by default** in SQLite connection handles for backwards compatibility.
- Journal mode defaults to `DELETE` (blocking all readers during writes).
- Busy timeout defaults to `0ms` (immediately throwing `sqlite3.OperationalError: database is locked`).

### Connection Context Manager (`get_db_connection`)
All database operations in ClaimSathi AI are routed exclusively through `@asynccontextmanager get_db_connection()`:

```python
@asynccontextmanager
async def get_db_connection(db_path: Optional[str] = None) -> AsyncIterator[aiosqlite.Connection]:
    path = db_path or get_db_path()
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    async with aiosqlite.connect(path) as db:
        # 1. Enforce referential integrity on every handle
        await db.execute("PRAGMA foreign_keys = ON;")
        
        # 2. Prevent instant lock timeouts
        await db.execute("PRAGMA busy_timeout = 5000;")
        
        # 3. Enable concurrent WAL journal mode
        if path != ":memory:":
            try:
                await db.execute("PRAGMA journal_mode = WAL;")
            except Exception:
                pass
                
        # 4. Standardize row factory for dual named and positional indexing
        db.row_factory = aiosqlite.Row
        yield db
```

### Direct Connection Provider (`connect_db`)
For long-lived callers or batch operations, `connect_db()` mirrors the exact same PRAGMA lifecycle.

---

## 4. Concurrency Model & Locking Strategy

SQLite supports multi-threaded and asynchronous access using the Write-Ahead Log (WAL) architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Worker Process                   │
├──────────────────────────────┬──────────────────────────────┤
│  Async Connection Pool A     │   Async Connection Pool B    │
│  (Read Operation: Claim)     │   (Write Operation: Evidence)│
└──────────────┬───────────────┴──────────────┬───────────────┘
               │                              │
               │ (Non-blocking Read)          │ (BEGIN IMMEDIATE)
               ▼                              ▼
┌──────────────────────────────┐┌──────────────────────────────┐
│  claimsathi.db (Data Pages)  ││ claimsathi.db-wal (Append Log│
└──────────────────────────────┘└──────────────────────────────┘
               ▲                              ▲
               └───────────────┬──────────────┘
                               │
                claimsathi.db-shm (Shared Index)
```

### WAL Mode Concurrency Guarantees:
1. **Readers never block writers:** When a transaction writes new evidence checks or updates claim status, concurrent customer dashboard queries read uninterrupted from existing database pages.
2. **Writers never block readers:** Readers always see a consistent point-in-time snapshot without acquiring exclusive locks.
3. **One Active Writer with Busy Timeout Queue:** SQLite serializes writes. Under concurrent writes, transactions wait up to 5,000ms (`busy_timeout = 5000`) for the active write lock to clear rather than failing immediately.

### Transaction Isolation & Explicit Boundaries:
Destructive or multi-table operations (such as `delete_claim_record` or `insert_claim`) execute using explicit `BEGIN IMMEDIATE;` transaction boundaries:

```python
async with get_db_connection() as db:
    await db.execute("BEGIN IMMEDIATE;")
    try:
        # Multi-table atomic cascade deletion
        await db.execute("DELETE FROM evidence_checks WHERE ...")
        await db.execute("DELETE FROM evidence_assets WHERE ...")
        await db.execute("DELETE FROM claim_fields WHERE ...")
        await db.execute("DELETE FROM claims WHERE id = ?", (claim_id,))
        await db.commit()
    except Exception:
        await db.execute("ROLLBACK;")
        raise
```

---

## 5. Schema Migration Framework

ClaimSathi AI uses a standalone, version-controlled SQLite migration framework located in `backend/migrations/sqlite/`.

### Migration Tracking Table
Migrations are recorded in the `schema_migrations` table:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);
```

### Migration Lifecycle (`apply_sqlite_migrations`)
When `init_db()` is invoked during application startup:
1. It verifies or initializes `schema_migrations`.
2. It lists all `*.sql` files in `backend/migrations/sqlite/` sorted by version number (`001_...`, `002_...`).
3. For each file not present in `schema_migrations`:
   - Reads the full SQL script.
   - Computes its SHA-256 cryptographic checksum.
   - Executes the script atomically within a migration transaction via `db.executescript()`.
   - Records the version, filename, ISO timestamp, and checksum into `schema_migrations`.
4. If already applied, it skips execution with zero overhead.

### Migration Inventory:
- `001_initial_schema.sql`: Initial 12 relational core tables with foreign keys and cascade rules.
- `002_add_foreign_keys_and_indexes.sql`: 21 performance and forensic search indexes.

---

## 6. Online Backup & Verified Restore Framework

Because SQLite databases are single files on disk, traditional file copies (`shutil.copy` or `cp`) during active writes can produce corrupt or torn pages.

ClaimSathi AI implements online hot backup using SQLite's native backup API:

### Online Backup (`create_sqlite_backup`)
```python
def create_sqlite_backup(src_db_path: Optional[str] = None, backup_dir: Optional[str] = None) -> str:
    # 1. Connect to live database and new destination file
    src_conn = sqlite3.connect(source_path)
    dst_conn = sqlite3.connect(str(backup_file))
    try:
        # 2. Stream data pages online without blocking active readers
        src_conn.backup(dst_conn, pages=100)
    finally:
        dst_conn.close()
        src_conn.close()
    return str(backup_file.resolve())
```

### Pre-Verified Restoration (`restore_sqlite_backup`)
Before overwriting a database with a backup file, `restore_sqlite_backup` enforces integrity checks:
1. Connects to the backup file and executes `PRAGMA integrity_check;`.
2. Rejects corrupted or truncated backup files before touching the active database.
3. Performs online restoration to the target database path using `sqlite3.backup`.

---

## 7. Performance Indexing Matrix

Prior to Sprint 1.2, `claimsathi.db` had 0 custom indexes. All cross-claim SHA-256 searches and customer claims queries executed via $O(N)$ full table scans.

Migration `002_add_foreign_keys_and_indexes.sql` introduced 21 specialized B-tree indexes:

| Table | Index Name | Columns | Purpose | Complexity |
|---|---|---|---|---|
| `claims` | `idx_claims_customer_id` | `customer_id` | Customer vault query filtering | $O(\log N)$ |
| `claims` | `idx_claims_created_at` | `created_at` | Chronological sort on dashboard | $O(\log N)$ |
| `claims` | `idx_claims_status` | `status` | Claim status aggregation | $O(\log N)$ |
| `claim_fields` | `idx_claim_fields_claim_id` | `claim_id` | Foreign key cascade & field lookup | $O(\log N)$ |
| `conversations` | `idx_conversations_user_id` | `user_id` | User session retrieval | $O(\log N)$ |
| `conversations` | `idx_conversations_claim_id` | `claim_id` | Claim session link | $O(\log N)$ |
| `timeline_events` | `idx_timeline_events_claim_id` | `claim_id` | Dossier timeline generation | $O(\log N)$ |
| `evidence_assets` | `idx_evidence_assets_claim_id` | `claim_id` | Claim media listing & deletion | $O(\log N)$ |
| `evidence_assets` | `idx_evidence_assets_user_id` | `user_id` | Customer asset auditing | $O(\log N)$ |
| `evidence_checks` | `idx_evidence_checks_sha256` | `sha256_hash` | Instant cross-claim duplicate match | $O(\log N)$ |
| `evidence_checks` | `idx_evidence_checks_claim_id` | `claim_id` | Cascade deletion & audit | $O(\log N)$ |
| `reports` | `idx_reports_claim_id` | `claim_id` | Dossier version history lookup | $O(\log N)$ |
| `reports` | `idx_reports_user_id` | `user_id` | Customer report history | $O(\log N)$ |
| `claim_status_events` | `idx_claim_status_events_claim_id` | `claim_id` | Status transition history | $O(\log N)$ |
| `audit_logs` | `idx_audit_logs_user_id` | `user_id` | Compliance audit log per user | $O(\log N)$ |
| `audit_logs` | `idx_audit_logs_claim_id` | `claim_id` | Forensic review per claim | $O(\log N)$ |
| `audit_logs` | `idx_audit_logs_timestamp` | `timestamp` | Time-series security analysis | $O(\log N)$ |
| `capture_sessions` | `idx_capture_sessions_user_id` | `user_id` | Live capture session lookups | $O(\log N)$ |
| `capture_sessions` | `idx_capture_sessions_claim_id` | `claim_id` | Claim binding queries | $O(\log N)$ |
| `capture_sessions` | `idx_capture_sessions_status` | `status` | Session TTL sweeps | $O(\log N)$ |
| `insurer_submissions` | `idx_insurer_submissions_claim_id` | `claim_id` | Carrier adapter submissions | $O(\log N)$ |

---

## 8. Relational Integrity Verification

Referential integrity can be verified at any time programmatically via `verify_sqlite_foreign_keys()`:

```python
violations = await verify_sqlite_foreign_keys()
assert len(violations) == 0
```

Internally, this executes `PRAGMA foreign_key_check;` across the entire database schema, guaranteeing that no orphaned child records exist in any table.
