# ClaimSathi AI — Sprint 1.2 Deployment & Operations Checklist
**Sprint Baseline:** Sprint 1.2 (SQLite Security Validation & Database Foundation)  
**Target Environment:** Linux / Docker / Windows Staging & Production Host  
**Engine:** SQLite 3.37+ (WAL Mode, Foreign Keys Enforced)

---

## 1. Pre-Deployment Configuration & Environment Variables

Verify that all mandatory environment variables are set in production before initiating startup:

| Variable | Required | Production Value / Requirement | Purpose |
|---|---|---|---|
| `APP_ENV` | **YES** | `production` | Enables production security controls, disables universal OTP, enforces strict authentication. |
| `CLAIMSATHI_JWT_SECRET` | **YES** | Cryptographically secure string $\ge 32$ chars | Signs and verifies customer session tokens. Startup fails if missing or weak. |
| `CLAIMSATHI_DB_PATH` | Optional | Absolute path (e.g. `/var/data/claimsathi/claimsathi.db`) | Overrides default database location. Ensure target directory has RW permissions. |
| `GNANI_API_KEY_ID` | **YES** | Valid Gnani Cloud credentials | Authenticates Prisma STT and Timbre TTS requests. |
| `CORS_ORIGINS` | **YES** | Specific production domains (e.g. `https://claimsathi.in`) | Blocks cross-origin browser requests from unauthorized domains. |

---

## 2. Filesystem Permissions & Storage Architecture

SQLite in WAL mode requires read, write, and create permissions for three distinct files in the database directory:
1. `claimsathi.db`: Main database storage pages.
2. `claimsathi.db-wal`: Write-Ahead Log journal file.
3. `claimsathi.db-shm`: Shared-memory index file.

### Required Directory Structure:
```
/var/data/claimsathi/
├── claimsathi.db           # rw-rw---- (660 or 600, app user)
├── claimsathi.db-wal       # Auto-created by SQLite
├── claimsathi.db-shm       # Auto-created by SQLite
├── uploads/                # Private evidence storage (0700)
├── reports/                # Generated PDF report storage (0700)
└── backups/                # Automated SQLite online snapshots (0700)
```

> [!IMPORTANT]
> The database directory must reside on a **local, POSIX-compliant filesystem** (e.g. ext4, XFS, NTFS). Never place an active SQLite database on network filesystems (NFS, SMB, CIFS, GlusterFS) as unreliable file locking can cause database corruption.

---

## 3. Pre-Deployment Validation Procedure

Execute these verification commands prior to starting production web traffic:

### Step 1: Verify Schema Migrations Status
Run migration verification to confirm all tables and indexes are applied:
```bash
python -c "
import sys; sys.path.insert(0, 'backend'); import asyncio; from app.database import get_schema_migration_history
async def check():
    h = await get_schema_migration_history()
    print('Applied migrations count:', len(h))
    for m in h:
        print(f' - Version {m[\"version\"]}: {m[\"name\"]} (applied {m[\"applied_at\"]})')
asyncio.run(check())
"
```
*Expected Output:* Versions 1 (`001_initial_schema.sql`) and 2 (`002_add_foreign_keys_and_indexes.sql`) confirmed.

### Step 2: Verify Referential Integrity (Zero FK Violations)
```bash
python -c "
import sys; sys.path.insert(0, 'backend'); import asyncio; from app.database import verify_sqlite_foreign_keys
async def check():
    violations = await verify_sqlite_foreign_keys()
    if violations:
        print('CRITICAL: Foreign key violations detected:', violations)
        sys.exit(1)
    print('SUCCESS: Zero foreign key violations.')
asyncio.run(check())
"
```

### Step 3: Run Database Integrity Check
```bash
python -c "
import sqlite3
con = sqlite3.connect('claimsathi.db')
res = con.execute('PRAGMA integrity_check;').fetchone()[0]
print('Database integrity:', res)
assert res == 'ok'
"
```

### Step 4: Create Baseline Pre-Deployment Backup
```bash
python -c "
import sys; sys.path.insert(0, 'backend'); from app.database import create_sqlite_backup
path = create_sqlite_backup()
print('Pre-deployment baseline backup generated:', path)
"
```

---

## 4. Automated Backup Recommendation

Implement an hourly or daily scheduled backup job using the built-in online backup utility:

### Recommended Cron Job (e.g. `/etc/cron.hourly/claimsathi-backup`):
```bash
#!/bin/bash
set -e
python -c "import sys; sys.path.insert(0, '/opt/claimsathi/backend'); from app.database import create_sqlite_backup; create_sqlite_backup(backup_dir='/var/backups/claimsathi')"
# Retain backups for 14 days, delete older snapshots
find /var/backups/claimsathi/ -name "claimsathi_backup_*.db" -type f -mtime +14 -delete
```

Because `create_sqlite_backup` uses SQLite's native `sqlite3.backup` API:
- It operates completely non-blockingly while users are filing claims and uploading evidence.
- It produces an internally consistent snapshot with no torn pages.

---

## 5. Emergency Rollback Procedure

If a deployment or bad data migration must be reverted:

1. **Stop the Application Service:**
   ```bash
   systemctl stop claimsathi-backend
   ```
2. **Restore from the Latest Verified Snapshot:**
   ```bash
   python -c "
   import sys; sys.path.insert(0, 'backend'); from app.database import restore_sqlite_backup
   restore_sqlite_backup('/var/backups/claimsathi/claimsathi_backup_YYYYMMDD_HHMMSS.db')
   print('Restoration completed successfully.')
   "
   ```
3. **Verify Integrity of Restored Database:**
   ```bash
   python -c "
   import sys; sys.path.insert(0, 'backend'); import asyncio; from app.database import verify_sqlite_foreign_keys
   asyncio.run(verify_sqlite_foreign_keys())
   "
   ```
4. **Restart the Application Service:**
   ```bash
   systemctl start claimsathi-backend
   ```
5. **Verify API Health:**
   ```bash
   curl -f http://127.0.0.1:8080/api/health
   ```
