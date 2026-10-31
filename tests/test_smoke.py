"""Project smoke test: the package imports and the assistant constructs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.assistant import Assistant
from core.memory import Memory
from memory.database import Database
from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech


class SmokeTest(unittest.TestCase):
    def test_assistant_constructs(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = Memory(Database(Path(tmp) / "smoke.db"))
            assistant = Assistant(
                memory=memory,
                tts=TextToSpeech(enabled=False),
                stt_engine=SpeechToText(enabled=False),
            )
            self.assertIsNotNone(assistant.engine)
            expected = [
                "apps", "browser", "calculator", "dictionary", "exam",
                "files", "finance", "game", "image", "jokes", "maps", "news",
                "search", "system", "tasks", "weather", "wikipedia",
            ]
            self.assertEqual(assistant.router.tool_names(), expected)
            memory.close()


if __name__ == "__main__":
    unittest.main()
