import asyncio
import asyncpg

PG_URI = "postgresql://postgres.btflaabvtrjlfrmqrslg:R.7D%2FcyXP%2C%259X%2Be@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    customer_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(32) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    preferred_language VARCHAR(32) NOT NULL DEFAULT 'en-IN',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS user_consents (
    consent_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL REFERENCES users(customer_id) ON DELETE CASCADE,
    ai_assistance_accepted BOOLEAN NOT NULL DEFAULT TRUE,
    media_storage_accepted BOOLEAN NOT NULL DEFAULT TRUE,
    fraud_screening_accepted BOOLEAN NOT NULL DEFAULT TRUE,
    privacy_policy_accepted BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    claim_id VARCHAR(64),
    primary_language VARCHAR(32) NOT NULL DEFAULT 'en-IN',
    mode VARCHAR(32) NOT NULL DEFAULT 'voice_and_text',
    turns_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    insurance_type VARCHAR(64) NOT NULL DEFAULT 'motor',
    policy_holder_name VARCHAR(255) NOT NULL DEFAULT 'Rahul Sharma',
    policy_reference VARCHAR(128) NOT NULL,
    incident_location TEXT NOT NULL,
    incident_date VARCHAR(64) NOT NULL,
    incident_time VARCHAR(64) NOT NULL DEFAULT 'Not specified',
    vehicle_type VARCHAR(64) NOT NULL,
    vehicle_registration VARCHAR(64) NOT NULL DEFAULT 'Pending verification',
    damage_description TEXT NOT NULL,
    drivable_status VARCHAR(128) NOT NULL DEFAULT 'Unknown',
    injuries_reported VARCHAR(128) NOT NULL DEFAULT 'None reported',
    police_fir_info VARCHAR(128) NOT NULL DEFAULT 'Not filed',
    transcript TEXT NOT NULL,
    language VARCHAR(32) NOT NULL DEFAULT 'en-IN',
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    customer_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_at TIMESTAMPTZ,
    report_version VARCHAR(32) NOT NULL DEFAULT '1.0',
    insurer_submission_status VARCHAR(64) NOT NULL DEFAULT 'not_submitted',
    is_demo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_fields (
    field_id VARCHAR(64) PRIMARY KEY,
    claim_id VARCHAR(64) NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    field_name VARCHAR(64) NOT NULL,
    field_label VARCHAR(128) NOT NULL,
    field_value TEXT,
    confidence VARCHAR(32) NOT NULL DEFAULT 'high',
    is_edited BOOLEAN NOT NULL DEFAULT FALSE,
    follow_up_question TEXT,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_assets (
    asset_id VARCHAR(64) PRIMARY KEY,
    claim_id VARCHAR(64) NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    customer_id VARCHAR(64) NOT NULL,
    label VARCHAR(64) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    media_type VARCHAR(32) NOT NULL,
    mime_type VARCHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL,
    capture_method VARCHAR(64) NOT NULL,
    capture_session_id VARCHAR(64),
    width INT,
    height INT,
    duration_seconds DOUBLE PRECISION,
    storage_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_checks (
    check_id VARCHAR(64) PRIMARY KEY,
    asset_id VARCHAR(64) NOT NULL REFERENCES evidence_assets(asset_id) ON DELETE CASCADE,
    claim_id VARCHAR(64) NOT NULL,
    magic_bytes_valid BOOLEAN NOT NULL,
    detected_mime VARCHAR(64) NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    phash_hex VARCHAR(32),
    provenance_status VARCHAR(64) NOT NULL,
    provenance_signal TEXT NOT NULL,
    provenance_summary TEXT NOT NULL,
    duplicate_status VARCHAR(32) NOT NULL,
    matched_claim_id VARCHAR(64),
    matched_asset_id VARCHAR(64),
    hamming_distance INT,
    requires_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    privacy_masked_match BOOLEAN NOT NULL DEFAULT FALSE,
    exif_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    screening_outcome_label TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id VARCHAR(64) PRIMARY KEY,
    claim_id VARCHAR(64) NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    version VARCHAR(32) NOT NULL,
    dossier_json JSONB NOT NULL,
    canonical_json JSONB NOT NULL,
    pdf_storage_path TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_status_events (
    event_id VARCHAR(64) PRIMARY KEY,
    claim_id VARCHAR(64) NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    from_status VARCHAR(32),
    to_status VARCHAR(32) NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id VARCHAR(64) PRIMARY KEY,
    claim_id VARCHAR(64) NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    claim_id VARCHAR(64),
    action VARCHAR(64) NOT NULL,
    details TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS capture_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    claim_id VARCHAR(64) NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    customer_id VARCHAR(64) NOT NULL,
    capture_type VARCHAR(64) NOT NULL,
    instructions_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS insurer_submissions (
    submission_id VARCHAR(64) PRIMARY KEY,
    claim_id VARCHAR(64) NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    recipient VARCHAR(64) NOT NULL,
    recipient_display_name VARCHAR(255) NOT NULL,
    adapter_payload_json JSONB NOT NULL,
    delivery_status VARCHAR(64) NOT NULL,
    insurer_claim_reference VARCHAR(64) NOT NULL,
    processing_status VARCHAR(64) NOT NULL,
    pipeline_steps_json JSONB NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL
);
"""

async def run():
    from datetime import datetime, timezone
    from app.auth import hash_password

    print("Connecting to Supabase PostgreSQL...")
    conn = await asyncpg.connect(PG_URI)
    print("Creating 12 ClaimSathi AI tables...")
    await conn.execute(SCHEMA_SQL)

    seed_users = [
        (
            "USR-100001",
            "Rahul Sharma",
            "rahul.sharma@claimsathi.in",
            "+91-9876543210",
            hash_password("Rahul@2026"),
            "kn-IN",
            datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc),
        ),
        (
            "USR-100002",
            "Sai Shankar Reddy",
            "saishankar.reddy@claimsathi.in",
            "+91-9848022334",
            hash_password("Shankar@2026"),
            "te-IN",
            datetime(2026, 9, 10, 11, 15, 0, tzinfo=timezone.utc),
        ),
        (
            "USR-100003",
            "Ananya Lakshmi Iyer",
            "ananya.iyer@claimsathi.in",
            "+91-9444155667",
            hash_password("Ananya@2026"),
            "ta-IN",
            datetime(2026, 9, 18, 14, 30, 0, tzinfo=timezone.utc),
        ),
        (
            "USR-100004",
            "Vikramaditya Deshmukh",
            "vikram.deshmukh@claimsathi.in",
            "+91-9820177889",
            hash_password("Vikram@2026"),
            "mr-IN",
            datetime(2026, 9, 25, 9, 45, 0, tzinfo=timezone.utc),
        ),
    ]

    for cid, uname, uemail, uphone, upw, ulang, udt in seed_users:
        await conn.execute(
            """INSERT INTO users (customer_id, name, email, phone, password_hash, preferred_language, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
               ON CONFLICT (customer_id) DO UPDATE
               SET name = EXCLUDED.name, email = EXCLUDED.email, phone = EXCLUDED.phone,
                   password_hash = EXCLUDED.password_hash, preferred_language = EXCLUDED.preferred_language""",
            cid, uname, uemail, uphone, upw, ulang, udt,
        )
        cns_id = f"CNS-{cid.replace('USR-', '')}"
        await conn.execute(
            """INSERT INTO user_consents (consent_id, customer_id, ai_assistance_accepted, media_storage_accepted, fraud_screening_accepted, privacy_policy_accepted, updated_at)
               VALUES ($1, $2, TRUE, TRUE, TRUE, TRUE, $3)
               ON CONFLICT (consent_id) DO NOTHING""",
            cns_id, cid, udt,
        )
        await conn.execute(
            """INSERT INTO audit_logs (log_id, user_id, claim_id, action, details, timestamp)
               VALUES ($1, $2, NULL, 'ACCOUNT_CREATED', $3, $4)
               ON CONFLICT (log_id) DO NOTHING""",
            f"AUD-INIT-{cid.replace('USR-', '')}",
            cid,
            f"Customer account {cid} ({uname}) registered in Supabase database with privacy & screening consent.",
            udt,
        )

    seed_claims = [
        (
            "CS-2026-000085",
            "USR-100001",
            "Rahul Sharma",
            "MOT-2026-KA-44210",
            "MG Road, Bengaluru",
            "2026-09-14",
            "car",
            "KA-01-MJ-4421",
            "Rear bumper minor dent and tail-lamp crack at traffic signal.",
            "Meri car MG Road signal pe ruki thi jab peeche se halka touch hua. Rear bumper aur tail light mein crack aaya hai. Policy MOT-2026-KA-44210.",
            "kn-IN",
            "archived",
            datetime(2026, 9, 14, 16, 20, 0, tzinfo=timezone.utc),
        ),
        (
            "CS-2026-000092",
            "USR-100002",
            "Sai Shankar Reddy",
            "MOT-2024-TS-98765",
            "Madhapur, Hyderabad",
            "2026-10-04",
            "car",
            "TS-09-UB-9876",
            "Left front door dent and front bumper scratch from side swipe.",
            "Naa car accident ayyindi Hyderabad Madhapur daggara. Policy MOT-2024-TS-98765. Left door and front bumper damage ayyindi.",
            "te-IN",
            "confirmed",
            datetime(2026, 10, 4, 18, 10, 0, tzinfo=timezone.utc),
        ),
        (
            "CS-2026-000104",
            "USR-100003",
            "Ananya Lakshmi Iyer",
            "MOT-2026-TN-55120",
            "Anna Nagar, Chennai",
            "2026-10-19",
            "bike",
            "TN-02-BM-5512",
            "Front mudguard bent and right indicator broken after skidding on wet road.",
            "En bike Anna Nagar Chennai la rain la skid aagiduchu. Policy MOT-2026-TN-55120. Front mudguard and right indicator damage.",
            "ta-IN",
            "confirmed",
            datetime(2026, 10, 19, 12, 40, 0, tzinfo=timezone.utc),
        ),
        (
            "CS-2026-000118",
            "USR-100004",
            "Vikramaditya Deshmukh",
            "MOT-2026-MH-33901",
            "Kothrud, Pune",
            "2026-10-28",
            "car",
            "MH-12-DE-3390",
            "Front grille cracked and right headlamp assembly damaged in parking lot.",
            "Pune Kothrud madhe parking madhe majhya car cha front grille aani right headlight damage zala. Policy MOT-2026-MH-33901.",
            "mr-IN",
            "confirmed",
            datetime(2026, 10, 28, 15, 5, 0, tzinfo=timezone.utc),
        ),
    ]

    for cid, uid, holder, pol, loc, dt_str, vtype, vreg, dmg, tr, lang, st, dt_obj in seed_claims:
        await conn.execute(
            """INSERT INTO claims
               (id, customer_id, insurance_type, policy_holder_name, policy_reference,
                incident_location, incident_date, vehicle_type, vehicle_registration,
                damage_description, transcript, language, status, customer_confirmed,
                confirmed_at, created_at, updated_at)
               VALUES ($1, $2, 'motor', $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, TRUE, $13, $13, $13)
               ON CONFLICT (id) DO NOTHING""",
            cid, uid, holder, pol, loc, dt_str, vtype, vreg, dmg, tr, lang, st, dt_obj,
        )

    users_in_db = await conn.fetch("SELECT customer_id, name, email, phone, preferred_language FROM users ORDER BY customer_id")
    print("Seeded Users in Supabase PostgreSQL:")
    for u in users_in_db:
        print(" ->", dict(u))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())

