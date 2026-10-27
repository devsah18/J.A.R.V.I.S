"""Tests for the SQLite persistence layer and the memory facade."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.memory import Memory
from memory.database import Database


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "test_memory.db"
        self.memory = Memory(Database(db_path))

    def tearDown(self):
        self.memory.close()
        self._tmp.cleanup()

    def test_remember_and_recall(self):
        self.memory.remember("Editor", "VS Code")
        self.assertEqual(self.memory.recall("editor"), "VS Code")  # keys are case-insensitive

    def test_recall_missing_is_none(self):
        self.assertIsNone(self.memory.recall("nothing"))

    def test_remember_overwrites(self):
        self.memory.remember("editor", "vim")
        self.memory.remember("editor", "VS Code")
        self.assertEqual(self.memory.recall("editor"), "VS Code")

    def test_forget(self):
        self.memory.remember("editor", "vim")
        self.assertTrue(self.memory.forget("editor"))
        self.assertIsNone(self.memory.recall("editor"))
        self.assertFalse(self.memory.forget("editor"))

    def test_conversation_log(self):
        self.memory.log("user", "hello")
        self.memory.log("assistant", "hi")
        recent = self.memory.recent(5)
        self.assertEqual([turn["role"] for turn in recent], ["user", "assistant"])

    def test_task_lifecycle(self):
        task = self.memory.add_task("write tests", due="today")
        self.assertEqual(task["title"], "write tests")

        open_tasks = self.memory.list_tasks()
        self.assertEqual(len(open_tasks), 1)

        completed = self.memory.complete_task("tests")
        self.assertIsNotNone(completed)
        self.assertEqual(self.memory.list_tasks(), [])

    def test_remove_task(self):
        self.memory.add_task("disposable")
        self.assertEqual(self.memory.remove_task("disposable"), 1)
        self.assertEqual(self.memory.list_tasks(), [])


if __name__ == "__main__":
    unittest.main()
