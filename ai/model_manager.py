"""Selects and constructs the AI backend for the current configuration.

The built-in :class:`~ai.engine.LocalEngine` is always available. Remote
backends are used only when explicitly configured *and* their dependency is
installed, otherwise the manager falls back to local and logs why.
"""

from __future__ import annotations

import logging

import config
from ai.engine import AIEngine, LocalEngine
from ai.remote import OllamaEngine, OpenAIEngine

logger = logging.getLogger(__name__)

REMOTE_BACKENDS: dict[str, type] = {
    "openai": OpenAIEngine,
    "ollama": OllamaEngine,
}


def create_engine(memory=None, tool_schemas: list[dict] | None = None, backend: str | None = None) -> AIEngine:
    """Build the engine for ``backend`` (or the configured default)."""
    choice = (backend or config.AI_BACKEND or "local").strip().lower()

    if choice in REMOTE_BACKENDS:
        engine_class = REMOTE_BACKENDS[choice]
        if engine_class.available():
            logger.info("Using '%s' AI backend.", choice)
            return engine_class(memory=memory, tool_schemas=tool_schemas)
        logger.warning("AI backend '%s' isn't available; using the local engine.", choice)

    return LocalEngine(memory=memory)


def engine_name(engine: AIEngine) -> str:
    return getattr(engine, "name", "unknown")


def available_backends() -> list[str]:
    names = ["local"]
    names += [name for name, cls in REMOTE_BACKENDS.items() if cls.available()]
    return names
