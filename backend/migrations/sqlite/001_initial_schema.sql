-- ClaimSathi AI — SQLite Schema Migration 001: Initial Relational Tables
-- Baseline 12-table core schema with relational integrity and append-only audit logging

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);

-- 1. users: Customer profiles and credentials
CREATE TABLE IF NOT EXISTS users (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    declared_insurer TEXT DEFAULT 'Bharat General Insurance',
    account_status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- 2. user_consents: Privacy and evidence processing consent
CREATE TABLE IF NOT EXISTS user_consents (
    consent_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    data_processing_consent INTEGER DEFAULT 1,
    evidence_screening_consent INTEGER DEFAULT 1,
    retention_policy_acknowledged INTEGER DEFAULT 1,
    consented_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(customer_id) ON DELETE CASCADE
);

-- 3. conversations: Claim-related voice and text conversation turns
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    claim_id TEXT,
    user_id TEXT NOT NULL,
    language TEXT DEFAULT 'indic-auto',
    turns_json TEXT DEFAULT '[]',
    transcript_full TEXT DEFAULT '',
    session_status TEXT DEFAULT 'completed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(customer_id) ON DELETE CASCADE
);

-- 4. claims: Structured insurance claim records
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL DEFAULT 'USR-100001',
    insurance_type TEXT DEFAULT 'motor',
    policy_reference TEXT NOT NULL,
    insurer_name TEXT DEFAULT 'Bharat General Insurance',
    policy_type TEXT DEFAULT 'Comprehensive Motor Policy',
    incident_location TEXT NOT NULL,
    incident_date TEXT NOT NULL,
    vehicle_type TEXT NOT NULL,
    damage_description TEXT NOT NULL,
    people_involved TEXT DEFAULT 'Policyholder (Driver)',
    injuries_reported TEXT DEFAULT 'No physical injuries reported',
    detailed_statement TEXT DEFAULT '',
    transcript TEXT DEFAULT '',
    status TEXT DEFAULT 'confirmed',
    customer_confirmation INTEGER DEFAULT 1,
    report_status TEXT DEFAULT 'not_generated',
    insurer_submission_status TEXT DEFAULT 'not_submitted',
    is_demo INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES users(customer_id) ON DELETE RESTRICT
);

-- 5. claim_fields: Granular extracted/verified fields with confidence
CREATE TABLE IF NOT EXISTS claim_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    label TEXT NOT NULL,
    value TEXT,
    confidence TEXT DEFAULT 'high',
    is_edited INTEGER DEFAULT 0,
    is_verified INTEGER DEFAULT 0,
    follow_up_question TEXT,
    source TEXT DEFAULT 'customer_input',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);

-- 6. timeline_events: Chronological claim milestones
CREATE TABLE IF NOT EXISTS timeline_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    source TEXT DEFAULT 'system',
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);

-- 7. evidence_assets: Metadata and object store pointers for preserved media
CREATE TABLE IF NOT EXISTS evidence_assets (
    evidence_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    label TEXT NOT NULL,
    media_type TEXT NOT NULL,
    capture_method TEXT NOT NULL,
    capture_session_id TEXT,
    original_filename TEXT NOT NULL,
    detected_mime TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    exif_metadata_json TEXT DEFAULT '{}',
    upload_timestamp TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(customer_id) ON DELETE RESTRICT
);

-- 8. evidence_checks: AI provenance, SHA-256 and pHash cross-claim duplicate results
CREATE TABLE IF NOT EXISTS evidence_checks (
    check_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    perceptual_hash TEXT,
    magic_bytes_valid INTEGER DEFAULT 1,
    detected_format TEXT DEFAULT 'unknown',
    malware_scan_status TEXT DEFAULT 'clean',
    c2pa_found INTEGER DEFAULT 0,
    synthid_found INTEGER DEFAULT 0,
    provenance_result TEXT NOT NULL,
    provenance_system_response TEXT NOT NULL,
    provenance_details_json TEXT DEFAULT '{}',
    duplicate_status TEXT DEFAULT 'unique',
    duplicate_match_type TEXT,
    matched_claim_id TEXT,
    matched_evidence_id TEXT,
    hamming_distance INTEGER,
    requires_human_review INTEGER DEFAULT 0,
    screening_outcome_label TEXT DEFAULT '',
    checked_at TEXT NOT NULL,
    FOREIGN KEY (evidence_id) REFERENCES evidence_assets(evidence_id) ON DELETE CASCADE,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);

-- 9. reports: Generated 9-section Dossier, Canonical JSON & PDF references
CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    version TEXT NOT NULL,
    dossier_json TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    pdf_storage_path TEXT NOT NULL,
    sha256_hash TEXT,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(customer_id) ON DELETE RESTRICT
);

-- 10. claim_status_events: Historical status change events
CREATE TABLE IF NOT EXISTS claim_status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);

-- 11. audit_logs: Security and application access events (Append-only)
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    claim_id TEXT,
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    ip_address TEXT DEFAULT '127.0.0.1',
    timestamp TEXT NOT NULL,
    resource_type TEXT DEFAULT 'claim',
    resource_id TEXT,
    outcome TEXT DEFAULT 'SUCCESS'
);

-- 12. capture_sessions: Server-generated live guided camera sessions
CREATE TABLE IF NOT EXISTS capture_sessions (
    session_id TEXT PRIMARY KEY,
    claim_id TEXT,
    user_id TEXT NOT NULL,
    instructions_json TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(customer_id) ON DELETE CASCADE
);

-- 13. insurer_submissions: Mock Insurer Gateway submission logs & status
CREATE TABLE IF NOT EXISTS insurer_submissions (
    submission_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    recipient_display_name TEXT NOT NULL,
    adapter_payload_json TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    insurer_claim_reference TEXT NOT NULL,
    processing_status TEXT NOT NULL,
    pipeline_steps_json TEXT DEFAULT '[]',
    submitted_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);
