"""Tests for the built-in engine's intent parser."""

from __future__ import annotations

import unittest

from ai.intents import IntentParser
from core.context import Context


class FakeMemory:
    def __init__(self):
        self.facts: dict[str, str] = {}

    def remember(self, key, value):
        self.facts[key.lower()] = value

    def recall(self, key):
        return self.facts.get(key.lower())

    def all_facts(self):
        return dict(self.facts)

    def forget(self, key):
        return self.facts.pop(key.lower(), None) is not None


class IntentParserTests(unittest.TestCase):
    def setUp(self):
        self.memory = FakeMemory()
        self.parser = IntentParser(memory=self.memory)
        self.context = Context()

    def parse(self, text):
        return self.parser.parse(text, self.context)

    def test_open_app(self):
        response = self.parse("open chrome")
        self.assertEqual(response.action.tool, "apps")
        self.assertEqual(response.action.params["action"], "open")
        self.assertEqual(response.action.params["name"], "chrome")

    def test_open_strips_article(self):
        response = self.parse("open the notepad")
        self.assertEqual(response.action.params["name"], "notepad")

    def test_open_url_is_browser(self):
        response = self.parse("open google.com")
        self.assertEqual(response.action.tool, "browser")
        self.assertEqual(response.action.params["url"], "google.com")

    def test_open_known_website(self):
        response = self.parse("open youtube")
        self.assertEqual(response.action.tool, "browser")
        self.assertIn("youtube.com", response.action.params["url"])

    def test_close_app(self):
        response = self.parse("close notepad")
        self.assertEqual(response.action.tool, "apps")
        self.assertEqual(response.action.params["action"], "close")

    def test_search(self):
        response = self.parse("search for rust ownership")
        self.assertEqual(response.action.tool, "search")
        self.assertEqual(response.action.params["query"], "rust ownership")

    def test_cpu_metric(self):
        response = self.parse("what is my cpu usage?")
        self.assertEqual(response.action.tool, "system")
        self.assertEqual(response.action.params["metric"], "cpu")

    def test_system_status_metric(self):
        response = self.parse("system status")
        self.assertEqual(response.action.params["metric"], "all")

    def test_add_task(self):
        response = self.parse("remind me to buy milk")
        self.assertEqual(response.action.tool, "tasks")
        self.assertEqual(response.action.params["action"], "add")
        self.assertEqual(response.action.params["title"], "buy milk")

    def test_list_tasks(self):
        response = self.parse("what are my tasks")
        self.assertEqual(response.action.params["action"], "list")

    def test_remember_then_recall(self):
        self.parse("remember my editor is VS Code")
        self.assertEqual(self.memory.recall("editor"), "VS Code")
        response = self.parse("what is my editor")
        self.assertIn("VS Code", response.speech)

    def test_unknown_returns_none(self):
        self.assertIsNone(self.parse("flibbertigibbet quux"))

    def test_greeting(self):
        response = self.parse("hello")
        self.assertIsNotNone(response.speech)
        self.assertIsNone(response.action)

    def test_time(self):
        response = self.parse("what time is it")
        self.assertIn("It's", response.speech)


if __name__ == "__main__":
    unittest.main()
