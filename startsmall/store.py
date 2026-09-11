"""SQLite persistence. One file, one learner, no accounts.

Tables
  settings       key/value JSON
  concept_state  per-concept mastery and review schedule
  attempts       every attempt, with hint use and solution views recorded honestly
  sessions       a session = one open of the app that started an activity
  events         light event log used by the evaluation view
  tasks          non-learning "everyday" tasks with a physical next action
  collection     things built or understood, shown on the home screen

All timestamps are unix seconds (float).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS concept_state (
  concept_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'new',
  review_stage INTEGER NOT NULL DEFAULT 0,
  due_at REAL,
  last_seen_at REAL,
  independent_count INTEGER NOT NULL DEFAULT 0,
  assisted_count INTEGER NOT NULL DEFAULT 0,
  fail_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at REAL NOT NULL,
  session_id INTEGER,
  activity_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  correct INTEGER,
  hints_used INTEGER NOT NULL DEFAULT 0,
  solution_viewed INTEGER NOT NULL DEFAULT 0,
  is_review INTEGER NOT NULL DEFAULT 0,
  is_variation INTEGER NOT NULL DEFAULT 0,
  is_micro INTEGER NOT NULL DEFAULT 0,
  seconds REAL,
  answer TEXT,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at REAL NOT NULL,
  ended_at REAL,
  mode TEXT NOT NULL,
  activities_done INTEGER NOT NULL DEFAULT 0,
  enjoyment INTEGER,
  frustration INTEGER,
  note TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at REAL NOT NULL,
  kind TEXT NOT NULL,
  data TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL NOT NULL,
  title TEXT NOT NULL,
  next_action TEXT NOT NULL,
  stop_when TEXT NOT NULL,
  minutes INTEGER NOT NULL DEFAULT 5,
  done_at REAL,
  last_started_at REAL,
  starts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS collection (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at REAL NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  detail TEXT,
  activity_id TEXT,
  concept_id TEXT
);
CREATE INDEX IF NOT EXISTS attempts_at ON attempts(at);
CREATE INDEX IF NOT EXISTS attempts_activity ON attempts(activity_id);
"""

# Every setting the app reads. Anything not listed here is rejected on write,
# so a typo in the UI cannot create a phantom setting.
DEFAULT_SETTINGS = {
    "entry_minutes": 2,          # design default, not an optimum
    "session_minutes": 8,        # design default, not an optimum
    "cue": "after opening my laptop",
    "quiet_hours": [22, 8],      # [start_hour, end_hour], 24h clock
    "reminders_enabled": False,  # off until the learner turns it on
    "animations": True,
    "sparks_enabled": True,      # cosmetic, secondary, transparent rules
    "ai_enabled": False,         # curated fallback is always available
    "ai_model": "claude-opus-5",
    "current_track": "python",
    "onboarded": False,
}


class Store:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path, timeout=5)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ---- settings -------------------------------------------------------
    def get_settings(self) -> dict:
        out = dict(DEFAULT_SETTINGS)
        with self.conn() as c:
            for row in c.execute("SELECT key, value FROM settings"):
                out[row["key"]] = json.loads(row["value"])
        return out

    def set_settings(self, patch: dict) -> dict:
        with self.conn() as c:
            for k, v in patch.items():
                if k in DEFAULT_SETTINGS:
                    c.execute(
                        "INSERT INTO settings(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (k, json.dumps(v)),
                    )
        return self.get_settings()

    # ---- concept state --------------------------------------------------
    def concept_state(self, concept_id: str) -> dict:
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM concept_state WHERE concept_id=?", (concept_id,)
            ).fetchone()
        if row:
            return dict(row)
        return {
            "concept_id": concept_id, "status": "new", "review_stage": 0,
            "due_at": None, "last_seen_at": None, "independent_count": 0,
            "assisted_count": 0, "fail_count": 0,
        }

    def all_concept_states(self) -> dict[str, dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM concept_state").fetchall()
        return {r["concept_id"]: dict(r) for r in rows}

    def save_concept_state(self, st: dict) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO concept_state(concept_id,status,review_stage,due_at,last_seen_at,
                     independent_count,assisted_count,fail_count)
                   VALUES(:concept_id,:status,:review_stage,:due_at,:last_seen_at,
                     :independent_count,:assisted_count,:fail_count)
                   ON CONFLICT(concept_id) DO UPDATE SET
                     status=excluded.status, review_stage=excluded.review_stage,
                     due_at=excluded.due_at, last_seen_at=excluded.last_seen_at,
                     independent_count=excluded.independent_count,
                     assisted_count=excluded.assisted_count, fail_count=excluded.fail_count""",
                st,
            )

    # ---- attempts -------------------------------------------------------
    def add_attempt(self, **fields) -> int:
        fields.setdefault("at", time.time())
        if isinstance(fields.get("detail"), (dict, list)):
            fields["detail"] = json.dumps(fields["detail"])
        cols = ",".join(fields)
        marks = ",".join("?" for _ in fields)
        with self.conn() as c:
            cur = c.execute(f"INSERT INTO attempts({cols}) VALUES({marks})", list(fields.values()))
            return cur.lastrowid

    def attempts_for_activity(self, activity_id: str, limit: int = 20) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM attempts WHERE activity_id=? ORDER BY at DESC LIMIT ?",
                (activity_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def attempts_since(self, since: float) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM attempts WHERE at>=? ORDER BY at", (since,)).fetchall()
        return [dict(r) for r in rows]

    def last_attempt_at(self) -> float | None:
        with self.conn() as c:
            row = c.execute("SELECT MAX(at) AS m FROM attempts").fetchone()
        return row["m"]

    def recent_activity_ids(self, n: int = 12) -> list[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT activity_id FROM attempts ORDER BY at DESC LIMIT ?", (n,)
            ).fetchall()
        return [r["activity_id"] for r in rows]

    # ---- sessions -------------------------------------------------------
    def start_session(self, mode: str) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO sessions(started_at, mode) VALUES(?,?)", (time.time(), mode)
            )
            return cur.lastrowid

    def bump_session(self, session_id: int) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE sessions SET activities_done=activities_done+1 WHERE id=?", (session_id,)
            )

    def end_session(self, session_id: int, enjoyment=None, frustration=None, note=None) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE sessions SET ended_at=?, enjoyment=COALESCE(?,enjoyment), "
                "frustration=COALESCE(?,frustration), note=COALESCE(?,note) WHERE id=?",
                (time.time(), enjoyment, frustration, note, session_id),
            )

    def sessions_since(self, since: float) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM sessions WHERE started_at>=? ORDER BY started_at", (since,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- events ---------------------------------------------------------
    def log(self, kind: str, data=None) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO events(at,kind,data) VALUES(?,?,?)",
                (time.time(), kind, json.dumps(data) if data is not None else None),
            )

    def events_since(self, since: float) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM events WHERE at>=? ORDER BY at", (since,)).fetchall()
        return [dict(r) for r in rows]

    # ---- tasks ----------------------------------------------------------
    def add_task(self, title, next_action, stop_when, minutes=5) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO tasks(created_at,title,next_action,stop_when,minutes) VALUES(?,?,?,?,?)",
                (time.time(), title, next_action, stop_when, int(minutes)),
            )
            return cur.lastrowid

    def list_tasks(self, include_done=False) -> list[dict]:
        q = "SELECT * FROM tasks" + ("" if include_done else " WHERE done_at IS NULL")
        with self.conn() as c:
            rows = c.execute(q + " ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def update_task(self, task_id: int, **fields) -> None:
        allowed = {"title", "next_action", "stop_when", "minutes", "done_at", "last_started_at"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        with self.conn() as c:
            c.execute(f"UPDATE tasks SET {sets} WHERE id=?", [*fields.values(), task_id])

    def task_started(self, task_id: int) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE tasks SET starts=starts+1, last_started_at=? WHERE id=?",
                (time.time(), task_id),
            )

    def delete_task(self, task_id: int) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    # ---- collection -----------------------------------------------------
    def add_collection(self, kind, title, detail=None, activity_id=None, concept_id=None) -> bool:
        with self.conn() as c:
            dup = c.execute(
                "SELECT 1 FROM collection WHERE kind=? AND title=?", (kind, title)
            ).fetchone()
            if dup:
                return False
            c.execute(
                "INSERT INTO collection(at,kind,title,detail,activity_id,concept_id) VALUES(?,?,?,?,?,?)",
                (time.time(), kind, title, detail, activity_id, concept_id),
            )
            return True

    def list_collection(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM collection ORDER BY at DESC").fetchall()
        return [dict(r) for r in rows]
