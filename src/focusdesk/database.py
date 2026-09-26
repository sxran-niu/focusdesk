"""SQLite persistence, foreign keys, and atomic write transactions."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL,
 target REAL NOT NULL CHECK(target > 0), unit TEXT NOT NULL,
 target_date TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))
);
CREATE TABLE IF NOT EXISTS milestones (
 id INTEGER PRIMARY KEY, goal_id INTEGER NOT NULL REFERENCES goals(id),
 title TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
 target REAL NOT NULL CHECK(target > 0), original_target REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes (
 id INTEGER PRIMARY KEY, milestone_id INTEGER NOT NULL REFERENCES milestones(id),
 title TEXT NOT NULL, amount REAL NOT NULL CHECK(amount > 0),
 status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','passed','failed')),
 result_date TEXT, grade TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS requirements (
 id INTEGER PRIMARY KEY, goal_id INTEGER NOT NULL REFERENCES goals(id),
 title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0 CHECK(done IN (0,1))
);
CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
 minutes INTEGER NOT NULL CHECK(minutes BETWEEN 5 AND 720),
 priority INTEGER NOT NULL CHECK(priority BETWEEN 1 AND 3), due_date TEXT,
 outcome_id INTEGER REFERENCES outcomes(id), notes TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done')),
 completed_at TEXT, actual_minutes INTEGER CHECK(actual_minutes >= 0)
);
CREATE TABLE IF NOT EXISTS day_settings (
 date TEXT PRIMARY KEY, start INTEGER NOT NULL, end INTEGER NOT NULL,
 CHECK(start >= 0 AND end <= 1440 AND start < end)
);
CREATE TABLE IF NOT EXISTS blocks (
 id INTEGER PRIMARY KEY, date TEXT NOT NULL,
 task_id INTEGER NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
 start INTEGER NOT NULL, end INTEGER NOT NULL,
 CHECK(start >= 0 AND end <= 1440 AND start < end)
);
CREATE TABLE IF NOT EXISTS changes (
 id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id INTEGER NOT NULL,
 old_value TEXT NOT NULL, new_value TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS weekly_targets (
 week_start TEXT NOT NULL, outcome_id INTEGER NOT NULL REFERENCES outcomes(id),
 minutes INTEGER NOT NULL CHECK(minutes BETWEEN 0 AND 10080),
 PRIMARY KEY(week_start,outcome_id)
);
CREATE TABLE IF NOT EXISTS recurring_rules (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL,
 category TEXT NOT NULL CHECK(category IN ('study','life','rest')),
 weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),
 start_date TEXT NOT NULL, end_date TEXT NOT NULL,
 start INTEGER NOT NULL, end INTEGER NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 CHECK(start >= 0 AND end <= 1440 AND start < end)
);
CREATE TABLE IF NOT EXISTS fixed_blocks (
 id INTEGER PRIMARY KEY, rule_id INTEGER NOT NULL REFERENCES recurring_rules(id),
 date TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
 UNIQUE(rule_id,date), CHECK(start >= 0 AND end <= 1440 AND start < end)
);
"""


class Database:
    """Each operation opens its own connection, safe for concurrent web requests."""

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(goals)")
            }
            if "archived" not in columns:
                connection.execute(
                    "ALTER TABLE goals ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 "
                    "CHECK(archived IN (0,1))"
                )

    @contextmanager
    def connect(self, write=False):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def rows(self, query, params=()):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, params)]

    def insert(self, table, values):
        """Insert trusted field names and bound values from the service layer."""
        columns = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        with self.connect(write=True) as connection:
            if table == "tasks":
                # Keep deleted task IDs retired so their audit trail cannot attach
                # to a new task that happens to reuse SQLite's highest row ID.
                retired = connection.execute(
                    "SELECT value FROM metadata WHERE key='retired_task_id'"
                ).fetchone()
                if retired:
                    highest = connection.execute(
                        "SELECT coalesce(max(id),0) FROM tasks"
                    ).fetchone()[0]
                    values = {"id": max(highest, int(retired[0])) + 1, **values}
                    columns = ", ".join(values)
                    marks = ", ".join("?" for _ in values)
            cursor = connection.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({marks})",
                tuple(values.values()),
            )
            return cursor.lastrowid
