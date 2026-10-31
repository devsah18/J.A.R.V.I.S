"""Main assistant orchestration layer (voice-first).

Wires the AI brain, memory, tool router, permissions and voice together and
drives the interaction loop. Three front-ends share the same :meth:`handle`
pipeline: interactive CLI, hands-free voice, and the PySide6 HUD.
"""

from __future__ import annotations

import logging

import config
from ai.model_manager import create_engine, engine_name
from core.context import Context
from core.memory import Memory
from core.permissions import PermissionManager
from core.router import ActionRequest, Router
from tools.apps import AppsTool
from tools.browser import BrowserTool
from tools.calculator import CalculatorTool
from tools.dictionary import DictionaryTool
from tools.exam_prep import ExamPrepTool
from tools.files import FilesTool
from tools.finance import FinanceTool
from tools.image import ImageTool
from tools.jokes import JokesTool
from tools.maps import MapsTool
from tools.news import NewsTool
from tools.search import SearchTool
from tools.system import SystemTool
from tools.tasks import TasksTool
from tools.weather import WeatherTool
from tools.wikipedia import WikipediaTool
from tools.game import GameTool
from voice import speech_to_text as stt
from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech
from voice.wake_word import WakeWordDetector

logger = logging.getLogger(__name__)

VALID_MODES = ("cli", "gui", "voice", "auto")
_EXIT_COMMANDS = {
    "exit", "quit", "bye", "goodbye", "good night", "goodnight",
    "shut down", "shutdown", "stop listening", "that's all",
}
_AFFIRMATIVE = {"yes", "yeah", "yep", "yup", "sure", "do it", "confirm", "go ahead", "ok", "okay"}


class Assistant:
    def __init__(self, memory: Memory | None = None, tts: TextToSpeech | None = None,
                 stt_engine: SpeechToText | None = None, engine=None):
        config.ensure_dirs()
        self.name = config.ASSISTANT_NAME
        self.memory = memory or Memory()
        self.context = Context()
        self._voice_output = False
        self._running = False

        self.permissions = PermissionManager(
            confirm_high_risk=config.CONFIRM_HIGH_RISK,
            confirm_medium_risk=config.CONFIRM_MEDIUM_RISK,
        )
        self.tts = tts if tts is not None else TextToSpeech(
            enabled=config.TTS_ENABLED, rate=config.TTS_RATE,
            volume=config.TTS_VOLUME, voice_id=config.TTS_VOICE_ID,
        )
        self.stt = stt_engine if stt_engine is not None else SpeechToText(
            language=config.STT_LANGUAGE, energy_threshold=config.STT_ENERGY_THRESHOLD,
            pause_threshold=config.STT_PAUSE_THRESHOLD, listen_timeout=config.STT_LISTEN_TIMEOUT,
            phrase_time_limit=config.STT_PHRASE_TIME_LIMIT, enabled=config.STT_ENABLED,
            device_index=config.STT_DEVICE_INDEX,
        )
        self.wake_word = WakeWordDetector(self.stt, config.WAKE_WORD)

        self.browser_tool = BrowserTool()
        self.router = Router(
            [
                SystemTool(),
                AppsTool(),
                self.browser_tool,
                SearchTool(self.browser_tool),
                FilesTool(),
                TasksTool(self.memory),
                WeatherTool(),
                MapsTool(),
                WikipediaTool(),
                DictionaryTool(),
                FinanceTool(),
                NewsTool(),
                JokesTool(),
                CalculatorTool(),
                ExamPrepTool(),
                ImageTool(),
                GameTool(),
            ],
            self.permissions,
        )
        self.engine = engine or create_engine(memory=self.memory, tool_schemas=self.router.schemas())
        logger.info("Assistant ready (engine=%s)", engine_name(self.engine))

    # ------------------------------------------------------------------ #
    # Core pipeline
    # ------------------------------------------------------------------ #
    def handle(self, text: str, speak: bool = True) -> str:
        """Process one utterance and return the spoken response."""
        text = (text or "").strip()
        if not text:
            return ""

        self.context.add_user(text)
        self.memory.log("user", text)

        response = self.engine.respond(text, self.context)
        spoken = self._resolve(response)

        self.context.add_assistant(spoken)
        self.memory.log("assistant", spoken)
        if speak:
            self._say(spoken)
        return spoken

    def _resolve(self, response) -> str:
        if response.has_action:
            outcome = self.router.dispatch(response.action)
            self.context.add_tool(outcome.tool, outcome.spoken)
            self._note_context(response.action)
            return outcome.spoken
        return response.speech or ""

    def _note_context(self, action: ActionRequest) -> None:
        params = action.params
        if action.tool == "apps" and params.get("action") == "open":
            self.context.note_app(params.get("name"))
        elif action.tool == "browser":
            self.context.note_url(params.get("url"))
        elif action.tool == "search":
            self.context.note_query(params.get("query"))

    def _say(self, text: str) -> None:
        if not text:
            return
        print(f"{self.name}: {text}")
        if self._voice_output and config.VOICE_ENABLED and self.tts.available:
            self.tts.speak(text)

    @staticmethod
    def _is_exit(text: str) -> bool:
        low = text.strip().lower().rstrip(" .!?")
        return low in _EXIT_COMMANDS

    # ------------------------------------------------------------------ #
    # Confirmation callbacks
    # ------------------------------------------------------------------ #
    def _cli_confirm(self, prompt: str) -> bool:
        try:
            answer = input(f"{prompt} [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return answer in ("y", "yes")

    def _voice_confirm(self, prompt: str) -> bool:
        self.tts.speak(prompt)
        result = self.stt.listen(timeout=6)
        return result.status == stt.OK and result.text.lower().strip(" .!?") in _AFFIRMATIVE

    # ------------------------------------------------------------------ #
    # Front-ends
    # ------------------------------------------------------------------ #
    def start(self, mode: str = "auto") -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"Unknown mode: {mode!r}. Expected one of {VALID_MODES}.")
        if mode == "auto":
            mode = "gui" if self._gui_available() else "cli"
        {"cli": self.run_cli, "gui": self.run_gui, "voice": self.run_voice}[mode]()

    def run_cli(self) -> None:
        self._running = True
        self._voice_output = False
        self.permissions.set_confirmer(self._cli_confirm)
        print(f"{self.name} ready. Type a command, 'voice' to speak, or 'exit' to quit.")
        while self._running:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            line = line.strip()
            if not line:
                continue
            if line.lower() in ("voice", "speak", "mic", "listen"):
                if not self.stt.available:
                    print("Microphone backend unavailable (check PyAudio).")
                    continue
                spoken_input = self.stt.take_input("Listening... (speak into your microphone)")
                if not spoken_input:
                    continue
                line = spoken_input
            if self._is_exit(line):
                print(f"{self.name}: Goodbye.")
                break
            self.handle(line)
        self._running = False

    def run_voice(self) -> None:
        if not self.stt.available:
            print("No microphone backend is available (install PyAudio). Switching to text mode.")
            return self.run_cli()

        self._running = True
        self._voice_output = True
        self.permissions.set_confirmer(self._voice_confirm)
        self._say(f"{self.name} online. Say '{config.WAKE_WORD}' when you need me.")
        try:
            while self._running:
                woken, remainder = self.wake_word.detect()
                if woken:
                    self._conversation(remainder)
        except KeyboardInterrupt:
            print()
        finally:
            self._running = False

    def _conversation(self, initial: str) -> None:
        """Continuous mode: handle follow-ups without repeating the wake word."""
        utterance = initial
        while self._running:
            if utterance:
                if self._is_exit(utterance):
                    self._say("Goodbye.")
                    self._running = False
                    return
                self.handle(utterance)
                utterance = ""

            result = self.stt.listen(timeout=config.CONVERSATION_TIMEOUT)
            if result.status in (stt.SILENCE, stt.ERROR, stt.UNAVAILABLE):
                return
            if result.status == stt.UNCLEAR:
                self._say("I didn't quite catch that.")
                continue
            utterance = result.text

    def run_gui(self) -> None:
        if not self._gui_available():
            print("The PySide6 UI isn't installed. Switching to text mode.")
            return self.run_cli()
        from ui.main_window import run_window

        self.permissions.set_confirmer(self._gui_confirm)
        run_window(self)

    def _gui_confirm(self, prompt: str) -> bool:
        # The window supplies its own modal callback; fall back to the console.
        return self._cli_confirm(prompt)

    @staticmethod
    def _gui_available() -> bool:
        try:
            import PySide6  # noqa: F401
        except ImportError:
            return False
        return True
