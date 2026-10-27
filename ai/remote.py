"""Remote AI backends: OpenAI-compatible APIs and a local Ollama server.

Both share one portable contract: the model is told the available tools and may
either answer normally or respond with a single JSON object
``{"tool": "...", "params": {...}}`` to request an action. This keeps a single
decoding path for every backend.

Neither backend is required. If its dependency or credentials are missing the
model manager falls back to the built-in local engine.
"""

from __future__ import annotations

import json
import logging
import re

from ai.engine import AIEngine
from ai.prompts import system_prompt
from ai.response import EngineResponse
from core.router import ActionRequest

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_ACTION_INSTRUCTION = """
You may act on the computer using these tools:
{tools}

To act, reply with ONLY a JSON object: {{"tool": "<name>", "params": {{...}}}}.
Otherwise, reply with the plain spoken answer, one or two sentences."""


class _RemoteEngine(AIEngine):
    """Shared prompt construction and response decoding."""

    def __init__(self, memory=None, tool_schemas: list[dict] | None = None):
        self._memory = memory
        self._tool_schemas = tool_schemas or []

    def set_tool_schemas(self, schemas: list[dict]) -> None:
        self._tool_schemas = schemas

    # ------------------------------------------------------------------ #
    def _messages(self, text: str, context) -> list[dict]:
        system = system_prompt() + "\n" + _ACTION_INSTRUCTION.format(tools=self._catalogue())
        messages = [{"role": "system", "content": system}]
        for turn in context.recent(8):
            role = "assistant" if turn.role == "assistant" else "user"
            messages.append({"role": role, "content": turn.content})
        messages.append({"role": "user", "content": text})
        return messages

    def _catalogue(self) -> str:
        lines = []
        for schema in self._tool_schemas:
            params = ", ".join(p["name"] for p in schema.get("parameters", []))
            lines.append(f"- {schema['name']}({params}): {schema['description']}")
        return "\n".join(lines) if lines else "(none)"

    @staticmethod
    def _decode(content: str) -> EngineResponse:
        content = (content or "").strip()
        match = _JSON_RE.search(content)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("tool"):
                return EngineResponse(action=ActionRequest(payload["tool"], payload.get("params") or {}))
        return EngineResponse(speech=content or "I don't have a response for that.")


class OpenAIEngine(_RemoteEngine):
    name = "openai"

    def __init__(self, memory=None, tool_schemas=None):
        super().__init__(memory, tool_schemas)
        import config

        self._model = config.AI_MODEL or "gpt-4o-mini"
        self._client = None

    @staticmethod
    def available() -> bool:
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        import config

        return bool(config.OPENAI_API_KEY)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            import config

            self._client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
        return self._client

    def respond(self, text: str, context) -> EngineResponse:
        import config

        try:
            completion = self._get_client().chat.completions.create(
                model=self._model,
                messages=self._messages(text, context),
                temperature=config.AI_TEMPERATURE,
            )
        except Exception as error:  # noqa: BLE001 - surface any API failure plainly
            logger.warning("OpenAI request failed: %s", error)
            return EngineResponse(speech="I couldn't reach the language model just now.")
        return self._decode(completion.choices[0].message.content)


class OllamaEngine(_RemoteEngine):
    name = "ollama"

    def __init__(self, memory=None, tool_schemas=None):
        super().__init__(memory, tool_schemas)
        import config

        self._model = config.AI_MODEL or "llama3.1"
        self._host = config.OLLAMA_HOST.rstrip("/")

    @staticmethod
    def available() -> bool:
        try:
            import requests  # noqa: F401
        except ImportError:
            return False
        return True

    def respond(self, text: str, context) -> EngineResponse:
        import requests

        try:
            response = requests.post(
                f"{self._host}/api/chat",
                json={"model": self._model, "messages": self._messages(text, context), "stream": False},
                timeout=60,
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
        except Exception as error:  # noqa: BLE001 - surface any connection failure plainly
            logger.warning("Ollama request failed: %s", error)
            return EngineResponse(speech="I couldn't reach the local model. Is Ollama running?")
        return self._decode(content)
