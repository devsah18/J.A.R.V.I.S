"""News headlines tool.

Fetches the latest top news headlines from trusted world and tech news feeds
(BBC World News and Hacker News) without requiring an API key.
"""

from __future__ import annotations

import html
import logging
import xml.etree.ElementTree as ET
from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class NewsTool(Tool):
    name = "news"
    description = "Get the latest top news headlines and breaking stories across world, tech, and business news."
    risk = Risk.LOW
    params = (
        ParamSpec("category", "News category: 'world', 'tech', or 'top'", required=False),
        ParamSpec("count", "Number of headlines to return (default 3)", required=False),
    )

    def run(self, category: str = "world", count: int = 3, **kwargs) -> ToolResult:
        if requests is None:
            return ToolResult.failure("The requests library is required for news fetching.")

        category = (category or "world").strip().lower()
        limit = max(1, min(int(count or 3), 5))

        # Tech news via Hacker News
        if category in ("tech", "technology", "coding", "software"):
            try:
                top_ids_resp = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=6)
                top_ids = top_ids_resp.json()[:limit]

                stories = []
                for item_id in top_ids:
                    item_resp = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json", timeout=5)
                    title = item_resp.json().get("title", "")
                    if title:
                        stories.append(title)

                if stories:
                    spoken = "Top tech headlines: " + "; ".join(f"{i+1}. {s}" for i, s in enumerate(stories))
                    return ToolResult.success(spoken, category="tech", headlines=stories)
            except Exception as e:
                logger.warning("Tech news error: %s", e)

        # General / World news via BBC World RSS
        try:
            resp = requests.get(
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                timeout=6,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VARSHA/1.0"},
            )
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")[:limit]

            headlines = []
            for item in items:
                title_elem = item.find("title")
                if title_elem is not None and title_elem.text:
                    clean_title = html.unescape(title_elem.text.strip())
                    headlines.append(clean_title)

            if headlines:
                spoken = "Top news stories right now: " + "; ".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
                return ToolResult.success(spoken, category="world", headlines=headlines)

        except Exception as e:
            logger.warning("BBC news error: %s", e)

        return ToolResult.failure("Could not fetch the latest news at this moment.")

