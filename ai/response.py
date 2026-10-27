"""The value the AI brain returns for one user turn."""

from __future__ import annotations

from dataclasses import dataclass

from core.router import ActionRequest


@dataclass
class EngineResponse:
    """Either a direct reply, a tool action, or both.

    * ``speech``  - what VARSHA should say.
    * ``action``  - a tool call to execute; when present the assistant runs it
      and prefers the tool's own result message as the spoken reply.
    * ``display`` - richer text for the UI, when the spoken form is too terse.
    """

    speech: str | None = None
    action: ActionRequest | None = None
    display: str | None = None

    @property
    def has_action(self) -> bool:
        return self.action is not None
