"""Jokes and Trivia tool.

Provides humor, programming jokes, and intriguing trivia facts via free public
APIs (Official Joke API and UselessFacts) without needing an API key.
"""

from __future__ import annotations

import logging
from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class JokesTool(Tool):
    name = "jokes"
    description = "Tell a funny joke, programming joke, or share an interesting random trivia fact."
    risk = Risk.LOW
    params = (
        ParamSpec("kind", "Type of content: 'joke', 'programming', or 'fact'", required=False),
    )

    def run(self, kind: str = "joke", **kwargs) -> ToolResult:
        if requests is None:
            return ToolResult.failure("The requests library is required.")

        kind = (kind or "joke").strip().lower()

        # Trivia / random fact
        if "fact" in kind or "trivia" in kind:
            try:
                resp = requests.get(
                    "https://uselessfacts.jsph.pl/api/v2/facts/random?language=en",
                    timeout=5,
                    headers={"User-Agent": "VARSHA/1.0"},
                )
                if resp.status_code == 200:
                    fact = resp.json().get("text", "").replace("’", "'").replace("“", '"').replace("”", '"')
                    if fact:
                        return ToolResult.success(f"Did you know? {fact}", kind="fact", fact=fact)
            except Exception as e:
                logger.warning("Fact API error: %s", e)

        # Joke (general or programming)
        joke_url = "https://official-joke-api.appspot.com/jokes/programming/random" if "program" in kind or "code" in kind else "https://official-joke-api.appspot.com/random_joke"
        try:
            resp = requests.get(joke_url, timeout=5, headers={"User-Agent": "VARSHA/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    data = data[0]
                setup = data.get("setup", "").replace("’", "'").replace("“", '"').replace("”", '"')
                punchline = data.get("punchline", "").replace("’", "'").replace("“", '"').replace("”", '"')
                if setup and punchline:
                    return ToolResult.success(f"{setup} ... {punchline}", kind="joke", setup=setup, punchline=punchline)
        except Exception as e:
            logger.warning("Joke API error: %s", e)

        # Fallback offline joke
        return ToolResult.success(
            "Why do programmers prefer dark mode? Because light attracts bugs!",
            kind="joke",
        )
