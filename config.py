"""VARSHA project configuration and settings.

All tunables live here. Values are read from the environment (optionally from a
project ``.env`` file) so the assistant can be reconfigured without code edits.
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is optional at runtime.
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover - only hit without the optional dep.
    pass


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
MEMORY_DB_PATH = DATA_DIR / "varsha_memory.db"


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "VARSHA")
VERSION = "1.0.0"
DEBUG = os.getenv("DEBUG", "true").strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# --------------------------------------------------------------------------- #
# Voice
# --------------------------------------------------------------------------- #
VOICE_ENABLED = _env_bool("VOICE_ENABLED", True)
TTS_ENABLED = _env_bool("TTS_ENABLED", True)
STT_ENABLED = _env_bool("STT_ENABLED", True)
TTS_RATE = _env_int("TTS_RATE", 180)
TTS_VOLUME = _env_float("TTS_VOLUME", 1.0)
TTS_VOICE_ID = os.getenv("TTS_VOICE_ID") or None
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "en-US")
STT_ENERGY_THRESHOLD = _env_int("STT_ENERGY_THRESHOLD", 150)
STT_PAUSE_THRESHOLD = _env_float("STT_PAUSE_THRESHOLD", 0.8)
STT_LISTEN_TIMEOUT = _env_int("STT_LISTEN_TIMEOUT", 10)
STT_PHRASE_TIME_LIMIT = _env_int("STT_PHRASE_TIME_LIMIT", 15)
STT_DEVICE_INDEX = _env_int("STT_DEVICE_INDEX", -1)
WAKE_WORD = os.getenv("WAKE_WORD", ASSISTANT_NAME.lower())
CONVERSATION_TIMEOUT = _env_int("CONVERSATION_TIMEOUT", 30)


# --------------------------------------------------------------------------- #
# AI backend
# --------------------------------------------------------------------------- #
# One of: "local" (built-in engine), "openai", "ollama".
AI_BACKEND = os.getenv("AI_BACKEND", "local").strip().lower()
AI_MODEL = os.getenv("AI_MODEL", "")
AI_TEMPERATURE = _env_float("AI_TEMPERATURE", 0.3)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


# --------------------------------------------------------------------------- #
# Permissions
# --------------------------------------------------------------------------- #
CONFIRM_HIGH_RISK = _env_bool("CONFIRM_HIGH_RISK", True)
CONFIRM_MEDIUM_RISK = _env_bool("CONFIRM_MEDIUM_RISK", False)


# --------------------------------------------------------------------------- #
# .env persistence
# --------------------------------------------------------------------------- #
_ENV_PATH = BASE_DIR / ".env"


def ensure_dirs() -> None:
    """Create the runtime directories the assistant writes to."""
    for directory in (DATA_DIR, LOGS_DIR, SCREENSHOTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def set_assistant_name(new_name: str) -> str:
    """Rename the assistant and persist the change to ``.env``."""
    global ASSISTANT_NAME
    clean_name = (new_name or "").strip()
    if not clean_name:
        raise ValueError("Assistant name cannot be empty.")
    ASSISTANT_NAME = clean_name
    _persist_env_var("ASSISTANT_NAME", clean_name)
    return ASSISTANT_NAME


def _persist_env_var(key: str, value: str) -> None:
    """Write or update ``key=value`` in the project ``.env`` file."""
    lines: list[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()

    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            break
    else:
        lines.append(f"{prefix}{value}")

    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
