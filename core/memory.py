"""High-level memory facade.

Sits between the assistant and the raw SQLite layer, exposing the two kinds of
memory described in the spec:

* long-term facts (key/value preferences and project knowledge)
* the conversation log (short-term context, fed to the AI engine)

It also delegates task storage, so the tasks tool only needs a ``Memory``.
"""

from __future__ import annotations

from memory.database import Database


class Memory:
    def __init__(self, database: Database | None = None):
        self._db = database if database is not None else Database()

    @property
    def database(self) -> Database:
        return self._db

    def close(self) -> None:
        self._db.close()

    # ------------------------------------------------------------------ #
    # Long-term facts
    # ------------------------------------------------------------------ #
    def remember(self, key: str, value: str) -> None:
        """Store or update a long-term fact."""
        if not key or value is None:
            return
        self._db.set_fact(key, str(value))

    def recall(self, key: str) -> str | None:
        """Return a stored fact, or ``None`` if unknown."""
        if not key:
            return None
        return self._db.get_fact(key)

    def all_facts(self) -> dict[str, str]:
        return self._db.all_facts()

    def forget(self, key: str) -> bool:
        return self._db.forget_fact(key)

    # ------------------------------------------------------------------ #
    # Conversation log
    # ------------------------------------------------------------------ #
    def log(self, role: str, content: str) -> None:
        self._db.log_message(role, content)

    def recent(self, limit: int = 10) -> list[dict]:
        return self._db.recent_messages(limit)

    # ------------------------------------------------------------------ #
    # Tasks (delegated storage for the tasks tool)
    # ------------------------------------------------------------------ #
    def add_task(self, title: str, due: str | None = None) -> dict:
        return self._db.add_task(title, due)

    def list_tasks(self, include_done: bool = False) -> list[dict]:
        return self._db.list_tasks(include_done)

    def complete_task(self, match: str) -> dict | None:
        return self._db.complete_task(match)

    def remove_task(self, match: str) -> int:
        return self._db.remove_task(match)
