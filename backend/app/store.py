"""SQLite persistence. Sessions are saved after every turn so a server
restart resumes the interview instead of losing it."""

import sqlite3
import time
from pathlib import Path

from . import config
from .interview.session import InterviewSession

SCHEMA = """
CREATE TABLE IF NOT EXISTS interviews (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    config TEXT NOT NULL,
    profile TEXT,
    plan TEXT NOT NULL,
    state TEXT NOT NULL,
    messages TEXT NOT NULL,
    turns TEXT NOT NULL,
    elapsed_s REAL NOT NULL DEFAULT 0,
    finished INTEGER NOT NULL DEFAULT 0,
    report TEXT
);
"""


class Store:
    def __init__(self, path: Path = config.DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def save(self, s: InterviewSession) -> None:
        rec = s.to_record()
        now = time.time()
        self._conn.execute(
            """INSERT INTO interviews (id, created_at, updated_at, config, profile, plan, state, messages, turns, elapsed_s, finished, report)
               VALUES (:id, :now, :now, :config, :profile, :plan, :state, :messages, :turns, :elapsed_s, :finished, :report)
               ON CONFLICT(id) DO UPDATE SET
                 updated_at=:now, profile=:profile, plan=:plan, state=:state, messages=:messages, turns=:turns,
                 elapsed_s=:elapsed_s, finished=:finished, report=:report""",
            {**rec, "now": now},
        )
        self._conn.commit()

    def load(self, session_id: str) -> InterviewSession | None:
        row = self._conn.execute("SELECT * FROM interviews WHERE id=?", (session_id,)).fetchone()
        return InterviewSession.from_record(dict(row)) if row else None

    def list(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, created_at, config, elapsed_s, finished, report IS NOT NULL AS has_report "
            "FROM interviews ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
