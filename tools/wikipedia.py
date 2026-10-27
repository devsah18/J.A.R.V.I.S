"""Wikipedia / Knowledge summary tool.

Queries the official Wikipedia REST API (no API key required) to fetch
summaries and concise explanations for any concept, person, place, or historical event.
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


class WikipediaTool(Tool):
    name = "wikipedia"
    description = "Search Wikipedia and return a concise summary about any person, place, thing, or concept."
    risk = Risk.LOW
    params = (
        ParamSpec("query", "The topic or entity to look up on Wikipedia"),
    )

    def run(self, query: str = "", **kwargs) -> ToolResult:
        query = (query or "").strip()
        if not query:
            return ToolResult.failure("Please specify what topic you want to look up on Wikipedia.")

        if requests is None:
            return ToolResult.failure("The requests library is required for Wikipedia lookups.")

        headers = {"User-Agent": "VARSHA-Assistant/1.0 (https://github.com; contact@example.com)"}

        try:
            # 1. Try with title casing first, then as-is
            for cand in (query.title(), query):
                encoded_title = urllib.parse.quote(cand.replace(" ", "_"))
                url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
                resp = requests.get(url, timeout=6, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    extract = data.get("extract", "")
                    title = data.get("title", query)
                    page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

                    if extract:
                        return ToolResult.success(
                            f"According to Wikipedia: {extract}",
                            title=title,
                            url=page_url,
                            extract=extract,
                        )

            # 2. Fall back to OpenSearch search endpoint
            search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(query)}&limit=1&format=json"
            search_resp = requests.get(search_url, timeout=6, headers=headers)
            if search_resp.status_code == 200:
                search_data = search_resp.json()
                if len(search_data) >= 4 and search_data[1]:
                    matched_title = search_data[1][0]
                    matched_desc = search_data[2][0] if search_data[2] else ""
                    matched_url = search_data[3][0] if search_data[3] else ""

                    sec_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(matched_title.replace(' ', '_'))}"
                    sec_resp = requests.get(sec_url, timeout=6, headers=headers)
                    if sec_resp.status_code == 200:
                        sec_extract = sec_resp.json().get("extract", "")
                        if sec_extract:
                            return ToolResult.success(
                                f"According to Wikipedia for {matched_title}: {sec_extract}",
                                title=matched_title,
                                url=matched_url,
                                extract=sec_extract,
                            )

                    if matched_desc:
                        return ToolResult.success(
                            f"According to Wikipedia for {matched_title}: {matched_desc}",
                            title=matched_title,
                            url=matched_url,
                        )

            return ToolResult.failure(f"I couldn't find an encyclopedic entry on Wikipedia for '{query}'.")

        except Exception as e:
            logger.warning("Wikipedia error: %s", e)
            return ToolResult.failure(f"Could not reach Wikipedia: {e}")

