"""
SQLite persistence layer for ClaimSathi AI (Phase 1).
Uses aiosqlite for async access.
"""

import aiosqlite
import json
from datetime import datetime
from typing import Optional
from .models import ClaimRecord, ClaimStatus

DB_PATH = "claimsathi.db"


async def init_db():
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,
                policy_reference TEXT NOT NULL,
                incident_location TEXT NOT NULL,
                incident_date TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                damage_description TEXT NOT NULL,
                transcript TEXT DEFAULT '',
                status TEXT DEFAULT 'confirmed',
                is_demo INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
        await db.commit()


async def insert_claim(claim: ClaimRecord) -> ClaimRecord:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO claims
               (id, policy_reference, incident_location, incident_date,
                vehicle_type, damage_description, transcript, status,
                is_demo, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                claim.id,
                claim.policy_reference,
                claim.incident_location,
                claim.incident_date,
                claim.vehicle_type,
                claim.damage_description,
                claim.transcript,
                claim.status.value,
                1,
                claim.created_at.isoformat(),
                claim.updated_at.isoformat(),
            ),
        )
        # Insert timeline events
        now = datetime.utcnow().isoformat()
        events = [
            (claim.id, now, "Claim Created [DEMO]",
             f"Demo claim ticket {claim.id} created via simulated voice intake."),
            (claim.id, now, "Transcript Processed [MOCK]",
             "Mock Hinglish transcription analysed and fields extracted."),
            (claim.id, now, "Fields Confirmed",
             "User reviewed and confirmed all extracted claim fields."),
        ]
        await db.executemany(
            """INSERT INTO timeline_events (claim_id, timestamp, title, description)
               VALUES (?, ?, ?, ?)""",
            events,
        )
        await db.commit()
    return claim


async def get_claim(claim_id: str) -> Optional[ClaimRecord]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM claims WHERE id = ?", (claim_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return ClaimRecord(
            id=row["id"],
            policy_reference=row["policy_reference"],
            incident_location=row["incident_location"],
            incident_date=row["incident_date"],
            vehicle_type=row["vehicle_type"],
            damage_description=row["damage_description"],
            transcript=row["transcript"],
            status=ClaimStatus(row["status"]),
            is_demo=bool(row["is_demo"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


async def get_all_claims() -> list[ClaimRecord]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM claims ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            ClaimRecord(
                id=row["id"],
                policy_reference=row["policy_reference"],
                incident_location=row["incident_location"],
                incident_date=row["incident_date"],
                vehicle_type=row["vehicle_type"],
                damage_description=row["damage_description"],
                transcript=row["transcript"],
                status=ClaimStatus(row["status"]),
                is_demo=bool(row["is_demo"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]


async def get_timeline(claim_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM timeline_events WHERE claim_id = ? ORDER BY timestamp ASC",
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


async def get_claim_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM claims")
        row = await cursor.fetchone()
        return row[0] if row else 0
