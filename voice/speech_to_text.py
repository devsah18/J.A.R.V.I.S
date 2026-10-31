"""Speech-to-text.

Uses the ``speech_recognition`` library and the Google Web Speech recogniser
(no API key needed). Microphone capture requires PyAudio; when it is missing the
engine reports ``unavailable`` instead of failing, so the assistant can fall back
to text input.
"""

from __future__ import annotations

import datetime
import logging
import os
import subprocess
import time
import urllib.parse
import warnings
import webbrowser
from dataclasses import dataclass

# Filter deprecation warnings from legacy dependencies in speech_recognition
with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=DeprecationWarning)
    try:
        import speech_recognition as sr  # type: ignore
    except ImportError:  # pragma: no cover - optional at runtime
        sr = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

logger = logging.getLogger(__name__)

# Listen outcomes.
OK = "ok"
UNCLEAR = "unclear"
SILENCE = "silence"
UNAVAILABLE = "unavailable"
ERROR = "error"


@dataclass
class ListenResult:
    status: str
    text: str = ""

    @property
    def heard_something(self) -> bool:
        return self.status == OK and bool(self.text)


class SpeechToText:
    def __init__(
        self,
        language: str = "en-US",
        energy_threshold: int = 150,
        pause_threshold: float = 0.8,
        listen_timeout: int = 10,
        phrase_time_limit: int = 15,
        enabled: bool = True,
        device_index: int | None = None,
    ):
        self.language = language
        self.listen_timeout = listen_timeout
        self.phrase_time_limit = phrase_time_limit
        self.device_index = self._resolve_device_index(device_index)
        self._recognizer = None
        self._mic_ok = False
        self._calibrated = False

        if enabled and sr is not None:
            self._recognizer = sr.Recognizer()
            # Use a higher base energy threshold to avoid missing speech on quieter mics.
            # The threshold can be overridden via the STT_ENERGY_THRESHOLD env var (default 150).
            self._recognizer.energy_threshold = max(300, energy_threshold)
            # Disable automatic dynamic adjustment for more predictable behavior.
            self._recognizer.dynamic_energy_threshold = False
            self._recognizer.pause_threshold = pause_threshold
            self._recognizer.non_speaking_duration = 0.5
            self._mic_ok = self._probe_microphone()
            # Perform a quick calibration to set the ambient noise floor.
            if self._mic_ok:
                try:
                    self.calibrate(duration=0.5)
                except Exception as e:
                    logger.warning("Calibration failed during init: %s", e)

    @staticmethod
    def _test_device_signal(device_index: int) -> int:
        """Read a test chunk from device and return peak amplitude."""
        if sr is None:
            return -1
        try:
            # First verify with pyaudio that device exists and has input channels
            audio = sr.Microphone.get_pyaudio().PyAudio()
            try:
                if device_index < 0 or device_index >= audio.get_device_count():
                    return -1
                info = audio.get_device_info_by_index(device_index)
                if not info or info.get("maxInputChannels", 0) <= 0:
                    return -1
            finally:
                audio.terminate()

            m = sr.Microphone(device_index=device_index)
            with m as source:
                if not hasattr(source, "stream") or source.stream is None:
                    return -1
                chunk = source.stream.read(source.CHUNK, exception_on_overflow=False)
                shorts = [
                    int.from_bytes(chunk[j : j + 2], "little", signed=True)
                    for j in range(0, len(chunk), 2)
                ]
                return max(abs(s) for s in shorts) if shorts else 0
        except Exception:
            return -1

    @classmethod
    def _resolve_device_index(cls, requested: int | None) -> int | None:
        """Resolve the most reliable microphone device index safely.

        Probes only valid input audio endpoints with maxInputChannels > 0,
        avoiding speaker/headphone output devices and invalid device crashes.
        """
        if sr is None:
            return None
        try:
            audio = sr.Microphone.get_pyaudio().PyAudio()
            input_devices: dict[int, dict] = {}
            try:
                for i in range(audio.get_device_count()):
                    try:
                        info = audio.get_device_info_by_index(i)
                        if info and info.get("maxInputChannels", 0) > 0:
                            input_devices[i] = info
                    except Exception:
                        continue
            finally:
                audio.terminate()

            if not input_devices:
                return None

            # If user explicitly requested a valid input device with signal, verify and use it
            if requested is not None and requested in input_devices:
                peak = cls._test_device_signal(requested)
                if peak > 80:
                    logger.info("Using configured microphone index %d (%s, signal=%d)", requested, input_devices[requested]["name"], peak)
                    return requested

            # Rank candidate input devices (prefer hardware microphones / arrays over virtual mappers)
            preferred = []
            others = []
            for idx, info in input_devices.items():
                name_low = info.get("name", "").lower()
                if any(k in name_low for k in ("output", "speaker", "headphone")):
                    continue
                if any(k in name_low for k in ("microphone", "array", "intel", "realtek", "input")):
                    preferred.append(idx)
                else:
                    others.append(idx)

            best_idx = None
            best_peak = 80

            for idx in preferred + others:
                peak = cls._test_device_signal(idx)
                if peak > best_peak:
                    best_peak = peak
                    best_idx = idx

            if best_idx is not None:
                logger.info("Auto-selected active microphone index %d (%s, signal=%d)", best_idx, input_devices[best_idx]["name"], best_peak)
                return best_idx

            if requested is not None and requested in input_devices:
                return requested

            # Return first available valid input device
            return next(iter(input_devices.keys()), None)
        except Exception as e:
            logger.warning("Error resolving microphone index: %s", e)
            return requested if (requested is not None and requested >= 0) else None

    def get_microphone(self):
        return sr.Microphone(device_index=self.device_index)

    def _probe_microphone(self) -> bool:
        try:
            if self.device_index is None:
                return False
            m = self.get_microphone()
            with m:
                pass
            return True
        except (OSError, AttributeError, Exception) as error:
            logger.warning("Microphone backend unavailable: %s", error)
            return False

    @staticmethod
    def list_microphones() -> list[str]:
        if sr is None:
            return []
        try:
            audio = sr.Microphone.get_pyaudio().PyAudio()
            result = []
            try:
                for i in range(audio.get_device_count()):
                    try:
                        info = audio.get_device_info_by_index(i)
                        result.append(info.get("name", f"Device {i}"))
                    except Exception:
                        result.append(f"Device {i}")
            finally:
                audio.terminate()
            return result
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    @property
    def available(self) -> bool:
        return self._recognizer is not None and self._mic_ok

    def calibrate(self, duration: float = 0.5) -> float:
        """Calibrate ambient noise floor once."""
        if not self.available:
            return 0.0
        try:
            with self.get_microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=duration)
                self._recognizer.energy_threshold = max(80, min(self._recognizer.energy_threshold, 2000))
                self._calibrated = True
                return float(self._recognizer.energy_threshold)
        except Exception as err:
            logger.warning("Calibration error: %s", err)
            return float(self._recognizer.energy_threshold)

    def listen(self, timeout: int | None = None, phrase_limit: int | None = None) -> ListenResult:
        """Capture one utterance and transcribe it via Google Speech Recognition."""
        if not self.available:
            return ListenResult(UNAVAILABLE)

        timeout = self.listen_timeout if timeout is None else timeout
        phrase_limit = self.phrase_time_limit if phrase_limit is None else phrase_limit

        try:
            with self.get_microphone() as source:
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        except sr.WaitTimeoutError:
            return ListenResult(SILENCE)
        except (OSError, AttributeError) as error:
            logger.warning("Microphone error: %s", error)
            return ListenResult(UNAVAILABLE)
        except Exception as error:
            logger.warning("Audio capture error: %s", error)
            return ListenResult(ERROR)

        try:
            text = self._recognizer.recognize_google(audio, language=self.language)
            return ListenResult(OK, text.strip())
        except sr.UnknownValueError:
            return ListenResult(UNCLEAR)
        except sr.RequestError as error:
            logger.warning("Speech recognition service error: %s", error)
            return ListenResult(ERROR)
        except Exception as error:
            logger.warning("Recognition error: %s", error)
            return ListenResult(ERROR)

    def take_input(
        self,
        prompt: str = "Listening for your voice...",
        timeout: int | None = None,
        phrase_limit: int | None = None,
    ) -> str:
        """Capture voice input with retry attempts and friendly console feedback."""
        if not self.available:
            print("Microphone not available. Please type your command.", flush=True)
            return ""

        if prompt:
            print(prompt, flush=True)

        for attempt in range(1, 4):
            print(f"\n[Listening... (attempt {attempt}/3)]", flush=True)
            result = self.listen(timeout=timeout, phrase_limit=phrase_limit)

            if result.status == OK:
                print(f"Heard: {result.text}", flush=True)
                return result.text
            elif result.status == SILENCE:
                print("[No speech detected]", flush=True)
            elif result.status == UNCLEAR:
                print("[Audio was detected, but could not understand. Try speaking more clearly.]", flush=True)
            else:
                print(f"[Speech recognition status: {result.status}]", flush=True)

            if attempt < 3:
                print("Retrying in 1 second...", flush=True)
                time.sleep(1)

        print("No speech recognized after 3 attempts.", flush=True)
        return ""


def take_input(
    prompt: str = "Listening for your voice...",
    timeout: int | None = None,
    phrase_limit: int | None = None,
    language: str = "en-US",
) -> str:
    """Convenience function: capture speech input using SpeechToText and return text."""
    engine = SpeechToText(language=language)
    return engine.take_input(prompt=prompt, timeout=timeout, phrase_limit=phrase_limit)


# --------------------------------------------------------------------------- #
# Standalone helper functions
# --------------------------------------------------------------------------- #
_tts_engine = None


def _get_tts_engine():
    global _tts_engine
    if _tts_engine is None and pyttsx3 is not None:
        try:
            _tts_engine = pyttsx3.init()
            _tts_engine.setProperty("rate", 175)
            _tts_engine.setProperty("volume", 1.0)
        except Exception:
            _tts_engine = None
    return _tts_engine


def speak(text: str) -> None:
    """Speak a response aloud."""
    assistant_name = os.getenv("ASSISTANT_NAME", "JARVIS")
    print(f"{assistant_name}: {text}")
    engine = _get_tts_engine()
    if engine is not None:
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            logger.warning("TTS error in speak(): %s", e)


def listen() -> str:
    """Listen to the microphone and recognize speech."""
    stt = SpeechToText()
    result = stt.listen(timeout=5, phrase_limit=8)
    if result.status == OK:
        text = result.text.lower().strip()
        print(f"You said: {text}")
        return text
    elif result.status == UNCLEAR:
        print("I couldn't understand that.")
        return ""
    elif result.status == UNAVAILABLE:
        print("Microphone not available.")
        return ""
    elif result.status == ERROR:
        speak("Speech recognition service is unavailable.")
        return ""
    return ""


def execute_command(command: str) -> bool:
    """Execute supported voice commands."""
    if not command:
        return True

    command = command.replace("jarvis", "", 1).strip()
    if not command:
        return True

    if any(phrase in command for phrase in ["stop listening", "shut down assistant", "exit assistant"]):
        speak("Shutting down. Goodbye.")
        return False
    elif "time" in command:
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"The current time is {current_time}.")
    elif "date" in command:
        today = datetime.datetime.now().strftime("%d %B %Y")
        speak(f"Today's date is {today}.")
    elif "open youtube" in command:
        speak("Opening YouTube.")
        webbrowser.open("https://www.youtube.com")
    elif "open google" in command:
        speak("Opening Google.")
        webbrowser.open("https://www.google.com")
    elif "open github" in command:
        speak("Opening GitHub.")
        webbrowser.open("https://github.com")
    elif "open notepad" in command:
        speak("Opening Notepad.")
        subprocess.Popen(["notepad.exe"])
    elif command.startswith("search "):
        query = command.removeprefix("search ").strip()
        if query:
            speak(f"Searching Google for {query}.")
            encoded_query = urllib.parse.quote_plus(query)
            webbrowser.open("https://www.google.com/search?q=" + encoded_query)
        else:
            speak("Please tell me what to search for.")

    return True


if __name__ == "__main__":
    speak("Voice module initialized. Say a command.")
    while True:
        cmd = listen()
        if not execute_command(cmd):
            break

