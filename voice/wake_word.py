"""Wake-word detection.

Sits on top of :class:`~voice.speech_to_text.SpeechToText`. A single listen is
used both to detect the wake word and to capture any command that followed it
("VARSHA, open Chrome"), so the user never has to repeat themselves.
"""

from __future__ import annotations

import logging
import re

from voice import speech_to_text as stt

logger = logging.getLogger(__name__)


class WakeWordDetector:
    def __init__(self, speech_to_text, wake_word: str = "jarvis"):
        self._stt = speech_to_text
        self.wake_word = (wake_word or "jarvis").strip().lower()

        # Build pattern matching wake word and natural variations
        aliases = [re.escape(self.wake_word)]
        if self.wake_word == "jarvis":
            aliases.extend([
                r"hey\s+jarvis", r"hi\s+jarvis", r"hello\s+jarvis",
                r"ok\s+jarvis", r"okay\s+jarvis",
                r"javis", r"jervis", r"travis", r"service", r"charvis", r"darvis",
            ])
        elif self.wake_word == "varsha":
            aliases.extend([r"hey\s+varsha", r"hi\s+varsha", r"hello\s+varsha", r"barsha"])

        self._pattern = re.compile(r"\b(" + "|".join(aliases) + r")\b", re.IGNORECASE)

    @property
    def available(self) -> bool:
        return self._stt is not None and self._stt.available

    def contains_wake_word(self, text: str) -> bool:
        return bool(text) and self._pattern.search(text) is not None

    def strip(self, text: str) -> str:
        """Remove the wake word and any leading punctuation from a phrase."""
        cleaned = self._pattern.sub("", text or "", count=1)
        return cleaned.strip(" ,.!?").strip()

    def detect(self) -> tuple[bool, str]:
        """Listen once for wake word."""
        if not self.available:
            return False, ""

        print(f"[{self.wake_word.upper()} is listening...]", flush=True)
        result = self._stt.listen(timeout=6, phrase_limit=8)
        if result.status == stt.UNCLEAR:
            print(
                f"[{self.wake_word.upper()}: Heard audio, but could not understand. "
                "Please say the wake word and command clearly, then try again.]",
                flush=True,
            )
            return False, ""
        elif result.status != stt.OK:
            return False, ""

        if self.contains_wake_word(result.text):
            remainder = self.strip(result.text)
            print(f">> Heard wake word! (command: '{remainder}')", flush=True)
            return True, remainder

        print(f">> Heard: '{result.text}' (Say '{self.wake_word}' to activate)", flush=True)
        return False, ""

