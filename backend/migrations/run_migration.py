"""
Migration Runner for ClaimSathi AI Sprint 1.1 Zero-Bypass Security RLS.
Executes 001_sprint1_security_rls.sql on PostgreSQL / Supabase
and verifies that RLS policies are applied across all tables with zero bypass mechanisms.
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


async def verify_rls_isolation_with_adversarial_bypass(database_url: str) -> bool:
    """Verify RLS isolation and thwart adversarial bypass using SET app.bypass_rls = 'true'."""
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute("SET ROLE authenticated;")

        # Test 1: Customer USR-100001
        await conn.execute("SET app.current_customer_id = 'USR-100001';")
        claims_usr1 = await conn.fetch("SELECT id, customer_id FROM claims;")

        # Test 2: Customer USR-100002
        await conn.execute("SET app.current_customer_id = 'USR-100002';")
        claims_usr2 = await conn.fetch("SELECT id, customer_id FROM claims;")

        ids_usr1 = {c["id"] for c in claims_usr1}
        ids_usr2 = {c["id"] for c in claims_usr2}
        assert ids_usr1.isdisjoint(ids_usr2), "Isolation violation: Claim IDs overlap across customers!"
        assert len(ids_usr1) > 0, "USR-100001 should see their claims"
        assert len(ids_usr2) > 0, "USR-100002 should see their claims"

        # Test 3: Adversarial Bypass Attempt via GUC parameter (app.bypass_rls)
        await conn.execute("SET app.current_customer_id = 'USR-100001';")
        await conn.execute("SET app.bypass_rls = 'true';")
        claims_bypass_attempt = await conn.fetch("SELECT id, customer_id FROM claims;")
        ids_after_bypass = {c["id"] for c in claims_bypass_attempt}
        assert ids_after_bypass == ids_usr1, "SECURITY BREACH: app.bypass_rls succeeded in leaking other customers' claims!"

        # Test 4: Unknown user context returns 0 rows
        await conn.execute("SET app.current_customer_id = 'USR-UNKNOWN';")
        claims_unknown = await conn.fetch("SELECT id, customer_id FROM claims;")
        assert len(claims_unknown) == 0, "Unknown customer should see 0 claims under RLS!"

        # Test 5: Unset / empty context returns 0 rows
        await conn.execute("RESET app.current_customer_id;")
        claims_unset = await conn.fetch("SELECT id, customer_id FROM claims;")
        assert len(claims_unset) == 0, "Unset customer ID should see 0 claims under RLS!"

        await conn.execute("RESET ROLE;")
        await conn.execute("RESET app.current_customer_id;")
        await conn.execute("RESET app.bypass_rls;")
        return True
    finally:
        await conn.close()


async def verify_audit_log_immutability(database_url: str) -> bool:
    """Verify that ordinary authenticated application roles cannot UPDATE or DELETE audit_logs."""
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute("SET ROLE authenticated;")
        await conn.execute("SET app.current_customer_id = 'USR-100001';")

        try:
            res = await conn.execute("UPDATE audit_logs SET details = 'tampered' WHERE user_id = 'USR-100001';")
            assert res in ("UPDATE 0", None)
        except asyncpg.exceptions.InsufficientPrivilegeError:
            pass

        try:
            res = await conn.execute("DELETE FROM audit_logs WHERE user_id = 'USR-100001';")
            assert res in ("DELETE 0", None)
        except asyncpg.exceptions.InsufficientPrivilegeError:
            pass

        await conn.execute("RESET ROLE;")
        await conn.execute("RESET app.current_customer_id;")
        return True
    finally:
        await conn.close()


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
        print("[*] Applying Sprint 1.1 Zero-Bypass RLS Migration (001_sprint1_security_rls.sql)...")
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

    finally:
        await conn.close()

    print("\n[*] Testing customer data isolation query simulation under role 'authenticated':")
    await verify_rls_isolation_with_adversarial_bypass(DATABASE_URL)
    print("[+] Customer isolation & zero bypass verified: app.bypass_rls has zero effect.")

    print("\n[*] Testing audit log immutability:")
    await verify_audit_log_immutability(DATABASE_URL)
    print("[+] Audit log immutability verified: UPDATE/DELETE safely rejected.")


if __name__ == "__main__":
    asyncio.run(run_migration())
