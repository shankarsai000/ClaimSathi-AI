-- ==============================================================================
-- ClaimSathi AI — Sprint 1: Security Hardening & Row-Level Security (RLS) Migration
-- Target: PostgreSQL / Supabase
-- Purpose:
--   1. Enforce strict multi-tenant customer-level data isolation via RLS policies.
--   2. Ensure claims, evidence assets, reports, conversations and consents can
--      ONLY be accessed by the authenticated customer who owns them.
--   3. Guard audit logs against modification or deletion (append-only).
--   4. Support both PostgreSQL session variable (`app.current_customer_id`) and
--      Supabase PostgREST JWT claims (`request.jwt.claims ->> 'sub'`).
-- ==============================================================================

-- 1. Ensure schema completeness & indexes
ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45) DEFAULT '127.0.0.1';
ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS resource_type VARCHAR(64);
ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS resource_id VARCHAR(64);
ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS outcome VARCHAR(32) DEFAULT 'SUCCESS';

CREATE INDEX IF NOT EXISTS idx_claims_customer_id ON claims(customer_id);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_evidence_assets_claim_id ON evidence_assets(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_assets_customer_id ON evidence_assets(customer_id);
CREATE INDEX IF NOT EXISTS idx_evidence_checks_asset_id ON evidence_checks(asset_id);
CREATE INDEX IF NOT EXISTS idx_evidence_checks_claim_id ON evidence_checks(claim_id);
CREATE INDEX IF NOT EXISTS idx_reports_claim_id ON reports(claim_id);
CREATE INDEX IF NOT EXISTS idx_conversations_customer_id ON conversations(customer_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_claim_id ON audit_logs(claim_id);

-- 2. Helper function to extract current authenticated customer ID
-- Reads from session context (app.current_customer_id) or Supabase JWT context
CREATE OR REPLACE FUNCTION current_customer_id() RETURNS TEXT AS $$
BEGIN
    -- Check for bypass flag (e.g. system maintenance worker or tests running with bypass flag)
    IF current_setting('app.bypass_rls', true) = 'true' THEN
        RETURN 'BYPASS';
    END IF;

    -- Return session parameter or JWT sub claim
    RETURN COALESCE(
        NULLIF(current_setting('app.current_customer_id', true), ''),
        NULLIF(current_setting('request.jwt.claim.sub', true), ''),
        (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')
    );
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- 3. Enable RLS and FORCE ROW LEVEL SECURITY on all customer-sensitive tables
-- FORCE ensures even table owner / connection role adheres to isolation policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE user_consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_consents FORCE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;
ALTER TABLE claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims FORCE ROW LEVEL SECURITY;
ALTER TABLE claim_fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_fields FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_assets FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_checks FORCE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports FORCE ROW LEVEL SECURITY;
ALTER TABLE claim_status_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_status_events FORCE ROW LEVEL SECURITY;
ALTER TABLE timeline_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE timeline_events FORCE ROW LEVEL SECURITY;
ALTER TABLE capture_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE capture_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE insurer_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE insurer_submissions FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

-- 4. Drop existing policies to allow idempotent execution
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

-- 5. Create explicit Row-Level Security policies

-- Table: users
CREATE POLICY users_isolation_policy ON users
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    );

-- Table: user_consents
CREATE POLICY user_consents_isolation_policy ON user_consents
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    );

-- Table: conversations
CREATE POLICY conversations_isolation_policy ON conversations
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    );

-- Table: claims
CREATE POLICY claims_isolation_select ON claims
    FOR SELECT
    USING (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    );

CREATE POLICY claims_isolation_insert ON claims
    FOR INSERT
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    );

CREATE POLICY claims_isolation_update ON claims
    FOR UPDATE
    USING (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    );

CREATE POLICY claims_isolation_delete ON claims
    FOR DELETE
    USING (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
    );

-- Table: claim_fields
CREATE POLICY claim_fields_isolation_policy ON claim_fields
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    );

-- Table: evidence_assets
CREATE POLICY evidence_assets_isolation_policy ON evidence_assets
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    );

-- Table: evidence_checks
CREATE POLICY evidence_checks_isolation_policy ON evidence_checks
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
        OR asset_id IN (
            SELECT asset_id FROM evidence_assets WHERE customer_id = current_customer_id()
        )
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
        OR asset_id IN (
            SELECT asset_id FROM evidence_assets WHERE customer_id = current_customer_id()
        )
    );

-- Table: reports
CREATE POLICY reports_isolation_policy ON reports
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    );

-- Table: claim_status_events
CREATE POLICY claim_status_events_isolation_policy ON claim_status_events
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    );

-- Table: timeline_events
CREATE POLICY timeline_events_isolation_policy ON timeline_events
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    );

-- Table: capture_sessions
CREATE POLICY capture_sessions_isolation_policy ON capture_sessions
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
        OR (
            claim_id IS NOT NULL AND claim_id IN (
                SELECT id FROM claims WHERE customer_id = current_customer_id()
            )
        )
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR customer_id = current_customer_id()
        OR (
            claim_id IS NOT NULL AND claim_id IN (
                SELECT id FROM claims WHERE customer_id = current_customer_id()
            )
        )
    );

-- Table: insurer_submissions
CREATE POLICY insurer_submissions_isolation_policy ON insurer_submissions
    FOR ALL
    USING (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    )
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR claim_id IN (
            SELECT id FROM claims WHERE customer_id = current_customer_id()
        )
    );

-- Table: audit_logs (Append-Only: SELECT and INSERT only, NO UPDATE, NO DELETE)
CREATE POLICY audit_logs_isolation_select ON audit_logs
    FOR SELECT
    USING (
        current_customer_id() = 'BYPASS'
        OR user_id = current_customer_id()
    );

CREATE POLICY audit_logs_isolation_insert ON audit_logs
    FOR INSERT
    WITH CHECK (
        current_customer_id() = 'BYPASS'
        OR user_id = current_customer_id()
    );

-- 6. Permissions: Ensure anon and authenticated roles can query public tables subject to RLS
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO anon, authenticated;

