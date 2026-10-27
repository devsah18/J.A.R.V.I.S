"""Dictionary and word definition tool.

Looks up word meanings, parts of speech, and definitions using free linguistic
endpoints (Datamuse and FreeDictionary API) without needing an API key.
"""

from __future__ import annotations

import logging
import urllib.parse
from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

_POS_MAP = {
    "n": "noun",
    "v": "verb",
    "adj": "adjective",
    "adv": "adverb",
    "u": "word",
}


class DictionaryTool(Tool):
    name = "dictionary"
    description = "Look up dictionary definitions, parts of speech, and meanings for any English word."
    risk = Risk.LOW
    params = (
        ParamSpec("word", "The word to define"),
    )

    def run(self, word: str = "", **kwargs) -> ToolResult:
        word = (word or "").strip().lower()
        if not word:
            return ToolResult.failure("Please specify the word you want defined.")

        if requests is None:
            return ToolResult.failure("The requests library is required for dictionary lookups.")

        try:
            # 1. Try Datamuse API (definitions flag: md=d)
            url = f"https://api.datamuse.com/words?sp={urllib.parse.quote(word)}&md=d&max=1"
            resp = requests.get(url, timeout=5, headers={"User-Agent": "VARSHA/1.0"})

            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list):
                    item = data[0]
                    defs = item.get("defs", [])
                    if defs:
                        first_def = defs[0]
                        # formatted as "n\tdefinition text"
                        parts = first_def.split("\t", 1)
                        if len(parts) == 2:
                            pos_code, definition = parts
                            pos = _POS_MAP.get(pos_code, pos_code)
                            speech = f"{word.capitalize()} ({pos}): {definition}"
                        else:
                            speech = f"{word.capitalize()}: {first_def}"

                        return ToolResult.success(speech, word=word, definitions=defs)

            # 2. Fallback to Wiktionary / Wikipedia summary
            wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(word)}"
            wiki_resp = requests.get(wiki_url, timeout=5, headers={"User-Agent": "VARSHA/1.0"})
            if wiki_resp.status_code == 200:
                extract = wiki_resp.json().get("extract", "")
                if extract:
                    first_sent = extract.split(". ")[0] + "."
                    return ToolResult.success(f"{word.capitalize()}: {first_sent}", word=word, definition=first_sent)

            return ToolResult.failure(f"I couldn't find a definition for '{word}'.")

        except Exception as e:
            logger.warning("Dictionary error: %s", e)
            return ToolResult.failure(f"Could not retrieve definition for {word}: {e}")

