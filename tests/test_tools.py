"""Tests for the individual tools (no network or OS side effects where avoidable)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.apps import AppsTool
from tools.base import Risk
from tools.browser import BrowserTool
from tools.files import FilesTool
from tools.search import SearchTool
from tools.system import SystemTool


class SystemToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = SystemTool()

    def test_cpu(self):
        result = self.tool.run(metric="cpu")
        self.assertTrue(result.ok)
        self.assertIn("percent", result.message)
        self.assertIn("percent", result.data)

    def test_all_does_not_raise(self):
        result = self.tool.run(metric="all")
        self.assertIn(result.ok, (True, False))  # battery may be absent on desktops

    def test_unknown_metric(self):
        result = self.tool.run(metric="gpu")
        self.assertFalse(result.ok)


class BrowserToolTests(unittest.TestCase):
    def test_normalize_adds_scheme(self):
        self.assertEqual(BrowserTool._normalize("example.com"), "https://example.com")

    def test_normalize_keeps_scheme(self):
        self.assertEqual(BrowserTool._normalize("http://example.com"), "http://example.com")

    def test_empty_is_rejected(self):
        self.assertEqual(BrowserTool._normalize("   "), "")

    def test_display(self):
        self.assertEqual(BrowserTool._display("https://example.com/page"), "example.com")


class AppsToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = AppsTool()

    def test_alias_resolution(self):
        command, process = self.tool._resolve("Chrome")
        self.assertEqual(command, "chrome")
        self.assertEqual(process, "chrome.exe")

    def test_close_is_high_risk(self):
        self.assertEqual(self.tool.risk_for(action="close"), Risk.HIGH)

    def test_open_is_medium_risk(self):
        self.assertEqual(self.tool.risk_for(action="open"), Risk.MEDIUM)

    def test_missing_name(self):
        self.assertFalse(self.tool.run(action="open", name="").ok)


class FilesToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.tool = FilesTool()

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_then_read(self):
        target = self.root / "note.txt"
        self.assertTrue(self.tool.run(action="write", path=str(target), content="hello world").ok)
        result = self.tool.run(action="read", path=str(target))
        self.assertTrue(result.ok)
        self.assertIn("hello world", result.data["content"])

    def test_append(self):
        target = self.root / "log.txt"
        self.tool.run(action="write", path=str(target), content="a")
        self.tool.run(action="append", path=str(target), content="b")
        self.assertEqual(target.read_text(encoding="utf-8"), "ab")

    def test_list_directory(self):
        (self.root / "one.txt").write_text("x", encoding="utf-8")
        result = self.tool.run(action="list", path=str(self.root))
        self.assertTrue(result.ok)
        self.assertIn("one.txt", result.data["entries"])

    def test_search_pattern(self):
        (self.root / "report_final.md").write_text("x", encoding="utf-8")
        result = self.tool.run(action="search", path=str(self.root), pattern="*report*")
        self.assertTrue(result.ok)
        self.assertEqual(len(result.data["matches"]), 1)

    def test_delete_file(self):
        target = self.root / "temp.txt"
        target.write_text("bye", encoding="utf-8")
        result = self.tool.run(action="delete", path=str(target))
        self.assertTrue(result.ok)
        self.assertFalse(target.exists())

    def test_delete_is_high_risk(self):
        self.assertEqual(self.tool.risk_for(action="delete"), Risk.HIGH)

    def test_read_missing_file(self):
        result = self.tool.run(action="read", path=str(self.root / "nope.txt"))
        self.assertFalse(result.ok)


class SearchToolParseTests(unittest.TestCase):
    def test_parse_results(self):
        markup = (
            '<a class="result-link" href="https://a.com">First result</a>'
            '<td class="result-snippet">Snippet one</td>'
            '<a class="result-link" href="https://b.com">Second result</a>'
            '<td class="result-snippet">Snippet two</td>'
        )
        results = SearchTool()._parse(markup)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "First result")
        self.assertEqual(results[0].url, "https://a.com")
        self.assertEqual(results[1].snippet, "Snippet two")


if __name__ == "__main__":
    unittest.main()
