"""
Append-only audit persistence.

A downloadable .txt report is not, on its own, an audit trail: nothing
stops it from being edited after the fact, and nothing guarantees it
was ever saved anywhere durable. This module writes every completed
workup to a local SQLite table (the app never issues UPDATE or DELETE
against it — inserts only) and stamps each record with a SHA-256 hash
of its own content, so a record can later be checked for tampering by
recomputing the hash and comparing.

In a real deployment this table would be a governed, access-controlled
datastore rather than a local SQLite file; SQLite stands in here so
the pattern — hash-anchored, append-only, queryable for aggregates —
is demonstrable without external infrastructure.
"""

from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "audit_log.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            case_id TEXT NOT NULL,
            reason_code TEXT,
            scheme TEXT,
            analyst TEXT NOT NULL,
            second_reviewer TEXT,
            ai_recommendation TEXT,
            human_decision TEXT,
            evidence_score INTEGER,
            confidence TEXT,
            ruleset_hash TEXT,
            payload_json TEXT NOT NULL,
            record_hash TEXT NOT NULL
        )
    """)
    return conn


def persist_record(record: dict) -> str:
    """Writes one workup record (insert-only) and returns its content hash."""
    payload = json.dumps(record, sort_keys=True, default=str)
    record_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    conn = _connect()
    with conn:
        conn.execute(
            """INSERT INTO audit_log
               (ts_utc, case_id, reason_code, scheme, analyst, second_reviewer,
                ai_recommendation, human_decision, evidence_score, confidence,
                ruleset_hash, payload_json, record_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record["timestamp"], record["case_id"], record.get("reason_code"),
                record.get("scheme"), record["analyst"], record.get("second_reviewer"),
                record.get("ai_recommendation"), record.get("human_decision"),
                record.get("evidence_score"), record.get("confidence"),
                record.get("ruleset_hash"), payload, record_hash,
            ),
        )
    conn.close()
    return record_hash


def fetch_all_records() -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_log ORDER BY ts_utc DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_portfolio_metrics() -> dict:
    """Aggregates for the portfolio view: case volume, avg evidence
    score and represent-rate by reason code, and human override rate.
    This is the piece that turns the tool from 'runs one case through
    an LLM' into something that demonstrates measurable process
    tracking across a caseload."""
    records = fetch_all_records()
    if not records:
        return {"total_cases": 0, "by_reason_code": {}, "override_rate": 0}

    by_reason_code: dict[str, dict] = {}
    overrides = 0

    for r in records:
        key = f"{(r.get('scheme') or '').upper()} {r.get('reason_code') or ''}".strip()
        bucket = by_reason_code.setdefault(key, {"count": 0, "score_sum": 0, "represent_count": 0})
        bucket["count"] += 1
        bucket["score_sum"] += r.get("evidence_score") or 0
        if (r.get("human_decision") or "").upper() == "REPRESENT":
            bucket["represent_count"] += 1

        ai_rec = r.get("ai_recommendation")
        human_dec = r.get("human_decision")
        if ai_rec and human_dec:
            if ai_rec.upper().replace("_", " ") != human_dec.upper():
                overrides += 1

    for bucket in by_reason_code.values():
        bucket["avg_evidence_score"] = round(bucket["score_sum"] / bucket["count"])
        bucket["represent_rate"] = round(100 * bucket["represent_count"] / bucket["count"])

    return {
        "total_cases": len(records),
        "by_reason_code": by_reason_code,
        "override_rate": round(100 * overrides / len(records)),
    }