"""SQLite persistence for VARSHA: long-term facts, conversation log and tasks."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    due        TEXT,
    done       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Thin, thread-safe wrapper around a single SQLite file."""

    def __init__(self, db_path: Path | str | None = None):
        self.path = Path(db_path) if db_path else config.MEMORY_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.executescript(SCHEMA)
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    # ------------------------------------------------------------------ #
    # Facts (long-term memory)
    # ------------------------------------------------------------------ #
    def set_fact(self, key: str, value: str) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO facts (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key.strip().lower(), value, _now()),
            )
            self._connection.commit()

    def get_fact(self, key: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM facts WHERE key = ?", (key.strip().lower(),)
            ).fetchone()
        return row["value"] if row else None

    def all_facts(self) -> dict[str, str]:
        with self._lock:
            rows = self._connection.execute("SELECT key, value FROM facts").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def forget_fact(self, key: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM facts WHERE key = ?", (key.strip().lower(),)
            )
            self._connection.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------ #
    # Conversation log
    # ------------------------------------------------------------------ #
    def log_message(self, role: str, content: str) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO conversations (role, content, created_at) VALUES (?, ?, ?)",
                (role, content, _now()),
            )
            self._connection.commit()

    def recent_messages(self, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT role, content, created_at FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #
    def add_task(self, title: str, due: str | None = None) -> dict:
        with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO tasks (title, due, done, created_at) VALUES (?, ?, 0, ?)",
                (title, due, _now()),
            )
            self._connection.commit()
            task_id = cursor.lastrowid
        return {"id": task_id, "title": title, "due": due, "done": False}

    def list_tasks(self, include_done: bool = False) -> list[dict]:
        query = "SELECT id, title, due, done FROM tasks"
        if not include_done:
            query += " WHERE done = 0"
        query += " ORDER BY id"
        with self._lock:
            rows = self._connection.execute(query).fetchall()
        return [
            {"id": row["id"], "title": row["title"], "due": row["due"], "done": bool(row["done"])}
            for row in rows
        ]

    def complete_task(self, match: str) -> dict | None:
        task = self._find_task(match)
        if task is None:
            return None
        with self._lock:
            self._connection.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task["id"],))
            self._connection.commit()
        return task

    def remove_task(self, match: str) -> int:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM tasks WHERE done = 0 AND lower(title) LIKE ?",
                (f"%{match.strip().lower()}%",),
            )
            self._connection.commit()
        return cursor.rowcount

    def _find_task(self, match: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT id, title, due, done FROM tasks "
                "WHERE done = 0 AND lower(title) LIKE ? ORDER BY id LIMIT 1",
                (f"%{match.strip().lower()}%",),
            ).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "title": row["title"], "due": row["due"], "done": bool(row["done"])}
