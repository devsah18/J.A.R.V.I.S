"""Web search tool.

Queries DuckDuckGo's lightweight HTML endpoint and summarises the top results.
If the network is unavailable it falls back to opening a search in the browser.
"""

from __future__ import annotations

import html
import re
import webbrowser
from dataclasses import dataclass

from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import requests
except ImportError:  # pragma: no cover - requests is a declared dependency
    requests = None


DUCKDUCKGO_LITE = "https://lite.duckduckgo.com/lite/"
DUCKDUCKGO_SEARCH = "https://duckduckgo.com/?q="
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VARSHA/1.0"
REQUEST_TIMEOUT = 10

_RESULT_LINK_RE = re.compile(
    r'<a[^>]*class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class SearchTool(Tool):
    name = "search"
    description = "Search the web and summarise the top results."
    risk = Risk.LOW
    params = (
        ParamSpec("query", "What to search for"),
        ParamSpec("count", "How many results to return (default 3)", required=False),
    )

    def __init__(self, browser_tool=None):
        self._browser = browser_tool

    def run(self, query: str = "", count: int = 3, **kwargs) -> ToolResult:
        query = (query or "").strip()
        if not query:
            return ToolResult.failure("What should I search for?")

        if requests is None:
            return self._fallback(query, "search libraries aren't installed")

        try:
            results = self._fetch(query)
        except Exception as error:  # noqa: BLE001 - network errors vary by platform
            return self._fallback(query, str(error))

        if not results:
            return self._fallback(query, "no results came back")

        limit = max(1, self._as_int(count, 3))
        top = results[:limit]
        return ToolResult.success(
            self._summarise(query, top),
            query=query,
            results=[r.__dict__ for r in top],
        )

    # ------------------------------------------------------------------ #
    # Fetching / parsing
    # ------------------------------------------------------------------ #
    def _fetch(self, query: str) -> list[SearchResult]:
        response = requests.get(
            DUCKDUCKGO_LITE,
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return self._parse(response.text)

    def _parse(self, markup: str) -> list[SearchResult]:
        links = [(url, self._clean(text)) for url, text in _RESULT_LINK_RE.findall(markup)]
        snippets = [self._clean(markup_text) for markup_text in _SNIPPET_RE.findall(markup)]

        results: list[SearchResult] = []
        for index, (url, title) in enumerate(links):
            if not title:
                continue
            snippet = snippets[index] if index < len(snippets) else ""
            results.append(SearchResult(title=title, url=url, snippet=snippet))
        return results

    # ------------------------------------------------------------------ #
    # Presentation
    # ------------------------------------------------------------------ #
    def _summarise(self, query: str, results: list[SearchResult]) -> str:
        top = results[0]
        if len(results) == 1:
            return f"Here's the top result for {query}: {top.title}."
        summary = f"I found {len(results)} results for {query}. The top one is {top.title}"
        if top.snippet:
            summary += f" - {self._shorten(top.snippet)}"
        return summary + "."

    def _fallback(self, query: str, reason: str | None) -> ToolResult:
        url = f"{DUCKDUCKGO_SEARCH}{requests.utils.quote(query) if requests else query}"
        opened = False
        if self._browser is not None:
            opened = self._browser.run(url=url).ok
        if not opened:
            try:
                opened = webbrowser.open(url)
            except webbrowser.Error:
                opened = False
        note = f" ({reason})" if reason else ""
        if opened:
            return ToolResult.success(
                f"I couldn't read live results{note}, so I've opened a web search for {query}.",
                query=query,
                url=url,
            )
        return ToolResult.failure(f"I couldn't search for {query} right now{note}.")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _clean(fragment: str) -> str:
        text = _TAG_RE.sub("", fragment)
        text = html.unescape(text)
        return _WHITESPACE_RE.sub(" ", text).strip()

    @staticmethod
    def _shorten(text: str, limit: int = 160) -> str:
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."

    @staticmethod
    def _as_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
