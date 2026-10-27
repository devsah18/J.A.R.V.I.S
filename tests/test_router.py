"""Tests for the router and the permission system."""

from __future__ import annotations

import unittest

from core.permissions import PermissionManager, PermissionRequest
from core.router import ActionRequest, Router
from tools.base import ParamSpec, Risk, Tool, ToolResult


class DummyTool(Tool):
    name = "dummy"
    description = "A controllable tool for tests."
    risk = Risk.LOW
    params = (ParamSpec("echo", "text to echo", required=False),)

    def __init__(self, risk=Risk.LOW, explode=False):
        self.risk = risk
        self.explode = explode

    def risk_for(self, **kwargs):
        return self.risk

    def run(self, echo: str = "", **kwargs) -> ToolResult:
        if self.explode:
            raise RuntimeError("boom")
        return ToolResult.success(f"echo: {echo}", echoed=echo)


class PermissionTests(unittest.TestCase):
    def request(self, risk):
        return PermissionRequest(tool="t", risk=risk, summary="do it", params={})

    def test_low_risk_always_allowed(self):
        manager = PermissionManager(confirm=None)
        self.assertTrue(manager.evaluate(self.request(Risk.LOW)))

    def test_high_risk_without_confirmer_denied(self):
        manager = PermissionManager(confirm=None)
        self.assertFalse(manager.evaluate(self.request(Risk.HIGH)))

    def test_high_risk_confirmed(self):
        manager = PermissionManager(confirm=lambda prompt: True)
        self.assertTrue(manager.evaluate(self.request(Risk.HIGH)))

    def test_high_risk_declined(self):
        manager = PermissionManager(confirm=lambda prompt: False)
        self.assertFalse(manager.evaluate(self.request(Risk.HIGH)))

    def test_medium_risk_not_confirmed_by_default(self):
        manager = PermissionManager(confirm=None)
        self.assertTrue(manager.evaluate(self.request(Risk.MEDIUM)))


class RouterTests(unittest.TestCase):
    def router(self, tool, **permission_kwargs):
        return Router([tool], PermissionManager(**permission_kwargs))

    def test_dispatch_success(self):
        outcome = self.router(DummyTool()).dispatch(ActionRequest("dummy", {"echo": "hi"}))
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.spoken, "echo: hi")

    def test_unknown_tool(self):
        outcome = self.router(DummyTool()).dispatch(ActionRequest("ghost"))
        self.assertFalse(outcome.ok)
        self.assertIn("ghost", outcome.spoken)

    def test_high_risk_denied(self):
        outcome = self.router(DummyTool(risk=Risk.HIGH)).dispatch(ActionRequest("dummy"))
        self.assertFalse(outcome.ok)
        self.assertTrue(outcome.denied)

    def test_tool_exception_is_reported(self):
        outcome = self.router(DummyTool(explode=True)).dispatch(ActionRequest("dummy"))
        self.assertFalse(outcome.ok)
        self.assertIn("boom", outcome.spoken)

    def test_schemas(self):
        schemas = self.router(DummyTool()).schemas()
        self.assertEqual(schemas[0]["name"], "dummy")


if __name__ == "__main__":
    unittest.main()
