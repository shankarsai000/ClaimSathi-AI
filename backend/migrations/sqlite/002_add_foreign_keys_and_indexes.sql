-- ClaimSathi AI — SQLite Schema Migration 002: Indexes & Relational Performance
-- Creates 20 high-performance indexes covering all foreign keys, status filters, and search columns

-- 1. Claims Indexes
CREATE INDEX IF NOT EXISTS idx_claims_customer_id ON claims(customer_id);
CREATE INDEX IF NOT EXISTS idx_claims_created_at ON claims(created_at);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);

-- 2. Claim Fields Indexes
CREATE INDEX IF NOT EXISTS idx_claim_fields_claim_id ON claim_fields(claim_id);

-- 3. Conversations Indexes
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_claim_id ON conversations(claim_id);

-- 4. Timeline Events Indexes
CREATE INDEX IF NOT EXISTS idx_timeline_events_claim_id ON timeline_events(claim_id);

-- 5. Evidence Assets Indexes
CREATE INDEX IF NOT EXISTS idx_evidence_assets_claim_id ON evidence_assets(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_assets_user_id ON evidence_assets(user_id);

-- 6. Evidence Checks Fingerprint & Cross-Claim Match Indexes
CREATE INDEX IF NOT EXISTS idx_evidence_checks_sha256 ON evidence_checks(sha256_hash);
CREATE INDEX IF NOT EXISTS idx_evidence_checks_claim_id ON evidence_checks(claim_id);

-- 7. Reports Indexes
CREATE INDEX IF NOT EXISTS idx_reports_claim_id ON reports(claim_id);
CREATE INDEX IF NOT EXISTS idx_reports_user_id ON reports(user_id);

-- 8. Claim Status Events Indexes
CREATE INDEX IF NOT EXISTS idx_claim_status_events_claim_id ON claim_status_events(claim_id);

-- 9. Audit Logs Forensic Query Indexes
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_claim_id ON audit_logs(claim_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);

-- 10. Capture Sessions Indexes
CREATE INDEX IF NOT EXISTS idx_capture_sessions_user_id ON capture_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_claim_id ON capture_sessions(claim_id);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_status ON capture_sessions(status);

-- 11. Insurer Submissions Indexes
CREATE INDEX IF NOT EXISTS idx_insurer_submissions_claim_id ON insurer_submissions(claim_id);
