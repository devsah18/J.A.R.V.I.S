"""The AI brain.

Two layers live here:

* :class:`AIEngine` - the interface every backend implements.
* :class:`LocalEngine` - the built-in, dependency-free engine that keeps VARSHA
  fully functional offline by parsing intents with :class:`~ai.intents.IntentParser`.

Remote backends (OpenAI, Ollama) live in :mod:`ai.remote` and are selected by
:mod:`ai.model_manager` when explicitly configured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai.intents import IntentParser
from ai.response import EngineResponse

FALLBACK_REPLY = (
    "I'm not sure what you'd like me to do with that. I can open and close applications, "
    "search the web, check your system, and manage files and tasks."
)


class AIEngine(ABC):
    """Interface for an AI backend."""

    name: str = "base"

    @abstractmethod
    def respond(self, text: str, context) -> EngineResponse:
        """Produce a reply or an action for one user turn."""


class LocalEngine(AIEngine):
    """Offline engine driven by rule-based intent parsing."""

    name = "local"

    def __init__(self, memory=None):
        self._parser = IntentParser(memory=memory)

    def respond(self, text: str, context) -> EngineResponse:
        parsed = self._parser.parse(text, context)
        if parsed is not None:
            return parsed
        return EngineResponse(speech=FALLBACK_REPLY)
