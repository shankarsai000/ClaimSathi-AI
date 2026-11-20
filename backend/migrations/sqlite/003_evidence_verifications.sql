-- ClaimSathi AI — SQLite Schema Migration 003: 5-Stage Evidence Verifications
-- Stores complete stage-by-stage fraud risk, YOLO vehicle/damage detections, and spoof scores

CREATE TABLE IF NOT EXISTS evidence_verifications (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    decision TEXT NOT NULL,
    spoof_risk REAL NOT NULL,
    predicted_spoof_class TEXT NOT NULL,
    vehicle_detected INTEGER NOT NULL,
    damage_count INTEGER NOT NULL,
    stage_results_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    processing_time_ms REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_verifications_sha256 ON evidence_verifications(sha256);
CREATE INDEX IF NOT EXISTS idx_evidence_verifications_decision ON evidence_verifications(decision);
CREATE INDEX IF NOT EXISTS idx_evidence_verifications_created_at ON evidence_verifications(created_at);
