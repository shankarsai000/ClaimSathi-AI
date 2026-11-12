"""
Emergency Rollback Script for Sprint 1 RLS Policies.
Safely removes the 17 RLS policies if an emergency rollback to Phase 1 state is required.
"""

import os
import sys
import asyncio
import asyncpg
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

ROLLBACK_SQL = """
ALTER TABLE IF EXISTS users NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS user_consents NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS conversations NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS claims NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS claim_fields NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS evidence_assets NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS evidence_checks NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS reports NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS claim_status_events NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS timeline_events NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS capture_sessions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS insurer_submissions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS audit_logs NO FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_isolation_policy ON users;
DROP POLICY IF EXISTS user_consents_isolation_policy ON user_consents;
DROP POLICY IF EXISTS conversations_isolation_policy ON conversations;
DROP POLICY IF EXISTS claims_isolation_select ON claims;
DROP POLICY IF EXISTS claims_isolation_insert ON claims;
DROP POLICY IF EXISTS claims_isolation_update ON claims;
DROP POLICY IF EXISTS claims_isolation_delete ON claims;
DROP POLICY IF EXISTS claim_fields_isolation_policy ON claim_fields;
DROP POLICY IF EXISTS evidence_assets_isolation_policy ON evidence_assets;
DROP POLICY IF EXISTS evidence_checks_isolation_policy ON evidence_checks;
DROP POLICY IF EXISTS reports_isolation_policy ON reports;
DROP POLICY IF EXISTS claim_status_events_isolation_policy ON claim_status_events;
DROP POLICY IF EXISTS timeline_events_isolation_policy ON timeline_events;
DROP POLICY IF EXISTS capture_sessions_isolation_policy ON capture_sessions;
DROP POLICY IF EXISTS insurer_submissions_isolation_policy ON insurer_submissions;
DROP POLICY IF EXISTS audit_logs_isolation_select ON audit_logs;
DROP POLICY IF EXISTS audit_logs_isolation_insert ON audit_logs;
"""

async def rollback():
    if not DATABASE_URL:
        print("[!] Error: DATABASE_URL not set.")
        sys.exit(1)

    print("[*] Connecting to database for Sprint 1 RLS rollback...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(ROLLBACK_SQL)
        print("[+] Sprint 1 RLS policies successfully rolled back.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(rollback())
