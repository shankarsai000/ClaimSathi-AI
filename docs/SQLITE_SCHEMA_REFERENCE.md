# ClaimSathi AI — SQLite Schema Reference & Data Dictionary
**Document Version:** 1.0.0  
**Sprint Baseline:** Sprint 1.2  
**Target Engine:** SQLite 3.37+ (WAL mode, Foreign Keys ON)

---

## 1. Overview & Data Privacy Classifications

ClaimSathi AI handles sensitive insurance claim intake, policyholder data, and evidence assets. All data stored in SQLite is categorized into four data classification tiers:

1. **PII (Personally Identifiable Information):** Customer names, phone numbers, email addresses, vehicle registration identifiers, and policy numbers. Protected by strict claim-level ownership and access token verification.
2. **Evidence & Forensics:** Image/video metadata, cryptographic fingerprints (SHA-256), perceptual hashes (pHash), EXIF provenance, and authenticity verification outcomes.
3. **Operational & Telemetry:** Multi-lingual voice transcripts, assistant dialogue states, and claim status timeline events.
4. **Append-Only Compliance & Forensics:** Immutable audit logs capturing every creation, update, view, download, and deletion event. Audit logs are preserved permanently even when associated claims are deleted.

---

## 2. Table-by-Table Data Dictionary

### Table 1: `schema_migrations`
- **Purpose:** Tracks versioned database schema migration scripts and checksums.
- **Classification:** System / Operational Metadata.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `version` | `INTEGER` | `PRIMARY KEY` | Sequential integer version (e.g. `1`, `2`) |
| `name` | `TEXT` | `NOT NULL` | Migration filename (e.g. `001_initial_schema.sql`) |
| `applied_at` | `TEXT` | `NOT NULL` | ISO 8601 UTC timestamp of execution |
| `checksum` | `TEXT` | `NOT NULL` | SHA-256 hash of the applied script contents |

---

### Table 2: `users`
- **Purpose:** Policyholder credentials, declared insurer, and profile identifiers.
- **Classification:** Sensitive PII / Credentials.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `customer_id` | `TEXT` | `PRIMARY KEY` | Unique customer format (e.g. `USR-100001`) |
| `name` | `TEXT` | `NOT NULL` | Full customer legal name |
| `email` | `TEXT` | `UNIQUE NOT NULL` | Verified login email address |
| `phone` | `TEXT` | `NOT NULL` | Verified mobile phone number |
| `password_hash` | `TEXT` | `NOT NULL` | PBKDF2-HMAC-SHA256 salted password hash |
| `declared_insurer` | `TEXT` | `DEFAULT 'Bharat General Insurance'` | Primary insurer name |
| `account_status` | `TEXT` | `DEFAULT 'active'` | Status (`active`, `suspended`) |
| `created_at` | `TEXT` | `NOT NULL` | ISO 8601 account creation timestamp |
| `updated_at` | `TEXT` | `NULLABLE` | ISO 8601 profile update timestamp |

---

### Table 3: `user_consents`
- **Purpose:** Privacy policy, DPDP Act compliance, and evidence processing consent flags.
- **Classification:** Legal Compliance / Consent Records.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `consent_id` | `TEXT` | `PRIMARY KEY` | Consent record ID (`CNS-100001`) |
| `user_id` | `TEXT` | `NOT NULL, FK -> users(customer_id) ON DELETE CASCADE` | Associated policyholder |
| `data_processing_consent` | `INTEGER` | `DEFAULT 1` | DPDP processing agreement (0/1) |
| `evidence_screening_consent` | `INTEGER` | `DEFAULT 1` | Media provenance screening consent (0/1) |
| `retention_policy_acknowledged` | `INTEGER` | `DEFAULT 1` | Evidence retention agreement (0/1) |
| `consented_at` | `TEXT` | `NOT NULL` | ISO 8601 timestamp of consent |
| `revoked_at` | `TEXT` | `NULLABLE` | ISO 8601 timestamp if revoked |

---

### Table 4: `conversations`
- **Purpose:** Stores conversational voice/text intake sessions and multilingual turn histories.
- **Classification:** Confidential Customer Incident Data.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `conversation_id` | `TEXT` | `PRIMARY KEY` | Session UUID |
| `claim_id` | `TEXT` | `NULLABLE, FK -> claims(id) ON DELETE SET NULL` | Associated claim (if bound) |
| `user_id` | `TEXT` | `NOT NULL, FK -> users(customer_id) ON DELETE CASCADE` | Policyholder ID |
| `language` | `TEXT` | `DEFAULT 'indic-auto'` | Detected or requested language |
| `turns_json` | `TEXT` | `DEFAULT '[]'` | Serialized array of user/assistant turns |
| `transcript_full` | `TEXT` | `DEFAULT ''` | Full cumulative speech transcript |
| `session_status` | `TEXT` | `DEFAULT 'completed'` | Status (`active`, `completed`) |
| `created_at` | `TEXT` | `NOT NULL` | ISO 8601 timestamp |
| `updated_at` | `TEXT` | `NOT NULL` | ISO 8601 timestamp |

**Indexes:** `idx_conversations_user_id`, `idx_conversations_claim_id`

---

### Table 5: `claims`
- **Purpose:** Core structured claim dossier header and incident parameters.
- **Classification:** Highly Confidential Insurance Claim Data.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `TEXT` | `PRIMARY KEY` | Claim reference (`CS-2026-000124` or `DEMO-...`) |
| `customer_id` | `TEXT` | `NOT NULL, FK -> users(customer_id) ON DELETE RESTRICT` | Owner customer ID |
| `insurance_type` | `TEXT` | `DEFAULT 'motor'` | Insurance category (`motor`, `health`, etc.) |
| `policy_reference` | `TEXT` | `NOT NULL` | Policy number (e.g. `MOT-2026-KA-44210`) |
| `insurer_name` | `TEXT` | `DEFAULT 'Bharat General Insurance'` | Declared insurance company |
| `policy_type` | `TEXT` | `DEFAULT 'Comprehensive Motor Policy'` | Policy tier |
| `incident_location` | `TEXT` | `NOT NULL` | City and landmark of incident |
| `incident_date` | `TEXT` | `NOT NULL` | Date of incident (`YYYY-MM-DD`) |
| `vehicle_type` | `TEXT` | `NOT NULL` | Vehicle class (`car`, `bike`, `commercial`) |
| `damage_description` | `TEXT` | `NOT NULL` | Plain-text summary of damage |
| `people_involved` | `TEXT` | `DEFAULT 'Policyholder (Driver)'` | Driver and passenger descriptions |
| `injuries_reported` | `TEXT` | `DEFAULT 'No physical injuries reported'` | Injury declaration |
| `detailed_statement` | `TEXT` | `DEFAULT ''` | Formal synthesized incident narrative |
| `transcript` | `TEXT` | `DEFAULT ''` | Raw vernacular transcript from intake |
| `status` | `TEXT` | `DEFAULT 'confirmed'` | Status (`draft`, `confirmed`, `submitted`, `archived`) |
| `customer_confirmation` | `INTEGER` | `DEFAULT 1` | Customer confirmation flag (0/1) |
| `report_status` | `TEXT` | `DEFAULT 'not_generated'` | Report status (`not_generated`, `generated`) |
| `insurer_submission_status` | `TEXT` | `DEFAULT 'not_submitted'` | Gateway status (`not_submitted`, `simulated_submitted`) |
| `is_demo` | `INTEGER` | `DEFAULT 1` | Simulation flag (0/1) |
| `created_at` | `TEXT` | `NOT NULL` | ISO 8601 creation timestamp |
| `updated_at` | `TEXT` | `NOT NULL` | ISO 8601 modification timestamp |

**Indexes:** `idx_claims_customer_id`, `idx_claims_created_at`, `idx_claims_status`

---

### Table 6: `claim_fields`
- **Purpose:** Normalized field extractions with verification confidence and follow-ups.
- **Classification:** Structured Claim Fields.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Auto-increment ID |
| `claim_id` | `TEXT` | `NOT NULL, FK -> claims(id) ON DELETE CASCADE` | Associated claim ID |
| `field_name` | `TEXT` | `NOT NULL` | Canonical field key (e.g. `vehicle_type`) |
| `label` | `TEXT` | `NOT NULL` | Human-readable label |
| `value` | `TEXT` | `NULLABLE` | Confirmed field value |
| `confidence` | `TEXT` | `DEFAULT 'high'` | Extraction confidence (`high`, `medium`, `low`) |
| `is_edited` | `INTEGER` | `DEFAULT 0` | Edited by policyholder (0/1) |
| `is_verified` | `INTEGER` | `DEFAULT 0` | Policyholder verified (0/1) |
| `follow_up_question` | `TEXT` | `NULLABLE` | Follow-up question if field was missing |
| `source` | `TEXT` | `DEFAULT 'customer_input'` | Field origin (`customer_input`, `ai_extracted`) |
| `updated_at` | `TEXT` | `NOT NULL` | ISO 8601 timestamp |

**Indexes:** `idx_claim_fields_claim_id`

---

### Table 7: `timeline_events`
- **Purpose:** Chronological audit milestones visible to policyholder on claim detail.
- **Classification:** User-Facing Timeline History.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Auto-increment ID |
| `claim_id` | `TEXT` | `NOT NULL, FK -> claims(id) ON DELETE CASCADE` | Associated claim ID |
| `title` | `TEXT` | `NOT NULL` | Milestone headline |
| `description` | `TEXT` | `NOT NULL` | Milestone narrative |
| `timestamp` | `TEXT` | `NOT NULL` | ISO 8601 timestamp |
| `source` | `TEXT` | `DEFAULT 'system'` | Event generator (`system`, `user`, `insurer`) |

**Indexes:** `idx_timeline_events_claim_id`

---

### Table 8: `evidence_assets`
- **Purpose:** Storage pointers and metadata for uploaded and live camera media.
- **Classification:** Sensitive Evidence Metadata.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `evidence_id` | `TEXT` | `PRIMARY KEY` | Evidence asset ID (`EVD-XXXXXXX`) |
| `claim_id` | `TEXT` | `NOT NULL, FK -> claims(id) ON DELETE CASCADE` | Associated claim ID |
| `user_id` | `TEXT` | `NOT NULL, FK -> users(customer_id) ON DELETE RESTRICT` | Uploader customer ID |
| `label` | `TEXT` | `NOT NULL` | Angle/damage label (e.g. `front_bumper`) |
| `media_type` | `TEXT` | `NOT NULL` | Media format (`image`, `video`) |
| `capture_method` | `TEXT` | `NOT NULL` | Capture source (`upload`, `live_guided_camera`) |
| `capture_session_id` | `TEXT` | `NULLABLE` | Session ID if live camera |
| `original_filename` | `TEXT` | `NOT NULL` | Sanitized original client filename |
| `detected_mime` | `TEXT` | `NOT NULL` | Validated MIME type (`image/jpeg`, `image/png`, `video/mp4`) |
| `file_size_bytes` | `INTEGER` | `NOT NULL` | Size on disk in bytes |
| `storage_path` | `TEXT` | `NOT NULL` | File path in private storage (`uploads/xyz.jpg`) |
| `width` | `INTEGER` | `NULLABLE` | Pixel width |
| `height` | `INTEGER` | `NULLABLE` | Pixel height |
| `exif_metadata_json` | `TEXT` | `DEFAULT '{}'` | Serialized EXIF tags and GPS data |
| `upload_timestamp` | `TEXT` | `NOT NULL` | ISO 8601 upload timestamp |

**Indexes:** `idx_evidence_assets_claim_id`, `idx_evidence_assets_user_id`

---

### Table 9: `evidence_checks`
- **Purpose:** Cryptographic integrity, 64-bit pHash, C2PA/SynthID provenance, and duplicate screening.
- **Classification:** Forensic Integrity Screening Outcomes.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `check_id` | `TEXT` | `PRIMARY KEY` | Check verification ID (`CHK-XXXXXXX`) |
| `evidence_id` | `TEXT` | `NOT NULL, FK -> evidence_assets(evidence_id) ON DELETE CASCADE` | Target asset |
| `claim_id` | `TEXT` | `NOT NULL, FK -> claims(id) ON DELETE CASCADE` | Associated claim |
| `sha256_hash` | `TEXT` | `NOT NULL` | 64-character SHA-256 byte digest |
| `perceptual_hash` | `TEXT` | `NULLABLE` | 16-character hex 64-bit perceptual hash |
| `magic_bytes_valid` | `INTEGER` | `DEFAULT 1` | Magic byte header check (0/1) |
| `detected_format` | `TEXT` | `DEFAULT 'unknown'` | Binary detected format |
| `malware_scan_status` | `TEXT` | `DEFAULT 'clean'` | Antivirus screening status |
| `c2pa_found` | `INTEGER` | `DEFAULT 0` | C2PA provenance manifest detected (0/1) |
| `synthid_found` | `INTEGER` | `DEFAULT 0` | Google SynthID watermark detected (0/1) |
| `provenance_result` | `TEXT` | `NOT NULL` | Provenance label (`authentic`, `ai_generated`, `inconclusive`) |
| `provenance_system_response`| `TEXT` | `NOT NULL` | Diagnostic summary message |
| `provenance_details_json` | `TEXT` | `DEFAULT '{}'` | Technical metadata report |
| `duplicate_status` | `TEXT` | `DEFAULT 'unique'` | Duplicate screening (`unique`, `exact_duplicate`, `perceptual_match`) |
| `duplicate_match_type` | `TEXT` | `NULLABLE` | Match algorithm (`sha256_exact`, `phash_near`) |
| `matched_claim_id` | `TEXT` | `NULLABLE` | Matched claim ID (privacy redacted on API) |
| `matched_evidence_id` | `TEXT` | `NULLABLE` | Matched evidence asset ID |
| `hamming_distance` | `INTEGER` | `NULLABLE` | pHash Hamming distance (0 to 64) |
| `requires_human_review` | `INTEGER` | `DEFAULT 0` | Fraud alert flag (0/1) |
| `screening_outcome_label` | `TEXT` | `DEFAULT ''` | Final badge label |
| `checked_at` | `TEXT` | `NOT NULL` | ISO 8601 analysis timestamp |

**Indexes:** `idx_evidence_checks_sha256`, `idx_evidence_checks_claim_id`

---

### Table 10: `reports`
- **Purpose:** Generated 9-Section Professional Claim Dossiers, Canonical Schemas, and PDF files.
- **Classification:** Formal Claim Dossiers & Legal Reports.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `report_id` | `TEXT` | `PRIMARY KEY` | Report ID (`REP-XXXXXXX`) |
| `claim_id` | `TEXT` | `NOT NULL, FK -> claims(id) ON DELETE CASCADE` | Associated claim ID |
| `user_id` | `TEXT` | `NOT NULL, FK -> users(customer_id) ON DELETE RESTRICT` | Requesting customer ID |
| `version` | `TEXT` | `NOT NULL` | Dossier version (e.g. `1.0`) |
| `dossier_json` | `TEXT` | `NOT NULL` | Complete 9-section dossier JSON |
| `canonical_json` | `TEXT` | `NOT NULL` | Layer 1 ClaimSathi canonical interchange JSON |
| `pdf_storage_path` | `TEXT` | `NOT NULL` | Private disk path to generated PDF |
| `sha256_hash` | `TEXT` | `NULLABLE` | Cryptographic hash of the binary PDF report |
| `generated_at` | `TEXT` | `NOT NULL` | ISO 8601 generation timestamp |

**Indexes:** `idx_reports_claim_id`, `idx_reports_user_id`

---

### Table 11: `claim_status_events`
- **Purpose:** Internal state transition tracking (e.g. `draft` -> `confirmed` -> `submitted`).
- **Classification:** Claim Workflow Events.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Auto-increment ID |
| `claim_id` | `TEXT` | `NOT NULL, FK -> claims(id) ON DELETE CASCADE` | Target claim ID |
| `status` | `TEXT` | `NOT NULL` | Target status |
| `title` | `TEXT` | `NOT NULL` | Transition title |
| `description` | `TEXT` | `NOT NULL` | Transition details |
| `timestamp` | `TEXT` | `NOT NULL` | ISO 8601 timestamp |

**Indexes:** `idx_claim_status_events_claim_id`

---

### Table 12: `audit_logs`
- **Purpose:** Append-only security and forensic access logs. **Never deleted.**
- **Classification:** Immutable Security Audit Trail.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `log_id` | `TEXT` | `PRIMARY KEY` | Audit event ID (`AUD-XXXXXXX`) |
| `user_id` | `TEXT` | `NOT NULL` | Actor customer ID or `ANONYMOUS` |
| `claim_id` | `TEXT` | `NULLABLE` | Associated claim (retained even after claim deletion) |
| `action` | `TEXT` | `NOT NULL` | Security event (`CLAIM_CREATED`, `CLAIM_DELETED`, `ACCESS_DENIED_CROSS_CUSTOMER`) |
| `details` | `TEXT` | `NOT NULL` | Descriptive audit details (credentials masked) |
| `ip_address` | `TEXT` | `DEFAULT '127.0.0.1'` | Client IP address |
| `resource_type` | `TEXT` | `DEFAULT 'claim'` | Target resource type (`claim`, `evidence`, `auth`) |
| `resource_id` | `TEXT` | `NULLABLE` | Resource identifier |
| `outcome` | `TEXT` | `DEFAULT 'SUCCESS'` | Outcome (`SUCCESS`, `DENIED`, `FAILURE`) |
| `timestamp` | `TEXT` | `NOT NULL` | ISO 8601 UTC timestamp |

**Indexes:** `idx_audit_logs_user_id`, `idx_audit_logs_claim_id`, `idx_audit_logs_timestamp`

---

### Table 13: `capture_sessions`
- **Purpose:** Server-generated, time-bounded live camera capture sessions.
- **Classification:** Session Security & Ephemeral Tokens.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `session_id` | `TEXT` | `PRIMARY KEY` | Session UUID |
| `claim_id` | `TEXT` | `NULLABLE, FK -> claims(id) ON DELETE SET NULL` | Target claim (bound upon upload) |
| `user_id` | `TEXT` | `NOT NULL, FK -> users(customer_id) ON DELETE CASCADE` | Creator customer ID |
| `instructions_json` | `TEXT` | `NOT NULL` | Randomized capture directives |
| `status` | `TEXT` | `DEFAULT 'active'` | State (`active`, `completed`, `expired`) |
| `created_at` | `TEXT` | `NOT NULL` | ISO 8601 creation timestamp |
| `completed_at` | `TEXT` | `NULLABLE` | ISO 8601 completion timestamp |

**Indexes:** `idx_capture_sessions_user_id`, `idx_capture_sessions_claim_id`, `idx_capture_sessions_status`

---

### Table 14: `insurer_submissions`
- **Purpose:** Carrier adapter translation payloads and simulated insurer submissions.
- **Classification:** Outbound Carrier Integration Data.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `submission_id` | `TEXT` | `PRIMARY KEY` | Submission UUID (`SUB-XXXXXXX`) |
| `claim_id` | `TEXT` | `NOT NULL, FK -> claims(id) ON DELETE CASCADE` | Insured claim reference |
| `recipient` | `TEXT` | `NOT NULL` | Target carrier code (`bharat_general`, `icici_lombard`) |
| `recipient_display_name` | `TEXT` | `NOT NULL` | Carrier name |
| `adapter_payload_json` | `TEXT` | `NOT NULL` | Carrier-specific mapped payload preview |
| `delivery_status` | `TEXT` | `NOT NULL` | Delivery outcome (`delivered`, `pending`) |
| `insurer_claim_reference` | `TEXT` | `NOT NULL` | Carrier tracking number (`BGI-2026-CLM-...`) |
| `processing_status` | `TEXT` | `NOT NULL` | Adjudication state (`accepted`, `under_review`) |
| `pipeline_steps_json` | `TEXT` | `DEFAULT '[]'` | Carrier processing milestones |
| `submitted_at` | `TEXT` | `NOT NULL` | ISO 8601 submission timestamp |

**Indexes:** `idx_insurer_submissions_claim_id`
