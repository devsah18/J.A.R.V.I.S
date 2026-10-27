"""Short-term conversation and runtime context.

Holds the rolling transcript plus the small amount of situational state the
assistant needs to resolve follow-up commands ("search for X" right after
"open Chrome") without the user repeating themselves.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

DEFAULT_MAX_TURNS = 20


@dataclass
class Turn:
    role: str  # "user" | "assistant" | "tool"
    content: str


@dataclass
class Context:
    max_turns: int = DEFAULT_MAX_TURNS
    current_project: str | None = None
    current_app: str | None = None
    last_url: str | None = None
    last_query: str | None = None
    turns: deque[Turn] = field(default_factory=lambda: deque(maxlen=DEFAULT_MAX_TURNS))

    def __post_init__(self) -> None:
        self.turns = deque(self.turns, maxlen=self.max_turns)

    # ------------------------------------------------------------------ #
    # Transcript
    # ------------------------------------------------------------------ #
    def add(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=(content or "").strip()))

    def add_user(self, content: str) -> None:
        self.add("user", content)

    def add_assistant(self, content: str) -> None:
        self.add("assistant", content)

    def add_tool(self, name: str, summary: str) -> None:
        self.add("tool", f"{name}: {summary}")

    def recent(self, limit: int = 10) -> list[Turn]:
        return list(self.turns)[-limit:]

    def transcript(self, limit: int = 10) -> str:
        """Render the recent conversation as plain text for an LLM prompt."""
        return "\n".join(f"{turn.role}: {turn.content}" for turn in self.recent(limit))

    # ------------------------------------------------------------------ #
    # Situational state
    # ------------------------------------------------------------------ #
    def note_app(self, name: str | None) -> None:
        if name:
            self.current_app = name

    def note_url(self, url: str | None) -> None:
        if url:
            self.last_url = url

    def note_query(self, query: str | None) -> None:
        if query:
            self.last_query = query

    def note_project(self, name: str | None) -> None:
        if name:
            self.current_project = name

    def reset(self) -> None:
        self.turns.clear()
        self.current_project = None
        self.current_app = None
        self.last_url = None
        self.last_query = None
