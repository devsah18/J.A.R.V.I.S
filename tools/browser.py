"""Web browser tool: open URLs in the default browser."""

from __future__ import annotations

import webbrowser

from tools.base import ParamSpec, Risk, Tool, ToolResult


class BrowserTool(Tool):
    name = "browser"
    description = "Open a website or URL in the default web browser."
    risk = Risk.LOW
    params = (ParamSpec("url", "The URL or website to open"),)

    def run(self, url: str = "", **kwargs) -> ToolResult:
        target = self._normalize(url)
        if not target:
            return ToolResult.failure("I need a website or URL to open.")

        try:
            opened = webbrowser.open(target)
        except webbrowser.Error as error:
            return ToolResult.failure(f"I couldn't open the browser: {error}")

        if not opened:
            return ToolResult.failure(f"I couldn't find a web browser to open {target}.")
        return ToolResult.success(f"Opening {self._display(target)}.", url=target)

    @staticmethod
    def _normalize(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        if "://" in url or url.startswith("mailto:"):
            return url
        return f"https://{url}"

    @staticmethod
    def _display(url: str) -> str:
        return url.split("://", 1)[-1].split("/", 1)[0]
