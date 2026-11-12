"""
SQLite Persistence Layer for ClaimSathi AI (Phases 1–7).
Implements the complete 12-table architecture from _ClaimSathi AI product flow.pdf (Pages 8–9):
1. users                  — Customer accounts and unique IDs (USR-100001)
2. user_consents          — Consent and privacy preferences
3. conversations          — Conversation sessions & multilingual turns
4. claims                 — Structured claim information (CS-2026-000124)
5. claim_fields           — Extracted and confirmed fields
6. evidence_assets        — Image/video metadata and storage references
7. evidence_checks        — AI provenance, SHA-256, 64-bit pHash & cross-claim duplicate results
8. reports                — Generated 9-section Dossier, Canonical JSON & PDF reports
9. claim_status_events    — Historical status changes
10. audit_logs            — Access and modification history
11. capture_sessions      — Server-generated live camera capture sessions
12. insurer_submissions   — Mock Insurer Integration Gateway records
"""

import aiosqlite
import json
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List
from uuid import uuid4
from .models import (
    ClaimRecord,
    ClaimStatus,
    UserProfile,
    UserConsentInput,
    EvidenceAssetRecord,
    EvidenceCheckRecord,
    DuplicateStatus,
)
from .auth import hash_password

DB_PATH = "claimsathi.db"


async def init_db():
    """Initialize all 12 tables, migrate any legacy schema columns, and seed Rahul's account (USR-100001)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. users
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                customer_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                declared_insurer TEXT DEFAULT 'Bharat General Insurance',
                created_at TEXT NOT NULL
            )
        """)

        # 2. user_consents
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_consents (
                consent_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                data_processing_consent INTEGER DEFAULT 1,
                evidence_screening_consent INTEGER DEFAULT 1,
                retention_policy_acknowledged INTEGER DEFAULT 1,
                consented_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(customer_id)
            )
        """)

        # 3. conversations
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                claim_id TEXT,
                user_id TEXT NOT NULL,
                language TEXT DEFAULT 'indic-auto',
                turns_json TEXT DEFAULT '[]',
                transcript_full TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # 4. claims
        await db.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,
                customer_id TEXT DEFAULT 'USR-100001',
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
                updated_at TEXT NOT NULL
            )
        """)

        # Safely migrate older claims table if missing new columns
        cursor = await db.execute("PRAGMA table_info(claims)")
        existing_cols = {row[1] for row in await cursor.fetchall()}
        migrations = [
            ("customer_id", "TEXT DEFAULT 'USR-100001'"),
            ("insurance_type", "TEXT DEFAULT 'motor'"),
            ("insurer_name", "TEXT DEFAULT 'Bharat General Insurance'"),
            ("policy_type", "TEXT DEFAULT 'Comprehensive Motor Policy'"),
            ("people_involved", "TEXT DEFAULT 'Policyholder (Driver)'"),
            ("injuries_reported", "TEXT DEFAULT 'No physical injuries reported'"),
            ("detailed_statement", "TEXT DEFAULT ''"),
            ("customer_confirmation", "INTEGER DEFAULT 1"),
            ("report_status", "TEXT DEFAULT 'not_generated'"),
            ("insurer_submission_status", "TEXT DEFAULT 'not_submitted'"),
        ]
        for col_name, col_def in migrations:
            if col_name not in existing_cols:
                await db.execute(f"ALTER TABLE claims ADD COLUMN {col_name} {col_def}")

        # 5. claim_fields
        await db.execute("""
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
                updated_at TEXT NOT NULL,
                FOREIGN KEY (claim_id) REFERENCES claims(id)
            )
        """)

        # 6. evidence_assets
        await db.execute("""
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
                FOREIGN KEY (claim_id) REFERENCES claims(id)
            )
        """)

        # 7. evidence_checks (Cross-claim fingerprint index & provenance results)
        await db.execute("""
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
                FOREIGN KEY (evidence_id) REFERENCES evidence_assets(evidence_id)
            )
        """)

        # 8. reports
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                claim_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                version TEXT NOT NULL,
                dossier_json TEXT NOT NULL,
                canonical_json TEXT NOT NULL,
                pdf_storage_path TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (claim_id) REFERENCES claims(id)
            )
        """)

        # 9. claim_status_events & legacy timeline_events
        await db.execute("""
            CREATE TABLE IF NOT EXISTS claim_status_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id TEXT NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (claim_id) REFERENCES claims(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                FOREIGN KEY (claim_id) REFERENCES claims(id)
            )
        """)

        # 10. audit_logs
        await db.execute("""
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
            )
        """)
        # Ensure new audit columns exist on existing databases
        async with db.execute("PRAGMA table_info(audit_logs)") as cur:
            audit_existing_cols = [row[1] for row in await cur.fetchall()]
        if "resource_type" not in audit_existing_cols:
            await db.execute("ALTER TABLE audit_logs ADD COLUMN resource_type TEXT DEFAULT 'claim'")
        if "resource_id" not in audit_existing_cols:
            await db.execute("ALTER TABLE audit_logs ADD COLUMN resource_id TEXT")
        if "outcome" not in audit_existing_cols:
            await db.execute("ALTER TABLE audit_logs ADD COLUMN outcome TEXT DEFAULT 'SUCCESS'")

        # 11. capture_sessions
        await db.execute("""
            CREATE TABLE IF NOT EXISTS capture_sessions (
                session_id TEXT PRIMARY KEY,
                claim_id TEXT,
                user_id TEXT NOT NULL,
                instructions_json TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)

        # 12. insurer_submissions
        await db.execute("""
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
                FOREIGN KEY (claim_id) REFERENCES claims(id)
            )
        """)

        # Seed 4 Indian Customer Accounts in database tables (USR-100001 to USR-100004)
        seed_users = [
            (
                "USR-100001",
                "Rahul Sharma",
                "rahul.sharma@claimsathi.in",
                "+91-9876543210",
                hash_password("Rahul@2026"),
                "Bharat General Insurance",
                "2026-09-01T10:00:00",
            ),
            (
                "USR-100002",
                "Sai Shankar Reddy",
                "saishankar.reddy@claimsathi.in",
                "+91-9848022334",
                hash_password("Shankar@2026"),
                "Royal Sundaram General Insurance",
                "2026-09-10T11:15:00",
            ),
            (
                "USR-100003",
                "Ananya Lakshmi Iyer",
                "ananya.iyer@claimsathi.in",
                "+91-9444155667",
                hash_password("Ananya@2026"),
                "Chola MS General Insurance",
                "2026-09-18T14:30:00",
            ),
            (
                "USR-100004",
                "Vikramaditya Deshmukh",
                "vikram.deshmukh@claimsathi.in",
                "+91-9820177889",
                hash_password("Vikram@2026"),
                "ICICI Lombard Motor Insurance",
                "2026-09-25T09:45:00",
            ),
        ]

        for cid, uname, uemail, uphone, upw, uinsurer, ucreated in seed_users:
            cursor = await db.execute("SELECT customer_id FROM users WHERE customer_id = ?", (cid,))
            if not await cursor.fetchone():
                await db.execute(
                    """INSERT INTO users (customer_id, name, email, phone, password_hash, declared_insurer, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (cid, uname, uemail, uphone, upw, uinsurer, ucreated),
                )
                cns_id = f"CNS-{cid.replace('USR-', '')}"
                await db.execute(
                    """INSERT OR IGNORE INTO user_consents
                       (consent_id, user_id, data_processing_consent, evidence_screening_consent, retention_policy_acknowledged, consented_at)
                       VALUES (?, ?, 1, 1, 1, ?)""",
                    (cns_id, cid, ucreated),
                )
                await db.execute(
                    """INSERT OR IGNORE INTO audit_logs (log_id, user_id, claim_id, action, details, timestamp)
                       VALUES (?, ?, NULL, ?, ?, ?)""",
                    (
                        f"AUD-INIT-{cid.replace('USR-', '')}",
                        cid,
                        "ACCOUNT_CREATED",
                        f"Customer account {cid} ({uname}) registered in database with privacy & screening consent.",
                        ucreated,
                    ),
                )
            elif cid == "USR-100001":
                # Ensure Rahul's email and password match the updated credentials
                await db.execute(
                    """UPDATE users SET email = ?, phone = ?, password_hash = ?, declared_insurer = ?
                       WHERE customer_id = 'USR-100001'""",
                    (uemail, uphone, upw, uinsurer),
                )

        # Ensure historical claims exist for each of the 4 customer vaults
        seed_claims = [
            (
                "CS-2026-000085",
                "USR-100001",
                "motor",
                "MOT-2026-KA-44210",
                "Bharat General Insurance",
                "Comprehensive Motor Policy",
                "MG Road, Bengaluru",
                "2026-09-14",
                "car",
                "Rear bumper minor dent and tail-lamp crack at traffic signal.",
                "Policyholder (Rahul Sharma)",
                "No injuries reported",
                "On 14 September 2026, while stationary at the MG Road traffic signal in Bengaluru, the insured vehicle (car, Policy MOT-2026-KA-44210) experienced a minor rear-end impact resulting in a rear bumper dent and right tail-lamp crack.",
                "Meri car MG Road signal pe ruki thi jab peeche se halka touch hua. Rear bumper aur tail light mein crack aaya hai. Policy MOT-2026-KA-44210.",
                ClaimStatus.ARCHIVED.value,
                "2026-09-14T16:20:00",
            ),
            (
                "CS-2026-000092",
                "USR-100002",
                "motor",
                "MOT-2024-TS-98765",
                "Royal Sundaram General Insurance",
                "Comprehensive Motor Policy",
                "Madhapur, Hyderabad",
                "2026-10-04",
                "car",
                "Left front door dent and front bumper scratch from side swipe.",
                "Policyholder (Sai Shankar Reddy)",
                "No injuries reported",
                "On 04 October 2026 near Madhapur, Hyderabad, an auto-rickshaw brushed the left side of the insured car (Policy MOT-2024-TS-98765), causing a dent on the left door and front bumper.",
                "Naa car accident ayyindi Hyderabad Madhapur daggara. Policy MOT-2024-TS-98765. Left door and front bumper damage ayyindi.",
                ClaimStatus.CONFIRMED.value,
                "2026-10-04T18:10:00",
            ),
            (
                "CS-2026-000104",
                "USR-100003",
                "motor",
                "MOT-2026-TN-55120",
                "Chola MS General Insurance",
                "Two-Wheeler Comprehensive Policy",
                "Anna Nagar, Chennai",
                "2026-10-19",
                "bike",
                "Front mudguard bent and right indicator broken after skidding on wet road.",
                "Policyholder (Ananya Lakshmi Iyer)",
                "No injuries reported",
                "On 19 October 2026 at Anna Nagar, Chennai, the insured two-wheeler (Policy MOT-2026-TN-55120) skidded during rain, bending the front mudguard and cracking the right indicator.",
                "En bike Anna Nagar Chennai la rain la skid aagiduchu. Policy MOT-2026-TN-55120. Front mudguard and right indicator damage.",
                ClaimStatus.CONFIRMED.value,
                "2026-10-19T12:40:00",
            ),
            (
                "CS-2026-000118",
                "USR-100004",
                "motor",
                "MOT-2026-MH-33901",
                "ICICI Lombard Motor Insurance",
                "Zero Depreciation Motor Policy",
                "Kothrud, Pune",
                "2026-10-28",
                "car",
                "Front grille cracked and right headlamp assembly damaged in parking lot.",
                "Policyholder (Vikramaditya Deshmukh)",
                "No injuries reported",
                "On 28 October 2026 at Kothrud, Pune, a reversing delivery van impacted the front grille and right headlamp of the insured car (Policy MOT-2026-MH-33901).",
                "Pune Kothrud madhe parking madhe majhya car cha front grille aani right headlight damage zala. Policy MOT-2026-MH-33901.",
                ClaimStatus.CONFIRMED.value,
                "2026-10-28T15:05:00",
            ),
        ]

        for (
            cl_id,
            cl_uid,
            cl_type,
            cl_pol,
            cl_ins,
            cl_ptype,
            cl_loc,
            cl_date,
            cl_veh,
            cl_dmg,
            cl_ppl,
            cl_inj,
            cl_stmt,
            cl_tr,
            cl_status,
            cl_time,
        ) in seed_claims:
            c_hist = await db.execute("SELECT id FROM claims WHERE id = ?", (cl_id,))
            if not await c_hist.fetchone():
                await db.execute(
                    """INSERT INTO claims
                       (id, customer_id, insurance_type, policy_reference, insurer_name, policy_type,
                        incident_location, incident_date, vehicle_type, damage_description,
                        people_involved, injuries_reported, detailed_statement, transcript,
                        status, customer_confirmation, report_status, insurer_submission_status,
                        is_demo, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cl_id,
                        cl_uid,
                        cl_type,
                        cl_pol,
                        cl_ins,
                        cl_ptype,
                        cl_loc,
                        cl_date,
                        cl_veh,
                        cl_dmg,
                        cl_ppl,
                        cl_inj,
                        cl_stmt,
                        cl_tr,
                        cl_status,
                        1,
                        "generated",
                        "simulated_submitted" if cl_status == ClaimStatus.ARCHIVED.value else "not_submitted",
                        1,
                        cl_time,
                        cl_time,
                    ),
                )
                await db.execute(
                    """INSERT INTO timeline_events (claim_id, timestamp, title, description)
                       VALUES (?, ?, ?, ?), (?, ?, ?, ?)""",
                    (
                        cl_id,
                        cl_time,
                        "Claim Created in Customer Vault",
                        f"Claim dossier {cl_id} initialized for customer {cl_uid}.",
                        cl_id,
                        cl_time,
                        "Multilingual Transcript & Fields Verified",
                        "Voice/text intake transcribed and structured fields confirmed by policyholder.",
                    ),
                )

        await db.commit()


# ── Audit Logging ──────────────────────────────────────
async def log_audit_event(
    user_id: str,
    action: str,
    details: str,
    claim_id: Optional[str] = None,
    ip_address: str = "127.0.0.1",
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    outcome: str = "SUCCESS",
):
    log_id = f"AUD-{uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO audit_logs (log_id, user_id, claim_id, action, details, ip_address, resource_type, resource_id, outcome, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_id, user_id, claim_id, action, details, ip_address, resource_type, resource_id, outcome, now),
        )
        await db.commit()


# ── User & Auth Persistence ────────────────────────────
async def generate_next_customer_id() -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        count = (await cursor.fetchone())[0]
        next_num = 100001 + count
        while True:
            cid = f"USR-{next_num}"
            chk = await db.execute("SELECT 1 FROM users WHERE customer_id = ?", (cid,))
            if not await chk.fetchone():
                return cid
            next_num += 1


async def create_user_account(
    name: str,
    email: str,
    phone: str,
    password: str,
    declared_insurer: str,
    consents: UserConsentInput,
) -> UserProfile:
    customer_id = await generate_next_customer_id()
    now_str = datetime.now(timezone.utc).isoformat()
    pw_hash = hash_password(password)
    consent_id = f"CNS-{customer_id.replace('USR-', '')}"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (customer_id, name, email, phone, password_hash, declared_insurer, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (customer_id, name.strip(), email.strip().lower(), phone.strip(), pw_hash, declared_insurer, now_str),
        )
        await db.execute(
            """INSERT INTO user_consents
               (consent_id, user_id, data_processing_consent, evidence_screening_consent, retention_policy_acknowledged, consented_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                consent_id,
                customer_id,
                int(consents.data_processing_consent),
                int(consents.evidence_screening_consent),
                int(consents.retention_policy_acknowledged),
                now_str,
            ),
        )
        await db.commit()

    await log_audit_event(
        user_id=customer_id,
        action="USER_REGISTERED",
        details=f"Registered customer {name} ({customer_id}) with explicit privacy & screening consent.",
    )
    return await get_user_profile(customer_id)


async def get_user_by_identifier(identifier: str) -> Optional[Dict[str, Any]]:
    clean = identifier.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM users
               WHERE LOWER(email) = LOWER(?) OR phone = ? OR UPPER(customer_id) = UPPER(?)""",
            (clean, clean, clean),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_profile(customer_id: str) -> Optional[UserProfile]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE customer_id = ?", (customer_id,))
        user_row = await cursor.fetchone()
        if not user_row:
            return None

        c_cursor = await db.execute(
            "SELECT * FROM user_consents WHERE user_id = ? ORDER BY consented_at DESC LIMIT 1",
            (customer_id,),
        )
        consent_row = await c_cursor.fetchone()

        cnt_cursor = await db.execute(
            "SELECT COUNT(*) FROM claims WHERE customer_id = ?",
            (customer_id,),
        )
        total_claims = (await cnt_cursor.fetchone())[0]

        consents = UserConsentInput(
            data_processing_consent=bool(consent_row["data_processing_consent"]) if consent_row else True,
            evidence_screening_consent=bool(consent_row["evidence_screening_consent"]) if consent_row else True,
            retention_policy_acknowledged=bool(consent_row["retention_policy_acknowledged"]) if consent_row else True,
        )

        return UserProfile(
            customer_id=user_row["customer_id"],
            name=user_row["name"],
            email=user_row["email"],
            phone=user_row["phone"],
            declared_insurer=user_row["declared_insurer"],
            consents=consents,
            total_claims=total_claims,
            created_at=datetime.fromisoformat(user_row["created_at"]),
        )


# ── Claim ID Generation & Persistence ──────────────────
async def generate_next_cs_claim_id() -> str:
    """Generate official ClaimSathi ID format: CS-2026-000124, CS-2026-000125, etc."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM claims WHERE id LIKE 'CS-2026-%'")
        rows = await cursor.fetchall()
        max_num = 123
        for (cid,) in rows:
            try:
                num = int(cid.split("-")[-1])
                if num >= 124 and num > max_num:
                    max_num = num
            except ValueError:
                pass
        return f"CS-2026-{max_num + 1:06d}"


def build_detailed_incident_statement(
    incident_date: str,
    incident_location: str,
    vehicle_type: str,
    policy_reference: str,
    damage_description: str,
    people_involved: str = "Policyholder (Driver)",
    injuries_reported: str = "No physical injuries reported",
) -> str:
    """Generate SECTION 04 — Detailed Incident Statement from structured conversation details."""
    return (
        f"On {incident_date}, at or near {incident_location}, the insured motor vehicle "
        f"({vehicle_type.upper()}, covered under Policy Reference {policy_reference}) was involved "
        f"in a reported motor incident. Per the policyholder's chronological voice and text statement, "
        f"the resulting vehicle damage consists of: {damage_description}. "
        f"Persons involved: {people_involved}. Injuries reported: {injuries_reported}. "
        f"This statement was synthesized from the customer's interactive intake conversation and "
        f"verified by the policyholder prior to dossier generation."
    )


async def _count_claim_evidence(db: aiosqlite.Connection, claim_id: str) -> tuple[int, int]:
    cur_img = await db.execute(
        "SELECT COUNT(*) FROM evidence_assets WHERE claim_id = ? AND media_type = 'image'",
        (claim_id,),
    )
    img_cnt = (await cur_img.fetchone())[0]
    cur_vid = await db.execute(
        "SELECT COUNT(*) FROM evidence_assets WHERE claim_id = ? AND media_type = 'video'",
        (claim_id,),
    )
    vid_cnt = (await cur_vid.fetchone())[0]
    return img_cnt, vid_cnt


def _row_to_claim_record(row: aiosqlite.Row, img_cnt: int = 0, vid_cnt: int = 0) -> ClaimRecord:
    keys = row.keys()
    return ClaimRecord(
        id=row["id"],
        customer_id=row["customer_id"] if "customer_id" in keys and row["customer_id"] else "USR-100001",
        insurance_type=row["insurance_type"] if "insurance_type" in keys and row["insurance_type"] else "motor",
        policy_reference=row["policy_reference"],
        insurer_name=row["insurer_name"] if "insurer_name" in keys and row["insurer_name"] else "Bharat General Insurance",
        policy_type=row["policy_type"] if "policy_type" in keys and row["policy_type"] else "Comprehensive Motor Policy",
        incident_location=row["incident_location"],
        incident_date=row["incident_date"],
        vehicle_type=row["vehicle_type"],
        damage_description=row["damage_description"],
        people_involved=row["people_involved"] if "people_involved" in keys and row["people_involved"] else "Policyholder (Driver)",
        injuries_reported=row["injuries_reported"] if "injuries_reported" in keys and row["injuries_reported"] else "No physical injuries reported",
        detailed_statement=row["detailed_statement"] if "detailed_statement" in keys and row["detailed_statement"] else "",
        transcript=row["transcript"] or "",
        status=ClaimStatus(row["status"]) if row["status"] in [s.value for s in ClaimStatus] else ClaimStatus.CONFIRMED,
        customer_confirmation=bool(row["customer_confirmation"]) if "customer_confirmation" in keys else True,
        report_status=row["report_status"] if "report_status" in keys and row["report_status"] else "not_generated",
        insurer_submission_status=row["insurer_submission_status"] if "insurer_submission_status" in keys and row["insurer_submission_status"] else "not_submitted",
        evidence_count_images=img_cnt,
        evidence_count_videos=vid_cnt,
        is_demo=bool(row["is_demo"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


async def insert_claim(
    claim: ClaimRecord,
    conversation_turns: Optional[list[dict[str, Any]]] = None,
) -> ClaimRecord:
    if not claim.detailed_statement:
        claim.detailed_statement = build_detailed_incident_statement(
            incident_date=claim.incident_date,
            incident_location=claim.incident_location,
            vehicle_type=claim.vehicle_type,
            policy_reference=claim.policy_reference,
            damage_description=claim.damage_description,
            people_involved=claim.people_involved,
            injuries_reported=claim.injuries_reported,
        )

    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO claims
               (id, customer_id, insurance_type, policy_reference, insurer_name, policy_type,
                incident_location, incident_date, vehicle_type, damage_description,
                people_involved, injuries_reported, detailed_statement, transcript,
                status, customer_confirmation, report_status, insurer_submission_status,
                is_demo, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                claim.id,
                claim.customer_id,
                claim.insurance_type,
                claim.policy_reference,
                claim.insurer_name,
                claim.policy_type,
                claim.incident_location,
                claim.incident_date,
                claim.vehicle_type,
                claim.damage_description,
                claim.people_involved,
                claim.injuries_reported,
                claim.detailed_statement,
                claim.transcript,
                claim.status.value,
                int(claim.customer_confirmation),
                claim.report_status,
                claim.insurer_submission_status,
                1,
                claim.created_at.isoformat(),
                claim.updated_at.isoformat(),
            ),
        )

        # Store structured claim_fields rows
        fields_data = [
            ("policy_reference", "Policy Reference", claim.policy_reference),
            ("incident_location", "Incident Location", claim.incident_location),
            ("incident_date", "Incident Date", claim.incident_date),
            ("vehicle_type", "Vehicle Type", claim.vehicle_type),
            ("damage_description", "Damage Description", claim.damage_description),
        ]
        for fname, flabel, fval in fields_data:
            await db.execute(
                """INSERT INTO claim_fields
                   (claim_id, field_name, label, value, confidence, is_edited, is_verified, updated_at)
                   VALUES (?, ?, ?, ?, 'high', 0, 1, ?)""",
                (claim.id, fname, flabel, fval, now),
            )

        # Store conversation session
        conv_id = f"CONV-{uuid4().hex[:8].upper()}"
        await db.execute(
            """INSERT INTO conversations
               (conversation_id, claim_id, user_id, language, turns_json, transcript_full, created_at, updated_at)
               VALUES (?, ?, ?, 'indic-auto', ?, ?, ?, ?)""",
            (
                conv_id,
                claim.id,
                claim.customer_id,
                json.dumps(conversation_turns or []),
                claim.transcript,
                now,
                now,
            ),
        )

        # Insert timeline events & claim_status_events
        events = [
            (claim.id, now, "Claim Created [DEMO]",
             f"Claim case {claim.id} created for customer {claim.customer_id}."),
            (claim.id, now, "Transcript Processed [MOCK]",
             "Multilingual voice/text intake analysed and structured fields extracted."),
            (claim.id, now, "Fields Confirmed",
             "Customer reviewed and confirmed extracted claim information."),
        ]
        await db.executemany(
            """INSERT INTO timeline_events (claim_id, timestamp, title, description)
               VALUES (?, ?, ?, ?)""",
            events,
        )
        for cid, ts, title, desc in events:
            await db.execute(
                """INSERT INTO claim_status_events (claim_id, status, title, description, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (cid, claim.status.value, title, desc, ts),
            )

        await db.commit()

    await log_audit_event(
        user_id=claim.customer_id,
        claim_id=claim.id,
        action="CLAIM_CREATED",
        details=f"Claim {claim.id} created with policy {claim.policy_reference}.",
    )
    return claim


async def add_timeline_event(claim_id: str, title: str, description: str, status: str = "confirmed"):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO timeline_events (claim_id, timestamp, title, description)
               VALUES (?, ?, ?, ?)""",
            (claim_id, now, title, description),
        )
        await db.execute(
            """INSERT INTO claim_status_events (claim_id, status, title, description, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (claim_id, status, title, description, now),
        )
        await db.commit()


async def update_claim_record(claim_id: str, updates: Dict[str, Any]) -> Optional[ClaimRecord]:
    if not updates:
        return await get_claim(claim_id)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [claim_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE claims SET {set_clause} WHERE id = ?", values)
        await db.commit()
    return await get_claim(claim_id)


async def get_claim(claim_id: str) -> Optional[ClaimRecord]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM claims WHERE id = ?", (claim_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        img_cnt, vid_cnt = await _count_claim_evidence(db, claim_id)
        return _row_to_claim_record(row, img_cnt, vid_cnt)


async def get_all_claims(customer_id: Optional[str] = None) -> list[ClaimRecord]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if customer_id:
            cursor = await db.execute(
                "SELECT * FROM claims WHERE customer_id = ? ORDER BY created_at DESC",
                (customer_id,),
            )
        else:
            cursor = await db.execute("SELECT * FROM claims ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            img_cnt, vid_cnt = await _count_claim_evidence(db, row["id"])
            results.append(_row_to_claim_record(row, img_cnt, vid_cnt))
        return results


async def get_timeline(claim_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM timeline_events WHERE claim_id = ? ORDER BY id ASC",
            (claim_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "title": row["title"],
                "description": row["description"],
            }
            for row in rows
        ]


# ── Evidence & Cross-Claim Fingerprint Persistence ─────
async def get_all_evidence_fingerprints() -> List[Dict[str, Any]]:
    """Retrieve all stored SHA-256 and perceptual hashes across all claims for duplicate detection."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT c.check_id, c.evidence_id, c.claim_id, c.sha256_hash, c.perceptual_hash,
                      a.user_id, a.media_type, a.original_filename
               FROM evidence_checks c
               JOIN evidence_assets a ON c.evidence_id = a.evidence_id
               ORDER BY c.checked_at ASC"""
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def count_claim_media_items(claim_id: str, media_type: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM evidence_assets WHERE claim_id = ? AND media_type = ?",
            (claim_id, media_type),
        )
        return (await cursor.fetchone())[0]


async def insert_evidence_asset_and_check(
    asset: EvidenceAssetRecord,
    storage_path: str,
    raw_matched_claim_id: Optional[str] = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO evidence_assets
               (evidence_id, claim_id, user_id, label, media_type, capture_method,
                capture_session_id, original_filename, detected_mime, file_size_bytes,
                storage_path, width, height, exif_metadata_json, upload_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset.evidence_id,
                asset.claim_id,
                asset.user_id,
                asset.label,
                asset.media_type,
                asset.capture_method,
                asset.capture_session_id,
                asset.original_filename,
                asset.detected_mime,
                asset.file_size_bytes,
                storage_path,
                asset.width,
                asset.height,
                json.dumps(asset.exif_metadata),
                asset.upload_timestamp.isoformat(),
            ),
        )
        chk = asset.screening
        await db.execute(
            """INSERT INTO evidence_checks
               (check_id, evidence_id, claim_id, sha256_hash, perceptual_hash,
                magic_bytes_valid, detected_format, malware_scan_status,
                c2pa_found, synthid_found, provenance_result, provenance_system_response,
                provenance_details_json, duplicate_status, duplicate_match_type,
                matched_claim_id, matched_evidence_id, hamming_distance,
                requires_human_review, screening_outcome_label, checked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chk.check_id,
                chk.evidence_id,
                chk.claim_id,
                chk.sha256_hash,
                chk.perceptual_hash,
                int(chk.magic_bytes_valid),
                chk.detected_format,
                chk.malware_scan_status,
                int(chk.c2pa_found),
                int(chk.synthid_found),
                chk.provenance_result,
                chk.provenance_system_response,
                json.dumps(chk.provenance_details),
                chk.duplicate_status.value,
                chk.duplicate_match_type,
                raw_matched_claim_id,
                chk.matched_evidence_id,
                chk.hamming_distance,
                int(chk.requires_human_review),
                chk.screening_outcome_label,
                chk.checked_at.isoformat(),
            ),
        )
        await db.commit()


async def get_claim_evidence(claim_id: str, requesting_user_id: Optional[str] = None) -> List[EvidenceAssetRecord]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT a.*, c.check_id, c.sha256_hash, c.perceptual_hash, c.magic_bytes_valid,
                      c.detected_format, c.malware_scan_status, c.c2pa_found, c.synthid_found,
                      c.provenance_result, c.provenance_system_response, c.provenance_details_json,
                      c.duplicate_status, c.duplicate_match_type, c.matched_claim_id,
                      c.matched_evidence_id, c.hamming_distance, c.requires_human_review,
                      c.screening_outcome_label, c.checked_at
               FROM evidence_assets a
               JOIN evidence_checks c ON a.evidence_id = c.evidence_id
               WHERE a.claim_id = ?
               ORDER BY a.upload_timestamp ASC""",
            (claim_id,),
        )
        rows = await cursor.fetchall()
        results: List[EvidenceAssetRecord] = []
        for r in rows:
            # Privacy rule (Page 3 of PDF): Never expose another customer's private claim info!
            matched_cid = r["matched_claim_id"]
            safe_matched_ref = None
            if matched_cid:
                if matched_cid == claim_id:
                    safe_matched_ref = f"Same Claim ({claim_id})"
                else:
                    # Check if the matched claim belongs to the same user
                    m_cur = await db.execute("SELECT customer_id FROM claims WHERE id = ?", (matched_cid,))
                    m_row = await m_cur.fetchone()
                    if m_row and requesting_user_id and m_row["customer_id"] == requesting_user_id:
                        safe_matched_ref = f"Previous Claim ({matched_cid})"
                    else:
                        safe_matched_ref = "Protected Cross-Claim Record [REDACTED]"

            chk = EvidenceCheckRecord(
                check_id=r["check_id"],
                evidence_id=r["evidence_id"],
                claim_id=r["claim_id"],
                sha256_hash=r["sha256_hash"],
                perceptual_hash=r["perceptual_hash"],
                magic_bytes_valid=bool(r["magic_bytes_valid"]),
                detected_format=r["detected_format"],
                malware_scan_status=r["malware_scan_status"],
                c2pa_found=bool(r["c2pa_found"]),
                synthid_found=bool(r["synthid_found"]),
                provenance_result=r["provenance_result"],
                provenance_system_response=r["provenance_system_response"],
                provenance_details=json.loads(r["provenance_details_json"] or "{}"),
                duplicate_status=DuplicateStatus(r["duplicate_status"]),
                duplicate_match_type=r["duplicate_match_type"],
                matched_claim_reference=safe_matched_ref,
                matched_evidence_id=r["matched_evidence_id"],
                hamming_distance=r["hamming_distance"],
                requires_human_review=bool(r["requires_human_review"]),
                screening_outcome_label=r["screening_outcome_label"],
                checked_at=datetime.fromisoformat(r["checked_at"]),
            )
            results.append(
                EvidenceAssetRecord(
                    evidence_id=r["evidence_id"],
                    claim_id=r["claim_id"],
                    user_id=r["user_id"],
                    label=r["label"],
                    media_type=r["media_type"],
                    capture_method=r["capture_method"],
                    capture_session_id=r["capture_session_id"],
                    original_filename=r["original_filename"],
                    detected_mime=r["detected_mime"],
                    file_size_bytes=r["file_size_bytes"],
                    width=r["width"],
                    height=r["height"],
                    exif_metadata=json.loads(r["exif_metadata_json"] or "{}"),
                    upload_timestamp=datetime.fromisoformat(r["upload_timestamp"]),
                    screening=chk,
                )
            )
        return results


# ── Live Camera Capture Sessions ───────────────────────
async def create_capture_session(user_id: str, claim_id: Optional[str], instructions: list[str]) -> Dict[str, Any]:
    session_id = f"CAP-2026-{uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO capture_sessions (session_id, claim_id, user_id, instructions_json, status, created_at)
               VALUES (?, ?, ?, ?, 'active', ?)""",
            (session_id, claim_id, user_id, json.dumps(instructions), now.isoformat()),
        )
        await db.commit()
    await log_audit_event(
        user_id=user_id,
        claim_id=claim_id,
        action="LIVE_CAPTURE_SESSION_STARTED",
        details=f"Guided live capture session {session_id} started with {len(instructions)} instructions.",
        resource_type="capture_session",
        resource_id=session_id,
        outcome="SUCCESS",
    )
    return {
        "session_id": session_id,
        "claim_id": claim_id,
        "instructions": instructions,
        "created_at": now,
    }


async def get_capture_session(session_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM capture_sessions WHERE session_id = ?", (session_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


# ── Reports & Insurer Submissions Persistence ──────────
async def save_generated_report(
    report_id: str,
    claim_id: str,
    user_id: str,
    version: str,
    dossier_dict: Dict[str, Any],
    canonical_dict: Dict[str, Any],
    pdf_storage_path: str,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO reports (report_id, claim_id, user_id, version, dossier_json, canonical_json, pdf_storage_path, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report_id,
                claim_id,
                user_id,
                version,
                json.dumps(dossier_dict),
                json.dumps(canonical_dict),
                pdf_storage_path,
                now,
            ),
        )
        await db.execute(
            "UPDATE claims SET report_status = 'generated', status = ?, updated_at = ? WHERE id = ?",
            (ClaimStatus.REPORT_GENERATED.value, now, claim_id),
        )
        await db.commit()
    return {
        "report_id": report_id,
        "claim_id": claim_id,
        "user_id": user_id,
        "version": version,
        "dossier": dossier_dict,
        "canonical_schema": canonical_dict,
        "pdf_storage_path": pdf_storage_path,
        "generated_at": now,
    }


async def get_claim_reports(claim_id: str) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM reports WHERE claim_id = ? ORDER BY generated_at DESC",
            (claim_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "report_id": r["report_id"],
                "claim_id": r["claim_id"],
                "user_id": r["user_id"],
                "version": r["version"],
                "dossier": json.loads(r["dossier_json"]),
                "canonical_schema": json.loads(r["canonical_json"]),
                "pdf_storage_path": r["pdf_storage_path"],
                "pdf_download_url": f"/api/claims/{claim_id}/report/pdf?version={r['version']}",
                "json_download_url": f"/api/claims/{claim_id}/report/json?version={r['version']}",
                "generated_at": r["generated_at"],
            }
            for r in rows
        ]


async def get_total_insurer_submissions_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM insurer_submissions")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def save_insurer_submission(
    submission_id: str,
    claim_id: str,
    recipient: str,
    recipient_display_name: str,
    adapter_payload: Dict[str, Any],
    delivery_status: str,
    insurer_claim_reference: str,
    processing_status: str,
    pipeline_steps: List[Dict[str, str]],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO insurer_submissions
               (submission_id, claim_id, recipient, recipient_display_name, adapter_payload_json,
                delivery_status, insurer_claim_reference, processing_status, pipeline_steps_json, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                submission_id,
                claim_id,
                recipient,
                recipient_display_name,
                json.dumps(adapter_payload),
                delivery_status,
                insurer_claim_reference,
                processing_status,
                json.dumps(pipeline_steps),
                now,
            ),
        )
        await db.execute(
            "UPDATE claims SET insurer_submission_status = ?, status = ?, updated_at = ? WHERE id = ?",
            ("simulated_submitted", ClaimStatus.SUBMITTED.value, now, claim_id),
        )
        await db.commit()
    return {
        "submission_id": submission_id,
        "claim_id": claim_id,
        "recipient": recipient,
        "recipient_display_name": recipient_display_name,
        "delivery_status": delivery_status,
        "insurer_claim_reference": insurer_claim_reference,
        "processing_status": processing_status,
        "pipeline_steps": pipeline_steps,
        "mapped_payload_preview": adapter_payload,
        "submitted_at": now,
        "disclaimer": "Demo only — not a real insurer submission",
    }


async def get_claim_insurer_submissions(claim_id: str) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM insurer_submissions WHERE claim_id = ? ORDER BY submitted_at DESC",
            (claim_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "submission_id": r["submission_id"],
                "claim_id": r["claim_id"],
                "recipient": r["recipient"],
                "recipient_display_name": r["recipient_display_name"],
                "delivery_status": r["delivery_status"],
                "insurer_claim_reference": r["insurer_claim_reference"],
                "processing_status": r["processing_status"],
                "pipeline_steps": json.loads(r["pipeline_steps_json"] or "[]"),
                "mapped_payload_preview": json.loads(r["adapter_payload_json"] or "{}"),
                "submitted_at": r["submitted_at"],
                "disclaimer": "Demo only — not a real insurer submission",
            }
            for r in rows
        ]


async def get_user_audit_logs(user_id: str, limit: int = 25) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM audit_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
