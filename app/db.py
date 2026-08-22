"""SQLite schema and connection boundary for CohortLoom."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL UNIQUE,
    audience_size INTEGER NOT NULL CHECK (audience_size >= 0),
    summary TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engagement_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES weekly_snapshots(id),
    platform TEXT NOT NULL,
    views INTEGER NOT NULL CHECK (views >= 0),
    comments INTEGER NOT NULL CHECK (comments >= 0),
    saves INTEGER NOT NULL CHECK (saves >= 0),
    shares INTEGER NOT NULL CHECK (shares >= 0),
    new_followers INTEGER NOT NULL CHECK (new_followers >= 0),
    qualified_replies INTEGER NOT NULL CHECK (qualified_replies >= 0),
    synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
    UNIQUE(snapshot_id, platform)
);

CREATE TABLE IF NOT EXISTS audience_hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES weekly_snapshots(id),
    segment_key TEXT NOT NULL,
    assumption TEXT NOT NULL,
    evidence_basis TEXT NOT NULL,
    risk_note TEXT NOT NULL,
    memory_key TEXT NOT NULL UNIQUE,
    injection_flagged INTEGER NOT NULL CHECK (injection_flagged IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED')),
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS growth_experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis_id INTEGER NOT NULL UNIQUE REFERENCES audience_hypotheses(id),
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('BLOCKED_PENDING_APPROVAL', 'WAITING_FOR_MEMORY',
                   'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'CANCELLED')
    ),
    why_now TEXT NOT NULL,
    success_condition TEXT NOT NULL,
    stop_condition TEXT NOT NULL,
    seven_day_plan_json TEXT NOT NULL,
    review_due_label TEXT NOT NULL,
    observed_result TEXT,
    review_decision TEXT CHECK (
        review_decision IS NULL OR review_decision IN ('CONTINUE', 'STOP', 'REVISE')
    ),
    review_reason TEXT,
    follow_up_count INTEGER NOT NULL DEFAULT 0,
    last_follow_up_at TEXT,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS minds_exchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis_id INTEGER NOT NULL REFERENCES audience_hypotheses(id),
    operation TEXT NOT NULL CHECK (
        operation IN ('store_hypothesis', 'recall_and_plan', 'recall_and_review')
    ),
    request_id TEXT NOT NULL UNIQUE,
    memory_key TEXT NOT NULL,
    session_alias TEXT NOT NULL,
    request_body TEXT NOT NULL,
    request_hash TEXT NOT NULL UNIQUE,
    semantic_hash TEXT NOT NULL UNIQUE,
    expected_channels_json TEXT NOT NULL DEFAULT '[]',
    injection_flagged INTEGER NOT NULL CHECK (injection_flagged IN (0, 1)),
    status TEXT NOT NULL CHECK (
        status IN ('PREPARED', 'SENDING', 'SENT', 'UNCERTAIN', 'COMPLETED', 'REJECTED')
    ),
    credits_before REAL,
    remote_conversation_id TEXT,
    remote_message_id TEXT,
    remote_reply_id TEXT UNIQUE,
    response_json TEXT,
    response_hash TEXT UNIQUE,
    raw_response_hash TEXT,
    clean_response_hash TEXT,
    history_request_hash TEXT,
    request_created_at TEXT,
    reply_created_at TEXT,
    timestamp_order_verified INTEGER CHECK (timestamp_order_verified IN (0, 1)),
    timestamp_evidence_limitation TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details_json TEXT NOT NULL
);
"""


class Database:
    """Small fail-closed SQLite wrapper."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO app_state(key, value) VALUES ('paused', '0')"
            )
            connection.execute(
                "INSERT OR IGNORE INTO app_state(key, value) VALUES ('auto_outreach', '0')"
            )
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()
