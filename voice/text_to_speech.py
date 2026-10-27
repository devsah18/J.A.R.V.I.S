"""Text-to-speech.

VARSHA is voice-first, so every spoken response goes through here. Uses pyttsx3
(offline, Windows SAPI5) when available; when it is not, the text is logged and
the assistant continues in text mode rather than pretending it spoke.

The speech engine is created lazily on the first utterance, so purely textual
sessions never pay for (or leave running) a speech backend.
"""

from __future__ import annotations

import logging
import threading

try:
    import pyttsx3
except ImportError:  # pragma: no cover - optional at runtime
    pyttsx3 = None

logger = logging.getLogger(__name__)


class TextToSpeech:
    def __init__(
        self,
        enabled: bool = True,
        rate: int = 180,
        volume: float = 1.0,
        voice_id: str | None = None,
    ):
        self.rate = rate
        self.volume = volume
        self.voice_id = voice_id
        self._engine = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._enabled = bool(enabled and pyttsx3 is not None)

    # ------------------------------------------------------------------ #
    @property
    def available(self) -> bool:
        return self._enabled

    def _ensure_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            engine = pyttsx3.init()
        except Exception as error:  # noqa: BLE001 - engine init varies by platform
            logger.warning("TTS engine unavailable: %s", error)
            self._enabled = False
            return None
        engine.setProperty("rate", self.rate)
        engine.setProperty("volume", self.volume)
        if self.voice_id:
            engine.setProperty("voice", self.voice_id)
        self._engine = engine
        return engine

    # ------------------------------------------------------------------ #
    def speak(self, text: str, block: bool = True) -> bool:
        """Speak ``text``. Returns True if it was spoken, False otherwise."""
        text = (text or "").strip()
        if not text or not self._enabled:
            if text:
                logger.info("TTS unavailable; response was: %s", text)
            return False
        if block:
            return self._speak_now(text)
        self._thread = threading.Thread(target=self._speak_now, args=(text,), daemon=True)
        self._thread.start()
        return True

    def _speak_now(self, text: str) -> bool:
        with self._lock:
            engine = self._ensure_engine()
            if engine is None:
                return False
            try:
                engine.say(text)
                engine.runAndWait()
                return True
            except Exception as error:  # noqa: BLE001 - never let TTS crash the loop
                logger.warning("TTS playback failed: %s", error)
                return False

    def stop(self) -> None:
        """Interrupt current playback (used for barge-in)."""
        with self._lock:
            if self._engine is None:
                return
            try:
                self._engine.stop()
            except Exception:  # noqa: BLE001 - stopping a stopped engine is fine
                pass

    def is_speaking(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
