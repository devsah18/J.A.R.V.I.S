"""End-to-end checks for desktop app + web application launching.

These tests verify the built-in engine routes natural-language commands to the
right tool without actually launching anything on the host machine.
"""
import unittest
import webbrowser
from unittest.mock import patch

from ai.intents import IntentParser
from core.router import ActionRequest
from core.context import Context


class _StubMemory:
    def get(self, key, default=None):
        return default


def _parse(text):
    parser = IntentParser(memory=_StubMemory())
    ctx = Context()
    return parser.parse(text, ctx)


class TestAppOpening(unittest.TestCase):
    def test_open_app_by_name(self):
        resp = _parse("open chrome")
        self.assertIsNotNone(resp)
        self.assertEqual(resp.action.tool, "apps")
        self.assertEqual(resp.action.params["action"], "open")
        self.assertEqual(resp.action.params["name"], "chrome")

    def test_launch_vs_code(self):
        resp = _parse("launch vs code")
        self.assertEqual(resp.action.tool, "apps")
        self.assertEqual(resp.action.params["name"], "vs code")

    def test_open_calculator(self):
        resp = _parse("open calculator")
        self.assertEqual(resp.action.tool, "apps")
        self.assertEqual(resp.action.params["name"], "calculator")

    def test_open_notepad(self):
        resp = _parse("open notepad")
        self.assertEqual(resp.action.tool, "apps")
        self.assertEqual(resp.action.params["name"], "notepad")

    def test_open_explorer(self):
        resp = _parse("open file explorer")
        self.assertEqual(resp.action.tool, "apps")
        self.assertEqual(resp.action.params["name"], "file explorer")

    def test_open_spotify(self):
        resp = _parse("open spotify")
        self.assertEqual(resp.action.tool, "apps")
        self.assertEqual(resp.action.params["name"], "spotify")

    def test_close_app(self):
        resp = _parse("close chrome")
        self.assertEqual(resp.action.tool, "apps")
        self.assertEqual(resp.action.params["action"], "close")
        self.assertEqual(resp.action.params["name"], "chrome")

    def test_kill_app(self):
        resp = _parse("kill notepad")
        self.assertEqual(resp.action.tool, "apps")
        self.assertEqual(resp.action.params["action"], "close")

    def test_app_suffix_form(self):
        resp = _parse("youtube kholo")
        self.assertEqual(resp.action.tool, "browser")
        self.assertEqual(resp.action.params["url"], "https://www.youtube.com")


class TestWebOpening(unittest.TestCase):
    def test_open_website_by_name(self):
        resp = _parse("open youtube")
        self.assertEqual(resp.action.tool, "browser")
        self.assertEqual(resp.action.params["url"], "https://www.youtube.com")

    def test_open_github(self):
        resp = _parse("open github")
        self.assertEqual(resp.action.tool, "browser")
        self.assertEqual(resp.action.params["url"], "https://github.com")

    def test_open_full_url(self):
        resp = _parse("open https://example.com")
        self.assertEqual(resp.action.tool, "browser")
        self.assertEqual(resp.action.params["url"], "https://example.com")

    def test_open_www_domain(self):
        resp = _parse("open www.google.com")
        self.assertEqual(resp.action.tool, "browser")
        # The intent parser keeps the raw domain; the browser tool normalizes it.
        self.assertEqual(resp.action.params["url"], "www.google.com")

    def test_open_mailto(self):
        resp = _parse("open mailto:test@example.com")
        self.assertEqual(resp.action.tool, "browser")
        self.assertEqual(resp.action.params["url"], "mailto:test@example.com")

    def test_open_maps(self):
        resp = _parse("open google maps")
        self.assertEqual(resp.action.tool, "maps")

    def test_open_news(self):
        resp = _parse("open news")
        self.assertEqual(resp.action.tool, "news")


class TestAppsToolResolution(unittest.TestCase):
    def test_known_alias_resolves(self):
        from tools.apps import AppsTool, APP_ALIASES
        tool = AppsTool()
        cmd, proc = tool._resolve("chrome")
        self.assertEqual(cmd, "chrome")
        self.assertEqual(proc, "chrome.exe")

    def test_unknown_app_falls_back(self):
        from tools.apps import AppsTool
        tool = AppsTool()
        cmd, proc = tool._resolve("my custom app")
        self.assertEqual(cmd, "my custom app")
        self.assertEqual(proc, "my custom app.exe")

    def test_open_failure_when_missing(self):
        from tools.apps import AppsTool
        with patch.object(AppsTool, "_spawn", return_value=False):
            result = AppsTool().run(action="open", name="definitely_not_real_app")
        self.assertFalse(result.ok)

    def test_open_success_when_spawned(self):
        from tools.apps import AppsTool
        with patch.object(AppsTool, "_spawn", return_value=True), \
             patch.object(AppsTool, "_wait_for_process", return_value=True):
            result = AppsTool().run(action="open", name="notepad")
        self.assertTrue(result.ok)
        self.assertIn("Notepad", result.message)

    def test_close_no_match(self):
        from tools.apps import AppsTool
        with patch.object(AppsTool, "_find_processes", return_value=[]):
            result = AppsTool().run(action="close", name="ghost_app")
        self.assertFalse(result.ok)


class TestBrowserTool(unittest.TestCase):
    def test_normalizes_bare_domain(self):
        from tools.browser import BrowserTool
        self.assertEqual(BrowserTool()._normalize("example.com"), "https://example.com")

    def test_keeps_https(self):
        from tools.browser import BrowserTool
        self.assertEqual(BrowserTool()._normalize("https://x.com"), "https://x.com")

    def test_keeps_mailto(self):
        from tools.browser import BrowserTool
        self.assertEqual(BrowserTool()._normalize("mailto:a@b.com"), "mailto:a@b.com")

    def test_open_failure_when_no_url(self):
        from tools.browser import BrowserTool
        result = BrowserTool().run(url="")
        self.assertFalse(result.ok)

    def test_open_failure_on_browser_error(self):
        from tools.browser import BrowserTool
        with patch("tools.browser.webbrowser.open", side_effect=webbrowser.Error("nope")):
            result = BrowserTool().run(url="https://example.com")
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()