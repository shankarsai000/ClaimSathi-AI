"""
Migration Runner for ClaimSathi AI Sprint 1 Security RLS.
Executes 001_sprint1_security_rls.sql on PostgreSQL / Supabase
and verifies that RLS policies are applied across all tables.
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


async def run_migration():
    if not DATABASE_URL:
        print("[!] Error: DATABASE_URL not set in environment or backend/.env.")
        sys.exit(1)

    print(f"[*] Connecting to database...")
    sql_file = Path(__file__).resolve().parent / "001_sprint1_security_rls.sql"
    if not sql_file.exists():
        print(f"[!] Error: Migration file {sql_file} not found.")
        sys.exit(1)

    sql_content = sql_file.read_text(encoding="utf-8")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        print("[*] Applying Sprint 1 RLS Migration (001_sprint1_security_rls.sql)...")
        await conn.execute(sql_content)
        print("[+] Migration executed successfully!")

        print("\n[*] Verifying Row-Level Security policies on tables:")
        policies = await conn.fetch("""
            SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual
            FROM pg_policies
            WHERE schemaname = 'public'
            ORDER BY tablename, policyname;
        """)

        print(f"[+] Total Active RLS Policies in 'public' schema: {len(policies)}")
        for p in policies:
            print(f"  - Table: {p['tablename']:<22} | Policy: {p['policyname']:<32} | Command: {p['cmd']}")

        print("\n[*] Testing customer data isolation query simulation:")
        # Test under authenticated role (which does not have superuser/bypassrls)
        await conn.execute("SET ROLE authenticated;")
        await conn.execute("SET app.bypass_rls = 'false';")

        await conn.execute("SET app.current_customer_id = 'USR-100001';")
        claims_usr1 = await conn.fetch("SELECT id, customer_id FROM claims;")
        print(f"  - Claims visible to USR-100001: {[dict(c) for c in claims_usr1]}")

        await conn.execute("SET app.current_customer_id = 'USR-100002';")
        claims_usr2 = await conn.fetch("SELECT id, customer_id FROM claims;")
        print(f"  - Claims visible to USR-100002: {[dict(c) for c in claims_usr2]}")

        # Check that none overlap
        ids_usr1 = {c["id"] for c in claims_usr1}
        ids_usr2 = {c["id"] for c in claims_usr2}
        assert ids_usr1.isdisjoint(ids_usr2), "Isolation violation: Claim IDs overlap across customers!"
        assert len(ids_usr1) > 0, "USR-100001 should see their claims"
        assert len(ids_usr2) > 0, "USR-100002 should see their claims"
        print("[+] Customer isolation verified: Zero overlap between customer claims.")

        # Test 2: Unauthenticated / Unknown user
        await conn.execute("SET app.current_customer_id = 'USR-NONEXISTENT';")
        claims_unknown = await conn.fetch("SELECT id, customer_id FROM claims;")
        assert len(claims_unknown) == 0, "Unknown customer should see 0 claims under RLS!"
        print("[+] Unknown customer isolation verified: 0 claims returned.")

        # Reset session
        await conn.execute("RESET ROLE;")
        await conn.execute("RESET app.current_customer_id;")
        await conn.execute("RESET app.bypass_rls;")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
