"""End-to-end tests for the assistant pipeline."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.assistant import Assistant
from core.memory import Memory
from memory.database import Database
from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        memory = Memory(Database(Path(self._tmp.name) / "assistant.db"))
        self.assistant = Assistant(
            memory=memory,
            tts=TextToSpeech(enabled=False),
            stt_engine=SpeechToText(enabled=False),
        )

    def tearDown(self):
        self.assistant.memory.close()
        self._tmp.cleanup()

    def test_greeting(self):
        reply = self.assistant.handle("hello")
        self.assertIn(self.assistant.name, reply)

    def test_empty_input(self):
        self.assertEqual(self.assistant.handle(""), "")

    def test_unknown_command_falls_back(self):
        reply = self.assistant.handle("flibbertigibbet quux")
        self.assertTrue(reply)

    def test_memory_roundtrip(self):
        self.assistant.handle("remember my city is Pune")
        reply = self.assistant.handle("what is my city")
        self.assertIn("Pune", reply)

    def test_task_roundtrip(self):
        self.assistant.handle("remind me to water plants")
        reply = self.assistant.handle("what are my tasks")
        self.assertIn("water plants", reply)

    def test_system_status(self):
        reply = self.assistant.handle("system status")
        self.assertTrue(reply)
        self.assertIn("CPU", reply)

    def test_context_tracks_conversation(self):
        self.assistant.handle("hello")
        self.assistant.handle("thanks")
        roles = [turn.role for turn in self.assistant.context.recent(10)]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)


if __name__ == "__main__":
    unittest.main()
